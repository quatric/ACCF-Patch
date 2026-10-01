/* GameCube controller (port 1) -> Classic Controller bridge for City Folk.
 *
 * Three hooks, one blob each (see hooks.S for the register-saving entry
 * stubs).  The game links the SI library but not PAD, so nothing ever polls
 * the pads: gc_poll() drives the Serial Interface's own auto-polling (the
 * approach is Barrel Blast Patch's, hardware-tested there).  gc_sample() turns
 * the pad's state into a Classic Controller sample in KPAD's ring, and
 * gc_probe() makes WPADProbe report a Classic Controller on channel 0, so the
 * game (and Vague Rant's Classic Controller code) treat the pad as one.
 *
 * Addresses come in as -D macros, resolved per disc revision by anchors.py.
 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;
typedef signed char s8;

#define R32(a) (*(volatile u32 *)(a))
#define SI_OUT0   (0xCD006400u)
#define SI_IN0H   (0xCD006404u)
#define SI_IN0L   (0xCD006408u)
#define SI_POLL   (0xCD006430u)
#define SI_COMCSR (0xCD006434u)
#define SI_SR     (0xCD006438u)

struct st {
    u32 probe_tb;   /* last SIGetType */
    u32 busy_tb;    /* when si:: was first seen busy (0 = idle) */
    u8 norep;       /* consecutive frames with NOREP on port 1 */
    u8 ours;        /* the last KPAD sample on channel 0 was ours */
    u32 dbg_h, dbg_l;   /* last pad response seen by gc_sample (for debugging) */
};
#define ST ((volatile struct st *)STATE)

static inline u32 tb(void)
{
    u32 t;
    __asm__ volatile("mftb %0" : "=r"(t));
    return t;
}

/* a valid, error-free pad response on port 1 */
static inline int gc_in(u32 *h, u32 *l)
{
#ifdef DEBUG_FEED
    /* test builds: the pad's response is written to STATE+0x20/0x24 by a debugger */
    if (!R32(STATE + 0x20))
        return 0;
    *h = R32(STATE + 0x20);
    *l = R32(STATE + 0x24);
    return 1;
#endif
    u32 v = R32(SI_IN0H);
    if ((v & 0x80000000u) || !(v & 0x00800000u))
        return 0;
    *h = v;
    *l = R32(SI_IN0L);
    return 1;
}

#if defined(HOOK_POLL)
void gc_poll(u32 chan)
{
    volatile u32 *types = (volatile u32 *)SI_TYPES;
    u32 type, sisr, mask, poll;
    int confirmed;
    s32 busy;

    if (chan)
        return;

    /* probe the port until a standard pad answers, at most every 0.25 s:
     * probing every frame collided with the pad's own polling on hardware */
    type = types[0];
    confirmed = !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
    if (!confirmed) {
        u32 now = tb();
        if (now - ST->probe_tb >= 15187500u) {
            ST->probe_tb = now;
            ((u32 (*)(u32))FN_SIGETTYPE)(0);
        }
    }

    /* an unplugged pad latches NOREP; si:: never reads it (no PAD library),
     * so copy a persistent one into the type cache ourselves, which makes
     * SIGetType probe the port again once a pad is plugged back in */
    sisr = R32(SI_SR);
    if (sisr & 0x08000000u) {
        if (ST->norep < 10)
            ST->norep++;
        else
            types[0] = 8;
    } else {
        ST->norep = 0;
    }

    R32(SI_OUT0) = 0x00400300u;                    /* poll command */
    R32(SI_SR) = (sisr & 0x0F0F0F0Fu) | 0x80000000u; /* ack errors, latch OUT */

    type = types[0];
    confirmed = !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
    mask = confirmed ? 0x88u : 0;                  /* EN0 + VBCPY0 */
    poll = R32(SI_POLL) & ~0xFFu;
    if (!(poll & 0xFF00u))
        poll |= 0x0100u;
    R32(SI_POLL) = poll | mask;
    /* si:: rewrites SIPOLL from its own shadow on every retrace */
    R32(SI_SHADOW) = (R32(SI_SHADOW) & ~0xFFu) | mask;

    /* a pad unplugged mid-transfer leaves si::'s global busy flag wedged
     * (nothing times it out); force it idle after a second */
    busy = (s32)R32(SI_BUSY);
    if (busy == -1) {
        ST->busy_tb = 0;
    } else {
        u32 now = tb();
        if (ST->busy_tb == 0) {
            ST->busy_tb = now | 1;
        } else if (now - ST->busy_tb >= 60750000u) {
            u32 lvl = ((u32 (*)(void))FN_OSDISABLE)();
            R32(SI_BUSY) = (u32)-1;
            R32(SI_COMCSR) = 0x80000000u;
            ((void (*)(u32))FN_OSRESTORE)(lvl);
            ST->busy_tb = 0;
        }
    }
}
#endif

