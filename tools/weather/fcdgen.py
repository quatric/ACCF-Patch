#!/usr/bin/env python3
"""Turn the RVL_MWM-FCD machine code of a donor DOL into relocatable PowerPC assembly.

The donor is Mario & Sonic at the Olympic Winter Games (USA) `main.dol`
(FCD build Feb 26 2009 14:23:09). Everything is emitted as `.long` except:
  - b/bl/bc     -> symbolic, so instructions can be inserted and the code moved
  - lis/addi/lwz/stw pairs that address FCD's own data -> symbol@ha / symbol@l
  - r13 (SDA) accesses -> absolute symbol accesses (City Folk's SDA is not ours)
External calls are mapped to City Folk functions (see EXT). FCD_LoadLZ
(donor 0x805633d8) is not emitted; calls to it go to fcd_load_lz (fcd_loader.c).
"""
import struct, sys

START, END = 0x80562950, 0x8056481C
LOADLZ = (0x805633D8, 0x80563574)           # replaced by fcd_load_lz
RT_DELTA = 0x8060BFB0 - 0x8044E808          # MW runtime helpers: identical block in City Folk

# City Folk's VF library has a fixed, small number of drive slots and the game already owns them
# (allocating a new name fails with 0xB002), so FCD's private drive "@24" is replaced by the game's
# own drive "C", the one its NWC24 code mounts its VFF on.
DRIVE = "C"

API = {                                      # donor address -> exported symbol
    0x80562950: "FCDGetWorkMemorySize", 0x8056295C: "FCDInit", 0x80562BE4: "FCDGetForecast",
    0x80562FBC: "FCDGetCurrent", 0x805631F4: "FCDGetOwnAddressId", 0x80563224: "FCDGetPlace",
    0x80563354: "FCDGetSaveField1", 0x80563384: "FCDGetSaveField2", 0x805633B4: "FCDFinalize",
}

# external callee (donor address) -> symbol resolved by link.ld
EXT = {
    0x8056A788: "accf_OSRegisterVersion",
    0x80463B88: "accf_VFMount", 0x80463D14: "accf_VFUnmount",
    0x805A5B48: "accf_NANDOpen", 0x805A541C: "accf_NANDGetLength",
    0x805A4EF4: "accf_NANDRead", 0x805A5DC8: "accf_NANDClose",
    0x804417B0: "fcd_crc32",
    LOADLZ[0]: "fcd_load_lz",
}
for a in (0x8060BFB0, 0x8060BFD8, 0x8060BFDC, 0x8060BFE0, 0x8060BFFC, 0x8060C024,
          0x8060C028, 0x8060C02C, 0x8060C134):
    EXT[a] = "accf_rt_%08x" % (a - RT_DELTA)

# Layout of the work buffer. The donor reserves 0x5000 bytes for short.bin, but current Forecast Channel data
# declares 0x54CC bytes (0x5000 is rejected with -11), so the short.bin region grows to 0x7800. City Folk allocates
# 0x48000 for the work buffer, so the total (0x3B89C) fits. Each patch checks the donor's original word.
SHORT_REGION = 0x7800
WORK_NEED = 0x3909C + (SHORT_REGION - 0x5000)           # 0x3B89C
WORD_PATCHES = {
    0x80562954: (0x3863909C, 0x38630000 | (-(0x40000 - WORK_NEED) & 0xFFFF)),    # FCDGetWorkMemorySize: addi r3,r3,-X
    0x805629AC: (0x3803909C, 0x38030000 | (-(0x40000 - WORK_NEED) & 0xFFFF)),    # FCDInit bound: addi r0,r3,-X
    0x805629C0: (0x3866501F, 0x38660000 | (SHORT_REGION + 0x1F)),                # carve: short region + alignment
    0x80562A7C: (0x38805000, 0x38800000 | SHORT_REGION),                         # max decompressed size of short.bin
}

# donor data objects -> our symbols
OBJ = {  # name: (donor address, size)
    "fcd_ctx": (0x807D5128, 0x20),
    "fcd_vff_paths": (0x80709424, 12),
    "fcd_save_paths": (0x807094CC, 12),
}
SDA = {  # r13 displacement -> symbol
    -0x6908: "fcd_flag", -0x7310: "fcd_p_short", -0x7314: "fcd_p_forecast",
    -0x7318: "fcd_p_banner", -0x730C: "fcd_s_drive",
}

