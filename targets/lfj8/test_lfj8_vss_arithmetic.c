#include "lfj8_bridge.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void check_uaz_axle_profile(void)
{
    const Lfj8Chery1ae status = {
        .byte1 = 0x32, .byte4 = 0x35, .byte3_high = 3,
        .flag_fd18_4 = 1, .flag_fd10_7 = 1,
    };
    const uint8_t expected[] = {0x08, 0x32, 0x13, 0x39, 0x35, 0, 0x17, 0x9c};
    uint8_t payload[8];
    /* Fixture clock 1 MHz, S51 at 100 Hz, Z25 and UAZ 37/8. */
    for (uint8_t pulses = 1; pulses <= 4; pulses <<= 1) {
        const uint16_t raw = lfj8_vss_raw_1ae(10000u * pulses, pulses, 1000000u,
                                              3530000u, 8u, 37u, LFJ8_VSS_VALID);
        assert(raw == 6044u);
        assert(lfj8_pack_1ae(payload, &status, raw) == 1u);
        assert(memcmp(payload, expected, sizeof expected) == 0);
    }
}
int main(void)
{
    check_uaz_axle_profile();
    static const struct {
        uint32_t ticks;
        uint32_t tick_hz;
        uint32_t wheel_um;
        uint16_t wheel_num;
        uint16_t wheel_den;
        uint8_t pulses;
        uint16_t expected;
    } cases[] = {
        /* floor(99 * pulses * tick_hz * wheel_um * wheel_num /
         *       (1250000 * ticks * wheel_den)), subject to the wire limit. */
        {105600, 1000000, 2000000, 1, 1, 4, 6000},
        {105600, 1000000, 2000000, UINT16_MAX, UINT16_MAX, 4, 6000},
        {26401, 1000000, 2000000, 1, 1, 1, 5999},
        {UINT32_MAX, UINT32_MAX, 2000000, UINT16_MAX, UINT16_MAX - 1, 1, 158},
        {UINT32_MAX, UINT32_MAX, 50346151, 50000, 61033, 4, 13066},
        {UINT32_MAX, UINT32_MAX, 646464646, UINT16_MAX, UINT16_MAX, 1, 51199},
        {UINT32_MAX, UINT32_MAX, 646464647, UINT16_MAX, UINT16_MAX, 1, LFJ8_SPEED_UNAVAILABLE},
        {UINT32_MAX, 1000000, 2000000, 1, UINT16_MAX, 1, 0},
        {UINT32_MAX, UINT32_MAX, UINT32_MAX, 15, UINT16_MAX, 4, 311},
        {1, UINT32_MAX, UINT32_MAX, UINT16_MAX, 1, 4, LFJ8_SPEED_UNAVAILABLE},
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        const uint16_t speed = lfj8_vss_raw_1ae(cases[i].ticks, cases[i].pulses,
            cases[i].tick_hz, cases[i].wheel_um, cases[i].wheel_num, cases[i].wheel_den,
            LFJ8_VSS_VALID);
        assert(speed == cases[i].expected);
    }

    assert(lfj8_vss_raw_1ae(0, 0, 1000000, 2000000, 1, 1, LFJ8_VSS_STOPPED) == 0);
    assert(lfj8_vss_raw_1ae(0, 1, 1000000, 2000000, 1, 1, LFJ8_VSS_VALID) == LFJ8_SPEED_UNAVAILABLE);
    assert(lfj8_vss_raw_1ae(10, 1, 1000000, 2000000, 1, 0, LFJ8_VSS_VALID) == LFJ8_SPEED_UNAVAILABLE);
    assert(lfj8_vss_raw_1ae(10, 3, 1000000, 2000000, 1, 1, LFJ8_VSS_VALID) == LFJ8_SPEED_UNAVAILABLE);
    assert(lfj8_vss_raw_1ae(10, 1, 1000000, 2000000, 1, 1, LFJ8_VSS_UNAVAILABLE) == LFJ8_SPEED_UNAVAILABLE);
    puts("VSS arithmetic: exact wide products, 0x1AE boundary and availability PASS");
    return 0;
}
