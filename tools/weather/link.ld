/* Symbols for one revision of City Folk come from region.ld, written by build_patch.py. */
INCLUDE region.ld

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
