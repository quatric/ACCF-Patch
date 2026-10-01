# ACCF-SDHC

SDHC (>2 GB) SD card support for *Animal Crossing: City Folk* on Wii.

Ported from **SDHC Extension 1.1 [Bero]** by way of *My Pokémon Ranch*.

## Quick start

The patcher has three independent checkboxes: **SDHC card support** (on by default), **GameCube controller** (port 1) and **Forecast Channel weather**
(the last needs a one-time local build, see below). Tick what you want, drop the disc.

1. **Download** `ACCF-Patcher` for your platform from
   [Releases](https://github.com/quatric/ACCF-SDHC/releases).
2. **Drop your `.wbfs`/`.iso` on the window.** It reads the disc's own ID and
   revision, applies the matching patch, and rebuilds the image in place. The
   original is kept as `<name>.bak`.
3. **Play.**

That's the whole thing. The patcher will refuse a disc it doesn't recognize
rather than guess, so it cannot apply the wrong revision's addresses.

If you'd rather install by hand — Gecko code, Riivolution XML, or a prebuilt
`main.dol` — **check your disc first**:

```sh
python3 tools/identify.py "Animal Crossing - City Folk (USA).wbfs"
```

It prints the disc ID, the revision, the exact `gecko/` and `riivolution/`
filenames that belong to it, and whether the disc is still unpatched. This
matters: nothing in the Gecko or Riivolution formats stops you applying Rev 1
addresses to a Rev 0 disc, and doing so silently breaks SDHC detection (the
card comes up as an unknown device) or crashes the title. See
[Revision matters](#️-revision-matters--check-yours-first).

## GameCube controller (optional)

Play with a GameCube controller in **port 1** — no Wii Remote needed. The pad
reaches the game as a Classic Controller, so it runs on Vague Rant's Classic
Controller support, with the pointer on the C-stick. Tick *GameCube controller* in the patcher, or use the per-revision Gecko codes in
[`gcpad/gecko/`](gcpad/). Controls, how it works and what has (and hasn't)
been tested are in [`gcpad/README.md`](gcpad/README.md).

## Forecast Channel weather (optional)

Replaces the town's weather with the Forecast Channel's 7-day data for the console's own location (the City keeps its own). Works on every revision;
see [`tools/weather/README.md`](tools/weather/README.md). The patch data ships with the patcher (`tools/weather/weather_patches.json`);
rebuilding it needs a Mario & Sonic Winter Olympics disc.

## What it does

City Folk's bundled PFD SD driver only understands standard-capacity cards: it
assumes byte addressing and reads capacity from a CSD v1 record. SDHC cards use
block addressing and a CSD v2 record, so the stock game either misreads the card
size or writes to the wrong offsets.

The patch adds three things:

- reads the OCR **CCS** bit at mount time and latches an "is SDHC" flag
- parses **CSD v2** capacity (`(C_SIZE + 1) × 1024` sectors of 512 bytes)
- switches the read/write paths to **block addressing** when that flag is set

It touches only the SD driver.

## Supported discs

| File       | Disc ID  | Rev | Version                                       | Rebase   |
|------------|----------|-----|-----------------------------------------------|----------|
| `RUUE01v0` | `RUUE01` | 0   | City Folk (USA)                               | −292     |
| `RUUE01v1` | `RUUE01` | 1   | City Folk (USA/Asia)                          | —        |
| `RUUJ01v1` | `RUUJ01` | 1   | Machi e Ikou yo: Doubutsu no Mori (Japan)     | +124     |
| `RUUJ01v2` | `RUUJ01` | 2   | Machi e Ikou yo: Doubutsu no Mori (Japan)     | +416     |
| `RUUP01v0` | `RUUP01` | 0   | Let's Go to the City (Europe)                 | −724     |
| `RUUP01v1` | `RUUP01` | 1   | Let's Go to the City (Europe)                 | −432     |
| `RUUE02`   | `RUUE02` | 0   | City Folk **Deluxe** (USA)                    | −292     |
| `RUUJ02`   | `RUUJ02` | 1   | City Folk **Deluxe** (Japan)                  | +124     |
| `RUUP02`   | `RUUP02` | 0   | City Folk **Deluxe** (PAL)                    | −724     |

Every retail region and revision is covered. Each Deluxe build turns out to share
its region's vanilla base exactly — `RUUE02` = USA Rev 0 (−292), `RUUJ02` = JP
Rev 1 (+124), `RUUP02` = Europe Rev 0 (−724).

Rebase is relative to the `RUUE01` Rev 1 site map. Helper and trampoline
addresses are absolute and do **not** move between builds; only the ten patch
sites shift, along with the two `bctr` return addresses embedded in the hook2 and
hook4 payloads.

### ⚠️ Revision matters — check yours first

`RUUE01`, `RUUJ01` and `RUUP01` each cover **two revisions** under one disc ID,
and each revision needs a *different* set of addresses. Applying the wrong
revision's patch overwrites unrelated live code — all four hook sites land on
different instructions — and **will crash**.

Every file here is named for the **revision**, not the disc ID — `RUUE01v0.txt`,
not `RUUE01.txt`. Never rename them to a bare disc ID or merge two revisions
into one file; the suffix is the only thing distinguishing two incompatible
address sets.

The Riivolution XMLs match on the disc version byte as well as the game ID
(`<id game="RUUE01" version="0" />`), so they cannot misapply. **Gecko codes
cannot do this** — cheat managers match on the 6-character ID only and have no
way to test the revision, so picking the right file is on you. Each Gecko file
states its revision in the header.

To find out which one you have, run:

```sh
python3 tools/identify.py <your disc image or main.dol>
```

Or read the disc version byte yourself at offset 7 of the disc header (offset
`0x207` in a `.wbfs`, `0x7` in a `.iso`).

If you applied the wrong revision's patch, restore from your `.bak` (or re-dump)
and start over — the patch cannot be cleanly reversed in place, and
`identify.py` will report an already-patched disc as such rather than let you
stack a second patch on top.

### Not supported: Korea (`RUUK01`, `RUUK02`) — and it does not need to be

Both the Korean vanilla disc and Korean Deluxe ship a **newer PFD library
revision** that already supports SDHC natively.

`pfd_sddrv_get_total_sectors` (`0x80220400`) tests `CSD_STRUCTURE`
(`rlwinm. r0,r0,0,9,9` at `0x80220484`) and branches to its own CSD v2 path at
`0x80220504` computing `(C_SIZE + 1) << 10` sectors — the same result this patch
adds — and the mount code already checks the OCR CCS bit (`0x802222F0`,
`0x80222324`), which the other regions do not. Both carry
`pfd_sddrv_calc_fat32_mbr_bpb()`, absent from every non-Korean build, and both
have the CSD v2 test at the identical address, so Korean Deluxe is built directly
on Korean vanilla.

**Do not patch either Korean disc.** It would be redundant and risks
double-converting block addresses. They should already work with SDHC cards as
shipped.

Note the Korean vanilla disc also requires **IOS 48**, not IOS 38 like every
other build here.

## Contents

- `gecko/` — Gecko codes, one per disc **revision** (needs a code handler)
- `riivolution/` — Riivolution `<memory>` patches, one per disc **revision**
- `tools/` — the porting, build and verification scripts
  (`identify.py` is the one to run before installing anything by hand)

No game binaries are included, and none should ever be committed here. The tools
operate on your own dumps; see `tools/paths.py`.

To patch a single disc image you already have, without any of the dumps/
setup above, run the GUI:

```sh
python3 tools/gui.py
```

Drop a `.wbfs`/`.iso` on the window (or click to browse). It extracts the disc,
reads its own id/revision, applies the matching site map to its own `main.dol`,
and rebuilds the image **in place** — the original is kept alongside as
`<name>.bak`.

Patching in place is deliberate: USB loaders key off the
`/wbfs/<Title> [ID6]/` layout, so writing a *renamed* file next to the
original can leave the loader unable to launch the title (it drops straight
back to the Homebrew Channel). Keeping the filename and folder avoids that.

It does not touch the TMD, so the disc keeps requesting its stock IOS and no
signature is invalidated. (An earlier build of this patcher also retargeted
the TMD to IOS 58 — see [IOS requirement](#ios-requirement) for why that was
tried and why it's no longer part of the GUI's default patch.)

Running from source needs [Wiimms ISO Tool](https://wit.wiimm.de/) (`wit`) on
`PATH`, plus `tkinterdnd2` for drag-and-drop (without it the window still
works as click-to-browse). The packaged builds below bundle both.

For a quick local macOS build during development (`wit` still needs to be on
`PATH`), install [PyInstaller](https://pyinstaller.org/) and run
`tools/build_gui.sh`; this uses the checked-in `tools/ACCF-Patcher.spec`
and produces `tools/dist/ACCF-Patcher.app`.

[`.github/workflows/build-gui.yml`](.github/workflows/build-gui.yml) builds
real, distributable binaries: macOS (universal2), Linux (x86_64), and Windows
(x86_64) -- the three platforms [Wiimms ISO
Tool](https://wit.wiimm.de/download.html) publishes prebuilt binaries for, out
of the fuller set Mobipeg targets. Each bundles the matching `wit` build
(GPLv2; `wit-gpl-2.0.txt` ships alongside it) so nothing else needs to be
installed. Every run (and additionally as release assets on a `v*` tag push)
publishes `ACCF-Patcher-<target>.*` for each platform, plus two separate,
platform-independent archives: `ACCF-Patch-SDHC-Gecko-Codes.zip` (`gecko/*.txt`) and
`ACCF-Patch-SDHC-Riivolution.zip` (`riivolution/*.xml`). Both keep the per-revision
filenames. The Gecko codes need a code handler and manual address-matching per
disc revision, but don't need a source dump, `wit`, or the GUI at all -- they're
a no-tooling fallback for anyone who'd rather not run an unsigned downloaded app,
or whose platform isn't one of the three above.

The app icon (`assets/icon.png`/`.ico`/`.icns`, generated from
`assets/leaf-source.svg` by `tools/make_icon.py`) is the Animal Crossing leaf
from [Wikimedia
Commons](https://commons.wikimedia.org/wiki/File:Animal_Crossing_Leaf.svg).
Commons tags it public domain (below the threshold of originality for
copyright) but notes it may still be a protected trademark in some
jurisdictions -- worth knowing if you redistribute your own builds.

## How it works

Three helper routines and four trampolines are written into dead padding in the
exception-vector image at `0x80005C00`, and ten sites in the SD driver are
redirected into them. The cave runs `0x80005C00`–`0x80005D38`, inside padding
that ends at `0x800060C0`. The static (DOL) form needs no code handler; the Gecko
form does.

Nine of the ten sites are byte-identical to the *My Pokémon Ranch* originals, so
Bero's register assumptions carry over unchanged. The tenth (hook4) differs only
in its r13 SDA offset.

## IOS requirement

The stock TMD requests **IOS 38**, whose SDIO module does not take the SDv2
initialization path. This is why the card can report CCS/SDHC while remaining
uninitialized; the ACMD41 literal is not the missing patch point. The GUI
patcher no longer retargets the TMD automatically. If you hit this, you can
still retarget it by hand to **IOS 58** with `tools/patch_tmd_ios.py` (or pass
`--ios58` to `tools/mkwbfs.py` for a rebuilt WBFS) — note this invalidates the
TMD signature, so it needs IOS 58 installed and a loader/WAD that accepts
fakesigned discs:

```sh
python3 tools/patch_tmd_ios.py path/to/tmd.bin 58
python3 tools/patch_tmd_ios.py path/to/tmd.bin --show
```

It works in Dolphin and with a fakesigned loader. With IOS 58, Dolphin
reported the card initialized, performed SDHC block DMA, and completed a
photo save.

## Verification

`tools/verify.py` and `tools/distverify.py` check the invariants that matter:
each C2 hook still executes the instruction it overwrote, every `bl` redirect
lands exactly on a helper entry, helpers end in `blr`, trampolines return to
site+4, the cave was zero beforehand and does not overflow, and nothing outside
the intended writes changed.

`tools/identify.py` is the user-facing half of the same check: it tells you which
patch a given disc takes and whether that disc is unpatched, already patched, or
some build this port doesn't know about.

`tools/boottest.py` confirms the patch is resident in live MEM1 through Dolphin's
GDB stub (`GDBPort` in `Dolphin.ini`, launch with `-d`). The stub accepts one
client per run, so it does halt → resume → interrupt → verify in a single
connection.

## Credits

- **Bero** — original *SDHC Extension 1.1*, which this is a port of
- Wiimm — [wit / Wiimms ISO Tools](https://wit.wiimm.de/)

## Contact

General questions or comments can be sent to
[quatricsoftware@gmail.com](mailto:quatricsoftware@gmail.com). No support will be provided
for this tool.

## License

Copyright (c) 2026 quatric
