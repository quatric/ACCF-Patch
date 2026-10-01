#!/usr/bin/env python3
"""Run City Folk with the Gecko build in Dolphin, a scripted GameCube pad on port 1 and no Wii Remote,
and read the game's KPAD state back over the GDB stub.

  dolphin_gc.py <image> <gecko.txt> <game id> [seconds]     (env: VIDEO=Metal for a window/frame dumps)

Input goes through Dolphin's Pipe device (User/Pipes/gc): see PRESS / SET lines in `script` below.
"""
import os, shutil, struct, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools'))
from gdbmem import Gdb

DOLPHIN = '/Applications/Dolphin.app/Contents/MacOS/Dolphin'
PORT = 2159

def prepare(user, gecko, gid, wiimote=False):
    shutil.rmtree(user, ignore_errors=True)
    for d in ('Config', 'GameSettings', 'Pipes'):
        os.makedirs(os.path.join(user, d))
    os.mkfifo(os.path.join(user, 'Pipes', 'gc'))
    open(os.path.join(user, 'Config', 'Dolphin.ini'), 'w').write(
        "[General]\nGDBPort = %d\n[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
        "[Core]\nMMU = True\nCPUThread = False\nCPUCore = 4\nEnableDebugging = True\nEnableCheats = True\n"
        "WiimoteContinuousScanning = False\nWiimoteControllerInterface = False\nSIDevice0 = 6\nSIDevice1 = 0\n"
        "[Analytics]\nPermissionAsked = True\nEnabled = False\n" % PORT +
        ("[Movie]\nDumpFrames = True\nDumpFramesSilent = True\nDumpFramesAsImages = True\n" if os.environ.get('FRAMEDUMP') else ""))
    open(os.path.join(user, 'Config', 'GCPadNew.ini'), 'w').write(
        "[GCPad1]\nDevice = Pipe/0/gc\n" + "".join("Buttons/%s = `Button %s`\n" % (b, b) for b in 'ABXYZ') +
        "Buttons/Start = `Button START`\n" +
        "".join("D-Pad/%s = `Button D_%s`\n" % (d.title(), d.upper()) for d in ('up', 'down', 'left', 'right')) +
        "Triggers/L = `Button L`\nTriggers/R = `Button R`\nTriggers/L-Analog = `Axis L -+`\nTriggers/R-Analog = `Axis R -+`\n"
        "Main Stick/Up = `Axis MAIN Y +`\nMain Stick/Down = `Axis MAIN Y -`\nMain Stick/Left = `Axis MAIN X -`\nMain Stick/Right = `Axis MAIN X +`\n"
        "C-Stick/Up = `Axis C Y +`\nC-Stick/Down = `Axis C Y -`\nC-Stick/Left = `Axis C X -`\nC-Stick/Right = `Axis C X +`\n")
    open(os.path.join(user, 'Config', 'WiimoteNew.ini'), 'w').write("[Wiimote1]\nSource = %d\n" % (1 if wiimote else 0))
    if not gecko or gecko == '-':          # a disc already patched with patch_dol.py
        return
    codes = open(gecko).read().split('\n')
    name = 'GCPAD'
    open(os.path.join(user, 'GameSettings', gid + '.ini'), 'w').write(
        "[Gecko_Enabled]\n$%s\n[Gecko]\n$%s\n%s\n" % (name, name, "\n".join(codes[1:]).strip()))

def launch(user, image, video):
    cmd = [DOLPHIN, '-b', '-u', user, '-e', image, '-v', video]
    subprocess.check_call(['open', '-n', '-a', '/Applications/Dolphin.app', '--args'] + cmd[1:])
    time.sleep(2)

def pid(user):
    out = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if user in ln and 'Dolphin' in ln and 'dolphin_gc' not in ln:
            return int(ln.split()[0])

def stop(user):
    p = pid(user)
    if p:
        os.kill(p, 15)
        time.sleep(2)
        if pid(user):
            os.kill(pid(user), 9)

