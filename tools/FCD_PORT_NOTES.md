# Forecast Channel (RVL_MWM - FCD) transplant notes

Donor: Mario & Sonic at the Olympic Winter Games (USA), `s.dol`, FCD build **Feb 26 2009 14:23:09**
(banner at `0x8070932f`). Target: ACCF `RUUE02` `main.dol`.

Note: the addresses in the public FCD gist are for the Dec 2008 build and do NOT match `s.dol`.

## FCD in s.dol (code `0x80562950`-`0x8056481c`)

| s.dol addr | size | name | notes |
|---|---|---|---|
| 0x80562950 | 0xc | FCDGetWorkMemorySize | returns 0x3909C |
| 0x8056295c | 0x288 | FCDInit(buf) | -1 already init / too small, -10 WC24 missing, -11 invalid |
| 0x80562be4 | 0x3d8 | FCDGetForecast(u32 id, u64 time, out) | r3=id, r4=pad, r5:r6=time, r7=out; -1 uninit, -12 not found, -13 time out of range |
| 0x80562fbc | 0x228 | FCDGetCurrent(u32 id, out) | short.bin lookup; fills place string + 0x112..0x11a fields |
| 0x805631f4 | 0x14 | getter: savedata+0x08 -> *r3 | likely FCDGetOwnAddressId (unconfirmed which of the three) |
| 0x80563224 | 0xfc | FCDGetPlace(u32 id, out 0x300) | 3x 0x80 UTF-16 strings: city, region, country |
| 0x80563354 | 0x14 | getter: savedata+0x0c -> *r3 | |
| 0x80563384 | 0x14 | getter: savedata+0x10 -> *r3 | |
| 0x805633b4 | 0x10 | FCDFinalize | clears init flag |
| 0x805633d8 | 0x19c | FCD_LoadLZ(maxSize, dst, &outSize) | reads `@24:/N.bin` from the mounted VFF in 0x2000 chunks, LZ10 (type byte & 0xf0 == 0x10) |
| 0x80563574 | 0x340 | fill forecast entry (helper) | |
| 0x805638b4 | 0x260 | fill forecast entry (helper) | |
| 0x80563b14 | 0xa44 | FCD_Parse/validate | checks magic, byte +0x1a == 1, 'HAF0' header, CRC32 |
| 0x80564558 | 0x24c | parse helper | |
| 0x805647a4 | 0x78 | parse helper | |

State: context struct at `0x807d5128` (.bss), init flag at SDA `-0x6908(r13)`.
Other SDA pointers used: `-0x7310`, `-0x7314`, `-0x7318` (string/pointer vars), plus address-of `-0x730c`, `-0x7308`, `-0x7320`.
Path table: `0x807093a0` (3x wc24dl.vff for 4841464a / 48414645 / 48414650), `0x80709430` (3x savedata.dat).

Work buffer: forecast.bin @ +0x0 (0x32000), short.bin @ +0x32000 (0x5000), HAF0 savedata @ +0x37000 (0x20),
chunk temp buffer (0x2000) after. Total 0x3909C.

## Dependencies -> ACCF equivalents (fingerprint matched)

| s.dol | role | ACCF | confidence |
|---|---|---|---|
| 0x80463b88 | VF mount drive | 0x80434e44 (0x80434cb8 is a near-identical sibling) | high |
| 0x80463d14 | VF unmount | 0x80434fd0 | exact |
| 0x80463df0 | VF open | 0x80435188 | high (slightly different body) |
| 0x80463eb4 | VF close | 0x80435264 | exact |
| 0x80463f20 | VF read | 0x8043535c | exact |
| 0x80463fbc | VF get file size | **not found** - ACCF's older VF lib has no size call with the 0x7fffffff clamp | OPEN |
| 0x805a5b48 | NANDOpen(path, info, mode) | 0x803a8a2c (0x803a8ab8 = async) | exact |
| 0x805a541c | NANDGetLength | 0x803a8154 (0x803a81dc = async) | exact |
| 0x805a4ef4 | NANDRead | 0x803a7bb8 (0x803a7c98 = async) | exact |
| 0x805a5dc8 | NANDClose | 0x803a8cac | exact |
| 0x805aae84 | CXGetUncompressedSize | 0x803a70cc | exact |
| 0x805aa698 / 0x805aa70c | CXInitUncompContextLZ / CXReadUncompLZ (streaming LZ10) | **not found** | write our own LZ10 |
| 0x804417b0 | CRC32 (nibble table @ 0x80657c78, init -1, final NOT) | reimplement | trivial |
| 0x8056a788 | lock/init helper | 0x8037b234 | exact |
| 0x8060bfb0 etc. | MW savegpr/restgpr, 0x8060c134 = 64-bit divide | 0x8044e808 / 0x8044e834 / 0x8044e880 / 0x8044e98c | exact |

