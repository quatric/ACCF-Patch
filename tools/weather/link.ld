/* City Folk Deluxe (RUUE02) symbols used by the weather patch.
 * Layout is set by the build script through BASE (see build_patch.py). */

/* hook return addresses (site + 4) */
ret_type_now  = 0x801c9d28;
ret_type_next = 0x801c9da0;
ret_tv        = 0x801c9e18;
ret_link      = 0x80086e04;
ret_pad       = 0x804438e4;

/* functions the transplanted FCD code calls (donor address in the comment) */
accf_OSSetMEM1ArenaLo  = 0x8037be1c;   /* OSSetMEM1ArenaLo */
accf_OSRegisterVersion = 0x8037b234;   /* 0x8056a788 */
accf_VFMount           = 0x80434cb8;   /* 0x80463b88: the variant the game's own NWC24 code uses (drive "C") */
accf_VFUnmount         = 0x80434fd0;   /* 0x80463d14 */
accf_NANDOpen          = 0x803a8a2c;   /* 0x805a5b48 */
accf_NANDGetLength     = 0x803a8154;   /* 0x805a541c */
accf_NANDRead          = 0x803a7bb8;   /* 0x805a4ef4 */
accf_NANDClose         = 0x803a8cac;   /* 0x805a5dc8 */
/* MW runtime helpers: the block is byte-identical, donor address - 0x1bd7a8 */
accf_rt_8044e808 = 0x8044e808;  accf_rt_8044e830 = 0x8044e830;  accf_rt_8044e834 = 0x8044e834;
accf_rt_8044e838 = 0x8044e838;  accf_rt_8044e854 = 0x8044e854;  accf_rt_8044e87c = 0x8044e87c;
accf_rt_8044e880 = 0x8044e880;  accf_rt_8044e884 = 0x8044e884;  accf_rt_8044e98c = 0x8044e98c;

SECTIONS
{
    . = BASE;
    .text   : { *(.text*) }
    .rodata : { *(.rodata*) }
    .data   : { *(.data*) *(.sdata*) *(.bss*) *(.sbss*) *(COMMON) }
    . = ALIGN(32);
    weather_blob_end = .;
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
