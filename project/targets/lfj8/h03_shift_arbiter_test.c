#include <stdint.h>

/* All addresses refer to the independent M32R simulator's memory. */
#define RAM8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define RAM32(address) (*(volatile uint32_t *)(uintptr_t)(address))

extern void call_stock_tail(void);

static const uint32_t pwm_proposal[] = {0x804f6c, 0x804f78, 0x804f84, 0x804f94};
static const uint32_t pwm_command[] = {0x804f74, 0x804f80, 0x804f8c, 0x804f9c};
static const uint32_t pwm_normal[] = {0x3e000000, 0x3e800000, 0x3ec00000, 0x3f400000};

static int equals_command(unsigned bits, uint32_t pressure, unsigned pwm_zero_mask,
                          uint32_t pwm_fallback)
{
    for (unsigned i = 0; i < 4; ++i) {
        uint32_t expected = pwm_fallback != 0 ? pwm_fallback : pwm_normal[i];
        if ((pwm_zero_mask & (1u << i)) != 0) {
            expected = 0;
        }
        if (RAM32(pwm_command[i]) != expected || RAM32(pwm_proposal[i]) != pwm_normal[i]) {
            return 0;
        }
    }
    return RAM8(0x8063d7) == (bits & 1u) && RAM8(0x8063da) == ((bits >> 1) & 1u) &&
           RAM8(0x8063dd) == ((bits >> 2) & 1u) && RAM32(0x805094) == pressure &&
           RAM8(0x8063d5) == 1 && RAM8(0x8063d8) == 0 && RAM8(0x8063db) == 1 &&
           RAM32(0x80508c) == 0x3f000000;
}

int main(void)
{
    for (unsigned i = 0; i < 4; ++i) {
        RAM32(pwm_proposal[i]) = pwm_normal[i];
    }
    RAM8(0x8063d5) = 1;
    RAM8(0x8063d8) = 0;
    RAM8(0x8063db) = 1;
    RAM32(0x80508c) = 0x3f000000;
    call_stock_tail();
    if (!equals_command(5, 0x3f000000, 0, 0)) {
        return 1;
    }

    RAM8(0x80636e) = 1;
    RAM8(0x8063d6) = 0;
    RAM8(0x80636f) = 1;
    RAM8(0x8063d9) = 1;
    RAM8(0x80636d) = 1;
    RAM32(0x805090) = 0x3e800000;
    call_stock_tail();
    if (!equals_command(6, 0x3e800000, 0, 0)) {
        return 2;
    }

    RAM8(0x80639f) = 1;
    RAM8(0x8063b7) = 1;
    RAM8(0x806356) = 1;
    call_stock_tail();
    if (!equals_command(4, 0, 2, 0)) {
        return 3;
    }

    RAM8(0x80639f) = 0;
    RAM8(0x8063b7) = 0;
    RAM8(0x806356) = 0;
    RAM8(0x80636e) = 0;
    RAM8(0x80636f) = 0;
    RAM8(0x80636d) = 0;
    RAM8(0x8063f2) = 1;
    call_stock_tail();
    if (!equals_command(0, 0x3f000000, 15, 0)) {
        return 4;
    }

    RAM8(0x8063f2) = 0;
    RAM8(0x8065ba) = 1;
    RAM8(0x8065b7) = 1;
    call_stock_tail();
    if (!equals_command(0, 0, 15, 0)) {
        return 5;
    }

    RAM8(0x8065ba) = 0;
    call_stock_tail();
    if (!equals_command(7, 0x3f7effc1, 0, 0x42c73801)) {
        return 6;
    }

    return 0;
}
