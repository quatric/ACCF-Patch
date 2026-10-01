#include "fcd_loader.h"
#include "weather.h"

extern FcdCtx fcd_ctx;
extern const u32 fcd_crc_table[16];    /* donor's nibble table, emitted by fcdgen.py */

#ifdef FCD_HOST
/* host test shim provides these */
void *vf_open(const char *path, const char *mode);
s32   vf_read(void *fd, void *buf, u32 len, u32 *got);
s32   vf_close(void *fd);
#else
/* City Folk (RUUE02) VF library */
#define vf_open  ((void *(*)(const char *, const char *))0x80435188)
#define vf_read  ((s32 (*)(void *, void *, u32, u32 *))0x8043535c)
#define vf_close ((s32 (*)(void *))0x80435264)
#endif

typedef struct {
    u8 *dst, *base;
    s32 remain;
    u8  flags, bits, ext, need, ntok;
    u8  tok[4];
} Lz;

static s32 lz_ref(Lz *z)
{
    u32 len, disp;
    u8 b0 = z->tok[0], b1 = z->tok[1];

    if (z->ext && (b0 >> 4) == 0) {
        len  = (((b0 & 0xF) << 4) | (b1 >> 4)) + 0x11;
        disp = (((b1 & 0xF) << 8) | z->tok[2]) + 1;
    } else if (z->ext && (b0 >> 4) == 1) {
        len  = (((b0 & 0xF) << 12) | (b1 << 4) | (z->tok[2] >> 4)) + 0x111;
        disp = (((z->tok[2] & 0xF) << 8) | z->tok[3]) + 1;
    } else {
        len  = (b0 >> 4) + (z->ext ? 1 : 3);
        disp = (((b0 & 0xF) << 8) | b1) + 1;
    }
    if ((u32)(z->dst - z->base) < disp)
        return -1;
    if ((s32)len > z->remain)
        len = z->remain;
    z->remain -= len;
    while (len--) {
        *z->dst = z->dst[-(s32)disp];
        z->dst++;
    }
    return 0;
}

static s32 lz_feed(Lz *z, u8 c)
{
    if (z->ntok) {
        z->tok[z->ntok++] = c;
        if (z->ntok < z->need)
            return 0;
        z->ntok = 0;
        if (lz_ref(z))
            return -1;
        z->flags <<= 1;
        z->bits--;
        return 0;
    }
    if (z->bits == 0) {
        z->flags = c;
        z->bits = 8;
        return 0;
    }
    if (z->flags & 0x80) {
        u8 n = (u8)(c >> 4);
        z->tok[0] = c;
        z->ntok = 1;
        z->need = (z->ext && n == 0) ? 3 : (z->ext && n == 1) ? 4 : 2;
        return 0;
    }
    *z->dst++ = c;
    z->remain--;
    z->flags <<= 1;
    z->bits--;
    return 0;
}

s32 fcd_load_lz(const char *path, u32 maxSize, void *dst, u32 *outSize)
{
    Lz z;
    void *fd;
    u8 *tmp = fcd_ctx.tmp;
    s32 first = 1;
    s32 rc = 0;

    fd = vf_open(path, "r");
    if (!fd)
        return -10;

    for (;;) {
        u32 got = 0, i = 0;

        if (vf_read(fd, tmp, FCD_CHUNK, &got)) {
            vf_close(fd);
            return -10;
        }
        if (got == 0)
            break;

        if (first) {
            u32 size;
            if (got < 4 || (tmp[0] & 0xF0) != 0x10 || (tmp[0] & 0x0F) > 1) {
                vf_close(fd);
                return -11;
            }
            size = tmp[1] | (tmp[2] << 8) | (tmp[3] << 16);
            if (size > maxSize) {
                vf_close(fd);
                return -11;
            }
            *outSize = size;
            z.dst = z.base = (u8 *)dst;
            z.remain = (s32)size;
            z.flags = z.bits = z.need = z.ntok = 0;
            z.ext = tmp[0] & 0x0F;
            first = 0;
            i = 4;
        }
        for (; i < got && z.remain > 0; i++) {
            if (lz_feed(&z, tmp[i])) {
                vf_close(fd);
                return -11;
            }
        }
        if (z.remain <= 0 || got < FCD_CHUNK)
            break;
    }

    /* mirrors s.dol 0x805633d8: a non-zero close result skips validation */
    if (vf_close(fd))
        return 0;
    if (first || z.remain > 0)
        rc = -11;
    return rc;
}

/* donor 0x804417b0: CRC-32 (init 0xFFFFFFFF, final NOT), two table steps per byte */
u32 fcd_crc32(const u8 *p, u32 len)
{
    u32 crc = 0xFFFFFFFFu;

    while (len--) {
        crc ^= *p++;
        crc = (crc >> 4) ^ fcd_crc_table[crc & 15];
        crc = (crc >> 4) ^ fcd_crc_table[crc & 15];
    }
    return ~crc;
}

#ifndef FCD_HOST
register char *fcd_sda asm("r13");

/* current scene kind: u8 at SDA -0x6384(r13) (0x80162548). The game's own City test (0x801c9578, which picks the
 * City weather variant 0x801c9d9c over the town one 0x801c9d24) is: byte table at 0x80479F10 (0x44 entries,
 * 0x8016286c) nonzero for the kind, or kind 0x3d. */
u32 weather_platform_scene_flags(void)
{
    u32 kind = *(u8 *)(fcd_sda - 0x6384);
    if (kind == 0x3D || (kind < 0x44 && ((const u8 *)0x80479F10)[kind]))
        return WEATHER_SCENE_CITY;
    return 0;
}

/* NWC24 heap: SDA -0x3284(r13); EGG heap vtable +0x14 alloc(size, align), +0x18 free(ptr) */
typedef struct { void **vtbl; } EggHeap;

#define NWC24_HEAP (*(EggHeap **)(fcd_sda - 0x3284))

void *fcd_heap_alloc(u32 size)
{
    EggHeap *h = NWC24_HEAP;
    if (!h)
        return 0;
    return ((void *(*)(EggHeap *, u32, s32))h->vtbl[0x14 / 4])(h, size, 0x20);
}

void fcd_heap_free(void *p)
{
    EggHeap *h = NWC24_HEAP;
    if (h && p)
        ((void (*)(EggHeap *, void *))h->vtbl[0x18 / 4])(h, p);
}

void *fcd_work_alloc(void)
{
    return fcd_heap_alloc(FCD_WORK_ALLOC);
}

void fcd_work_free(void *p)
{
    fcd_heap_free(p);
}
#endif
