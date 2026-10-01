"""Find the City Folk addresses the GameCube-pad patch needs in any revision.

Everything is written once against USA Rev 0 (RUUE01v0); the other discs share
the same compiled code at other addresses.  A function is located by matching
a window of USA instructions against the target DOL with the relocatable bits
(branch displacements, address halves, small-data offsets) masked out, and it
must match exactly once.  Data addresses are then read back from the matched
code (the lis/addi that references them), never guessed.
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
from dol import Dol

def mask(w):
    op = w >> 26
    if op in (18,):                      # b / bl: keep opcode, AA, LK
        return w & 0xFC000003
    if op == 16:                         # bc: keep everything but displacement
        return w & 0xFFFF0003
    if op in (14, 15, 24, 25, 26, 27, 28, 29):   # addi/lis/ori/oris/xori/andi
        return w & 0xFFFF0000
    if 32 <= op <= 55:                   # loads/stores: drop displacement
        return w & 0xFFFF0000
    return w

def words(d, va, n):
    b = d.read(va, n * 4)
    return list(struct.unpack('>%dI' % n, b)) if b and len(b) == n * 4 else None

class Finder:
    def __init__(self, ref, tgt):
        self.ref, self.tgt = ref, tgt
        o, a, s, _ = [x for x in tgt.secs if x[3] == 1][0]
        self.tw = struct.unpack('>%dI' % (s // 4), tgt.data[o:o + s])
        self.tbase = a
        self.tm = [mask(w) for w in self.tw]

    def locate(self, ref_va, n=24):
        rw = words(self.ref, ref_va, n)
        rm = [mask(w) for w in rw]
        hits = []
        first = rm[0]
        tm = self.tm
        for i in range(len(tm) - n):
            if tm[i] != first:
                continue
            if tm[i:i + n] == rm:
                hits.append(self.tbase + i * 4)
        if len(hits) != 1:
            raise SystemExit('anchor %08X: %d matches' % (ref_va, len(hits)))
        return hits[0]

    def pair(self, ref_va, ref_target, n=64):
        """the target revision's value for the address that the lis + addi pair
        near ref_va loads (ref_target on USA Rev 0)"""
        t_va = self.locate(ref_va)
        rw = words(self.ref, ref_va, n)
        tw = words(self.tgt, t_va, n)

        def imm(w):
            v = w & 0xFFFF
            return v - 0x10000 if v & 0x8000 else v

        for i in range(n):
            w = rw[i]
            if w >> 26 != 15:
                continue
            reg = (w >> 21) & 31
            for j in range(i + 1, min(n, i + 16)):
                w2 = rw[j]
                if w2 >> 26 == 14 and (w2 >> 16) & 31 == reg:
                    val = ((w & 0xFFFF) << 16) + imm(w2)
                    if val & 0xFFFFFFFF == ref_target:
                        t, t2 = tw[i], tw[j]
                        assert t >> 26 == 15 and t2 >> 26 == 14
                        return (((t & 0xFFFF) << 16) + imm(t2)) & 0xFFFFFFFF
        raise SystemExit('no pair for %08X near %08X' % (ref_target, ref_va))

# (name, USA Rev 0 address)
FUNCS = {
    'KPADiRead':   0x803BF16C,
    'WPADProbe':   0x803B2524,
    'SIGetType':   0x8038B72C,
    'OSDisableInterrupts': 0x803807E8,
    'OSRestoreInterrupts': 0x80380810,
}
# offsets inside KPADiRead (identical code in every revision)
SAMPLE_COUNT_OFF = 0x803BF284 - 0x803BF16C       # lbz r0,0x10f(r31)

def resolve(ref, tgt):
    f = Finder(ref, tgt)
    r = {}
    for k, v in FUNCS.items():
        if k.startswith('OS'):
            r[k] = f.locate(v, 6)
        else:
            r[k] = f.locate(v, 40)
    r['SampleCount'] = r['KPADiRead'] + SAMPLE_COUNT_OFF
    r['SiTypes'] = f.pair(0x8038B72C, 0x805528A0)
    r['SiBusy'] = r['SiTypes'] - 0x18
    r['SiShadow'] = r['SiBusy'] + 4
    r['Kpad0'] = f.pair(0x803BF16C, 0x806E23C0)
    return r

if __name__ == '__main__':
    ref = Dol(sys.argv[1])
    for p in sys.argv[2:]:
        r = resolve(ref, Dol(p))
        print(os.path.basename(p), {k: '%08X' % v for k, v in r.items()})
