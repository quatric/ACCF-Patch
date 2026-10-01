# GameCube controller for City Folk

Plug a GameCube controller into **port 1** and play *Animal Crossing: City
Folk* with it — no Wii Remote needed. The pad shows up to the game as a
Classic Controller, so it runs on Vague Rant and crediar's Classic Controller support (the same code,
relocated to every revision), with the pointer on the C-stick.

The SI polling and hot-plug handling follow
[Barrel Blast Patch](https://github.com/quatric/Barrel-Blast-Patch), which
ran the same trick on a console.

## Installing

Three ways, same code:

- **The patcher** — tick *Also add GameCube controller support (port 1)* before
  dropping a disc on the window (`tools/gui.py`). It is added to `main.dol`
  together with the SDHC patch.
- **A single `main.dol`** — `python3 gcpad/patch_dol.py <revision> main.dol out.dol`.
  The code goes in a new DOL section in low memory (`0x80001820`, or just past
  the code handler that City Folk Deluxe discs already carry at `0x80001800`).
- **Gecko codes** — `gecko/` holds one per disc **revision**, named like the
  SDHC ones (`RUUE01v0.txt`, `RUUE02.txt`, …). Use `python3 tools/identify.py
  <disc>` to pick the right one — the same warning as the SDHC patch applies:
  addresses are per revision, and a Gecko code can't check which revision it
  is running on. (Korea, `RUUK01`/`RUUK02`, is included here although the SDHC
  patch skips it — the controller code is not related to the SD driver.)

Don't combine the Gecko codes with the DOL patch: they are the same hooks.

## Controls

The layout follows the Classic Controller diagram: A confirms, B cancels and
runs, the C-stick moves the cursor, L toggles it.

| GameCube | Action |
| --- | --- |
| Control stick | Walk |
| C-stick | Move cursor |
| L | Toggle cursor (pointer mode) |
| A | Confirm / action |
| B | Cancel / run / pick up items |
| R | Run (same as B) |
| X | Map / next tab |
| Y | Inventory / last tab |
| Z | Take photo |
| Start | Open/close photos |
| D-pad | Up: change view · Left/Right: change tool · Down: put tool away |

There is no HOME button on a GameCube pad, so the HOME Menu still needs a Wii
Remote. A Wii Remote that *is* connected keeps working alongside the pad; a
real Classic Controller or Nunchuk on it is never overridden.

## How it works

City Folk links the SI library but not PAD, so nothing ever polls a pad, and a
Wii game with no Wii Remote has no KPAD sample for the Classic Controller code
to read. Three hooks fix that (`src/gcpad.c`, one small blob each):

| Hook | Site | What it does |
| --- | --- | --- |
| poll | `KPADiRead` entry | Drives the Serial Interface's own auto-polling for port 1, re-probes a replugged pad, acknowledges latched errors, and frees si:: if an unplugged pad leaves its busy flag stuck |
| sample | `KPADiRead`, before the queued-sample check | Writes the pad into KPAD's sample ring as a Classic Controller sample (extension 2, format 8: buttons, both sticks, both triggers). With a Wii Remote connected, its own samples get the pad as their extension instead |
| probe | `WPADProbe` entry | Reports a Classic Controller on channel 0 while a pad is plugged in, so the game believes a controller is connected |

Everything is expressed as a Classic Controller sample, so the rest — button
remapping, pointer mode, the game's own extension checks — is Vague Rant's code
untouched (`vr_usa0_right.txt`, relocated per revision).

The GameCube side was not guessed: the Serial Interface lives at `0xCD006400`
on a Wii (not `0xCC…`), the result registers are hardware-written (software
can't fake them), and polling has to be re-asserted because si:: rewrites
`SIPOLL` from its own shadow every retrace. Barrel Blast's notes cover each of
these; `src/gcpad.c` carries the reasoning inline.

State lives at `0x80005D40`, in zeroed padding that every revision has and the
SDHC patch doesn't use (`STATE` in `gcbuild.py`).

## Building

Needs devkitPPC and your own `main.dol` dumps, one per revision, in a folder
named by `ACCF_DOLS` as `<REV>.dol` (`RUUE01v0.dol`, …, `RUUE02.dol`, …).

```sh
ACCF_DOLS=dumps python3 gcpad/gcbuild.py            # writes gcpad/gecko/*.txt
```

Addresses are found, not hard-coded: `anchors.py` locates each function by
matching USA Rev 0's instructions against the target DOL with the relocatable
bits masked, requires exactly one match, and reads data addresses back from
the matched code. The Vague Rant sites relocate the same way and reproduce, for
every revision Vague Rant published, the addresses in the original post.

## Testing

`tools/dolphin_gc.py` boots a revision in Dolphin with no Wii Remote and reads
KPAD back over the GDB stub; `tools/play.py` scripts a pad and saves frames.
Both need a build with `DEBUG_FEED=1` (the pad's response is written to
`STATE+0x20` by the debugger — Dolphin's Pipe input device did not deliver
input here). Without it the real SI path runs: Dolphin reports the pad as a
valid, centred controller.

What was checked in Dolphin:

- USA Rev 0, no Wii Remote: the title screen and Rover's introduction advance
  on the pad alone; every button, the D-pad and both sticks reach the game as
  the Wii Remote buttons in the table above; L turns pointer mode on and off
  and the C-stick moves the cursor.
- Every revision (`RUUE01v0`/`v1`, `RUUP01v0`/`v1`, `RUUJ01v1`/`v2`,
  `RUUK01v1`) as a Gecko code, with the same button results. Vague Rant never
  published Japan Rev 2; its relocated sites work.
- `RUUE01v0` and `RUUE02` (Deluxe) as a patched `main.dol`, and with a Wii
  Remote connected as well. `RUUE01v0` through the patcher together with the
  SDHC patch.
- The real SI path (no debugger feed): the pad is detected as a Classic
  Controller and idles correctly.

Not checked: the other Deluxe discs (they resolve to the same addresses as
their base revision), and pressing buttons through the real SI path (Dolphin's
Pipe input never delivered).

**Not tested on a console.** The poller is Barrel Blast's, which was; the
mapping and the KPAD/WPAD side are verified in Dolphin only.

## Credits

- **Vague Rant, crediar** — Classic Controller support for City Folk (the code
  this builds on), and mogchamp for the button layout
- **Barrel Blast Patch** — GameCube SI polling, hot-plug recovery and the
  KPAD sample synthesis this follows
