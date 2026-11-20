#include "lfj8_h03_button_capture.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

static const Lfj8H03ButtonMap map = {{
    {LFJ8_H03_BUTTON_P1, 8, 1}, {LFJ8_H03_BUTTON_P1, 64, 0},
    {LFJ8_H03_BUTTON_P1, 32, 0}, {LFJ8_H03_BUTTON_AUX, 1, 1},
}};

typedef struct {
    uint8_t p1;
    unsigned reads;
} Port;

static uint8_t read_port(void *context, uint32_t address)
{
    Port *port = context;
    assert(address == 0x800701u);
    ++port->reads;
    return port->p1;
}

static void test_decode(void)
{
    Port port = {0};
    const Lfj8RegisterIo io = {.context = &port, .read8 = read_port};
    Lfj8H03ButtonSample sample = {UINT32_MAX, 7, 0, 3};
    Lfj8ButtonReading reading;
    for (unsigned raw = 0; raw < 256; ++raw) {
        port.p1 = (uint8_t)raw;
        for (unsigned aux = 0; aux < 2; ++aux) {
            sample.auxiliary = (uint8_t)aux;
            assert(lfj8_h03_button_capture_locked(&io, &map, &sample, 7, &reading));
            const uint8_t expected = ((raw & 8) ? 0 : RBM_U340E_BUTTON_MODE) |
                ((raw & 64) ? RBM_U340E_BUTTON_UP : 0) |
                ((raw & 32) ? RBM_U340E_BUTTON_DOWN : 0) |
                (aux ? 0 : RBM_U340E_BUTTON_OVERDRIVE);
            assert(reading.valid == 1 && reading.captured_us == UINT32_MAX);
            assert(reading.pressed == expected);
        }
    }
    assert(port.reads == 512);
}

static void test_missing_and_bad_mapping(void)
{
    Port port = {0};
    const Lfj8RegisterIo io = {.context = &port, .read8 = read_port};
    Lfj8H03ButtonSample sample = {0, 7, 0, 3};
    Lfj8ButtonReading reading = {4, UINT8_MAX, 1};
    assert(!lfj8_h03_button_capture_locked(&io, &map, &sample, 8, &reading));
    assert(!reading.valid && !reading.pressed && !reading.captured_us);
    assert(!lfj8_h03_button_capture_locked(NULL, &map, &sample, 7, &reading));
    sample.available_banks = 1;
    assert(!lfj8_h03_button_capture_locked(&io, &map, &sample, 7, &reading));
    sample.available_banks = 2;
    assert(!lfj8_h03_button_capture_locked(&io, &map, &sample, 7, &reading));
    sample.available_banks = 3;
    const Lfj8H03ButtonPin bad[] = {{0, 0, 0}, {0, 3, 0}, {0, 64, 0}, {2, 1, 0}, {0, 8, 2}};
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; ++i) {
        Lfj8H03ButtonMap broken = map;
        broken.pins[0] = bad[i];
        assert(!lfj8_h03_button_capture_locked(&io, &broken, &sample, 7, &reading));
        assert(!reading.valid && !reading.pressed);
    }
    assert(port.reads == 0);

    Lfj8H03ButtonMap optional = map;
    optional.pins[3] = (Lfj8H03ButtonPin){0};
    sample.available_banks = 1;
    port.p1 = 8;
    assert(lfj8_h03_button_capture_locked(&io, &optional, &sample, 7, &reading));
    assert(port.reads == 1 && reading.valid && !reading.pressed);

    const Lfj8H03ButtonMap auxiliary_only = {{
        {1, 1, 0}, {1, 2, 0}, {1, 4, 0}, {1, 8, 0},
    }};
    sample.available_banks = 2;
    sample.auxiliary = 10;
    assert(lfj8_h03_button_capture_locked(NULL, &auxiliary_only, &sample, 7, &reading));
    assert(reading.pressed == (RBM_U340E_BUTTON_UP | RBM_U340E_BUTTON_OVERDRIVE));
}

static uint8_t button_step(Lfj8RangeControl *control, Lfj8ButtonFilter *filter,
                           uint32_t time, uint8_t p1, uint32_t generation)
{
    Port port = {.p1 = p1};
    const Lfj8RegisterIo io = {.context = &port, .read8 = read_port};
    const Lfj8H03ButtonSample sample = {time, generation, 1, 3};
    const Lfj8SelectorAdcReading adc = {.captured_us = time, .raw = 500, .event = LFJ8_SELECTOR_ADC_VALUE};
    const RbmU340eInput driver = {.actual_gear = 2, .allowed_gears = 15};
    Lfj8ButtonReading reading;
    RbmU340eOutput output;
    const int valid = lfj8_h03_button_capture_locked(&io, &map, &sample, 7, &reading);
    if (!valid) {
        lfj8_range_control_disarm_buttons(control, filter);
    }
    assert(lfj8_range_control_step_with_buttons(control, adc, filter, valid ? &reading : NULL,
                                                time, &driver, &output));
    return output.requested_gear;
}

