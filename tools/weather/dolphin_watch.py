#!/usr/bin/env python3
"""Watch the scene kind and the weather object of the running game over time (title screen behaviour).

  dolphin_watch.py <image.wbfs> <build dir> [total seconds] [interval]
Samples by interrupting briefly, so it only reads memory (never calls into the game).
"""
import os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
from dolphin_test import start, NAMES7

R13 = 0x807516C0

def attach_main(build, total, step):
    """Attach to an already running game (opened with DEBUG_STUB=1) and log scene/weather changes while you play."""
    import json
    from gdbmem import Gdb
    info = json.load(open(os.path.join(build, "weather-patch.json"))); sym = info["symbols"]
    g = None
    for _ in range(60):
        try:
            g = Gdb(timeout=30); break
        except OSError:
            time.sleep(1)
    if g is None:
        print("no debug connection on port 2159"); return
    table = struct.unpack(">68I", g.read_mem(0x80479BE0, 68 * 4))
    last = None; t0 = time.time()
    g.cont()
    print("attached; logging scene kind / weather every %ds (Ctrl-C or %ds to stop)" % (step, total), flush=True)
    while time.time() - t0 < total:
        time.sleep(step)
        g.interrupt()
        kind = g.read_mem(R13 - 0x6384, 1)[0]
        flags = table[kind] if kind < 0x44 else 0
        wp = struct.unpack(">I", g.read_mem(R13 - 0x2AD8, 4))[0]
        if 0x80000000 <= wp < 0x94000000:
            cur, nxt = struct.unpack(">II", g.read_mem(wp + 0x5884, 8))
            indoor, snow = g.read_mem(wp + 0x5894, 2)
            w = "weather type %d (%s) next %d indoor %d snowseason %d" % (cur, NAMES7[cur] if cur < 7 else "?", nxt, indoor, snow)
        else:
            w = "no weather object"
        n, = struct.unpack(">i", g.read_mem(sym["g_cache"] + 4, 4))
        types = list(g.read_mem(sym["g_cache"] + 8, 7))[:max(n, 0)]
        off = g.read_mem(sym["g_off"], 1)[0]
        line = "scene kind %#04x flags %#010x %-6s | %s | forecast types %s%s" % (kind, flags, "CITY" if flags & 0x200 else "", w, types, "  (B latch: OFF)" if off else "")
        if line != last:
            print("t=%4ds %s" % (time.time() - t0, line), flush=True)
        last = line
        g.cont()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--attach":
        attach_main(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 3600, float(sys.argv[4]) if len(sys.argv) > 4 else 3)
        return
    disc, build = sys.argv[1], sys.argv[2]
    total = float(sys.argv[3]) if len(sys.argv) > 3 else 180
    step = float(sys.argv[4]) if len(sys.argv) > 4 else 10
    proc, g, info, blob, sym = start(disc, build)
    try:
        g.cmd("?"); g.cont()
        t0 = time.time(); last = None
        while time.time() - t0 < total:
            time.sleep(step)
            g.interrupt()
            kind = g.read_mem(R13 - 0x6384, 1)[0]
            wp = struct.unpack(">I", g.read_mem(R13 - 0x2AD8, 4))[0]
            if 0x80000000 <= wp < 0x94000000:
                cur, nxt = struct.unpack(">II", g.read_mem(wp + 0x5884, 8))
                indoor, snow = g.read_mem(wp + 0x5894, 2)
                w = "weather object %#010x type %d next %d indoor %d snowseason %d" % (wp, cur, nxt, indoor, snow)
            else:
                w = "no weather object"
            n = struct.unpack(">i", g.read_mem(sym["g_cache"] + 4, 4))[0] if "g_cache" in sym else -1
            line = "t=%3ds scene kind %#04x  %s  forecast days cached: %d" % (time.time() - t0, kind, w, n)
            if line[10:] != last:
                print(line, flush=True)
            last = line[10:]
            g.cont()
    finally:
        proc.terminate(); proc.wait(10); proc.kill()

if __name__ == "__main__":
    main()