LOAD_STORE = {32: "lwz", 34: "lbz", 36: "stw", 38: "stb", 40: "lhz", 42: "lha", 44: "sth",
              48: "lfs", 50: "lfd", 52: "stfs", 54: "stfd"}
STORES = {36, 38, 44, 52, 54}


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


class Donor:
    def __init__(self, path):
        d = open(path, "rb").read()
        off = struct.unpack(">18I", d[0:72]); addr = struct.unpack(">18I", d[72:144]); size = struct.unpack(">18I", d[144:216])
        self.d, self.secs = d, [(off[i], addr[i], size[i]) for i in range(18) if size[i]]

    def read(self, va, n):
        for o, a, s in self.secs:
            if a <= va < a + s:
                return self.d[o + va - a:o + va - a + n]
        raise KeyError(hex(va))

    def cstr(self, va):
        out = b""
        while True:
            c = self.read(va + len(out), 1)
            if c == b"\0":
                return out
            out += c

    def words(self, va, n):
        return struct.unpack(">%dI" % n, self.read(va, 4 * n))

    def r13(self):
        w = self.words(0x80004000, 0x800)           # crt0 loads r13 with lis/ori
        for i in range(len(w) - 1):
            if w[i] >> 16 == 0x3DA0 and w[i + 1] >> 16 == 0x61AD:
                return ((w[i] & 0xFFFF) << 16 | (w[i + 1] & 0xFFFF)) & 0xFFFFFFFF
        raise SystemExit("donor r13 not found")


def branch_target(a, x):
    op = x >> 26
    if op == 18:
        t = x & 0x03FFFFFC; t -= 0x4000000 if t & 0x2000000 else 0
    else:
        t = s16(x & 0xFFFC)
    return (a + t) & 0xFFFFFFFF


def uses_reg(x, r):
    """True if instruction x reads or writes general register r (decoded per form)."""
    op = x >> 26
    rt, ra, rb = (x >> 21) & 31, (x >> 16) & 31, (x >> 11) & 31
    d_form = {7, 8, 10, 11, 12, 13, 14, 15, 24, 25, 26, 27, 28, 29, 32, 33, 34, 35, 36, 37, 38, 39,
              40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 21}
    if op in d_form:
        if op in (48, 49, 50, 51, 52, 53, 54, 55):      # fp load/store: rt is an FPR
            return ra == r
        return r in (rt, ra)
    if op in (20, 23):
        return r in (rt, ra, rb)
    if op == 31:
        return r in (rt, ra, rb)
    if op in (16, 18, 17):
        return False
    if op == 19:
        return False
    if op in (4, 59, 63):                               # fp/altivec arithmetic: no GPRs
        return False
    return True                                         # unknown: be conservative


