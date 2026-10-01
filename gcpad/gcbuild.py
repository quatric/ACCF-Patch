#!/usr/bin/env python3
"""Build the GameCube-pad Classic Controller port for every City Folk revision.

  gcbuild.py [--out DIR]        (default: gecko/)

For each revision this resolves the addresses (anchors.py), relocates Vague
Rant's Classic Controller code (vr_usa0_right.txt, USA Rev 0) to it, compiles
the three GameCube hooks (src/) against it, and writes a Gecko code file.
Needs devkitPPC and your own main.dol dumps (see DOLS below / paths.py).
"""
import json, os, struct, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
sys.path.insert(0, HERE)
from dol import Dol
import anchors

DEVKIT = os.environ.get('DEVKITPPC', '/opt/devkitpro/devkitPPC')
CC = DEVKIT + '/bin/powerpc-eabi-'
STATE = 0x80005D40          # zeroed padding in every revision's text (see README)

REVS = ['RUUE01v0', 'RUUE01v1', 'RUUP01v0', 'RUUP01v1', 'RUUJ01v1', 'RUUJ01v2', 'RUUK01v1',
        'RUUE02', 'RUUP02', 'RUUJ02', 'RUUK02']

# USA Rev 0 sites of Vague Rant's code, as (name, address, words to match)
VR_SITES = [0x800FA624, 0x800FA68C, 0x802CE160, 0x80443CE4, 0x80443D00,
            0x803BE750, 0x803BF784]
VR_FUNC = 0x803AD338            # helper its pointer code calls (lis/ori pair)

def dol_paths():
    base = os.environ.get('ACCF_DOLS', 'dols')       # dir of <REV>.dol
    return {r: os.path.join(base, r + '.dol') for r in REVS}

def parse_vr(path):
    L = [l.split() for l in open(path) if l.strip() and not l.startswith('#')]
    ops, i = [], 0
    while i < len(L):
        h = L[i]
        if h[0].startswith('C2'):
            n = int(h[1], 16)
            words = []
            for l in L[i + 1:i + 1 + n]:
                words += [int(x, 16) for x in l]
            ops.append(('c2', 0x80000000 | (int(h[0], 16) & 0x01FFFFFF), words))
            i += 1 + n
        elif h[0].startswith('04'):
            ops.append(('w32', 0x80000000 | (int(h[0], 16) & 0x01FFFFFF), int(h[1], 16)))
            i += 1
        else:
            raise SystemExit('unknown VR line %r' % h)
    return ops

def relocate_vr(ops, fnd):
    """Move the USA Rev 0 code to another revision: every site address, and the
    helper address in the lis/ori pair inside the pointer code."""
    site = {a: fnd.locate(a, 16) for a in VR_SITES}
    func = fnd.locate(VR_FUNC, 80)
    out = []
    for kind, addr, data in ops:
        na = site[addr]
        if kind == 'w32':
            w = data
            if w >> 26 == 18:                      # relative branch: re-aim it
                # the original branch skips over the instruction following it
                w = data
            out.append((kind, na, w))
            continue
        words = list(data)
        for j in range(len(words) - 1):
            if words[j] >> 16 == 0x3CC0 and words[j + 1] >> 16 == 0x60C6:
                assert ((words[j] & 0xFFFF) << 16 | (words[j + 1] & 0xFFFF)) == VR_FUNC
                words[j] = 0x3CC00000 | (func >> 16)
                words[j + 1] = 0x60C60000 | (func & 0xFFFF)
        out.append((kind, na, words))
    return out

