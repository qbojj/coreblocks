_start:
    li x5, 0
    li x4, 0

    la x1, trap_handler
    csrw mtvec, x1

    # PMP Entry 0: [0, 0x100), TOR, RWX
    # PMP Entry 1: [0x100, 0x200), TOR, RX, locked
    li x1, 0x100 >> 2
    csrw pmpaddr0, x1
    li x1, 0x200 >> 2
    csrw pmpaddr1, x1

    li x1, 0b00001111 | (0b10001101 << 8)
    csrw pmpcfg0, x1

    # try to write to pmp addr 0 and 1, as those should be read-only
    # as pmp1cfg is locked and is TOR
    li x3, 0x12345
    csrw pmpaddr0, x3
    csrw pmpaddr1, x3

    csrr x2, pmpaddr0
    beq x2, x3, fail
    csrr x2, pmpaddr1
    beq x2, x3, fail

    # the first configuration entry should still be writeable, but the second should be read-only
    csrw pmpcfg0, x0
    csrr x2, pmpcfg0
    li x3, (0b10001101 << 8)
    bne x2, x3, fail

    # reconfigure the pmp
    csrw pmpcfg0, x1

    la x1, user_code
    csrw mepc, x1
    mret              # Go to user_code in user mode

user_code:
    sw x0, 0(x0)      # Store inside PMP, should succeed

    li x2, 0x100
    lw x1, 0(x2)      # Load inside locked PMP, should succeed

    li x4, 1
    sw x0, 0(x2)      # Store inside locked PMP, should fail
    j fail

trap_handler:
    li x5, 50
    beqz x4, fail

    li x5, 60
    csrr x1, mcause
    li x2, 7
    bne x1, x2, fail  # Check if it is a store fault

    li x5, 99
    li x3, 1
    beq x3, x4, mmode_check
    li x3, 2
    beq x3, x4, pass
    j fail

mmode_check:
    li x4, 0
    li x5, 100

    li x2, 0x100
    lw x1, 0(x2)      # Load inside locked PMP, should succeed

    li x5, 110

    li x4, 2
    sw x0, 0(x2)      # Store inside locked PMP, should fail
    li x5, 199
    j fail

fail:
    j .

pass:
    li x5, 1
    j .

.section .data
.zero 0x200
