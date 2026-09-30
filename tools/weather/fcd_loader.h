/* Forecast Channel data (FCD) support code for City Folk (RUUE02 main.dol).
 * Replaces the parts of RVL_MWM-FCD that depend on libraries City Folk lacks:
 *   - the CX LZ streaming decompressor (absent from City Folk)
 *   - the VF file-size call (absent from City Folk's older VF library)
 * and provides the work-buffer allocation from the NWC24 heap.
 */
#ifndef FCD_LOADER_H
#define FCD_LOADER_H

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef int            s32;
typedef unsigned long long u64;

/* FCDGetWorkMemorySize() is 0x3909C. City Folk gets a ~1.25x buffer for
 * forecast.bin (0x32000) + short.bin (0x5000) + savedata and the read chunk. */
#define FCD_WORK_NEED   0x3909C
#define FCD_WORK_ALLOC  0x48000
#define FCD_CHUNK       0x2000

/* RVL_MWM-FCD context (s.dol 0x807d5128). Layout recovered from FCDInit. */
typedef struct FcdCtx {
    u8 *forecast;      /* +0x00 forecast.bin, 0x32000 bytes            */
    u32 forecastSize;  /* +0x04 decompressed size                      */
    u8 *shortBin;      /* +0x08 short.bin, 0x5000 bytes                */
    u32 shortSize;     /* +0x0c decompressed size                      */
    u8 *save;          /* +0x10 HAF0 savedata copy, 0x20 bytes         */
    u8 *tmp;           /* +0x14 read chunk, FCD_CHUNK bytes            */
    u8 *raw;           /* +0x18 buffer passed to FCDInit               */
} FcdCtx;

/* FCD_LoadLZ: drop-in for s.dol 0x805633d8.
 * Returns 0, -10 (VF open/read failed) or -11 (bad or truncated LZ data). */
s32 fcd_load_lz(const char *path, u32 maxSize, void *dst, u32 *outSize);

u32 fcd_crc32(const u8 *p, u32 len);

/* Allocate/free the FCD work buffer from the NWC24 heap. */
void *fcd_work_alloc(void);
void  fcd_work_free(void *p);

#endif