def compile_hook(name, defs):
    src = os.path.join(HERE, 'src')
    tmp = tempfile.mkdtemp(prefix='gcpad')
    D = ['-D%s=%s' % kv for kv in defs.items()] + ['-DHOOK_' + name]
    if os.environ.get('DEBUG_FEED'):
        D.append('-DDEBUG_FEED')
    cflags = ['-O2', '-fno-unroll-loops', '-mbig-endian', '-msoft-float', '-msdata=none', '-ffreestanding', '-fno-pic',
              '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-nostdlib', '-Wall']
    subprocess.check_call([CC + 'gcc'] + cflags + D + ['-c', src + '/gcpad.c', '-o', tmp + '/g.o'])
    subprocess.check_call([CC + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp'] + D +
                          [src + '/hooks.S', '-o', tmp + '/h.o'])
    subprocess.check_call([CC + 'ld', '-T', src + '/link.ld', '-o', tmp + '/b.elf', tmp + '/h.o', tmp + '/g.o'])
    subprocess.check_call([CC + 'objcopy', '-O', 'binary', tmp + '/b.elf', tmp + '/b.bin'])
    b = open(tmp + '/b.bin', 'rb').read()
    return list(struct.unpack('>%dI' % (len(b) // 4), b))

def build_rev(rev, ref, dol):
    f = anchors.Finder(ref, dol)
    a = anchors.resolve(ref, dol)
    wpad_tbl = f.pair(0x803B2524, 0x806DEC10)
    defs = {
        'STATE': '0x%08Xu' % STATE,
        'SI_TYPES': '0x%08Xu' % a['SiTypes'],
        'SI_BUSY': '0x%08Xu' % a['SiBusy'],
        'SI_SHADOW': '0x%08Xu' % a['SiShadow'],
        'FN_SIGETTYPE': '0x%08Xu' % a['SIGetType'],
        'FN_OSDISABLE': '0x%08Xu' % a['OSDisableInterrupts'],
        'FN_OSRESTORE': '0x%08Xu' % a['OSRestoreInterrupts'],
        'WPAD_TBL': '0x%08Xu' % wpad_tbl,
    }
    hooks = [('POLL', a['KPADiRead']), ('SAMPLE', a['SampleCount']), ('PROBE', a['WPADProbe'])]
    ops = relocate_vr(parse_vr(os.path.join(HERE, 'vr_usa0_right.txt')), f)
    gc = []
    for name, site in hooks:
        w = compile_hook(name, defs)
        # last word is the slot the hook installer turns into the branch back
        assert w[-1] == 0x60000000
        w[-1] = 0
        if len(w) % 2:
            w.insert(len(w) - 1, 0x60000000)
        gc.append(('c2', site, w))
    return ops, gc, a

def gecko_text(rev, ops, gc):
    lines = ['Classic Controller + GameCube Controller (port 1) [%s]' % rev]
    for kind, addr, data in ops + gc:
        a = addr & 0x01FFFFFF
        if kind == 'w32':
            lines.append('04%06X %08X' % (a, data))
        else:
            lines.append('C2%06X %08X' % (a, len(data) // 2))
            for i in range(0, len(data), 2):
                lines.append('%08X %08X' % (data[i], data[i + 1]))
    return '\n'.join(lines) + '\n'

def main():
    out = os.path.join(HERE, 'gecko')
    if '--out' in sys.argv:
        out = sys.argv[sys.argv.index('--out') + 1]
    os.makedirs(out, exist_ok=True)
    paths = dol_paths()
    ref = Dol(paths['RUUE01v0'])
    patches = {}
    for rev in REVS:
        dol = Dol(paths[rev])
        ops, gc, a = build_rev(rev, ref, dol)
        open(os.path.join(out, rev + '.txt'), 'w').write(gecko_text(rev, ops, gc))
        patches[rev] = {
            'state': STATE,
            'sites': [[addr, data] for kind, addr, data in ops + gc if kind == 'c2'],
            'writes': [[addr, data] for kind, addr, data in ops + gc if kind == 'w32'],
        }
        print(rev, {k: '%08X' % v for k, v in a.items() if k in ('KPADiRead', 'WPADProbe', 'SampleCount')},
              [len(w) * 4 for _, _, w in gc])
    json.dump(patches, open(os.path.join(HERE, 'patches_feed.json' if os.environ.get('DEBUG_FEED') else 'patches.json'), 'w'))

if __name__ == '__main__':
    main()
