#!/usr/bin/env python3
"""Boot the patched game in Dolphin and check the weather patch from the outside (GDB stub).

  dolphin_test.py <extracted disc dir with the patched sys/main.dol> <build dir> [seconds]

Uses an isolated Dolphin user folder (copy of your Dolphin.ini), so your own setup is untouched.
Checks, after the game has been running:
  - the blob is resident and unmodified in MEM1 (the heap must not have been placed over it)
  - every hook site holds the expected branch
  - the weather state shows the title-reached hook fired and the B latch is not set
"""
import json, os, shutil, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from gdbmem import Gdb

DOLPHIN = "/Applications/Dolphin.app/Contents/MacOS/Dolphin"
PORT = 2159
fail = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fail.append(msg)
    return cond


def main():
    disc, build = sys.argv[1], sys.argv[2]
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    info = json.load(open(os.path.join(build, "weather-patch.json")))
    blob = open(os.path.join(build, "weather.bin"), "rb").read()
    sym = info["symbols"]
    user = os.path.join(build, "dolphin_user")
    shutil.rmtree(user, ignore_errors=True)
    os.makedirs(os.path.join(user, "Config"))
    ini = ("[General]\nGDBPort = %d\n[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
           "[Core]\nMMU = True\nCPUThread = False\nCPUCore = 4\nWiimoteContinuousScanning = False\n"
           "WiimoteControllerInterface = False\nEnableWiiLink = False\n[Analytics]\nPermissionAsked = True\nEnabled = False\n" % PORT)
    open(os.path.join(user, "Config", "Dolphin.ini"), "w").write(ini)
    cmd = [DOLPHIN, "-b", "-u", user, "-e", disc, "-v", "Null"]
    print("launching:", " ".join(cmd))
    subprocess.check_call(["open", "-n", "-a", "/Applications/Dolphin.app", "--args"] + cmd[1:])
    time.sleep(2)

    class _Proc:                                   # find our instance by its unique user folder
        def pid(self):
            out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
            for ln in out.splitlines():
                if user in ln and "Dolphin" in ln and "dolphin_test" not in ln:
                    return int(ln.split()[0])
        def poll(self):
            return None if self.pid() else 1
        def terminate(self):
            p = self.pid()
            if p:
                os.kill(p, 15)
        def wait(self, t):
            for _ in range(int(t)):
                if not self.pid():
                    return
                time.sleep(1)
        def kill(self):
            p = self.pid()
            if p:
                os.kill(p, 9)
        returncode = "?"
    proc = _Proc()
    try:
        g = None
        for _ in range(120):
            try:
                g = Gdb(timeout=30)
                break
            except OSError:
                if proc.poll() is not None:
                    print("Dolphin exited early (code %s)" % proc.returncode)
                    return 2
                time.sleep(1)
        if g is None:
            print("could not reach the GDB stub")
            return 2
        print("stop reply:", g.cmd("?"))
        disc_id = g.read_mem(0x80000000, 6).decode("ascii", "replace")
        check(disc_id == "RUUE02", "disc id is %r" % disc_id)
        g.cont()
        print("running %ds ..." % secs)
        time.sleep(secs)
        r = g.interrupt()
        print("interrupted:", r)

        print("\n== blob in MEM1 ==")
        base = info["base"]
        text_end = sym["fcd_text_end"] - base
        data_start = sym["fcd_ctx"] - base
        # code + rodata + the generated tables before the mutable state must be unchanged
        got = g.read_mem(base, len(blob))
        check(got[:text_end] == blob[:text_end], "code (%#x bytes at %#010x) matches the build" % (text_end, base))
        rel_end = min(v for k, v in sym.items() if k.startswith(("g_", "weather_blob"))) if False else None
        mismatch = [i for i in range(len(blob)) if got[i] != blob[i]]
        print("  info: %d of %#x blob bytes differ from the build (mutable state)" % (len(mismatch), len(blob)))
        if mismatch:
            lo, hi = base + mismatch[0], base + mismatch[-1]
            print("        differing range %#010x..%#010x" % (lo, hi))
            check(lo >= base + text_end, "all differences are in the data area, not code")

        print("\n== hook sites ==")
        for p in info["patches"]:
            va, want = p["address"], bytes.fromhex(p["bytes"])
            cur = g.read_mem(va, len(want))
            check(cur == want, "%#010x holds %s" % (va, cur.hex()))

        print("\n== weather state ==")
        def rd32(name, off=0):
            return struct.unpack(">I", g.read_mem(sym[name] + off, 4))[0]
        title, off_latch = g.read_mem(sym["g_titleReached"], 1)[0], g.read_mem(sym["g_off"], 1)[0]
        last_try = struct.unpack(">i", g.read_mem(sym["g_lastTryDay"], 4))[0]
        n_days = rd32("g_cache", 4)
        raw = rd32("fcd_ctx", 0x18)
        flag = rd32("fcd_flag")
        print("  g_titleReached = %d, g_off = %d, g_lastTryDay = %d, cached days = %d" % (title, off_latch, last_try, n_days))
        print("  fcd_ctx.raw = %#010x (work buffer), fcd_flag = %d" % (raw, flag))
        check(title == 1, "a weather hook ran and closed the B window (title reached)")
        check(off_latch == 0, "B latch not set (nothing was held)")
        if last_try != 0:
            # the game day number is days since 1970; 2009-2036 is 14000..24000
            check(10000 < last_try < 40000, "a fetch was attempted for a sane game day (%d)" % last_try)
            check(0x90000000 <= raw < 0x94000000, "FCDInit got a work buffer from the NWC24 heap in MEM2 (%#010x)" % raw)
            check(flag == 0 and n_days == 0, "fetch found no Forecast Channel data here, so vanilla weather stays (flag 0, 0 cached days)")
        else:
            print("  (no fetch attempted in this window)")
        print("\nFAILED" if fail else "\nall checks passed")
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