ACCF VF lock object: `0x807b5a80`-ish (`lis -0x7f8c; addi 0x5a80`), enabled flag SDA `-0x1b4c(r13)`.
ACCF already carries the string `wc24dl.vff` at `0x805606b4` and the NWC24 library, so VF is in use there.

## Open items
1. VF file size in ACCF (or read header/size another way - the LZ10 header gives the decompressed size, and the
   file length could be taken from the VF file struct).
2. CX LZ10 streaming decompressor is absent in ACCF; needs a small replacement.
3. Decide hook point / weather consumer in ACCF, and where to put the ~0x3909C work buffer + 0x807d5128-style context.
4. Ghidra: no code units/functions exist in the FCD range of `s.dol`; scripting is disabled on the GhydraMCP server
   and auto-analysis was not run.

## ACCF weather (RUUE02 main.dol)

`dWeather_c` ctor `0x801c8ba4`; instance pointer in SDA `-0x2ad8(r13)`.
Fields: `+0x5884` current type, `+0x5888` next-hour type, `+0x5894` indoor/"rain-visible" flag,
`+0x5895` snow-season flag (from `0x80162a80`), `+0x5896/+0x5897/+0x5899` init state.
Sub-objects: rain `+0x64`, snow `+0x2a4`, sakura `+0x1bc4`, confetti `+0x39e8`.

Type is chosen by `0x801c9d24` (this hour) and `0x801c9d9c` (next hour):
pattern = `0x801c9c08/0x801c9cac(date)` (0..15), type = `*(u8*)(patternTable[pattern] + (hour-6 mod 24))`,
tables at `0x8047e420 + 0x18*n`, pointer array at `0x805002d8`. If `0x801c9ea0()` (snow flag) is set: 3->5, 4->6.

| type | meaning | evidence |
|---|---|---|
| 0 | clear / fine | no rain/snow |
| 1 | mild overcast | no rain (0.0) and no snow |
| 2 | heavier overcast | no rain (0.0) and no snow |
| 3 | rain | `+0x220` intensity 3.0 (`0x801732d4`) |
| 4 | heavy rain | `+0x220` intensity 6.0 |
| 5 | snow | 100 particles (`0x80174b24`) |
| 6 | heavy snow | 200 particles |

Types 1/2 are inferred (no particles); sakura (`ef_sakura`) and confetti (`ef_kamifubuki`) are date/event
effects outside the type enum (sakura gate: `0x801757c4`).
Single override point: return value of `0x801c9d24` / `0x801c9d9c` (before the 3->5 / 4->6 remap).

## Forecast condition -> ACCF weather type (draft)

Source: WiiLink24/ForecastChannel `weather.xml` `<conditions>` (40 entries), keyed on `code_2` (international)
and `japanese_code_2` (Japan). Keep the full 16-bit values (0x8000 = night variant); masking `code_2` collides `806A`/`006A`.

### International (`code_2`) - exact

| ACCF type | code_2 |
|---|---|
| 0 clear | 0065 0066 8065 8066 |
| 1 mild overcast | 006B 007A 806A 806B 807A |
| 2 heavy overcast | 006A 007C |
| 3 rain | 0067 006C 006F 0071 806C 8071 |
| 4 heavy rain | 007D 807D |
| 5 snow | 0068 006D 0072 0073 0076 0079 806D 8076 |
| 6 heavy snow | 0074 |

### Japan (`japanese_code_2`) - coarse, lossy

