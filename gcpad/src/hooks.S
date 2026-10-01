/* Entry stubs: save every volatile register, call the C hook, restore, then
 * run the instruction the Gecko/DOL hook replaced.  The last word is the slot
 * the hook installer turns into the branch back. */
    .macro SAVE
    stwu    1, -0x70(1)
    stw     0, 0x0c(1)
    stw     3, 0x10(1)
    stw     4, 0x14(1)
    stw     5, 0x18(1)
    stw     6, 0x1c(1)
    stw     7, 0x20(1)
    stw     8, 0x24(1)
    stw     9, 0x28(1)
    stw     10, 0x2c(1)
    stw     11, 0x30(1)
    stw     12, 0x34(1)
    mflr    0
    stw     0, 0x38(1)
    mfcr    0
    stw     0, 0x3c(1)
    mfctr   0
    stw     0, 0x40(1)
    mfxer   0
    stw     0, 0x44(1)
    .endm

    .macro RESTORE_ALL          /* everything but r0 */
    lwz     0, 0x44(1)
    mtxer   0
    lwz     0, 0x40(1)
    mtctr   0
    lwz     0, 0x3c(1)
    mtcr    0
    lwz     0, 0x38(1)
    mtlr    0
    lwz     3, 0x10(1)
    lwz     4, 0x14(1)
    lwz     5, 0x18(1)
    lwz     6, 0x1c(1)
    lwz     7, 0x20(1)
    lwz     8, 0x24(1)
    lwz     9, 0x28(1)
    lwz     10, 0x2c(1)
    lwz     11, 0x30(1)
    lwz     12, 0x34(1)
    .endm

    .section .gcstart, "ax"
    b       _entry

    .section .gctail, "ax"
    .globl _entry
_entry:
#if defined(HOOK_POLL)
    # KPADiRead(chan, buf, n): r3 = channel
    SAVE
    bl      gc_poll
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, 0x70
    stwu    1, -192(1)          # original instruction
#elif defined(HOOK_SAMPLE)
    # KPADiRead before the sample-count check: r31 = KPAD base, r27 = channel
    SAVE
    mr      3, 31
    mr      4, 27
    bl      gc_sample
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, 0x70
    lbz     0, 0x10f(31)        # original instruction
#elif defined(HOOK_PROBE)
    # WPADProbe(chan, &type)
    SAVE
    bl      gc_probe
    stw     3, 0x08(1)
    RESTORE_ALL
    lwz     0, 0x08(1)
    addi    1, 1, 0x70
    cmpwi   0, 0
    beq     1f
    li      3, 0
    blr
1:  stwu    1, -16(1)           # original instruction
#endif
    nop