class Pad:
    def __init__(self, user):
        self.f = os.open(os.path.join(user, 'Pipes', 'gc'), os.O_WRONLY | os.O_NONBLOCK)
    def cmd(self, s):
        os.write(self.f, (s + '\n').encode())
    def press(self, b):   self.cmd('PRESS ' + b)
    def release(self, b): self.cmd('RELEASE ' + b)
    def stick(self, which, x, y): self.cmd('SET %s %.3f %.3f' % (which, x, y))
    def trig(self, which, v): self.cmd('SET %s %.3f' % (which, v))

KPAD0 = {'RUUE01v0': 0x806E23C0, 'RUUE01v1': 0x806E2640, 'RUUP01v0': 0x806E4EC0, 'RUUP01v1': 0x806E5140,
         'RUUJ01v1': 0x806E6940, 'RUUJ01v2': 0x806E6BC0, 'RUUK01v1': 0x806FD5C0}

def kpad(g, base):
    b = g.read_mem(base, 0x110)
    hold, trig, rel = struct.unpack('>III', b[0:12])
    dev, err, dpd = b[0x5C], b[0x5D], b[0x5E]
    ls = struct.unpack('>ff', b[0x6C:0x74]); rs = struct.unpack('>ff', b[0x74:0x7C])
    chold = struct.unpack('>I', b[0x60:0x64])[0]
    return dict(hold=hold, trig=trig, dev=dev, err=err, dpd=dpd, cl_hold=chold, ls=ls, rs=rs)

def main():
    image, gecko, gid = sys.argv[1:4]
    secs = float(sys.argv[4]) if len(sys.argv) > 4 else 60
    rev = os.environ.get('REV') or os.path.basename(gecko).split('.')[0]
    user = os.path.abspath(os.environ.get('USERDIR', 'dolphin_user'))
    prepare(user, gecko, gid, wiimote=bool(os.environ.get('WIIMOTE')))
    launch(user, image, os.environ.get('VIDEO', 'Null'))
    g = None
    for _ in range(120):
        try:
            g = Gdb(timeout=30); break
        except OSError:
            time.sleep(1)
    pad = Pad(user)
    g.cont()
    t0 = time.time()
    BASE_H, BASE_L = 0x00808080, 0x80800000
    tests = [('A', 0x01000000, 0), ('B', 0x02000000, 0), ('X', 0x04000000, 0), ('Y', 0x08000000, 0), ('Start', 0x10000000, 0),
             ('Z', 0x00100000, 0), ('L', 0x00400000, 0), ('R', 0x00200000, 0), ('Up', 0x00080000, 0), ('Down', 0x00040000, 0),
             ('Left', 0x00010000, 0), ('Right', 0x00020000, 0), ('stick right', 0x0000FF00 & 0x0000E000 | 0x00800080 & 0, 0)]
    def feed(h, l):
        g.interrupt()
        g.cmd('M%x,8:%s' % (0x80005D60, struct.pack('>II', h, l).hex()))
        g.cont()
    try:
        time.sleep(float(os.environ.get('BOOT', 15)))
        for name, hb, lb in tests:
            feed(BASE_H | hb if name != 'stick right' else (0x00800000 | 0xE080 ), BASE_L | lb)
            time.sleep(1.0)
            g.interrupt(); k = kpad(g, KPAD0[rev])
            print('%-12s hold=%08X cl_hold=%04X dev=%d ls=(%.2f,%.2f)' % (name, k['hold'], k['cl_hold'], k['dev'], *k['ls']), flush=True)
            g.cont()
            feed(BASE_H, BASE_L); time.sleep(0.6)
        feed(BASE_H, 0x80FF0000 | 0)           # C-stick up
        time.sleep(1.0); g.interrupt(); k = kpad(g, KPAD0[rev]); print('C-stick up rs=(%.2f,%.2f) dpd=%d' % (*k['rs'], k['dpd'])); g.cont()
    finally:
        stop(user)

if __name__ == '__main__':
    main()
