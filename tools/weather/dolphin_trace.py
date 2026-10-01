#!/usr/bin/env python3
"""Trace the calls FCDInit makes (return values) in the running patched game.

  dolphin_trace.py <image.wbfs> <build dir> [seconds]
Sets breakpoints on the instruction after each external call inside the transplanted FCDInit,
runs the game, and prints r3 every time one is hit.
"""
import json, os, shutil, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from gdbmem import Gdb
import fcdgen

DOLPHIN = "/Applications/Dolphin.app/Contents/MacOS/Dolphin"
# donor call sites inside FCDInit -> what they call
CALLS = {
    0x80562990: "OSRegisterVersion", 0x80562A04: "VFMount(drive, path[i])", 0x80562A60: "load forecast (fcd_load_lz)",
    0x80562A80: "load short (fcd_load_lz)", 0x80562A94: "VFUnmount", 0x80562AB4: "NANDOpen(save path)",
    0x80562AD0: "NANDGetLength", 0x80562B04: "NANDRead", 0x80562B1C: "NANDClose", 0x80562B48: "parse/validate",
    0x80562B94: "crc32",
}


def main():
    image, build = sys.argv[1], sys.argv[2]
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    info = json.load(open(os.path.join(build, "weather-patch.json")))
    sym = info["symbols"]
    # donor address -> relocated address of the instruction after the call
    _, finfo = fcdgen.generate(os.environ["DONOR_DOL"])
    start = sym["FCDGetWorkMemorySize"]
    idx, j = {}, 0
    for a in sorted(finfo["sizes"]):
        idx[a] = start + 4 * j
        j += finfo["sizes"][a]
    bps = {idx[a + 4]: name for a, name in CALLS.items()}
    user = os.path.join(build, "dolphin_user")
    # reuse the isolated user folder prepared by dolphin_test.py (config + copied NAND data)
    cmd = [DOLPHIN, "-b", "-u", user, "-e", image, "-v", "Null"]
    subprocess.check_call(["open", "-n", "-a", "/Applications/Dolphin.app", "--args"] + cmd[1:])
    g = None
    for _ in range(120):
        try:
            g = Gdb(timeout=30)
            break
        except OSError:
            time.sleep(1)
    print("stub:", g.cmd("?"))
    for a in bps:
        print("breakpoint %#010x after %s ->" % (a, bps[a]), g.cmd("Z0,%x,4" % a))
    g.send("c")
    end = time.time() + secs
    hits = 0
    g.s.settimeout(2)
    while time.time() < end:
        try:
            r = g.recv()
        except Exception:
            continue
        if not r.startswith("T"):
            continue
        regs = g.cmd("g")
        raw = bytes.fromhex(regs)
        r3 = struct.unpack(">i", raw[12:16])[0]
        pc = int(r.split("40:")[1][:8], 16) if "40:" in r else 0
        print("  hit %#010x  %-28s r3 = %d (%#x)" % (pc, bps.get(pc, "?"), r3, r3 & 0xFFFFFFFF))
        hits += 1
        g.send("c")
        if hits > 60:
            break
    for p in subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout.splitlines():
        if user in p and "dolphin_trace" not in p and "Dolphin" in p:
            os.kill(int(p.split()[0]), 9)


if __name__ == "__main__":
    main()
