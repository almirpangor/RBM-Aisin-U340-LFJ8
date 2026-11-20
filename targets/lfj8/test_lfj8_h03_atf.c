#include "lfj8_bridge.h"
#include "lfj8_h03_atf.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint32_t volts;
    uint32_t temperature;
    unsigned reads;
    uint16_t adc;
    uint8_t fault;
    uint8_t locked;
} AtfRegisters;

static uint32_t lock_registers(void *context)
{
    AtfRegisters *registers = context;
    assert(!registers->locked);
    registers->locked = 1;
    return UINT32_C(0xA5000000);
}

static void unlock_registers(void *context, uint32_t saved)
{
    AtfRegisters *registers = context;
    assert(registers->locked && saved == UINT32_C(0xA5000000));
    registers->locked = 0;
}

static uint8_t read_byte(void *context, uint32_t address)
{
    AtfRegisters *registers = context;
    assert(registers->locked && address == UINT32_C(0x8063E7));
    ++registers->reads;
    return registers->fault;
}

static uint16_t read_adc(void *context, uint32_t address)
{
    AtfRegisters *registers = context;
    assert(registers->locked && address == UINT32_C(0x804BC4));
    ++registers->reads;
    return registers->adc;
}

static uint32_t read_word(void *context, uint32_t address)
{
    AtfRegisters *registers = context;
    assert(registers->locked);
    ++registers->reads;
    if (address == UINT32_C(0x804F04)) {
        return registers->volts;
    }
    assert(address == UINT32_C(0x805028));
    return registers->temperature;
}

static Lfj8RegisterIo io_for(AtfRegisters *registers)
{
    return (Lfj8RegisterIo){
        .context = registers, .read8 = read_byte, .read16 = read_adc, .read32 = read_word,
        .enter = lock_registers, .leave = unlock_registers,
    };
}

static void record_measurement(Lfj8H03Atf *state, const Lfj8RegisterIo *io,
                               uint32_t site, uint32_t acquired, uint32_t published)
{
    assert(lfj8_h03_atf_after_adc_store(state, io, acquired));
    assert(lfj8_h03_atf_after_store(state, io, site, &acquired, published));
}

static void check_publication_and_fault(void)
{
    AtfRegisters registers = {
        .adc = 315, .volts = UINT32_C(0x3FC4E000), .temperature = UINT32_C(0x42700000),
    };
    const Lfj8RegisterIo io = io_for(&registers);
    Lfj8H03Atf state;
    Lfj8H03AtfSample sample;
    uint8_t can_payload[8];
    lfj8_h03_atf_init(&state);
    assert(!lfj8_h03_atf_snapshot(&state, &io, 14, 10, &sample));
    assert(sample.atf_c == 0 && sample.toyota_gp_m7184 == 0 && registers.reads == 0);
    assert(!lfj8_h03_atf_after_store(&state, &io, 0x03B1B0, NULL, 15)); /* No OEM write. */

    assert(lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, NULL, 15));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 16, 10, &sample)); /* No acquisition. */

    const uint32_t first_adc = 17;
    record_measurement(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, first_adc, 19);
    const int valid = lfj8_h03_atf_snapshot(&state, &io, 20, 10, &sample);
    assert(valid && sample.acquired_us == first_adc && sample.atf_c == 60);
    assert(sample.toyota_gp_m7184 == 25600);
    lfj8_pack_300(can_payload, 0, 0, 0, sample.atf_c, (uint8_t)valid);
    assert(can_payload[3] == 100);

    registers.temperature = UINT32_C(0x43020000); /* 130 C. */
    assert(!lfj8_h03_atf_after_adc_store(&state, &io, first_adc));
    assert(!lfj8_h03_atf_after_adc_store(&state, &io, 16));
    assert(!lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_FILTERED_STORE, &first_adc, 19));
    assert(!lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_FILTERED_STORE, &first_adc, 18));
    assert(lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_FILTERED_STORE, &first_adc, 26));
    assert(lfj8_h03_atf_snapshot(&state, &io, 26, 10, &sample) && sample.atf_c == 60);
    assert(!lfj8_h03_atf_snapshot(&state, &io, 27, 10, &sample)); /* Repeat does not renew age. */
    assert(!lfj8_h03_atf_snapshot(&state, &io, 28, 30, &sample)); /* Expiry latches. */

    record_measurement(&state, &io, LFJ8_H03_ATF_FILTERED_STORE, 29, 30);
    assert(lfj8_h03_atf_snapshot(&state, &io, 30, 10, &sample) && sample.atf_c == 130);
    assert(sample.toyota_gp_m7184 == 43520);
    lfj8_pack_300(can_payload, 0, 0, 0, sample.atf_c, 1);
    assert(can_payload[3] == 144);

    registers.fault = 1;
    const int fault_valid = lfj8_h03_atf_snapshot(&state, &io, 31, 10, &sample);
    assert(!fault_valid && sample.atf_c == 0 && sample.toyota_gp_m7184 == 0);
    lfj8_pack_300(can_payload, 0, 0, 0, sample.atf_c, (uint8_t)fault_valid);
    assert(can_payload[3] == 255);
    registers.fault = 0;
    assert(!lfj8_h03_atf_snapshot(&state, &io, 32, 10, &sample));
    record_measurement(&state, &io, LFJ8_H03_ATF_FILTERED_STORE, 33, 34);
    assert(lfj8_h03_atf_snapshot(&state, &io, 34, 10, &sample));
    assert(lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_FAULT_STORE, NULL, 35));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 35, 10, &sample));
    assert(!registers.locked);
}

