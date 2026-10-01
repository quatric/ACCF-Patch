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


NAMES7 = ["clear", "mild overcast", "heavy overcast", "rain", "heavy rain", "snow", "heavy snow"]


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fail.append(msg)
    return cond


def start(disc, build):
    """Prepare the isolated Dolphin user folder, launch the game and connect the GDB stub.
    Returns (proc, gdb, info, blob, sym)."""
    info = json.load(open(os.path.join(build, "weather-patch.json")))
    blob = open(os.path.join(build, "weather.bin"), "rb").read()
    sym = info["symbols"]
    user = os.path.join(build, "dolphin_user")
    shutil.rmtree(user, ignore_errors=True)
    os.makedirs(os.path.join(user, "Config"))
    ini = ("[General]\nGDBPort = %d\n[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
           "[Core]\nMMU = True\nCPUThread = False\nCPUCore = 4\nEnableDebugging = True\nWiimoteContinuousScanning = False\n"
           "WiimoteControllerInterface = False\nEnableWiiLink = %s\n[Analytics]\nPermissionAsked = True\nEnabled = False\n" % (PORT, "True" if os.environ.get("WC24") else "False"))
    if os.environ.get("FRAMEDUMP"):
        ini += "[Movie]\nDumpFrames = True\nDumpFramesSilent = True\nDumpFramesAsImages = True\n"
    if os.environ.get("USER_INI"):
        # start from the user's real settings; add the GDB stub, drop the bits that would prompt or touch hardware
        real = open(os.path.expanduser("~/Library/Application Support/Dolphin/Config/Dolphin.ini")).read()
        real = real.replace("[General]\n", "[General]\nGDBPort = %d\n" % PORT, 1).replace("[Core]\n", "[Core]\nEnableDebugging = True\n", 1)
        for k in ("WiimoteContinuousScanning", "WiimoteControllerInterface", "WiiSDCard"):
            real = "\n".join(("%s = False" % k) if ln.startswith(k + " =") else ln for ln in real.split("\n"))
        if not os.environ.get("WC24"):
            real = "\n".join("EnableWiiLink = False" if ln.startswith("EnableWiiLink =") else ln for ln in real.split("\n"))
        ini = real
    open(os.path.join(user, "Config", "Dolphin.ini"), "w").write(ini)
    if os.environ.get("IOS_LOG"):
        open(os.path.join(user, "Config", "Logger.ini"), "w").write(
            "[Logs]\nIOS_FS = True\nIOS = True\nIOS_WC24 = True\nIOS_NET = True\nIOS_SSL = True\nOSREPORT = True\nOSREPORT_HLE = True\n[Options]\nVerbosity = 5\nWriteToFile = True\nWriteToConsole = False\n")
    wii_src = os.path.expanduser("~/Library/Application Support/Dolphin/Wii")
    if os.environ.get("MIN_NAND") and os.path.isdir(wii_src):
        # only the pieces the game and the forecast need: system settings, WiiConnect24 folder, forecast title data
        for rel in ("shared2/sys", "shared2/wc24", "title/00000001/00000002/data", "title/00010002/48414645"):
            srcp = os.path.join(wii_src, rel)
            if os.path.exists(srcp):
                os.makedirs(os.path.join(user, "Wii", rel), exist_ok=True)
                subprocess.check_call(["rsync", "-a", "--exclude=.DS_Store", srcp.rstrip("/") + "/", os.path.join(user, "Wii", rel) + "/"])
        print("copied a minimal NAND subset from", wii_src)
    if os.environ.get("FULL_NAND") and os.path.isdir(wii_src):
        # mirror the user's NAND (WiiConnect24 setup, SYSCONF, saves); read-only copy, no virtual SD card
        subprocess.check_call(["rsync", "-a", "--exclude=sd.raw", "--exclude=tmp", "--exclude=.DS_Store", wii_src + "/", os.path.join(user, "Wii") + "/"])
        print("mirrored the NAND from", wii_src)
    save_src = os.environ.get("SAVE_DIR")
    if save_src:
        # a raw Wii save folder (BANNER.BIN, RVFOREST.DAT, ...): the game opens lowercase names
        dst = os.path.join(user, "Wii", "title", "00010000", "52555545", "data")
        shutil.rmtree(dst, ignore_errors=True)
        os.makedirs(dst)
        for f in os.listdir(save_src):
            shutil.copy(os.path.join(save_src, f), os.path.join(dst, f.lower()))
        print("installed save:", sorted(f.lower() for f in os.listdir(dst)))
    src_nand = os.path.expanduser("~/Library/Application Support/Dolphin/Wii/title/00010002")
    for tid in ("4841464a", "48414645", "48414650"):
        for rel in ("data/wc24dl.vff", "data/noerase/savedata.dat"):
            f = os.path.join(src_nand, tid, rel)
            if os.path.exists(f):
                dst = os.path.join(user, "Wii", "title", "00010002", tid, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy(f, dst)
                print("copied forecast data:", tid, rel, os.path.getsize(f), "bytes")
    cmd = [DOLPHIN, "-b", "-u", user, "-e", disc, "-v", os.environ.get("VIDEO", "Null")]
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
    g = None
    for _ in range(120):
        try:
            g = Gdb(timeout=30)
            break
        except OSError:
            if proc.poll() is not None:
                print("Dolphin exited early (code %s)" % proc.returncode)
                raise SystemExit(2)
            time.sleep(1)
    if g is None:
        proc.kill()
        print("could not reach the GDB stub")
        raise SystemExit(2)
    return proc, g, info, blob, sym


def main():
    disc, build = sys.argv[1], sys.argv[2]
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    proc, g, info, blob, sym = start(disc, build)
    try:
        print("stop reply:", g.cmd("?"))
        disc_id = g.read_mem(0x80000000, 6).decode("ascii", "replace")
        check(disc_id == info.get("disc_id", "RUUE02"), "disc id is %r" % disc_id)
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
        base_day = struct.unpack(">i", g.read_mem(sym["g_cache"], 4))[0]
        types = list(g.read_mem(sym["g_cache"] + 8, 7))
        raw = rd32("fcd_ctx", 0x18)
        flag = rd32("fcd_flag")
        print("  g_titleReached = %d, g_off = %d, g_lastTryDay = %d, cached days = %d" % (title, off_latch, last_try, n_days))
        print("  fcd_ctx.raw = %#010x (work buffer), fcd_flag = %d" % (raw, flag))
        if "g_fetch_status" in sym:
            st = struct.unpack(">5i", g.read_mem(sym["g_fetch_status"], 20))
            print("  fetch status: lock=%d FCDInit=%d ownAreaId=%#x getOwnId=%d firstForecast=%d  (99 = not reached)" % st)
        R = info.get("region", {})
        r13 = R.get("r13", 0x807516C0)
        kind = g.read_mem(r13 + R.get("scene_kind", -0x6384), 1)[0]
        city = g.read_mem(R.get("city_table", 0x80479F10), 0x44)
        is_city = kind == 0x3D or (kind < 0x44 and city[kind])
        print("  current scene kind %#04x -> %s" % (kind, "CITY: weather not overridden" if is_city else "not the City: forecast applies"))
        if "fcd_trace" in sym and info.get("trace_names"):
            vals = struct.unpack(">%di" % len(info["trace_names"]), g.read_mem(sym["fcd_trace"], 4 * len(info["trace_names"])))
            print("  FCDInit call results (0 = never executed):")
            for nm, v in zip(info["trace_names"], vals):
                print("    %-34s -> %d" % (nm, v))
        ctx = g.read_mem(sym["fcd_ctx"], 0x20)
        print("  FCD context words:", " ".join("%08x" % struct.unpack(">I", ctx[i:i + 4])[0] for i in range(0, 0x20, 4)))
        c_fsz, c_ssz, c_tmp = struct.unpack(">I", ctx[4:8])[0], struct.unpack(">I", ctx[0xC:0x10])[0], struct.unpack(">I", ctx[0x14:0x18])[0]
        print("  FCD context: forecast size recorded = %d (0x%x), short size recorded = %d (0x%x), chunk buffer %#010x" % (c_fsz, c_fsz, c_ssz, c_ssz, c_tmp))
        if 0x80000000 <= c_tmp < 0x94000000:
            hdr = g.read_mem(c_tmp, 16)
            sz = hdr[1] | hdr[2] << 8 | hdr[3] << 16
            print("  last file read (chunk head): %s  -> type byte %#04x, claims %d (%#x) bytes decompressed (limit for short.bin is 0x5000)" % (hdr.hex(), hdr[0], sz, sz))
        wptr = struct.unpack(">I", g.read_mem(r13 + R.get("weather_obj", -0x2AD8), 4))[0]
        if 0x80000000 <= wptr < 0x94000000:
            wcur, wnext = struct.unpack(">II", g.read_mem(wptr + 0x5884, 8))
            windoor, wsnow = g.read_mem(wptr + 0x5894, 2)
            print("  title scene weather object %#010x: current type %d (%s), next-hour type %d, indoor flag %d, snow-season flag %d" % (
                wptr, wcur, NAMES7[wcur] if wcur < 7 else "?", wnext, windoor, wsnow))
            if n_days > 0:
                check(wcur == types[0] and wnext == types[0], "the title screen's weather is the forecast (type %d) " % types[0])
            else:
                print("  (vanilla weather: no forecast cached)")
        else:
            print("  (no weather object in the title scene)")
        check(title == 1, "a weather hook ran and closed the B window (title reached)")
        check(off_latch == 0, "B latch not set (nothing was held)")
        if n_days > 0:
            names = ["clear", "mild overcast", "heavy overcast", "rain", "heavy rain", "snow", "heavy snow"]
            print("  cache base game day %d, %d days:" % (base_day, n_days))
            raw_codes = struct.unpack(">%dH" % n_days, g.read_mem(sym["g_codes"], 2 * n_days)) if "g_codes" in sym else [0] * n_days
            cond = {}
            xml = os.environ.get("WEATHER_XML")
            if xml and os.path.exists(xml):
                import xml.etree.ElementTree as ET
                for c in ET.parse(xml).getroot().iter("condition"):
                    nm = c.find("name").get("eng").replace("\n", " ")
                    for tag in ("code_2", "japanese_code_2"):
                        cond.setdefault(int((c.findtext(tag) or "0").strip(), 16), set()).add(nm)
            for i in range(n_days):
                tname = names[types[i]] if types[i] < 7 else "unknown -> vanilla"
                what = "/".join(sorted(cond.get(raw_codes[i], []))) or "?"
                print("    day +%d (game day %d): code %#06x (%s)  ->  type %d  %s" % (i, base_day + i, raw_codes[i], what, types[i], tname))
            check(base_day == last_try, "cache is anchored on today's game day")
            check(all(x < 7 or x == 0xFF for x in types[:n_days]), "every cached type is a valid City Folk weather type")
            check(n_days >= 1, "forecast read through the transplanted FCD: %d day(s) cached" % n_days)
        elif last_try != 0:
            # the game day number is days since 1970; 2009-2036 is 14000..24000
            check(10000 < last_try < 40000, "a fetch was attempted for a sane game day (%d)" % last_try)
            check(0x90000000 <= raw < 0x94000000, "FCDInit got a work buffer from the NWC24 heap in MEM2 (%#010x)" % raw)
            check(flag == 0 and n_days == 0, "fetch found no Forecast Channel data here, so vanilla weather stays (flag 0, 0 cached days)")
        if last_try != 0 and n_days > 0:
            check(0x90000000 <= raw < 0x94000000, "FCDInit got a work buffer from the NWC24 heap in MEM2 (%#010x)" % raw)
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