#if defined(HOOK_SAMPLE)
/* Classic Controller buttons as WPAD reports them */
#define CL_UP    0x0001
#define CL_LEFT  0x0002
#define CL_X     0x0008
#define CL_A     0x0010
#define CL_Y     0x0020
#define CL_B     0x0040
#define CL_R     0x0200
#define CL_PLUS  0x0400
#define CL_MINUS 0x1000
#define CL_L     0x2000
#define CL_DOWN  0x4000
#define CL_RIGHT 0x8000

static inline s16 stick(u32 raw)
{
    s32 v = ((s32)(raw & 0xFF) - 128) * 3;       /* pad ~+-100 -> game +-300 */
    if (v > 308)
        v = 308;
    if (v < -308)
        v = -308;
    return (s16)v;
}

static void fill_cc(u8 *s, u32 h, u32 l)
{
    u32 b = 0, la = (l >> 8) & 0xFF, ra = l & 0xFF;

    if (h & 0x01000000u) b |= CL_A;          /* A: confirm / action */
    if (h & 0x02000000u) b |= CL_B;          /* B: cancel / run / pick up */
    if (h & 0x04000000u) b |= CL_PLUS;       /* X: map / next tab */
    if (h & 0x08000000u) b |= CL_X;          /* Y: inventory / last tab */
    if (h & 0x10000000u) b |= CL_Y;          /* Start: photos */
    if (h & 0x00100000u) b |= CL_MINUS;      /* Z: take photo */
    if (h & 0x00400000u) b |= CL_L;          /* L: toggle cursor */
    if (h & 0x00200000u) b |= CL_R;          /* R: run */
    if (h & 0x00080000u) b |= CL_UP;
    if (h & 0x00040000u) b |= CL_DOWN;
    if (h & 0x00020000u) b |= CL_RIGHT;
    if (h & 0x00010000u) b |= CL_LEFT;

    *(u16 *)(s + 0x2A) = (u16)b;
    *(s16 *)(s + 0x2C) = stick(h >> 8);      /* control stick x */
    *(s16 *)(s + 0x2E) = stick(h);           /* control stick y */
    *(s16 *)(s + 0x30) = stick(l >> 24);     /* C-stick x */
    *(s16 *)(s + 0x32) = stick(l >> 16);     /* C-stick y */
    s[0x34] = (h & 0x00400000u) ? 180 : (u8)((la * 180) / 255);
    s[0x35] = (h & 0x00200000u) ? 180 : (u8)((ra * 180) / 255);
    s[0x28] = 2;                             /* extension: Classic Controller */
    s[0x29] = 0;                             /* no extension error */
    s[0x36] = 8;                             /* classic + accel + pointer data */
}

void gc_sample(u8 *k, u32 chan)
{
    u32 h, l;
    u8 cnt, idx;
    u32 i;

    if (chan || !gc_in(&h, &l))
        return;

    ST->dbg_h = h;
    ST->dbg_l = l;
    cnt = k[0x10F];
    idx = k[0x10E];
    if (cnt == 0) {
        /* no sample queued: no Wii Remote (dev type 0xFD), a bare one that
         * has not delivered one yet, or our own sample showing through */
        u8 dev = k[0x5C];
        u8 *s;
        if (!(dev == 0 || dev == 0xFD || ST->ours))
            return;
        if (idx >= 0x10)
            idx = 0;
        s = k + 0x110 + idx * 0x38;
        for (i = 0; i < 0x38; i += 4)
            *(u32 *)(s + i) = 0;
        fill_cc(s, h, l);
        k[0x10E] = idx + 1;
        k[0x10F] = 1;
        ST->ours = 1;
        return;
    }

    /* real samples queued: a bare Wii Remote gets the pad as its extension;
     * a real Nunchuk or Classic Controller is never touched */
    ST->ours = 0;
    if (cnt > 0x10)
        cnt = 0x10;
    for (i = 0; i < cnt; i++) {
        u8 *s = k + 0x110 + ((idx - cnt + i) & 0xF) * 0x38;
        if (s[0x28] == 0 || s[0x28] == 0xFD)
            fill_cc(s, h, l);
    }
}
#endif

#if defined(HOOK_PROBE)
/* WPADProbe(chan, &type): report a Classic Controller on channel 0 while a
 * pad is plugged in, unless the channel already has a real extension */
u32 gc_probe(u32 chan, u32 *type)
{
    u32 h, l;
    u8 *blk;
    u32 t;
    s32 status;

    if (chan || !gc_in(&h, &l))
        return 0;
    blk = *(u8 **)(WPAD_TBL + chan * 4);
    t = blk[2241];
    status = *(s32 *)(blk + 2236);
    if (status != -1 && (t == 1 || t == 2))
        return 0;
    if (type)
        *type = 2;
    return 1;
}
#endif