| japanese_code_2 | conditions sharing it | ACCF type |
|---|---|---|
| 0001 | Sunny, Mostly Sunny, Haze, Hot, Cold, Windy | 0 clear |
| 0002 | Partly Cloudy, Intermittent Clouds | 1 mild overcast |
| 0003 | Partly Sunny with Showers | 3 rain |
| 0004 | Partly Sunny with Flurries | 5 snow |
| 0005 | Partly Sunny with Thunderstorms | 4 heavy rain |
| 000A | Mostly Cloudy, Cloudy, Overcast, Fog | 2 heavy overcast |
| 000C | Mostly Cloudy with Showers, Mostly Cloudy with Flurries, Mostly Cloudy with Snow | 5 snow |
| 000E | Mostly Cloudy with Thunderstorms | 4 heavy rain |
| 0013 | Showers, Rain | 3 rain |
| 0016 | Rain and Snow | 5 snow |
| 0021 | Thunderstorms | 4 heavy rain |
| 8001 | Clear, Mostly Clear | 0 clear |
| 800A | Partly Cloudy, Intermittent Clouds, Hazy Moonlight, Mostly Cloudy | 1 mild overcast |
| 800C | Partly Cloudy with Showers, Mostly Cloudy with Showers | 3 rain |
| 800D | Mostly Cloudy with Flurries, Mostly Cloudy with Snow | 5 snow |
| 800E | Partly Cloudy with Thunderstorms, Mostly Cloudy with Thunderstorms | 4 heavy rain |
| 801A | Flurries, Snow, Ice, Sleet, Freezing Rain | 5 snow |

Resolution rules for the ambiguous Japanese codes: the majority/lightest type wins (`000A` -> heavy overcast, `800A` -> mild overcast,
`0002` -> mild overcast, `801A` -> snow (heavy snow is unreachable), `0001` -> clear), and `000C` (showers vs flurries vs snow) is fixed to
5 (snow), so Japanese "Mostly Cloudy with Showers" shows snow.

Hook must override the FINAL value of `0x801c9d24`/`0x801c9d9c` (after the snow-season 3->5 / 4->6 remap) so real snow forecasts show snow
out of season.

## Using FCDGetForecast for "today"

M&S's own caller (`0x802bd30c` in s.dol) is the reference. Sequence:

```
size = FCDGetWorkMemorySize();            // 0x3909C
buf  = alloc(size);                       // 32-byte aligned; M&S: 0x8013f744 (heap thunk)
if (lockFn() < 0) goto fail;              // s.dol 0x80449e60 -> ACCF 0x8040c7dc  (paired with unlock below)
if (FCDInit(buf) == 0) {
    FCDGetOwnAddressId(&id);              // s.dol 0x805631f4 (savedata+0x08); M&S falls back to a fixed id
    FCDGetPlace(id, place);               // optional
    now = OSGetTime();                    // s.dol 0x805747f8 -> ACCF 0x803855d4 (mftb read)
    if (FCDGetForecast(id, /*pad*/0, now, out) == 0) use(out);   // r3=id r4=pad r5:r6=time r7=out (0x530 bytes)
    FCDFinalize();
}
unlockFn();                               // s.dol 0x80449f30 -> ACCF 0x8040c990
free(buf);
```

`FCDGetForecast`: day = ((now/ticks_per_sec)/60 - record.base_minutes) / 1440; day 0..2 use 0x1c-byte entries, 3..8 use
8-byte entries; >8 or before base -> `-13`, unknown id -> `-12`, not initialised -> `-1`. "Today" is day 0 (passing `OSGetTime()` as M&S does).

Output (`out`, 0x530 bytes): `+0x00/+0x08` u64 start/duration in ticks, **`+0x10` u16 condition code of the day**, `+0x12` UTF-16 description,
`+0x112..+0x119` bytes (temperatures etc.), `+0x11a/+0x11e` bytes, **`+0x120 + 2*i` u16 condition code for 4 sub-periods (i=0..3)**,
`+0x128 + 0x100*i` UTF-16 description per sub-period, `+0x528..+0x52b` bytes. Code 0xFFFF = unknown.

M&S reads the same u16 at `+0x10` of `FCDGetCurrent` and passes it through `0x8022bd9c`, which strips `0x8000` and looks the code up in a
0x3b-entry table at `0x80635e80`. That table contains exactly the codes `0x01..0x21` (japanese_code_2) and `0x65..0x7e` (code_2),
confirming those are the two sets that appear at runtime.

