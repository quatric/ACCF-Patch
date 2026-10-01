SECTIONS {
  . = 0;
  .text : { *(.gcstart) *(.text .text.*) *(.gctail) }
  /DISCARD/ : { *(.comment) *(.eh_frame) *(.note*) *(.sdata*) *(.sbss*) }
}
