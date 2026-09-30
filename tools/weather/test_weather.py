#!/usr/bin/env python3
"""Host tests for weather.c: day math, code mapping, 7-day cache, TV program and the B-button latch."""
import ctypes, os, subprocess, sys, tempfile, datetime

HERE = os.path.dirname(os.path.abspath(__file__))

class Cal(ctypes.Structure):
    _fields_ = [(n, ctypes.c_int) for n in ("sec", "min", "hour", "mday", "mon", "year", "wday", "yday", "msec", "usec")]

SHIM = r'''
#include "weather.h"
int g_calls; int g_ret; int g_lastBack; unsigned short g_codes[8];
s32 weather_platform_fetch(const CalTime *d, s32 back, u16 *codes, s32 max) {
    int i; (void)d; g_calls++; g_lastBack = back;
    if (g_ret <= 0) return g_ret;
    for (i = 0; i < g_ret && i < max; i++) codes[i] = g_codes[i];
    return g_ret;
}
'''

def cal(y, m, d, h=12):
    return Cal(0, 0, h, d, m - 1, y, 0, 0, 0, 0)

def main():
    t = tempfile.mkdtemp()
    try:
        open(f"{t}/shim.c", "w").write(SHIM)
        so = f"{t}/w.so"
        subprocess.check_call(["cc", "-O1", "-shared", "-fPIC", "-I", HERE, f"{t}/shim.c", f"{HERE}/weather.c", "-o", so])
        L = ctypes.CDLL(so)
        L.weather_game_day.argtypes = [ctypes.POINTER(Cal)]
        L.weather_type_for_date.argtypes = [ctypes.POINTER(Cal)]
        L.weather_tv_for_date.argtypes = [ctypes.POINTER(Cal)]
        L.weather_map_code.argtypes = [ctypes.c_uint16]; L.weather_map_code.restype = ctypes.c_ubyte
        L.weather_tv_program.argtypes = [ctypes.c_ubyte]; L.weather_tv_program.restype = ctypes.c_ubyte
        L.weather_sample_buttons.argtypes = [ctypes.c_uint, ctypes.c_ubyte, ctypes.c_uint]
        bad = 0
        def check(name, got, want):
            nonlocal bad
            ok = got == want
            bad += not ok
            print(f"{'OK  ' if ok else 'FAIL'} {name}: got {got!r}" + ("" if ok else f" want {want!r}"))
        gd = lambda *a: L.weather_game_day(ctypes.byref(cal(*a)))

        # day math vs Python, incl. year/leap boundaries and the 6 AM rollover
        ep = datetime.date(1970, 1, 1)
        allok = True
        for (y, m, d) in [(2009, 1, 1), (2009, 12, 31), (2012, 2, 29), (2012, 3, 1), (2100, 3, 1), (2000, 2, 29), (2036, 6, 15)]:
            allok &= gd(y, m, d, 12) == (datetime.date(y, m, d) - ep).days
        check("game day == days since epoch (noon)", allok, True)
        check("05:59 belongs to the previous day", gd(2009, 3, 10, 5), gd(2009, 3, 9, 12))
        check("06:00 starts the new day", gd(2009, 3, 10, 6), gd(2009, 3, 10, 12))
        check("year rollover at 6 AM", gd(2010, 1, 1, 5), gd(2009, 12, 31, 12))

        # mapping
        for code, want in [(0x0065, 0), (0x006A, 2), (0x006F, 3), (0x007D, 4), (0x0074, 6), (0x8065, 0), (0x806A, 1),
                           (0x0001, 0), (0x000A, 2), (0x000C, 5), (0x801A, 5), (0x0021, 4), (0x1234, 0xFF), (0xFFFF, 0xFF)]:
            check(f"map {code:#06x}", L.weather_map_code(code), want)
        for ty, want in [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2), (5, 8), (6, 8), (9, 0xFF)]:
            check(f"tv program for type {ty}", L.weather_tv_program(ty), want)

        # cache: fetch once, serve 7 days, refetch after the window, one try per day on failure
        def setup(codes, ret=None):
            L.weather_reset()
            ctypes.c_int.in_dll(L, "g_calls").value = 0
            ctypes.c_int.in_dll(L, "g_ret").value = len(codes) if ret is None else ret
            arr = (ctypes.c_uint16 * 8).in_dll(L, "g_codes")
            for i, c in enumerate(codes): arr[i] = c
        calls = lambda: ctypes.c_int.in_dll(L, "g_calls").value
        back = lambda: ctypes.c_int.in_dll(L, "g_lastBack").value
        week = [0x0065, 0x006F, 0x007D, 0x0074, 0x006A, 0x006B, 0x0071]   # clear, rain, heavy rain, heavy snow, heavy ovc, mild ovc, rain
        setup(week)
        d0 = cal(2009, 4, 10, 12)
        check("day 0 type", L.weather_type_for_date(ctypes.byref(d0)), 0)
        check("fetched once, back=0", (calls(), back()), (1, 0))
        check("same call again uses cache", (L.weather_type_for_date(ctypes.byref(d0)), calls()), (0, 1))
        got = [L.weather_type_for_date(ctypes.byref(cal(2009, 4, 10 + i, 12))) for i in range(7)]
        check("7 days of types", got, [0, 3, 4, 6, 2, 1, 3])
        check("no extra fetch inside the window", calls(), 1)
        check("05:00 on day 2 still day 1's weather", L.weather_type_for_date(ctypes.byref(cal(2009, 4, 11, 5))), 0)
        check("06:00 on day 2 advances", L.weather_type_for_date(ctypes.byref(cal(2009, 4, 11, 6))), 3)
        # TV shows tomorrow: date passed is already today+1
        check("tv (today=day0) shows tomorrow's rain", L.weather_tv_for_date(ctypes.byref(cal(2009, 4, 11, 12))), 2)
        check("tv for heavy snow tomorrow", L.weather_tv_for_date(ctypes.byref(cal(2009, 4, 13, 12))), 8)
        check("still one fetch", calls(), 1)
        # past the window -> refetch once for the new day, else vanilla
        ctypes.c_int.in_dll(L, "g_ret").value = 0
        check("day 8 has no data -> -1", L.weather_type_for_date(ctypes.byref(cal(2009, 4, 18, 12))), -1)
        check("one failed fetch", calls(), 2)
        L.weather_type_for_date(ctypes.byref(cal(2009, 4, 18, 13)))
        check("failed fetch not repeated the same day", calls(), 2)
        L.weather_type_for_date(ctypes.byref(cal(2009, 4, 19, 12)))
        check("retried next day", calls(), 3)
        # TV anchors the fetch one day back
        setup(week)
        L.weather_tv_for_date(ctypes.byref(cal(2009, 4, 11, 12)))
        check("tv fetch anchored back=1", back(), 1)
        # unknown code on one day only falls back for that day
        setup([0x0065, 0x1234, 0x006F])
        L.weather_type_for_date(ctypes.byref(cal(2009, 4, 10, 12)))     # anchors the cache on day 0
        check("unknown code -> -1", L.weather_type_for_date(ctypes.byref(cal(2009, 4, 11, 12))), -1)
        check("known neighbour still served", L.weather_type_for_date(ctypes.byref(cal(2009, 4, 12, 12))), 3)
        # partial data
        setup([0x0065, 0x006F, 0x007D])
        L.weather_type_for_date(ctypes.byref(cal(2009, 4, 10, 12)))     # anchors the cache on day 0
        ctypes.c_int.in_dll(L, "g_ret").value = 0                        # later fetches find no data
        check("day beyond partial data -> -1", L.weather_type_for_date(ctypes.byref(cal(2009, 4, 13, 12))), -1)

        # B button latch
        B_CORE, B_CL = 0x0400, 0x0040
        for name, args, want in [
            ("no buttons", (0, 0, 0), 0),
            ("core B", (B_CORE, 0, 0), 1),
            ("core A only", (0x0800, 0, 0), 0),
            ("classic B", (0, 2, B_CL), 1),
            ("classic X must not match", (0, 2, 0x0008), 0),
            ("classic bits ignored when not classic", (0, 1, B_CL), 0),
        ]:
            setup(week)
            L.weather_sample_buttons(*args)
            check(f"latch: {name}", ctypes.c_int(L.weather_is_disabled()).value, want)
        setup(week)
        L.weather_sample_buttons(B_CORE, 0, 0)
        check("disabled -> type hook falls through, no fetch", (L.weather_type_for_date(ctypes.byref(d0)), calls()), (-1, 0))
        check("disabled -> tv hook falls through", L.weather_tv_for_date(ctypes.byref(d0)), -1)
        setup(week)
        L.weather_title_reached()
        L.weather_sample_buttons(B_CORE, 2, B_CL)
        check("B after the title screen is ignored", ctypes.c_int(L.weather_is_disabled()).value, 0)
        check("...and weather stays on", L.weather_type_for_date(ctypes.byref(d0)), 0)
        print("FAILED" if bad else "all passed")
        return 1 if bad else 0
    finally:
        subprocess.call(["rm", "-rf", t])

if __name__ == "__main__":
    sys.exit(main())
