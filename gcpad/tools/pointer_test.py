#!/usr/bin/env python3
"""Pointer mode through the GC pad: L toggles it, the C-stick moves the cursor (DEBUG_FEED build).

  pointer_test.py <image> <gecko.txt> <game id>    (env WIIMOTE=1 adds an idle emulated Wii Remote)
"""
import os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dolphin_gc as dg
from gdbmem import Gdb

def main():
    image, gecko, gid = sys.argv[1:4]
    rev = os.environ.get('REV') or os.path.basename(gecko).split('.')[0]
    base = dg.KPAD0[rev]
    user = os.path.abspath(os.environ.get('USERDIR', 'dolphin_user'))
    dg.prepare(user, gecko, gid, wiimote=bool(os.environ.get('WIIMOTE')))
    dg.launch(user, image, 'Null')
    g = None
    for _ in range(120):
        try:
            g = Gdb(timeout=30); break
        except OSError:
            time.sleep(1)
    g.cont()
    def feed(h, l):
        g.interrupt(); g.cmd('M%x,8:%s' % (0x80005D60, struct.pack('>II', h, l).hex())); g.cont()
    def look(tag):
        g.interrupt()
        b = g.read_mem(base, 0x110)
        pos = struct.unpack('>ff', b[0x20:0x28])
        print('%-22s dev=%d dpd_valid=%d pos=(%.3f,%.3f) hold=%08X rs=(%.2f,%.2f)' %
              (tag, b[0x5C], b[0x5E], pos[0], pos[1], struct.unpack('>I', b[0:4])[0], *struct.unpack('>ff', b[0x74:0x7C])), flush=True)
        g.cont()
    try:
        time.sleep(float(os.environ.get('BOOT', 18)))
        N = (0x00808080, 0x80800000)
        feed(*N); time.sleep(1); look('idle')
        feed(N[0] | 0x00400000, N[1]); time.sleep(0.5); feed(*N); time.sleep(1); look('after L (cursor on?)')
        feed(N[0], 0xFF800000); time.sleep(1.5); look('C-stick right 1.5s')
        feed(N[0], 0x80FF0000); time.sleep(1.5); look('C-stick up 1.5s')
        feed(N[0] | 0x00400000, 0xFF800000); time.sleep(0.5); feed(*N); time.sleep(1); look('after L again (cursor off?)')
    finally:
        dg.stop(user)

if __name__ == '__main__':
    main()
