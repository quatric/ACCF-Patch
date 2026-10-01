/* weather_platform_fetch() on top of RVL_MWM-FCD, following the call sequence of
 * Mario & Sonic's own weather code (s.dol 0x802bd30c):
 *   alloc -> acquire IOS resource -> FCDInit -> own address id -> FCDGetForecast -> FCDFinalize -> release -> free
 */
#include "weather.h"

/* the transplanted FCD entry points (fcd_relocated.S) */
s32 FCDGetWorkMemorySize(void);
s32 FCDInit(void *work);
s32 FCDGetOwnAddressId(u32 *id);
s32 FCDGetForecast(u32 id, u32 pad, u64 time, void *out);
s32 FCDFinalize(void);

#ifdef FCD_HOST
s32 accf_lock(void);
s32 accf_unlock(void);
u64 accf_cal_to_ticks(const CalTime *c);
u32 accf_bus_clock(void);
#else
/* City Folk (RUUE02) */
#define accf_lock          ((s32 (*)(void))0x8040c7dc)          /* twin of s.dol 0x80449e60 */
#define accf_unlock        ((s32 (*)(void))0x8040c990)          /* twin of s.dol 0x80449f30 */
#define accf_cal_to_ticks  ((u64 (*)(const CalTime *))0x803859e8)  /* OSCalendarTimeToTicks */
#define accf_bus_clock()   (*(volatile u32 *)0x800000F8)
/* VF library (City Folk): flag -0x1b50(r13) says initialised; the game's NWC24 code calls VFInit(buf, 0x4000) with a
 * buffer from the NWC24 heap when it needs VF and shuts it down afterwards */
#define vf_is_init         ((s32 (*)(void))0x80434a0c)
#define vf_init            ((void (*)(void *, u32))0x80434a20)
#define vf_shutdown        ((void (*)(void))0x80434ae8)
#define VF_BUF_SIZE        0x4000
#endif

#define FCD_FORECAST_SIZE   0x530
#define FCD_FORECAST_CODE   0x10     /* u16 condition code of the day */

/* last fetch, for diagnostics: lock, FCDInit, own area id, FCDGetOwnAddressId, first FCDGetForecast */
s32 g_fetch_status[5] = { 99, 99, 99, 99, 99 };

static u16 be16(const u8 *p) { return (u16)((p[0] << 8) | p[1]); }

s32 weather_platform_fetch(const CalTime *date, s32 dayBack, u16 *codes, s32 max)
{
    static u8 out[FCD_FORECAST_SIZE] __attribute__((aligned(32)));
    s32 n = 0;
    u32 id = 0, tps, i;
    u64 t, tpd;
    void *work, *vfbuf = 0;

    g_fetch_status[0] = g_fetch_status[1] = g_fetch_status[2] = g_fetch_status[3] = g_fetch_status[4] = 99;
    work = fcd_work_alloc();
    if (!work)
        return 0;
    g_fetch_status[0] = accf_lock();
    if (g_fetch_status[0] < 0) {
        fcd_work_free(work);
        return 0;
    }
    if (!vf_is_init()) {                            /* bring VF up the way the game's NWC24 does */
        vfbuf = fcd_heap_alloc(VF_BUF_SIZE);
        if (!vfbuf) {
            accf_unlock();
            fcd_work_free(work);
            return 0;
        }
        vf_init(vfbuf, VF_BUF_SIZE);
    }
    g_fetch_status[1] = FCDInit(work);
    if (g_fetch_status[1] == 0) {
        g_fetch_status[3] = FCDGetOwnAddressId(&id);
        g_fetch_status[2] = (s32)id;
        if (g_fetch_status[3] == 0 && id != 0) {
            tps = accf_bus_clock() / 4;                 /* timebase ticks per second */
            tpd = (u64)tps * 86400u;
            t   = accf_cal_to_ticks(date);
            t  -= (u64)tps * 21600u;                    /* game day starts at 6 AM */
            for (i = 0; i < (u32)dayBack; i++)
                t -= tpd;
            for (i = 0; (s32)i < max; i++, t += tpd) {
                s32 r = FCDGetForecast(id, 0, t, out);
                if (i == 0)
                    g_fetch_status[4] = r;
                if (r != 0)
                    break;
                codes[n++] = be16(out + FCD_FORECAST_CODE);
            }
        }
        FCDFinalize();
    }
    if (vfbuf) {                                    /* only tear down what we brought up */
        vf_shutdown();
        fcd_heap_free(vfbuf);
    }
    accf_unlock();
    fcd_work_free(work);
    return n;
}
