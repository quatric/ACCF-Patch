/* External (Forecast Channel) weather for City Folk.
 *
 * Decision logic only; the platform (FCD calls, heap, VF) is behind
 * weather_platform_fetch() so this file can be tested on the host.
 */
#ifndef WEATHER_H
#define WEATHER_H

#include "fcd_loader.h"

#define WEATHER_DAYS     7      /* Forecast Channel keeps up to 7 days */
#define WEATHER_NONE     0xFF

/* City Folk weather types (dWeather_c+0x5884) */
enum {
    WEATHER_CLEAR = 0, WEATHER_MILD_OVERCAST, WEATHER_HEAVY_OVERCAST,
    WEATHER_RAIN, WEATHER_HEAVY_RAIN, WEATHER_SNOW, WEATHER_HEAVY_SNOW
};

/* OSCalendarTime layout used by the game's clock (0x80600898) */
typedef struct CalTime {
    s32 sec, min, hour, mday, mon /* 0-11 */, year, wday, yday, msec, usec;
} CalTime;

/* Platform: fill codes[0..n-1] with the Forecast Channel condition code for the
 * game days starting at (game day of `date`) - dayBack (0xFFFF = unknown).
 * `dayBack` is 1 when the caller's date is already tomorrow (the TV hook).
 * Returns n (<= max), 0 if no forecast data is available, or -1 if the platform is not ready yet
 * (try again later; this does not count as a failed attempt). */
s32 weather_platform_fetch(const CalTime *date, s32 dayBack, u16 *codes, s32 max);

/* Scene flags: WEATHER_SCENE_CITY is set while the game uses its separate City weather (scene kinds 0x2d-0x37 and
 * 0x3d, the ones for which the game picks its City type function). The City is never overridden. */
#define WEATHER_SCENE_CITY 0x200
u32 weather_platform_scene_flags(void);

/* Game day number of a calendar time. City Folk's day rolls over at 6 AM. */
s32 weather_game_day(const CalTime *c);

/* Forecast condition code -> weather type (WEATHER_NONE if unknown) */
u8 weather_map_code(u16 code);
/* Weather type -> TV program index (/Ftr/tv_program_XY: 0 ff, 1 cc, 2 rr, 8 ss) */
u8 weather_tv_program(u8 type);

/* Hooks. Return -1 to fall through to the original game code.
 *   weather_type_for_date: dWeather type functions 0x801c9d24 / 0x801c9d9c
 *   weather_tv_for_date:   TV program function 0x801c9e14 (date is already +1 day) */
s32 weather_type_for_date(const CalTime *date);
s32 weather_tv_for_date(const CalTime *date);

/* Disable switch: B held on a Wii Remote or Classic Controller before the
 * title screen latches external weather off for the whole session. */
#define WEATHER_KPAD_DEV_CLASSIC 2
#define WEATHER_CORE_B   0x0400u
#define WEATHER_CLASSIC_B 0x0040u
void weather_sample_buttons(u32 coreHold, u8 devType, u32 classicHold);
void weather_title_reached(void);

/* Glue called from the hook trampolines (hooks.S):
 *   weather_hook_pad:         after KPADRead in the EGG CoreController update (0x804438dc);
 *                             `ctrl` is the controller, samples at +0x14 (KPADStatus, 0x84 bytes), count at +0x854
 *   weather_on_module_link:   module link request (0x80086e00); closes the B window when a
 *                             scene module (title demo 0xA5, 0xA6, select 0xA2, stage 0x01) is linked */
#define WEATHER_CTRL_STATUS   0x14
#define WEATHER_CTRL_COUNT    0x854
#define WEATHER_KPAD_DEV      0x5C
#define WEATHER_KPAD_CLHOLD   0x60
void weather_hook_pad(const u8 *ctrl);
void weather_on_module_link(u32 id);
s32  weather_is_disabled(void);

void weather_reset(void);   /* tests */

#endif
