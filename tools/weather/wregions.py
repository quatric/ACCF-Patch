"""Find the City Folk addresses the weather patch needs, in any revision.

Reference is City Folk Deluxe USA (RUUE02), the build the patch was written
against; the other discs share its compiled code at other addresses (the same
approach as gcpad/anchors.py, whose Finder does the matching).
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'gcpad'))
import anchors
from anchors import words, mask
from dol import Dol

# name -> RUUE02 address
FUNCS = {
    'lock': 0x8040C7DC, 'unlock': 0x8040C990,
    'cal_to_ticks': 0x803859E8, 'get_time': 0x803855D4,
    'vf_is_init': 0x80434A0C, 'vf_init': 0x80434A20, 'vf_shutdown': 0x80434AE8,
    'VFMount': 0x80434CB8, 'VFUnmount': 0x80434FD0,
    'vf_open': 0x80435188, 'vf_read': 0x8043535C, 'vf_close': 0x80435264,
    'NANDOpen': 0x803A8A2C, 'NANDGetLength': 0x803A8154, 'NANDRead': 0x803A7BB8, 'NANDClose': 0x803A8CAC,
    'OSRegisterVersion': 0x8037B234, 'OSSetMEM1ArenaLo': 0x8037BE1C,
}
RT_BLOCK = 0x8044E808
RT_OFFS = [0x00, 0x28, 0x2C, 0x30, 0x4C, 0x74, 0x78, 0x7C, 0x184]     # 8044e808 .. 8044e98c
# patch sites (RUUE02): hook sites, the OSInit call, the NWC24 heap size
SITES = {'type_now': 0x801C9D24, 'type_next': 0x801C9D9C, 'tv': 0x801C9E14, 'link': 0x80086E00,
         'pad': 0x804438E0, 'arena_call': 0x8037AB10, 'nwc_heap': 0x800E94A8}
DATA = {'calendar': 0x80600898, 'city_table': 0x80479F10}
SDA = {'scene_kind': -0x6384, 'nwc_heap_ptr': -0x3284, 'weather_obj': -0x2AD8}
R13_REF = 0x807516C0


def r13_of(dol):
    w = struct.unpack('>%dI' % (0x400 // 4), dol.read(0x80004000, 0x400))
    for i in range(len(w) - 1):
        if w[i] >> 26 == 15 and (w[i] >> 21) & 31 == 13 and w[i + 1] >> 26 == 24 and (w[i + 1] >> 21) & 31 == 13:
            return ((w[i] & 0xFFFF) << 16) | (w[i + 1] & 0xFFFF)
    raise SystemExit('r13 not found')


def stack_top(dol):
    w = struct.unpack('>%dI' % (0x400 // 4), dol.read(0x80004000, 0x400))
    for i in range(len(w) - 1):
        if w[i] >> 26 == 15 and (w[i] >> 21) & 31 == 1:
            for j in range(i + 1, i + 4):
                if w[j] >> 26 in (24, 14) and (w[j] >> 21) & 31 == 1 or (w[j] >> 26 == 14 and (w[j] >> 16) & 31 == 1):
                    lo = w[j] & 0xFFFF
                    if w[j] >> 26 == 14 and lo & 0x8000:
                        lo -= 0x10000
                    return ((w[i] & 0xFFFF) << 16) + lo
    raise SystemExit('stack not found')


def _text(dol):
    o, a, s, _ = [x for x in dol.secs if x[3] == 1][0]
    return a, struct.unpack('>%dI' % (s // 4), dol.data[o:o + s])


def _imm(w):
    v = w & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def _data_candidates(ref, target):
    """indices of lis + (addi|load|store) pairs in the reference text that make `target`"""
    a, w = _text(ref)
    out = []
    for i, x in enumerate(w):
        if x >> 26 != 15:
            continue
        reg = (x >> 21) & 31
        for j in range(i + 1, min(len(w), i + 10)):
            y = w[j]
            if (y >> 26) in (14, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 48, 50, 52, 54) and (y >> 16) & 31 == reg:
                if ((((x & 0xFFFF) << 16) + _imm(y)) & 0xFFFFFFFF) == target:
                    out.append((a + 4 * i, a + 4 * j))
                break
    return out


def data_addr(ref, tgt, target, fnd):
    """the target revision's value of the data address `target` (RUUE02), via a unique code reference"""
    ra, rw = _text(ref)
    ta, tw = _text(tgt)
    for lis_va, use_va in _data_candidates(ref, target):
        for back in (6, 12, 20):
            start = lis_va - 4 * back
            n = 48
            try:
                t0 = fnd.locate(start, n)
            except SystemExit:
                continue
            ti, tj = (t0 + (lis_va - start) - ta) // 4, (t0 + (use_va - start) - ta) // 4
            x, y = tw[ti], tw[tj]
            if x >> 26 == 15 and (y >> 16) & 31 == (x >> 21) & 31:
                return (((x & 0xFFFF) << 16) + _imm(y)) & 0xFFFFFFFF
    raise SystemExit('no unique reference for data %08X' % target)


def sda_disp(ref, tgt, disp, fnd):
    """the target revision's r13 displacement for the SDA variable at `disp` (RUUE02)"""
    ra, rw = _text(ref)
    ta, tw = _text(tgt)
    for i, x in enumerate(rw):
        if (x >> 26) in (32, 34, 36, 38, 40, 42, 44, 48, 50, 52, 54) and (x >> 16) & 31 == 13 and _imm(x) == disp:
            for back in (6, 12, 20):
                start = ra + 4 * (i - back)
                try:
                    t0 = fnd.locate(start, 48)
                except SystemExit:
                    continue
                y = tw[(t0 + 4 * back - ta) // 4]
                if y >> 26 == x >> 26 and (y >> 16) & 31 == 13:
                    return _imm(y)
    raise SystemExit('no unique reference for SDA %d' % disp)


def resolve(ref, tgt):
    f = anchors.Finder(ref, tgt)
    r = {}
    for k, v in FUNCS.items():
        r[k] = f.locate(v, 40, ordered=True)
    base = f.locate(RT_BLOCK, 100, ordered=True)
    r['rt'] = [base + o for o in RT_OFFS]
    for k, v in SITES.items():
        r[k] = f.locate(v, 16, ordered=True)
    for k, v in DATA.items():
        r[k] = data_addr(ref, tgt, v, f)
    for k, v in SDA.items():
        r[k] = sda_disp(ref, tgt, v, f)
    r['r13'] = r13_of(tgt)
    r['stack_top'] = stack_top(tgt)
    r['base'] = (r['stack_top'] + 0xFFF) & ~0xFFF
    return r


if __name__ == '__main__':
    ref = Dol(sys.argv[1])
    for p in sys.argv[2:]:
        d = Dol(p)
        r = resolve(ref, d)
        print(os.path.basename(p), {k: ('%08X' % v if isinstance(v, int) and v > 0 else v) if not isinstance(v, list) else ['%08X' % x for x in v] for k, v in r.items()})
