#!/usr/bin/env python3
"""Build the Forecast Channel weather patch for City Folk Deluxe (USA, RUUE02).

  build_patch.py --accf <RUUE02 sys/main.dol> --donor <Mario & Sonic main.dol> --out <dir>

Steps: generate the relocatable FCD assembly from the donor, compile the glue,
link everything at BASE, verify that every transplanted branch still reaches the
instruction it reached in the donor, then write the patch description.
"""
import argparse, os, re, struct, subprocess, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fcdgen

GCC_DIR = os.environ.get("DEVKITPPC", "/opt/devkitpro/devkitPPC") + "/bin/"
GCC, LD, OBJCOPY, NM = (GCC_DIR + "powerpc-eabi-" + t for t in ("gcc", "ld", "objcopy", "nm"))
CFLAGS = ["-mcpu=750", "-O2", "-ffreestanding", "-fno-builtin", "-fno-common", "-msdata=none", "-I", HERE]

BASE = 0x80764000          # first address above the main thread stack (0x80763a40); see notes
LINK_OBJS = ["hooks.o", "weather.o", "fcd_fetch.o", "fcd_loader.o", "fcd_relocated.o"]


def run(cmd):
    subprocess.check_call(cmd)


def build_blob(donor, out, base=BASE):
    os.makedirs(out, exist_ok=True)
    src, info = fcdgen.generate(donor)
    asm = os.path.join(out, "fcd_relocated.S")
    open(asm, "w").write(src)
    obj = lambda n: os.path.join(out, n)
    for c in ("weather", "fcd_fetch", "fcd_loader"):
        run([GCC] + CFLAGS + ["-c", os.path.join(HERE, c + ".c"), "-o", obj(c + ".o")])
    run([GCC, "-mcpu=750", "-Wa,-mregnames", "-c", os.path.join(HERE, "hooks.S"), "-o", obj("hooks.o")])
    run([GCC, "-mcpu=750", "-Wa,-mregnames", "-c", asm, "-o", obj("fcd_relocated.o")])
    elf = obj("weather.elf")
    run([LD, "-T", os.path.join(HERE, "link.ld"), "--defsym", "BASE=0x%08X" % base, "-e", "0", "-o", elf] + [obj(o) for o in LINK_OBJS])
    binf = obj("weather.bin")
    run([OBJCOPY, "-O", "binary", elf, binf])
    syms = {}
    for line in subprocess.check_output([NM, elf]).decode().splitlines():
        p = line.split()
        if len(p) == 3:
            syms[p[2]] = int(p[0], 16)
    return open(binf, "rb").read(), syms, info


