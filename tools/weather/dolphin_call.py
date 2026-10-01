#!/usr/bin/env python3
"""Call the weather code in the live (emulated) game over GDB, then read back what it produced.

  dolphin_call.py <image.wbfs> <build dir> [warmup seconds]

The game is stopped at the per-frame pad hook (tramp_pad, a clean point in the main thread), its registers are
saved, weather_type_for_date() is called with the game's own calendar (0x80600898), and the registers are restored.
Used to exercise the full path (heap, VF, FCD, cache) without needing to press buttons.
"""
import json, os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from dolphin_test import start

NAMES = ["clear", "mild overcast", "heavy overcast", "rain", "heavy rain", "snow", "heavy snow"]
CAL = 0x80600898          # the game's current OSCalendarTime


def stop_pc(reply):
    for part in reply.split(";"):
        if part.startswith("40:"):
            return int(part[3:], 16)
    return None


def wait_stop(g, seconds):
    end = time.time() + seconds
    g.s.settimeout(2)
    while time.time() < end:
        try:
            r = g.recv()
        except Exception:
            continue
        if r[:1] in ("T", "S", "W", "X"):
            return r
    return None


def main():
    disc, build = sys.argv[1], sys.argv[2]
    warm = float(sys.argv[3]) if len(sys.argv) > 3 else 40
    proc, g, info, blob, sym = start(disc, build)
    try:
        g.cmd("?")
        g.cont()
        print("warming up %ds ..." % warm)
        time.sleep(warm)
        g.interrupt()
        # run to a clean point in the main thread: the pad hook trampoline executes every frame
        hook = sym["tramp_pad"]
        print("breakpoint at tramp_pad %#010x ->" % hook, g.cmd("Z0,%x,4" % hook))
        g.send("c")
        r = wait_stop(g, 60)
        if not r or stop_pc(r) != hook:
            print("did not stop at the pad hook:", r)
            return 2
        raw = bytearray(bytes.fromhex(g.cmd("g")))
        print("registers: %d bytes; pc=%#x r1=%#x" % (len(raw), struct.unpack(">I", raw[384:388])[0], struct.unpack(">I", raw[4:8])[0]))
        saved = bytes(raw)
        g.cmd("z0,%x,4" % hook)
        ret = sym["weather_reset"]                       # never executed by the game: our return breakpoint
        print("return breakpoint at %#010x ->" % ret, g.cmd("Z0,%x,4" % ret))
        r1 = (struct.unpack(">I", raw[4:8])[0] - 0x400) & ~0xF
        new = bytearray(raw)
        struct.pack_into(">I", new, 4, r1)               # r1
        struct.pack_into(">I", new, 12, CAL)             # r3 = &calendar
        struct.pack_into(">I", new, 384, sym["weather_type_for_date"] if "weather_type_for_date" in sym else 0)   # pc
        struct.pack_into(">I", new, 396, ret)            # lr (gdb ppc layout: pc,msr,cr,lr,ctr,xer)
        g.cmd("M%x,4:%s" % (r1, saved[4:8].hex()))       # back chain
        print("write regs ->", g.cmd("G" + bytes(new).hex()))
        g.send("c")
        r = wait_stop(g, 90)
        print("call returned, stop:", r)
        if not r or stop_pc(r) != ret:
            print("the call did not return to the breakpoint (hung or crashed)")
            return 2
        res = bytes.fromhex(g.cmd("g"))
        result = struct.unpack(">i", res[12:16])[0]
        print("\nweather_type_for_date(calendar) returned %d" % result)
        rd = lambda name, n: g.read_mem(sym[name], n)
        st = struct.unpack(">5i", rd("g_fetch_status", 20))
        print("fetch status: lock=%d FCDInit=%d ownAreaId=%#x getOwnId=%d firstForecast=%d" % st)
        base, n = struct.unpack(">ii", rd("g_cache", 8))
        types = list(g.read_mem(sym["g_cache"] + 8, 7))
        print("cache: base game day %d, %d days" % (base, n))
        for i in range(n):
            print("   day +%d (game day %d): type %d  %s" % (i, base + i, types[i], NAMES[types[i]] if types[i] < 7 else "unknown -> vanilla"))
        if "out.0" in sym:
            o = rd("out.0", 0x530)
            code = struct.unpack(">H", o[0x10:0x12])[0]
            desc = o[0x12:0x112].decode("utf-16-be", "replace").split("\x00")[0]
            print("last forecast record: code %#06x  '%s'" % (code, desc))
        if "fcd_trace" in sym and info.get("trace_names"):
            vals = struct.unpack(">%di" % len(info["trace_names"]), g.read_mem(sym["fcd_trace"], 4 * len(info["trace_names"])))
            for nm, v in zip(info["trace_names"], vals):
                print("   %-34s -> %d" % (nm, v))
        # put the game back exactly as it was and let it run on
        g.cmd("z0,%x,4" % ret)
        g.cmd("G" + saved.hex())
        g.send("c")
        time.sleep(3)
        print("game resumed")
    finally:
        proc.terminate()
        proc.wait(10)
        proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
