# City Folk weather from the Forecast Channel

Replaces the town's weather (and the TV's "tomorrow" forecast) with the Forecast Channel's 7-day data for the console's own location. The City keeps its own weather.
The patcher offers two boot modes: weather on by default with **B** to disable, or weather off by default with **B** to enable. Hold B on the Wii Remote or Classic Controller before the title screen; the choice lasts for the session.

Supports every revision: `RUUE01v0`/`v1`, `RUUP01v0`/`v1`, `RUUJ01v1`/`v2`, `RUUK01v1` and the Deluxe discs `RUUE02`, `RUUP02`, `RUUJ02`, `RUUK02`. It was written against `RUUE02`; `wregions.py` finds every address in the others (the same masked-instruction matching as `gcpad/anchors.py`) and the build checks each transplanted branch. It ships as a patched `main.dol` or a Riivolution XML, not a Gecko code (13 KB of code, and it moves the heap start in `OSInit`). Korea has no Forecast Channel, so there the patch falls back to vanilla weather.

## Build

    python3 build_patch.py --accf <RUUE02 sys/main.dol> --donor <Mario & Sonic Winter Olympics (USA) sys/main.dol> --out build/

needs devkitPPC (`DEVKITPPC`, default `/opt/devkitpro/devkitPPC`). The donor supplies the RVL_MWM-FCD machine code (`fcdgen.py` relocates it). Outputs: `main.weather.dol`,
`RUUE02-weather.xml`, `weather-patch.json`. Add `--enable-with-b` for the off-by-default variant. Add `--trace` / `--selftest` only for diagnostics. `gen_weather_map.py` regenerates `weather_map.inc` from WiiLink's `weather.xml`.

## All revisions, and in the patcher

    python3 build_all.py --dols <dir of <REV>.dol> --donor <Mario & Sonic main.dol> --out build/

builds every revision (`build/<REV>/main.weather.dol`, `build/riivolution/<REV>-weather.xml`) and writes `weather_patches.json`, which the patcher
(`tools/gui.py`, *Also add Forecast Channel weather*) and `apply_weather.py` use. That file contains the Mario & Sonic Forecast Channel code; it is committed and bundled into the
released patcher, so the checkbox is enabled out of the box (rerun `build_all.py` to regenerate it). It combines with the SDHC patch and the GameCube
controller patch (each takes its own DOL section; weather sits above the main thread stack, the controller code in low memory).

## Test

    python3 test_lz.py        # LZ10/LZ11 loader and CRC-32, on the host
    python3 test_weather.py   # day math, mapping, cache, TV program, City rule, B latch, on the host
    MIN_NAND=1 WC24=1 python3 dolphin_test.py <image.wbfs> build/ 70    # boots the patched game in Dolphin (see FCD_PORT_NOTES.md)

    python3 dolphin_play.py <image.wbfs> <scratch user dir> [raw Wii save folder]   # open it in a normal Dolphin window to look at it

`../FCD_PORT_NOTES.md` has the reverse-engineering notes, addresses and the verification log.
