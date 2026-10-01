#!/usr/bin/env python3
"""Apply the GameCube-controller patch to a City Folk main.dol (no Gecko handler needed).

  patch_dol.py <revision> <in main.dol> <out main.dol>

The code goes in a new DOL text section at 0x80001820 (below the OS globals at
0x80003000, clear of everything the game and the SDHC patch use, and not 0x80001800,
which a loader's code handler overwrites).  City Folk Deluxe discs already carry a code
handler section at 0x80001800, so there it goes just past that section instead.  Each hook site becomes a branch into its
body, and the last word of every body branches back to site+4 -- what a Gecko C2 does.
`patches.json` is written by gcbuild.py; it holds only this project's code and
Vague Rant's, never anything from the game.
"""
import json, os, struct, sys

BASE = 0x80001820          # first choice; moves up past any section already there
LIMIT = 0x80003000
HERE = os.path.dirname(os.path.abspath(__file__))


def branch(frm, to):
    off = to - frm
    assert off % 4 == 0 and -0x2000000 <= off < 0x2000000
    return 0x48000000 | (off & 0x03FFFFFC)


class Dol:
    def __init__(self, data):
        self.d = bytearray(data)
        self.off = list(struct.unpack('>18I', self.d[0x00:0x48]))
        self.addr = list(struct.unpack('>18I', self.d[0x48:0x90]))
        self.size = list(struct.unpack('>18I', self.d[0x90:0xD8]))

    def v2f(self, va):
        for o, a, s in zip(self.off, self.addr, self.size):
            if s and a <= va < a + s:
                return o + va - a
        return None

    def word(self, va):
        return struct.unpack('>I', self.d[self.v2f(va):][:4])[0]

    def put(self, va, word):
        self.d[self.v2f(va):self.v2f(va) + 4] = struct.pack('>I', word)

    def add_text(self, va, blob):
        slot = next((i for i in range(7) if self.size[i] == 0), None)
        if slot is None:
            raise RuntimeError('no free text section in the DOL header')
        for a, s in zip(self.addr, self.size):
            if s and a < va + len(blob) and va < a + s:
                raise RuntimeError('0x%08X overlaps an existing section' % va)
        while len(self.d) % 0x20:
            self.d.append(0)
        self.off[slot], self.addr[slot], self.size[slot] = len(self.d), va, len(blob)
        self.d += blob
        self.d[0x00:0x48] = struct.pack('>18I', *self.off)
        self.d[0x48:0x90] = struct.pack('>18I', *self.addr)
        self.d[0x90:0xD8] = struct.pack('>18I', *self.size)


def apply(data, patch):
    """patch: {'sites': [[site, [words]]], 'writes': [[va, word]], 'state': va}"""
    dol = Dol(data)
    state = patch['state']
    cave = dol.d[dol.v2f(state):dol.v2f(state) + 0x80]
    if any(cave):
        raise RuntimeError('the state area at 0x%08X is not empty; already patched, or another build' % state)
    # Bodies are position independent.  They go in a new low-memory section; if that does not fit (Deluxe
    # discs already use the start of it) the smallest ones move to the zeroed padding after the state area.
    sites = list(patch['sites'])
    cave_at, cave_end = state + 0x80, state + 0x380
    moved = []
    def low_base(size):
        base = BASE
        for _ in range(8):
            hit = [a + s for a, s in zip(dol.addr, dol.size) if s and a < base + size and base < a + s]
            if not hit:
                break
            base = (max(hit) + 0x1F) & ~0x1F
        return base

    while True:
        size = sum(len(w) for _, w in sites) * 4
        base = low_base(size)
        if base + size <= LIMIT or not sites:
            break
        small = min(sites, key=lambda x: len(x[1]))
        sites.remove(small)
        moved.append(small)
    if moved:
        if sum(len(w) for _, w in moved) * 4 > cave_end - cave_at or any(dol.d[dol.v2f(cave_at):dol.v2f(cave_end)]):
            raise RuntimeError('patch does not fit in low memory below 0x%08X' % LIMIT)
    placed, blob = [], bytearray()

    def body(at, words, site):
        if dol.word(site) >> 26 == 18 and dol.word(site) & 2 == 0:
            tgt = site + (((dol.word(site) & 0x03FFFFFC) ^ 0x02000000) - 0x02000000)
            if 0x80001800 <= tgt < LIMIT or cave_at <= tgt < cave_end:
                raise RuntimeError('hook site 0x%08X is already patched' % site)
        w = list(words)
        w[-1] = branch(at + 4 * (len(w) - 1), site + 4)
        return struct.pack('>%dI' % len(w), *w)

    for site, words in sites:
        at = base + len(blob)
        blob += body(at, words, site)
        placed.append((site, at))
    at = cave_at
    for site, words in moved:
        data = body(at, words, site)
        fo = dol.v2f(at)
        dol.d[fo:fo + len(data)] = data
        placed.append((site, at))
        at += len(data)
    if blob:
        dol.add_text(base, bytes(blob))
    for site, at in placed:
        dol.put(site, branch(site, at))
    for va, word in patch['writes']:
        dol.put(va, word)
    return bytes(dol.d)


def load(rev, name='patches.json', root=HERE):
    return json.load(open(os.path.join(root, name)))[rev]


if __name__ == '__main__':
    rev, src, dst = sys.argv[1:4]
    out = apply(open(src, 'rb').read(), load(rev, os.environ.get('PATCHES', 'patches.json')))
    open(dst, 'wb').write(out)
    print('%s: patched (%d bytes added)' % (rev, len(out) - os.path.getsize(src)))
