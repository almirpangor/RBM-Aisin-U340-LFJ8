"""Emit the Bosch 0x1AE receive timestamp checks for the pinned ST10 image."""

T4, T4CON, T4IC, T4_HIGH = 0xFE44, 0xFF44, 0xFF64, 0xE176
CAN_CONTROL, CAN_STATUS, CAN_NEWDAT = 0xEF00, 0xEF02, 0xEF90
BOUND_LOW, BOUND_HIGH = 0xE7F4, 0xE7FE
BUSY_MASK = 0x003F
WAITING, HAVE_BOUND = 0x0040, 0x0080


def clear_speed(a, age, speed):
    a.zero(age)
    a.extp(0x3C)
    a.zero(speed)


def read_clock(a, invalid):
    # R5:R4 = T4, without modifying the timer or acknowledging its IRQ.
    # Reject an overflow in progress, or a change of the software high word.
    a.ld(6, T4CON)
    a.andi(6, 0x01FF)
    a.cmp(6, 0x46)
    a.branch(3, invalid)
    a.ld(5, T4_HIGH)
    a.ld(4, T4)
    a.ld(6, T4IC)
    a.andi(6, 0x80)
    a.branch(3, invalid)
    a.ld(6, T4_HIGH)
    a.cmpreg(6, 5)
    a.branch(3, invalid)


def poll(a, state, age, speed, object_number):
    read_clock(a, "rx_poll_clock_invalid")
    a.imm(7, 1)
    a.branch(0, "rx_poll")
    a.label("rx_poll_clock_invalid")
    a.zero(state)
    clear_speed(a, age, speed)
    a.imm(7, 0)
    a.label("rx_poll")
    a.ld(6, CAN_NEWDAT)
    a.andi(6, 1 << (object_number - 1))
    a.branch(3, "rx_start_if1")
    a.cmp(7, 0)
    a.branch(2, "free")
    a.st(BOUND_LOW, 4)
    a.st(BOUND_HIGH, 5)
    a.set(state, HAVE_BOUND)
    a.branch(0, "free")
    a.label("rx_start_if1")
    a.ld(4, state)
    a.ori(4, WAITING)
    a.st(state, 4)


def check_bound(a):
    # R8 holds the receive state taken before releasing this IF1 transfer.
    a.andi(8, HAVE_BOUND)
    a.branch(2, "invalid_speed")
    for register, mask in ((CAN_CONTROL, 1), (CAN_STATUS, 0x80)):
        a.ld(6, register)
        a.andi(6, mask)
        a.branch(3, "invalid_speed")
    read_clock(a, "invalid_speed")
    a.ld(6, BOUND_HIGH)
    a.rr(7, 5)
    a.sub(7, 6)
    a.ld(6, BOUND_LOW)
    a.cmpreg(4, 6)
    a.branch(9, "rx_age_high")
    a.subi(7, 1)
    a.label("rx_age_high")
    a.andi(7, 0x8000)
    a.branch(3, "invalid_speed")
    a.label("rx_bound_checked")