ACCF still needs: an allocator choice for the 0x3909C buffer (M&S's `0x8013f744` is a thunk into its own heap), VF size replacement, LZ10 decompressor.

## Work buffer, loader and heap (implemented in tools/weather/)

- `tools/weather/fcd_loader.c`: replaces FCD's LZ loader (s.dol `0x805633d8`). Streaming LZ10 **and** LZ11 (the game's CX code accepts header
  byte `0x10`/`0x11`), reading `@24:/3.bin` / `@24:/4.bin` in 0x2000-byte chunks through City Folk's own `VFOpen` (`0x80435188`),
  `VFRead` (`0x8043535c`) and `VFClose` (`0x80435264`). No file-size call is needed: City Folk's `VFRead(handle, buf, len, &got)` clamps at EOF,
  zero-fills and reports `got`. Returns 0 / -10 (VF failure) / -11 (bad, truncated or oversize LZ data) like the original.
  Builds for PPC with devkitPPC (1062 bytes); `tools/weather/test_lz.py` round-trips both formats on the host.
- Context struct (s.dol `0x807d5128`): `+0 forecast`, `+4 forecast size`, `+8 short.bin`, `+0xc short size`, `+0x10 savedata`, `+0x14 read chunk`, `+0x18 raw buffer`.
- Buffer: `FCDGetWorkMemorySize` = 0x3909C; City Folk allocates `0x48000` (about 1.26x) for forecast.bin (0x32000) + short.bin (0x5000) + savedata + chunk.
- Allocation: the NWC24 heap, an EGG ExpHeap created by `0x800b5c30` from `RootHeapMEM2`, pointer at SDA `-0x3284(r13)`. Alloc is vtable `+0x14`
  (`heap, size, align`), free is vtable `+0x18` (`heap, ptr`). Its size comes from `0x800e94a8` (only caller: `0x800b5c48`), currently `0x5C800`; NWC24 itself
  takes about 0x55000 of that, so the heap has to grow by the buffer. Patch `0x800e94a8`:
  `3C600006 3863C800` (`lis r3,6; addi r3,r3,-0x3800`) -> `3C60000A 38634800` (`lis r3,0xA; addi r3,r3,0x4800`) = `0xA4800`. Not yet run on hardware/emulator.

## Design requirements (from the project owner)

- The forecast is used **per game day**, not hourly. Forecast Channel stores 7 days, so the game shows day N's forecast for game day N, and when the
  game is left running past the 6 AM rollover (after the cutscene) it advances to the next stored day, and so on. Never use `FCDGetCurrent`.
- City Folk already works in a 6-hour-shifted day: `0x801757c4` calls `0x8016d7b8` with an hour offset of -6, and the pattern tables are indexed by `hour-6 mod 24`.
  So the forecast day to ask for is the date of `(now - 6h)`; pass that as the time argument of `FCDGetForecast`.
- Fetch once, cache the daily types (up to 7), and index by `gameDate - fetchDate`; fall back to the vanilla pattern when the offset is outside the cache or FCD fails.

## Does City Folk use temperature / wind / UV index?

Nookipedia's Weather page lists no temperature, wind, UV index or humidity mechanic for City Folk or Wild World. Weather there is purely visual and seasonal
(rain, snow, cloud density, plus aurora, rainbows and meteor showers). So the forecast's temperature/UV/wind fields can be ignored. Things to keep in mind:
- Cloud density is a separate layer: `0x801c9e14` derives a cloud level from the same day pattern (u8 table at `0x8047e960`), not from the weather type.
  Overriding only the final type leaves the clouds on the vanilla pattern.
- City Folk eases weather changes in over the last ten minutes of the hour, and rainbows follow heavy rain. A constant all-day type removes those transitions.

## Decision: hook the final type, leave the pattern functions alone

Pattern selection (`0x801c9c08` this hour, `0x801c9cac` next hour) is not modified. The forecast override goes on the return value of the type
functions `0x801c9d24` (this hour) and `0x801c9d9c` (next hour), after their snow-season remap.

What stays on the vanilla pattern as a result (callers of the pattern functions, all outside the dWeather type logic):
- `0x80039bac` and `0x800ec72c` only test `pattern == 0` (the "fine day" pattern) and act on it.
- `0x801ad590` calls `0x801c9cac` and range-tests the pattern (0-6, 7-8, 0x10-0x12, 0x13-0x15, 0x16-0x19 against the date) before asking `0x801c9d9c`
  for a next-hour type, so it does go through the type hook once its own gate passes.
- The cloud level (`0x801c9e14`, from the pattern via the u8 table at `0x8047e960`) has no direct callers (reached indirectly), so it is also untouched.
Open item: decide whether to also derive the cloud level from the forecast type with a separate override.