static void test_owner_handoff(void)
{
    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .initial_mode = RBM_U340E_TIPTRONIC,
        .initial_overdrive_enabled = 1,
    };
    Lfj8RangeControl control;
    Lfj8ButtonFilter filter;
    assert(lfj8_range_control_init(&control, &policy, 25));
    assert(lfj8_button_filter_init(&filter, 5, 25));
    uint32_t time = UINT32_MAX - 33u;
    const uint8_t released = 8, held = 8 | 64;
    for (unsigned i = 0; i < 4u; ++i) {
        time += 5;
        assert(button_step(&control, &filter, time, held, 7) == 0);
    }
    assert(!filter.armed);
    time += 5;
    assert(button_step(&control, &filter, time, released, 7) == 0);
    time += 5;
    assert(button_step(&control, &filter, time, released, 7) == 0 && filter.armed);
    time += 5; /* Wrap while qualifying the first real edge. */
    assert(button_step(&control, &filter, time, held, 7) == 0);
    time += 5;
    assert(button_step(&control, &filter, time, held, 7) == 3);
    assert(button_step(&control, &filter, time, held, 7) == 0); /* Duplicate capture. */
    time += 5;
    assert(button_step(&control, &filter, time, held, 6) == 0 && !filter.armed);
    time += 5;
    assert(button_step(&control, &filter, time, held, 7) == 0);
    time += 5;
    assert(button_step(&control, &filter, time, held, 7) == 0 && !filter.armed);
    time += 5;
    assert(button_step(&control, &filter, time, released, 7) == 0);
    time += 5;
    assert(button_step(&control, &filter, time, released, 7) == 0 && filter.armed);
}

#ifdef CHECK_H03_STOCK_P1
extern void stock_p1(void);
extern void stock_p1_profile(void);
extern void stock_p1_dispatch(void);

#define BYTE_AT(address) (*(volatile uint8_t *)(address))
#define WORD_AT(address) (*(volatile uint16_t *)(address))

static void test_stock(void)
{
    for (unsigned raw = 0; raw < 256u; ++raw) {
        BYTE_AT(0x800701u) = (uint8_t)raw;
        BYTE_AT(0x804af4u) = BYTE_AT(0x804af5u) = BYTE_AT(0x804af6u) = 255;
        BYTE_AT(0x804af8u) = BYTE_AT(0x804af9u) = 255;
        stock_p1();
        assert(BYTE_AT(0x804af4u) == ((raw >> 6) & 1u));
        assert(BYTE_AT(0x804af5u) == ((raw >> 5) & 1u));
        assert(BYTE_AT(0x804af6u) == ((raw >> 3) & 1u));
        assert(BYTE_AT(0x804af8u) == (1u ^ ((raw >> 6) & 1u)));
        assert(BYTE_AT(0x804af9u) == (1u ^ ((raw >> 5) & 1u)));

        BYTE_AT(0x8046f1u) = (uint8_t)(raw & 1u);
        WORD_AT(0x8061e4u) = UINT16_MAX;
        stock_p1_profile();
        assert(WORD_AT(0x8061e4u) == 2u);
        BYTE_AT(0x8063efu) = BYTE_AT(0x80640eu) = 255;
        stock_p1_dispatch();
        assert(BYTE_AT(0x8063efu) == BYTE_AT(0x804af4u));
        assert(BYTE_AT(0x80640eu) == BYTE_AT(0x804af5u));

        WORD_AT(0x8061e4u) = 1u; /* Exercise the other route with stock fallback config. */
        BYTE_AT(0x8063efu) = BYTE_AT(0x80640eu) = BYTE_AT(0x80642fu) = 255;
        stock_p1_dispatch();
        assert(BYTE_AT(0x8063efu) == 0 && BYTE_AT(0x80640eu) == 0);
        assert(BYTE_AT(0x80642fu) == BYTE_AT(0x804af6u));
    }
    puts("H03 stock P1DATA: 256 raw bytes, five flags, stock selector and both projections PASS");
}
#endif

int main(void)
{
    test_decode();
    test_missing_and_bad_mapping();
    test_owner_handoff();
    puts("H03 button capture: 512 source combinations, invalid wiring and debounce handoff PASS");
#ifdef CHECK_H03_STOCK_P1
    test_stock();
#endif
    return 0;
}