def generate(donor_path, trace=False):
    D = Donor(donor_path)
    r13 = D.r13()
    w = D.words(START, (END - START) // 4)
    addr = lambda i: START + 4 * i
    in_loadlz = lambda a: LOADLZ[0] <= a < LOADLZ[1]

    # ---- branch targets
    targets = set(API)
    for i, x in enumerate(w):
        a = addr(i)
        if in_loadlz(a) or (x >> 26) not in (16, 18):
            continue
        assert not x & 2, "absolute branch"
        t = branch_target(a, x)
        if START <= t < END and not in_loadlz(t):
            targets.add(t)
        elif t not in EXT:
            raise SystemExit("unmapped external branch at %#x -> %#x" % (a, t))

    # ---- lis pairs addressing FCD data
    def obj_of(va):
        for n, (b, s) in OBJ.items():
            if b <= va < b + s:
                return n, va - b
        return None
    lis_sym = {}     # lis index -> (obj name)
    use_fix = {}     # use index -> (obj, off)
    for i, x in enumerate(w):
        if in_loadlz(addr(i)) or x >> 26 != 15 or (x >> 16) & 31 != 0:
            continue
        rt, hi = (x >> 21) & 31, x & 0xFFFF
        found = set()
        for j in range(i + 1, min(i + 400, len(w))):
            y = w[j]; op = y >> 26
            if in_loadlz(addr(j)):
                break
            if (op == 14 or op in LOAD_STORE) and (y >> 16) & 31 == rt:
                va = ((hi << 16) + s16(y & 0xFFFF)) & 0xFFFFFFFF
                o = obj_of(va)
                if o:
                    found.add(o[0]); use_fix[j] = o
            elif op == 24 and (y >> 21) & 31 == rt:
                va = (hi << 16) | (y & 0xFFFF)
                o = obj_of(va)
                if o:
                    found.add(o[0]); use_fix[j] = o
            if (op in (14, 15, 24, 32, 34, 40, 42) and (y >> 21) & 31 == rt and (y >> 16) & 31 != rt and op != 24) or \
               (op in (14, 15, 24, 32, 34, 40, 42) and (y >> 21 if op != 24 else y >> 16) & 31 == rt and op in (15, 32, 34, 40, 42)):
                pass
        if found:
            assert len(found) == 1, (hex(addr(i)), found)
            lis_sym[i] = found.pop()

    # completeness: every instruction carrying the low half of a donor data address must have been rewritten
    donor_lows = {OBJ[n][0] & 0xFFFF: n for n in OBJ}
    for i, x in enumerate(w):
        a = addr(i)
        if in_loadlz(a) or (x >> 26) not in (14, 24) and (x >> 26) not in LOAD_STORE:
            continue
        if (x >> 26) == 15:
            continue
        if (x & 0xFFFF) in donor_lows and ((x >> 16) & 31) != 13 and i not in use_fix and (x >> 26) != 14 + 0 * 1 or \
           ((x & 0xFFFF) in donor_lows and (x >> 26) == 14 and ((x >> 16) & 31) != 0 and i not in use_fix):
            raise SystemExit("unrewritten donor data reference at %#x (%08x), object %s" % (a, x, donor_lows[x & 0xFFFF]))

    r12_ok = []
    def r12_free(i):
        lo = max(0, i - 6); hi = min(len(w), i + 7)
        return not any(uses_reg(w[k], 12) for k in range(lo, hi) if k != i)

    # ---- emit
    out = []
    emit = out.append
    emit("/* generated by fcdgen.py from the donor FCD code - do not edit */")
    emit("    .text\n    .balign 4")
    n_sda = n_obj = 0
    sizes = {}                     # donor address -> number of instructions emitted for it
    trace_names = []
    sda_uses = {}                  # donor address -> SDA replacement symbol
    for i, x in enumerate(w):
        a = addr(i)
        if in_loadlz(a):
            continue
        sizes[a] = 1
        if a in API:
            emit("    .globl %s\n%s:" % (API[a], API[a]))
        if a in targets:
            emit("L_%08x:" % a)
        op = x >> 26
        rt, ra = (x >> 21) & 31, (x >> 16) & 31
        if op in (16, 18):
            t = branch_target(a, x)
            sym = "L_%08x" % t if t in targets else EXT[t]
            lk = x & 1
            if op == 18:
                emit("    %s %s   /* %08x */" % ("bl" if lk else "b", sym, a))
                if trace and lk and t in EXT and 0x8056295C <= a < 0x80562BE4:
                    k = len(trace_names)
                    trace_names.append("%s @%08x" % (sym, a))
                    sizes[a] = 3
                    emit("    lis r12,fcd_trace@ha\n    stw r3,(fcd_trace+%d)@l(r12)   /* trace: result of %s */" % (4 * k, sym))
            else:
                emit("    %s %d,%d,%s   /* %08x */" % ("bcl" if lk else "bc", rt, ra, sym, a))
        elif ra == 13 and (op == 14 or op in LOAD_STORE) and s16(x & 0xFFFF) in SDA:
            sym = SDA[s16(x & 0xFFFF)]
            n_sda += 1
            sizes[a] = 2
            sda_uses[a] = sym
            if op == 14:
                assert rt != 0
                emit("    lis r%d,%s@ha\n    addi r%d,r%d,%s@l   /* %08x was addi r%d,r13,%s */" % (rt, sym, rt, rt, sym, a, rt, sym))
            elif op in STORES:
                assert r12_free(i) and rt != 12, hex(a)
                emit("    lis r12,%s@ha\n    %s r%d,%s@l(r12)   /* %08x */" % (sym, LOAD_STORE[op], rt, sym, a))
            elif rt != 0:
                emit("    lis r%d,%s@ha\n    %s r%d,%s@l(r%d)   /* %08x */" % (rt, sym, LOAD_STORE[op], rt, sym, rt, a))
            else:
                assert r12_free(i), hex(a)
                emit("    lis r12,%s@ha\n    %s r0,%s@l(r12)   /* %08x */" % (sym, LOAD_STORE[op], sym, a))
        elif i in lis_sym:
            n_obj += 1
            emit("    lis r%d,%s@ha   /* %08x */" % (rt, lis_sym[i], a))
        elif i in use_fix:
            n_obj += 1
            o, off = use_fix[i]
            ref = "(%s+%d)@l" % (o, off)
            if op == 14:
                emit("    addi r%d,r%d,%s   /* %08x */" % (rt, ra, ref, a))
            elif op == 24:
                emit("    ori r%d,r%d,%s   /* %08x */" % (ra, rt, ref, a))
            else:
                emit("    %s r%d,%s(r%d)   /* %08x */" % (LOAD_STORE[op], rt, ref, ra, a))
        elif a in WORD_PATCHES:
            orig, new = WORD_PATCHES[a]
            assert x == orig, "donor word at %#x is %08x, expected %08x" % (a, x, orig)
            emit("    .long 0x%08x   /* %08x patched from %08x: work buffer layout */" % (new, a, x))
        else:
            emit("    .long 0x%08x   /* %08x */" % (x, a))

    emit("    .globl fcd_text_end\nfcd_text_end:")

    # ---- data
    emit("\n    .data\n    .balign 32")
    emit("    .globl fcd_ctx\nfcd_ctx:\n    .space 0x20")
    for name, (b, n) in (("fcd_vff_paths", OBJ["fcd_vff_paths"]), ("fcd_save_paths", OBJ["fcd_save_paths"])):
        ptrs = D.words(b, 3)
        emit("    .balign 4\n%s:" % name)
        for k in range(3):
            emit("    .long %s_%d" % (name, k))
        for k, p in enumerate(ptrs):
            emit("%s_%d:\n    .asciz \"%s\"" % (name, k, D.cstr(p).decode()))
    p_f = struct.unpack(">I", D.read(r13 - 0x7314, 4))[0]
    p_s = struct.unpack(">I", D.read(r13 - 0x7310, 4))[0]
    p_b = struct.unpack(">I", D.read(r13 - 0x7318, 4))[0]
    emit("    .balign 4\nfcd_flag:\n    .long 0")
    emit("fcd_p_forecast:\n    .long fcd_str_forecast\nfcd_p_short:\n    .long fcd_str_short\nfcd_p_banner:\n    .long fcd_str_banner")
    donor_drive = D.read(r13 - 0x730C, 4).split(b"\0")[0].decode()
    emit("fcd_s_drive:\n    .asciz \"%s\"" % DRIVE)
    emit("fcd_str_forecast:\n    .asciz \"%s\"\nfcd_str_short:\n    .asciz \"%s\"" % (D.cstr(p_f).decode().replace(donor_drive, DRIVE, 1), D.cstr(p_s).decode().replace(donor_drive, DRIVE, 1)))
    banner = D.cstr(p_b).decode().replace("\\", "\\\\").replace("\t", "\\t").replace('"', '\\"')
    emit("fcd_str_banner:\n    .asciz \"%s\"" % banner)
    if trace:
        emit("    .balign 4\n    .globl fcd_trace\nfcd_trace:\n    .space 64")
    emit("    .balign 4\n    .globl fcd_crc_table\nfcd_crc_table:")
    emit("    .long " + ",".join("0x%08x" % v for v in D.words(0x80657C78, 16)))
    return "\n".join(out) + "\n", dict(sda=n_sda, obj=n_obj, targets=targets, donor=D, sizes=sizes, sda_uses=sda_uses, trace_names=trace_names,
                                          use_fix={addr(j): v for j, v in use_fix.items()},
                                          lis_sym={addr(j): v for j, v in lis_sym.items()})


if __name__ == "__main__":
    src, info = generate(sys.argv[1])
    open(sys.argv[2], "w").write(src)
    print("wrote %s: %d SDA rewrites, %d data-object rewrites, %d labels" % (sys.argv[2], info["sda"], info["obj"], len(info["targets"])))
