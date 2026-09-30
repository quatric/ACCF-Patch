#!/usr/bin/env python3
"""Host round-trip test for fcd_loader.c (LZ10 + LZ11 streaming decoder).

Compiles the loader natively with a mock VF layer that clamps at EOF the way
City Folk's VFRead does, then decodes data produced by an independent encoder
in 0x2000-byte chunks, including streams that split tokens across chunks.
"""
import ctypes, os, random, subprocess, sys, tempfile, zlib

HERE = os.path.dirname(os.path.abspath(__file__))

SHIM = r'''
#include <stdlib.h>
#include <string.h>
#include "fcd_loader.h"
FcdCtx fcd_ctx;
const u32 fcd_crc_table[16] = { %CRCTAB% };
static const unsigned char *g_data; static unsigned g_len, g_pos;
void fcd_test_set(const unsigned char *d, unsigned n) { g_data = d; g_len = n; g_pos = 0;
    if (!fcd_ctx.tmp) fcd_ctx.tmp = malloc(FCD_CHUNK); }
void *vf_open(const char *p, const char *m) { (void)p; (void)m; return g_data ? (void *)&g_pos : 0; }
s32 vf_read(void *fd, void *buf, u32 len, u32 *got) {
    u32 n = g_len - g_pos; (void)fd;
    if (len > n) { memset(buf, 0, len); len = n; }
    memcpy(buf, g_data + g_pos, len); g_pos += len;
    if (got) *got = len;
    return 0;
}
s32 vf_close(void *fd) { (void)fd; return 0; }
'''

def enc(data, ext):
    out = bytearray([0x10 | ext]) + len(data).to_bytes(3, 'little')
    i, n = 0, len(data)
    minlen = 3 if not ext else 3
    while i < n:
        flags, blk, bit = 0, bytearray(), 0
        while bit < 8 and i < n:
            best_l, best_d = 0, 0
            maxl = 0x10110 if ext else 18
            for d in range(1, min(i, 0x1000) + 1):
                l = 0
                while i + l < n and l < maxl and data[i + l - d] == data[i + l]:
                    l += 1
                if l > best_l:
                    best_l, best_d = l, d
            if best_l >= 3:
                flags |= 0x80 >> bit
                d = best_d - 1
                if not ext:
                    blk += bytes([((best_l - 3) << 4) | (d >> 8), d & 0xFF])
                elif best_l <= 16:
                    blk += bytes([((best_l - 1) << 4) | (d >> 8), d & 0xFF])
                elif best_l <= 0x110:
                    l = best_l - 0x11
                    blk += bytes([l >> 4, ((l & 0xF) << 4) | (d >> 8), d & 0xFF])
                else:
                    l = best_l - 0x111
                    blk += bytes([0x10 | (l >> 12), (l >> 4) & 0xFF, ((l & 0xF) << 4) | (d >> 8), d & 0xFF])
                i += best_l
            else:
                blk.append(data[i]); i += 1
            bit += 1
        out.append(flags); out += blk
    return bytes(out)

def main():
    t = tempfile.mkdtemp()
    try:
        tab = []
        for i in range(16):
            c = i
            for _ in range(4):
                c = (c >> 1) ^ (0xEDB88320 if c & 1 else 0)
            tab.append("0x%08X" % c)
        open(f"{t}/shim.c", "w").write(SHIM.replace("%CRCTAB%", ", ".join(tab)))
        so = f"{t}/fcd.so"
        subprocess.check_call(["cc", "-O1", "-shared", "-fPIC", "-DFCD_HOST", "-I", HERE,
                               f"{t}/shim.c", f"{HERE}/fcd_loader.c", "-o", so])
        lib = ctypes.CDLL(so)
        lib.fcd_load_lz.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        lib.fcd_load_lz.restype = ctypes.c_int
        rnd = random.Random(1)
        cases = []
        cases.append(bytes(rnd.getrandbits(8) for _ in range(5000)))
        cases.append(b"ABCD" * 6000)
        cases.append(bytes(0x20000))
        blob = bytearray()
        for _ in range(3000):
            blob += rnd.choice([b"sunny", b"rain", b"\x00\x01\x02", bytes(rnd.getrandbits(8) for _ in range(rnd.randint(1, 9)))])
        cases.append(bytes(blob))
        bad = 0
        for ext in (0, 1):
            for k, data in enumerate(cases):
                comp = enc(data, ext)
                buf = (ctypes.c_ubyte * len(comp)).from_buffer_copy(comp)
                lib.fcd_test_set.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                lib.fcd_test_set(buf, len(comp))
                dst = (ctypes.c_ubyte * (len(data) + 16))()
                outsz = ctypes.c_uint(0)
                rc = lib.fcd_load_lz(b"@24:/3.bin", len(data) + 16, dst, ctypes.byref(outsz))
                ok = rc == 0 and outsz.value == len(data) and bytes(dst[:len(data)]) == data
                print(f"LZ1{ext} case {k}: {len(data):7d} -> {len(comp):7d} bytes  rc={rc}  {'OK' if ok else 'FAIL'}")
                bad += not ok
        # error paths
        lib.fcd_test_set.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        junk = (ctypes.c_ubyte * 8)(0x30, 1, 0, 0, 0, 0, 0, 0)
        lib.fcd_test_set(junk, 8)
        dst = (ctypes.c_ubyte * 8192)(); o = ctypes.c_uint(0)
        rc = lib.fcd_load_lz(b"x", 64, dst, ctypes.byref(o)); print("bad type rc =", rc, "OK" if rc == -11 else "FAIL"); bad += rc != -11
        comp = enc(b"hello world" * 100, 0)
        buf = (ctypes.c_ubyte * len(comp)).from_buffer_copy(comp)
        lib.fcd_test_set(buf, len(comp) // 2)
        rc = lib.fcd_load_lz(b"x", 4096, dst, ctypes.byref(o)); print("truncated rc =", rc, "OK" if rc == -11 else "FAIL"); bad += rc != -11
        lib.fcd_test_set(buf, len(comp))
        rc = lib.fcd_load_lz(b"x", 16, dst, ctypes.byref(o)); print("over maxSize rc =", rc, "OK" if rc == -11 else "FAIL"); bad += rc != -11
        # fcd_crc32 (donor 0x804417b0) must be standard CRC-32
        lib.fcd_crc32.argtypes = [ctypes.c_char_p, ctypes.c_uint]; lib.fcd_crc32.restype = ctypes.c_uint
        for data in (b"", b"a", b"123456789", bytes(range(256)) * 3, b"HAF0" + bytes(24)):
            ok = lib.fcd_crc32(data, len(data)) == zlib.crc32(data)
            bad += not ok
            print("crc32 %5d bytes: %s" % (len(data), "OK" if ok else "FAIL"))
        print("FAILED" if bad else "all passed")
        return 1 if bad else 0
    finally:
        subprocess.call(["rm", "-rf", t])

if __name__ == "__main__":
    sys.exit(main())
