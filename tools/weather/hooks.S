/* Hook trampolines for the City Folk (RUUE02) weather patch.
 *
 * Each site in main.dol gets its first (or one) instruction replaced by `b <tramp>`.
 * The trampoline runs the C glue, then either returns early or executes the
 * displaced instruction and branches back to site+4.
 */

/* Return addresses (site + 4) are external symbols supplied by the linker, see link.ld:
 *   ret_type_now  = 0x801c9d28   (site 0x801c9d24: stwu r1,-0x10(r1))
 *   ret_type_next = 0x801c9da0   (site 0x801c9d9c: stwu r1,-0x10(r1))
 *   ret_tv        = 0x801c9e18   (site 0x801c9e14: stwu r1,-0x10(r1))
 *   ret_link      = 0x80086e04   (site 0x80086e00: lwz r4,-0x3418(r13))
 *   ret_pad       = 0x804438e4   (site 0x804438e0: stw r3,0x854(r31), right after KPADRead)
 */
    .extern ret_type_now, ret_type_next, ret_tv, ret_link, ret_pad
    .extern accf_OSSetMEM1ArenaLo, weather_blob_end
    .extern weather_type_for_date, weather_tv_for_date, weather_on_module_link, weather_hook_pad

    .text

/* int type_hook(const CalTime *date): r3 = date. Returns the weather type, or falls
 * through to the original function when the glue returns < 0. */
    .macro DATE_HOOK name, glue, ret
    .globl \name
\name:
    stwu    r1,-0x20(r1)
    mflr    r0
    stw     r0,0x24(r1)
    stw     r3,0x14(r1)
    bl      \glue
    cmpwi   r3,0
    blt     1f
    lwz     r0,0x24(r1)             /* return our value */
    mtlr    r0
    addi    r1,r1,0x20
    blr
1:  lwz     r3,0x14(r1)             /* restore the date and run the original */
    lwz     r0,0x24(r1)
    mtlr    r0
    addi    r1,r1,0x20
    stwu    r1,-0x10(r1)            /* displaced instruction */
    b       \ret
    .endm

    DATE_HOOK tramp_type_now,  weather_type_for_date, ret_type_now
    DATE_HOOK tramp_type_next, weather_type_for_date, ret_type_next
    DATE_HOOK tramp_tv,        weather_tv_for_date,   ret_tv

/* module link request: r3 = module id */
    .globl tramp_link
tramp_link:
    stwu    r1,-0x20(r1)
    mflr    r0
    stw     r0,0x24(r1)
    stw     r3,0x14(r1)
    bl      weather_on_module_link
    lwz     r3,0x14(r1)
    lwz     r0,0x24(r1)
    mtlr    r0
    addi    r1,r1,0x20
    lwz     r4,-0x3418(13)          /* displaced instruction */
    b       ret_link

/* after KPADRead: r31 = controller, r3 = sample count */
    .globl tramp_pad
tramp_pad:
    stw     r3,0x854(r31)           /* displaced instruction */
    stwu    r1,-0x20(r1)
    mflr    r0
    stw     r0,0x24(r1)
    mr      r3,r31
    bl      weather_hook_pad
    lwz     r0,0x24(r1)
    mtlr    r0
    addi    r1,r1,0x20
    b       ret_pad

/* OSInit: `bl OSSetMEM1ArenaLo` (0x8037ab10) is redirected here. The arena must start
 * above the blob (0x80764000..weather_blob_end), whichever value OSInit computed:
 * arenaLo = max(r3, weather_blob_end), then tail-call the real setter. */
    .globl tramp_arena
tramp_arena:
    lis     r0,weather_blob_end@h
    ori     r0,r0,weather_blob_end@l     /* (addi would read r0 as zero) */
    cmplw   r3,r0
    bge     1f
    mr      r3,r0
1:  b       accf_OSSetMEM1ArenaLo
