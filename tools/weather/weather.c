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
u16 g_codes[WEATHER_DAYS];   /* raw Forecast Channel codes of the last successful fetch (diagnostics) */
static s32 g_lastTryDay;
static u8  g_tries;          /* failed fetch attempts on g_lastTryDay */
#define WEATHER_MAX_TRIES 3
#define WEATHER_RETRY_CALLS 240     /* hook calls between attempts (about a few seconds of frames) */
static s32 g_wait;           /* hook calls left before the next attempt */
static u8  g_off;           /* latched by the B button */
static u8  g_titleReached;

void weather_reset(void)
{
    g_cache.baseDay = 0;
    g_cache.n = 0;
    g_lastTryDay = -0x7FFFFFFF;
    g_tries = 0;
    g_wait = 0;
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
    if (weather_platform_scene_flags() & WEATHER_SCENE_CITY)
        return -1;                /* the City keeps its own weather */
    if (g_wait > 0)
        g_wait--;
    if ((off < 0 || off >= g_cache.n) && g_wait == 0 && (day != g_lastTryDay || g_tries < WEATHER_MAX_TRIES)) {
        u16 codes[WEATHER_DAYS];
        s32 i, n;

        n = weather_platform_fetch(c, queryBack, codes, WEATHER_DAYS);
        if (n < 0)
            return -1;                /* platform not ready: no attempt used, ask again next call */
        if (day != g_lastTryDay)
            g_tries = 0;
        g_lastTryDay = day;
        g_tries++;
        g_wait = n > 0 ? 0 : WEATHER_RETRY_CALLS;
        if (n > WEATHER_DAYS)
            n = WEATHER_DAYS;
        if (n > 0) {
            /* platform fills codes relative to the anchor (today's game day) */
            g_cache.baseDay = day;
            g_cache.n = n;
            for (i = 0; i < n; i++) {
                g_codes[i] = codes[i];
                g_cache.type[i] = weather_map_code(codes[i]);
            }
        }
        off = day + queryBack - g_cache.baseDay;
    }
    if (off < 0 || off >= g_cache.n)
        return -1;
    return g_cache.type[off] == WEATHER_NONE ? -1 : g_cache.type[off];
}

s32 weather_type_for_date(const CalTime *date)
{
    g_titleReached = 1;     /* weather code only runs in town, which is past the title */
    return cache_type(date, 0);
}

s32 weather_tv_for_date(const CalTime *date)
{
    s32 t;

    g_titleReached = 1;
    t = cache_type(date, 1);
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

/* the game's memory is big-endian; explicit loads keep this testable on any host */
static u32 rd32be(const u8 *p)
{
    return ((u32)p[0] << 24) | ((u32)p[1] << 16) | ((u32)p[2] << 8) | (u32)p[3];
}

void weather_hook_pad(const u8 *ctrl)
{
    const u8 *st = ctrl + WEATHER_CTRL_STATUS;

    if (g_titleReached || (s32)rd32be(ctrl + WEATHER_CTRL_COUNT) <= 0)
        return;
    weather_sample_buttons(rd32be(st), st[WEATHER_KPAD_DEV], rd32be(st + WEATHER_KPAD_CLHOLD));
}

void weather_on_module_link(u32 id)
{
#ifdef WEATHER_SELFTEST
    /* test builds only: run one fetch on the game's own calendar when the title/select/stage scene links */
    static u8 done;
    if (!done && (id == 0xA5 || id == 0xA2 || id == 0x01)) {
        done = 1;
        weather_type_for_date((const CalTime *)ACCF_CALENDAR);
    }
#endif
    if (id == 0xA5 || id == 0xA6 || id == 0xA2 || id == 0x01)
        g_titleReached = 1;
}