static void check_causal_binding(void)
{
    AtfRegisters registers = {
        .adc = 410, .volts = UINT32_C(0x40002000), .temperature = UINT32_C(0x41200000),
    };
    const Lfj8RegisterIo io = io_for(&registers);
    Lfj8H03Atf state;
    Lfj8H03AtfSample sample;
    lfj8_h03_atf_init(&state);
    uint32_t acquired = 0;
    assert(!lfj8_h03_atf_capture_source(&state, registers.adc, &acquired));
    assert(lfj8_h03_atf_after_adc_store(&state, &io, 20));
    uint32_t saved = io.enter(io.context);
    assert(!lfj8_h03_atf_capture_source(&state, registers.adc + 1u, &acquired));
    assert(lfj8_h03_atf_capture_source(&state, read_adc(io.context, 0x804BC4), &acquired));
    io.leave(io.context, saved);
    assert(acquired == 20);
    assert(lfj8_h03_atf_after_adc_store(&state, &io, 21));
    assert(lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, &acquired, 22));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 22, 10, &sample)); /* Same bits, wrong generation. */
    saved = io.enter(io.context);
    assert(lfj8_h03_atf_capture_source(&state, read_adc(io.context, 0x804BC4), &acquired));
    io.leave(io.context, saved);
    assert(acquired == 21);
    assert(lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, &acquired, 23));
    assert(lfj8_h03_atf_snapshot(&state, &io, 23, 10, &sample) && sample.acquired_us == 21);
    assert(lfj8_h03_atf_after_adc_store(&state, &io, 24));
    /* The ROM-voltage branch can publish the same bits without reading AN1. */
    assert(lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, NULL, 25));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 25, 10, &sample));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 35, 10, &sample)); /* Both generations stale. */
    acquired = 24;
    assert(lfj8_h03_atf_after_store(&state, &io, LFJ8_H03_ATF_FILTERED_STORE, &acquired, 36));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 36, 10, &sample));
    assert(!registers.locked);
}

