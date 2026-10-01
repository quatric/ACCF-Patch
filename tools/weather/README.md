# City Folk weather from the Forecast Channel

Replaces the town's weather (and the TV's "tomorrow" forecast) with the Forecast Channel's 7-day data for the console's own location. The City keeps its own weather.
Hold **B** (Wii Remote or Classic Controller) while booting, before the title screen, to turn it off for that session.

Supports City Folk Deluxe (USA) `RUUE02` only. It ships as a patched `main.dol` or a Riivolution XML, not a Gecko code (13 KB of code, and it moves the heap start in `OSInit`).

## Build

    python3 build_patch.py --accf <RUUE02 sys/main.dol> --donor <Mario & Sonic Winter Olympics (USA) sys/main.dol> --out build/

needs devkitPPC (`DEVKITPPC`, default `/opt/devkitpro/devkitPPC`). The donor supplies the RVL_MWM-FCD machine code (`fcdgen.py` relocates it). Outputs: `main.weather.dol`,
`RUUE02-weather.xml`, `weather-patch.json`. Add `--trace` / `--selftest` only for diagnostics. `gen_weather_map.py` regenerates `weather_map.inc` from WiiLink's `weather.xml`.

## Test

    python3 test_lz.py        # LZ10/LZ11 loader and CRC-32, on the host
    python3 test_weather.py   # day math, mapping, cache, TV program, City rule, B latch, on the host
    MIN_NAND=1 WC24=1 python3 dolphin_test.py <image.wbfs> build/ 70    # boots the patched game in Dolphin (see FCD_PORT_NOTES.md)

    python3 dolphin_play.py <image.wbfs> <scratch user dir> [raw Wii save folder]   # open it in a normal Dolphin window to look at it

`../FCD_PORT_NOTES.md` has the reverse-engineering notes, addresses and the verification log.