def verify_transplant(blob, base, syms, info):
    """Every branch in the relocated FCD code must reach the same target as in the donor."""
    D = info["donor"]
    start = syms["FCDGetWorkMemorySize"]
    # relocated code spans from FCDGetWorkMemorySize to the end of the FCD text (next data symbol)
    end = syms["fcd_text_end"]
    words = struct.unpack(">%dI" % ((end - start) // 4), blob[start - base:end - base])
    label = {int(k[2:], 16): v for k, v in syms.items() if re.fullmatch(r"L_[0-9a-f]{8}", k)}
    ext = {addr: syms[name] for addr, name in fcdgen.EXT.items()}
    dw = D.words(fcdgen.START, (fcdgen.END - fcdgen.START) // 4)
    sizes = info["sizes"]
    j, bad, checked = 0, [], 0
    for i, x in enumerate(dw):
        a = fcdgen.START + 4 * i
        if a not in sizes:
            continue                                  # FCD_LoadLZ, replaced
        op = x >> 26
        new_a = label.get(a)
        if new_a is not None and new_a != start + 4 * j:
            bad.append("label %#x expected at %#x got %#x" % (a, start + 4 * j, new_a))
        y = words[j]
        if op in (16, 18):
            t = fcdgen.branch_target(a, x)
            want = label[t] if t in label else ext[t]
            got = fcdgen.branch_target(start + 4 * j, y)
            checked += 1
            if got != want or (y & 1) != (x & 1) or (y >> 26) != op:
                bad.append("branch at donor %#x: target %#x want %#x" % (a, got, want))
        elif sizes[a] == 1 and y != x and (y >> 26) != (x >> 26):
            bad.append("unexpected change at donor %#x: %08x -> %08x" % (a, x, y))
        j += sizes[a]
    if j * 4 != end - start:
        bad.append("walked %d words, relocated code has %d" % (j, (end - start) // 4))
    return checked, bad


def verify_data_refs(blob, base, syms, info):
    """Every rewritten data reference must compute exactly the address of its intended object."""
    start, end = syms["FCDGetWorkMemorySize"], syms["fcd_text_end"]
    words = struct.unpack(">%dI" % ((end - start) // 4), blob[start - base:end - base])
    s16 = fcdgen.s16
    idx, j = {}, 0
    for a in sorted(info["sizes"]):
        idx[a] = j
        j += info["sizes"][a]

    def addr_of_use(k, sign_extend=True):
        """relocated word k is `op rD,imm(rA)` / addi / ori; find the feeding lis and return the address"""
        x = words[k]
        op, rt, ra = x >> 26, (x >> 21) & 31, (x >> 16) & 31
        reg = rt if op == 24 else ra
        for b in range(k - 1, max(k - 16, -1), -1):
            y = words[b]
            if (y >> 26) == 15 and ((y >> 21) & 31) == reg and ((y >> 16) & 31) == 0:
                hi = (y & 0xFFFF) << 16
                return (hi | (x & 0xFFFF)) if op == 24 else (hi + s16(x & 0xFFFF)) & 0xFFFFFFFF
        return None

    bad, n_obj, n_sda = [], 0, 0
    for a, (obj, off) in sorted(info["use_fix"].items()):
        got = addr_of_use(idx[a])
        want = syms[obj] + off
        n_obj += 1
        if got != want:
            bad.append("use at donor %#x: %s+%d want %#x got %s" % (a, obj, off, want, hex(got) if got else None))
    for a, sym in sorted(info["sda_uses"].items()):
        k = idx[a] + 1                                   # second instruction of the pair
        got = addr_of_use(k)
        n_sda += 1
        if got != syms[sym]:
            bad.append("SDA access at donor %#x: %s want %#x got %s" % (a, sym, syms[sym], hex(got) if got else None))
    for name, size in (("fcd_ctx", 0x20), ("fcd_vff_paths", 12), ("fcd_save_paths", 12)):
        lo = syms[name] & 0xFFFF
        if (lo & 0x8000) != ((lo + size - 1) & 0x8000):
            bad.append("%s straddles a @ha carry boundary" % name)
    return n_obj, n_sda, bad


# ---- patch sites in main.dol (RUUE02): (address, original word, trampoline, is_bl)
SITES = [
    (0x801C9D24, 0x9421FFF0, "tramp_type_now",  False),   # stwu r1,-0x10(r1)   dWeather type, this hour
    (0x801C9D9C, 0x9421FFF0, "tramp_type_next", False),   # stwu r1,-0x10(r1)   dWeather type, next hour
    (0x801C9E14, 0x9421FFF0, "tramp_tv",        False),   # stwu r1,-0x10(r1)   TV forecast program
    (0x80086E00, 0x808DCBE8, "tramp_link",      False),   # lwz  r4,-0x3418(r13) module link request
    (0x804438E0, 0x907F0854, "tramp_pad",       False),   # stw  r3,0x854(r31)  after KPADRead
    (0x8037AB10, None,       "tramp_arena",     True),    # bl   OSSetMEM1ArenaLo (OSInit)
]
OSSETMEM1ARENALO = 0x8037BE1C
# NWC24 heap size (0x800e94a8): 0x5C800 -> 0xA4800, room for the 0x48000-byte forecast buffer
STATIC = [(0x800E94A8, bytes.fromhex("3C600006" "3863C800"), bytes.fromhex("3C60000A" "38634800"))]
DOL_TEXT_SLOT = 3


def enc_branch(site, target, link):
    off = target - site
    assert -0x2000000 <= off < 0x2000000 and off % 4 == 0
    return struct.pack(">I", 0x48000000 | (off & 0x03FFFFFC) | (1 if link else 0))


def collect_patches(accf_dol, blob, base, syms):
    """[(address, bytes)] for main.dol memory, after verifying every site holds what we expect."""
    raw = open(accf_dol, "rb").read()
    hdr_off = struct.unpack(">18I", raw[0:72]); hdr_addr = struct.unpack(">18I", raw[72:144]); hdr_size = struct.unpack(">18I", raw[144:216])
    def read(va, n):
        for i in range(18):
            if hdr_size[i] and hdr_addr[i] <= va < hdr_addr[i] + hdr_size[i]:
                return raw[hdr_off[i] + va - hdr_addr[i]: hdr_off[i] + va - hdr_addr[i] + n]
        raise SystemExit("address %#x not in the DOL" % va)
    patches = []
    for site, orig, tramp, link in SITES:
        w = struct.unpack(">I", read(site, 4))[0]
        if link:
            want = struct.unpack(">I", enc_branch(site, OSSETMEM1ARENALO, True))[0]
            orig = want
        if w != orig:
            raise SystemExit("site %#x holds %08x, expected %08x: wrong revision?" % (site, w, orig))
        patches.append((site, enc_branch(site, syms[tramp], link)))
    for addr, old, new in STATIC:
        if read(addr, len(old)) != old:
            raise SystemExit("static patch site %#x does not hold the expected bytes" % addr)
        patches.append((addr, new))
    size = (syms["weather_blob_end"] - base)
    patches.append((base, blob.ljust(size, b"\0")))
    return patches


def write_dol(accf_dol, out_dol, patches, base):
    raw = bytearray(open(accf_dol, "rb").read())
    off = list(struct.unpack(">18I", raw[0:72])); addr = list(struct.unpack(">18I", raw[72:144])); size = list(struct.unpack(">18I", raw[144:216]))
    blob_patch = [p for p in patches if p[0] == base][0]
    def to_file(va):
        for i in range(18):
            if size[i] and addr[i] <= va < addr[i] + size[i]:
                return off[i] + va - addr[i]
        return None
    for va, data in patches:
        if va == base:
            continue
        fo = to_file(va)
        assert fo is not None
        raw[fo:fo + len(data)] = data
    slot = DOL_TEXT_SLOT
    assert size[slot] == 0, "text slot %d is in use" % slot
    while len(raw) % 32:
        raw.append(0)
    off[slot], addr[slot], size[slot] = len(raw), base, len(blob_patch[1])
    raw += blob_patch[1]
    raw[0:72] = struct.pack(">18I", *off); raw[72:144] = struct.pack(">18I", *addr); raw[144:216] = struct.pack(">18I", *size)
    open(out_dol, "wb").write(raw)


def riivolution_xml(patches):
    L = ['<!-- Animal Crossing: City Folk Deluxe (USA) -- External (Forecast Channel) weather -->',
         '<wiidisc version="1" root="/">',
         '  <id game="RUUE02" version="0" />',
         '  <options>',
         '    <section name="Animal Crossing: City Folk">',
         '      <option name="External Weather (Forecast Channel)" default="1">',
         '        <choice name="Enabled"><patch id="weather" /></choice>',
         '      </option>',
         '    </section>',
         '  </options>',
         '  <patch id="weather">']
    for va, data in patches:
        for k in range(0, len(data), 0x400):
            chunk = data[k:k + 0x400]
            L.append('    <memory offset="0x%08X" value="%s" />' % (va + k, chunk.hex().upper()))
    L += ['  </patch>', '</wiidisc>']
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accf", required=True)
    ap.add_argument("--donor", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    blob, syms, info = build_blob(a.donor, a.out)
    checked, bad = verify_transplant(blob, BASE, syms, info)
    print("blob: %#x bytes at %#010x (ends %#010x)" % (len(blob), BASE, BASE + len(blob)))
    print("transplant check: %d branches verified, %d problems" % (checked, len(bad)))
    for b in bad[:10]:
        print("  ", b)
    nobj, nsda, bad2 = verify_data_refs(blob, BASE, syms, info)
    print("data references: %d object refs, %d SDA replacement refs, %d problems" % (nobj, nsda, len(bad2)))
    for b in bad2[:10]:
        print("  ", b)
    if bad or bad2:
        return 1
    patches = collect_patches(a.accf, blob, BASE, syms)
    os.makedirs(a.out, exist_ok=True)
    write_dol(a.accf, os.path.join(a.out, "main.weather.dol"), patches, BASE)
    open(os.path.join(a.out, "RUUE02-weather.xml"), "w").write(riivolution_xml(patches))
    json.dump({"base": BASE, "blob_end": syms["weather_blob_end"],
               "patches": [{"address": va, "bytes": d.hex()} for va, d in patches if va != BASE],
               "symbols": {k: v for k, v in syms.items() if k.startswith(("tramp_", "FCD", "fcd_", "weather_", "g_", "out."))}},
              open(os.path.join(a.out, "weather-patch.json"), "w"), indent=1)
    print("patches: %d memory writes + blob; wrote main.weather.dol, RUUE02-weather.xml, weather-patch.json" % (len(patches) - 1))
    for va, d in patches:
        if va != BASE:
            print("  %#010x  %s" % (va, d.hex()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