static void check_input_boundaries(void)
{
    static const struct {
        uint32_t volts;
        uint32_t temperature;
        uint16_t adc;
        uint16_t expected_gp;
        int16_t expected_c;
        uint8_t valid;
    } cases[] = {
        {0x3D700000u, 0x43160000u, 12, 0, 0, 0},
        {0x3D700043u, 0x43160000u, 13, 0, 0, 0}, /* Voltage mismatches ADC. */
        {0x3D820000u, 0x43160000u, 13, 48640, 150, 1},
        {0x40956000u, 0xC2200000u, 956, 0, -40, 1},
        {0x40956001u, 0xC2200000u, 956, 0, 0, 0}, /* Voltage mismatches ADC. */
        {0x40958800u, 0xC2200000u, 957, 0, 0, 0},
        {0x7FC00000u, 0x42380000u, 410, 0, 0, 0},
        {0x40002000u, 0x7F800000u, 410, 0, 0, 0},
        {0x40002000u, 0xFFC00000u, 410, 0, 0, 0},
        {0x40002000u, 0x43160001u, 410, 0, 0, 0},
        {0x40002000u, 0xC2200001u, 410, 0, 0, 0},
        {0x40002000u, 0xC2480000u, 410, 0, 0, 0}, /* OEM -50 C fallback. */
        {0x40002000u, 0x419E0000u, 410, 15296, 19, 1}, /* 19.75 C. */
        {0x40002000u, 0xC19E0000u, 410, 5184, -19, 1}, /* -19.75 C. */
        {0x40002000u, 0x3B800000u, 410, 10241, 0, 1}, /* 1/256 C. */
        {0x40002000u, 0x3B7FFFFFu, 410, 10240, 0, 1}, /* Just below 1/256 C. */
        {0x40002000u, 0xBB800000u, 410, 10239, 0, 1}, /* -1/256 C. */
        {0x40002000u, 0x80000000u, 410, 10240, 0, 1}, /* Negative zero. */
    };
    AtfRegisters registers = {0};
    const Lfj8RegisterIo io = io_for(&registers);
    Lfj8H03Atf state;
    Lfj8H03AtfSample sample;
    lfj8_h03_atf_init(&state);

    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        registers.volts = cases[i].volts;
        registers.temperature = cases[i].temperature;
        registers.adc = cases[i].adc;
        record_measurement(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, i, i);
        assert(lfj8_h03_atf_snapshot(&state, &io, i, 1, &sample) == cases[i].valid);
        assert(sample.atf_c == cases[i].expected_c);
        assert(sample.toyota_gp_m7184 == cases[i].expected_gp);
    }
    assert(!registers.locked);
}

static void check_all_adc_codes(void)
{
    AtfRegisters registers = {.temperature = UINT32_C(0x41200000)};
    const Lfj8RegisterIo io = io_for(&registers);
    Lfj8H03Atf state;
    Lfj8H03AtfSample sample;
    lfj8_h03_atf_init(&state);
    assert(sizeof(float) == sizeof registers.volts);
    for (unsigned adc = 0; adc < 1024u; ++adc) {
        const float volts = (float)adc * (5.0f / 1024.0f);
        memcpy(&registers.volts, &volts, sizeof registers.volts);
        registers.adc = (uint16_t)adc;
        record_measurement(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, adc, adc);
        const int expected = adc >= 13u && adc <= 956u;
        assert(lfj8_h03_atf_snapshot(&state, &io, adc, 1, &sample) == expected);
    }
}
static void check_wrapping_clock(void)
{
    AtfRegisters registers = {
        .adc = 410, .volts = UINT32_C(0x40002000), .temperature = UINT32_C(0x41200000),
    };
    const Lfj8RegisterIo io = io_for(&registers);
    Lfj8H03Atf state;
    Lfj8H03AtfSample sample;
    lfj8_h03_atf_init(&state);
    record_measurement(&state, &io, LFJ8_H03_ATF_DIRECT_STORE, UINT32_MAX - 3u, 2);
    assert(lfj8_h03_atf_snapshot(&state, &io, 4, 10, &sample));
    record_measurement(&state, &io, LFJ8_H03_ATF_FILTERED_STORE, 5, 6);
    assert(!lfj8_h03_atf_after_adc_store(&state, &io, UINT32_MAX));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 6, 0, &sample));
    assert(!lfj8_h03_atf_snapshot(&state, &io, 6, UINT32_C(0x80000000), &sample));
    assert(lfj8_h03_atf_snapshot(&state, &io, 7, 10, &sample) && sample.acquired_us == 5);
    assert(!lfj8_h03_atf_snapshot(&state, &io, 15, 10, &sample));
    assert(!registers.locked);
}

int main(void)
{
    check_publication_and_fault();
    check_causal_binding();
    check_input_boundaries();
    check_all_adc_codes();
    check_wrapping_clock();
    puts("H03 ATF: acquisition pairing, electrical bounds, freshness, fixed point and Chery 0x300 passed.");
    return 0;
}
