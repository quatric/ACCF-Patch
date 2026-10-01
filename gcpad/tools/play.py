#!/usr/bin/env python3
"""Drive City Folk in Dolphin with a scripted GC pad (the DEBUG_FEED build) and save frames.

  play.py <image> <gecko.txt> <game id> <steps> <out prefix>
steps: comma list of  <seconds>:<name>  where name is a button (A B X Y Z S L R U D LT RT) , 'N' (neutral),
or stk=<x>,<y> / cst=<x>,<y> with -1..1 ; each step is held until the next one.  Frames are dumped at every step.
"""
import glob, os, shutil, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('VIDEO', 'Metal'); os.environ['FRAMEDUMP'] = '1'
import dolphin_gc as dg
from gdbmem import Gdb

BTN = dict(A=0x01000000, B=0x02000000, X=0x04000000, Y=0x08000000, S=0x10000000, Z=0x00100000, L=0x00400000,
           R=0x00200000, U=0x00080000, D=0x00040000, LT=0x00010000, RT=0x00020000)

def state(name):
    h, l = 0x00808080, 0x80800000
    if name in BTN:
        h |= BTN[name]
    elif name.startswith('stk='):
        x, y = [float(v) for v in name[4:].split(',')]
        h = (h & ~0xFFFF) | (int(128 + 127 * x) << 8) | int(128 + 127 * y)
    elif name.startswith('cst='):
        x, y = [float(v) for v in name[4:].split(',')]
        l = (int(128 + 127 * x) << 24) | (int(128 + 127 * y) << 16)
    return h, l

def main():
    image, gecko, gid, steps, out = sys.argv[1:6]
    rev = os.path.basename(gecko).split('.')[0]
    user = os.path.abspath(os.environ.get('USERDIR', 'dolphin_user'))
    dg.prepare(user, gecko, gid, wiimote=bool(os.environ.get('WIIMOTE')))
    dg.launch(user, image, os.environ['VIDEO'])
    g = None
    for _ in range(120):
        try:
            g = Gdb(timeout=30); break
        except OSError:
            time.sleep(1)
    g.cont()
    t0 = time.time()
    plan = [(float(a), b) for a, b in (s.split(':', 1) for s in steps.split(','))]
    marks = []
    try:
        for t, name in plan:
            while time.time() - t0 < t:
                time.sleep(0.2)
            h, l = state(name)
            g.interrupt(); g.cmd('M%x,8:%s' % (0x80005D60, struct.pack('>II', h, l).hex())); g.cont()
            frames = sorted(glob.glob(os.path.join(user, 'Dump', 'Frames', '**', '*.png'), recursive=True), key=os.path.getmtime)
            marks.append((t, name, len(frames)))
        time.sleep(3)
    finally:
        frames = sorted(glob.glob(os.path.join(user, 'Dump', 'Frames', '**', '*.png'), recursive=True), key=os.path.getmtime)
        for i, (t, name, n) in enumerate(marks):
            k = min(n + 90, len(frames) - 1)
            if frames:
                shutil.copy(frames[k], '%s_%02d_%s.png' % (out, i, name.replace('=', '').replace(',', '_')))
        dg.stop(user)
        shutil.rmtree(os.path.join(user, 'Dump'), ignore_errors=True)
        print('frames', len(frames), marks)

if __name__ == '__main__':
    main()
