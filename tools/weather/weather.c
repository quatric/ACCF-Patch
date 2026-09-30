#include "weather.h"

typedef struct { u16 code; u8 type; } MapEntry;
static const MapEntry kMap[] = {
#include "weather_map.inc"
};

typedef struct {
    s32 baseDay;
    s32 n;
    u8  type[WEATHER_DAYS];
} WeatherCache;

static WeatherCache g_cache;
static s32 g_lastTryDay;
static u8  g_off;           /* latched by the B button */
static u8  g_titleReached;

void weather_reset(void)
{
    g_cache.baseDay = 0;
    g_cache.n = 0;
    g_lastTryDay = -0x7FFFFFFF;
    g_off = 0;
    g_titleReached = 0;
}

s32 weather_game_day(const CalTime *c)
{
    /* days since 1970-01-01 (civil from days), month given 0-based */
    s32 y = c->year, m = c->mon + 1, d = c->mday;
    s32 era, yoe, doy, doe, day;

    if (m <= 2)
        y--;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = y - era * 400;
    doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    day = era * 146097 + doe - 719468;
    if (c->hour < 6)
        day--;
    return day;
}

u8 weather_map_code(u16 code)
{
    s32 lo = 0, hi = (s32)(sizeof(kMap) / sizeof(kMap[0])) - 1;
    while (lo <= hi) {
        s32 mid = (lo + hi) >> 1;
        if (kMap[mid].code == code)
            return kMap[mid].type;
        if (kMap[mid].code < code)
            lo = mid + 1;
        else
            hi = mid - 1;
    }
    return WEATHER_NONE;
}

u8 weather_tv_program(u8 type)
{
    switch (type) {
    case WEATHER_CLEAR:          return 0;   /* ff */
    case WEATHER_MILD_OVERCAST:
    case WEATHER_HEAVY_OVERCAST: return 1;   /* cc */
    case WEATHER_RAIN:
    case WEATHER_HEAVY_RAIN:     return 2;   /* rr */
    case WEATHER_SNOW:
    case WEATHER_HEAVY_SNOW:     return 8;   /* ss */
    }
    return WEATHER_NONE;
}

/* The anchor is the game day of "today"; the TV asks about tomorrow, so its
 * date is anchor + queryBack (1). Fetches at most once per game day. */
static s32 cache_type(const CalTime *c, s32 queryBack)
{
    s32 day = weather_game_day(c) - queryBack;      /* anchor: today's game day */
    s32 off = day + queryBack - g_cache.baseDay;    /* queried day minus base   */

    if (g_off)
        return -1;
    if ((off < 0 || off >= g_cache.n) && day != g_lastTryDay) {
        u16 codes[WEATHER_DAYS];
        s32 i, n;

        g_lastTryDay = day;
        n = weather_platform_fetch(c, queryBack, codes, WEATHER_DAYS);
        if (n > WEATHER_DAYS)
            n = WEATHER_DAYS;
        if (n > 0) {
            /* platform fills codes relative to the anchor (today's game day) */
            g_cache.baseDay = day;
            g_cache.n = n;
            for (i = 0; i < n; i++)
                g_cache.type[i] = weather_map_code(codes[i]);
        }
        off = day + queryBack - g_cache.baseDay;
    }
    if (off < 0 || off >= g_cache.n)
        return -1;
    return g_cache.type[off] == WEATHER_NONE ? -1 : g_cache.type[off];
}

s32 weather_type_for_date(const CalTime *date)
{
    return cache_type(date, 0);
}

s32 weather_tv_for_date(const CalTime *date)
{
    s32 t = cache_type(date, 1);
    return t < 0 ? -1 : (s32)weather_tv_program((u8)t);
}

void weather_sample_buttons(u32 coreHold, u8 devType, u32 classicHold)
{
    if (g_titleReached)
        return;
    if (coreHold & WEATHER_CORE_B)
        g_off = 1;
    if (devType == WEATHER_KPAD_DEV_CLASSIC && (classicHold & WEATHER_CLASSIC_B))
        g_off = 1;
}

void weather_title_reached(void) { g_titleReached = 1; }
s32  weather_is_disabled(void)   { return g_off; }
