/* Windows and M32R model. Timing and S01 projection are fixture data only. */
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_bench_input.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

Lfj8H03Application rbm_h03_application;
Lfj8H03SensorTarget rbm_h03_sensor_state;
Lfj8H03CanOwner h03_can_owner;
volatile Lfj8SelectorAdc rbm_h03_selector_adc_state;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;

static int owned = 1;
static int projection = 1, driver_valid = 1;
static uint32_t now_us;
static uint16_t can_status;
static int old_local;

#ifndef __m32r__
static uint32_t depth;
static uint32_t enter(void *context) { (void)context; return depth++; }
static void leave(void *context, uint32_t saved) { (void)context; assert(depth == saved + 1u); depth = saved; }

static uint8_t reg8(void *context, uint32_t address)
{
    (void)context;
    switch (address) {
    case 0x800203: return 9u;
    case 0x8003eb: return 0x01u;
    case 0x800feb: return 0x31u;
    case 0x806ae6: return 6u;
    default: return 0u;
    }
}
static uint16_t reg16(void *context, uint32_t address)
{
    (void)context;
    return address == 0x801002 ? can_status : 0u;
}
static uint32_t reg32(void *context, uint32_t address)
{
    (void)context;
    assert(address == 0x8003e0u);
    return now_us;
}
const Lfj8RegisterIo lfj8_h03_mmio = {
    .enter = enter, .leave = leave, .read8 = reg8, .read16 = reg16, .read32 = reg32,
};
uint32_t lfj8_h03_tml0ct_m32r(void *context) { return reg32(context, 0x8003e0u); }
#endif

static void registers(void)
{
#ifdef __m32r__
    *(volatile uint8_t *)(uintptr_t)0x800203u = 9u;
    *(volatile uint8_t *)(uintptr_t)0x8003ebu = 1u;
    *(volatile uint8_t *)(uintptr_t)0x800febu = 0x31u;
    *(volatile uint8_t *)(uintptr_t)0x806ae6u = 6u;
    *(volatile uint16_t *)(uintptr_t)0x801002u = can_status;
    *(volatile uint32_t *)(uintptr_t)0x8003e0u = now_us;
#endif
}

int rbm_h03_target_ram_owned(void *context)
{
    assert(!context);
#ifdef __m32r__
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    assert(!(psw & 0x40u));
#else
    assert(depth);
#endif
    return owned;
}
int lfj8_h03_application_running_locked(void)
{
    return rbm_h03_target_ram_owned(NULL) && rbm_h03_application.running;
}

static int read_local(const Lfj8H03SensorSnapshot *sensors, uint32_t now,
    RbmU340eInput *driver, Lfj8H03RangeInputs *range, uint32_t *driver_at)
{
    assert(now == now_us && rbm_h03_target_ram_owned(NULL));
    driver->actual_gear = 0u; /* No confirmed forward ratio in this model. */
    const Lfj8H03RangeBit bit = {.captured_us = now - 1u, .generation = sensors->epoch, .valid = 1u};
    for (unsigned i = 0; i < 4u; ++i) {
        range->range_5722[i] = bit;
    }
    range->range_5722[2].asserted = 1u;
    range->inhibit_5250_2 = bit;
    *driver_at = now - (old_local ? 90u : 3u);
    return driver_valid;
}
static int project(const Lfj8H03RawLoadSample *raw, RbmU340eQualifiedLoadFeed *out)
{
    assert(rbm_h03_target_ram_owned(NULL) && raw->load_f8d6 == 0xfedcu);
    assert(raw->divisor_f4686 == 0x8123u && raw->model_9680 == 0x4567u && raw->source_bits == 2u);
    out->sampled_at = now_us; /* The backend must replace this newer time. */
    out->gp_8270 = -21; /* Verify signed transport between the two model providers. */
    return projection;
}

static Lfj8H03BenchInputState state;
static const Lfj8H03RawLoadConfig timing = {
    .max_age_us = 100u, .producer_bound_us = 20u, .max_can_age_bits = 15u, .bit_time_us = 2u,
};
static const Lfj8H03BenchInputProfile profile = {
    .state = &state, .raw_config = &timing, .driver_max_age_us = 30u,
    .read_local = read_local, .project_load = project,
};
static Lfj8H03InputProposal proposal;
static Lfj8RangeControl control;
static Lfj8ButtonFilter filter;
static const Lfj8H03ButtonMap pins = {{
    {LFJ8_H03_BUTTON_P1, 8u, 1u}, {LFJ8_H03_BUTTON_P1, 64u, 0u},
    {LFJ8_H03_BUTTON_P1, 32u, 0u}, {0},
}};
static const RbmU340eSelectorProfile selector = {
    .windows = {{1, 10}, {10, 20}, {20, 30}, {30, 40}, {40, 50}, {50, 60}}, .stable_samples = 1u,
};
static const Lfj8H03RangeAgeLimits limits = {{30u, 30u, 30u, 30u}, 30u};
static const Lfj8H03InputBinding binding = {
    .adc = &rbm_h03_selector_adc_state, .control = &control, .button_filter = &filter,
    .io = &lfj8_h03_mmio, .range_limits = &limits, .p1_button_map = &pins,
    .manual_max_age_us = 40u, .selector_profile = &selector,
};
static const Lfj8H03InputStartup startup = {
    .policy = {.initial_overdrive_enabled = 1u}, .selector_max_age_us = 80u,
    .button_debounce_us = 1u, .button_max_age_us = 80u,
};
#define RBM_H03_PROFILE_BENCH_INPUT profile
#define RBM_H03_PROFILE_BENCH_INPUT_BINDING binding
#define RBM_H03_PROFILE_BENCH_INPUT_PROPOSAL proposal
#define RBM_H03_PROFILE_TOYOTA_INPUT_STARTUP startup
#include "lfj8_h03_bench_input_profile.h"

static void publish_selector(uint32_t at)
{
    rbm_h03_selector_adc_state = (Lfj8SelectorAdc){
        .pending_us = at, .pending_raw = 33u, .pending_p1data = 8u, .pending_p1_valid = 1u,
        .pending_event = LFJ8_SELECTOR_ADC_VALUE,
    };
    RBM_H03_PROFILE_SAMPLE_TOYOTA_INPUTS(at, 0u);
}

/* Packed OEM BasicCAN identifier 0x6B2, DLC 8, payload, then hardware timestamp. */
static const uint8_t frame[16] = {
    0x1a, 0x32, 0, 0, 0, 8, 0x16, 255, 0xfe, 0xdc, 0x81, 0x23, 0x45, 0x67, 0xff, 0xfe,
};

static void receive_cases(void)
{
    Lfj8H03RawLoadRx rx = {0};
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, frame, 0x41, false, 9, 7, 5, 2) ==
           LFJ8_H03_RAW_LOAD_REJECTED);
    lfj8_h03_raw_load_reset(&rx, UINT32_MAX - 20u);
    uint8_t f[16];
    for (unsigned i = 0; i < sizeof f; ++i) f[i] = frame[i];

    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 7, 5, 2) ==
           LFJ8_H03_RAW_LOAD_RECEIVED);
    const Lfj8H03RawLoadSample *raw = lfj8_h03_raw_load_snapshot(&rx, &timing, 9, 7, 74);
    assert(raw && raw->oldest_us == UINT32_MAX - 24u && raw->sequence == 255u);
    assert(!lfj8_h03_raw_load_snapshot(&rx, &timing, 9, 7, 75)); /* Age exactly 100. */
    assert(!lfj8_h03_raw_load_snapshot(&rx, &timing, 10, 7, 5));
    assert(!lfj8_h03_raw_load_snapshot(&rx, &timing, 9, 8, 5));

    f[1] = 0x33; /* An unrelated standard frame has no effect. */
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 7, 10, 2) ==
           LFJ8_H03_RAW_LOAD_OTHER);
    assert(lfj8_h03_raw_load_snapshot(&rx, &timing, 9, 7, 10));
    f[1] = frame[1];
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 7, 10, 2) ==
           LFJ8_H03_RAW_LOAD_REJECTED); /* Duplicate sequence cannot refresh a frame. */
    assert(lfj8_h03_raw_load_snapshot(&rx, &timing, 9, 7, 10)->oldest_us == UINT32_MAX - 24u);
    f[7] = 0u;
    f[14] = 0u;
    f[15] = 2u;
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 7, 10, 2) ==
           LFJ8_H03_RAW_LOAD_RECEIVED);
    f[5] = 7u;
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 7, 14, 2) ==
           LFJ8_H03_RAW_LOAD_REJECTED);
    assert(!lfj8_h03_raw_load_snapshot(&rx, &timing, 9, 7, 14));
    f[5] = 8u;
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 7, 50, 17) ==
           LFJ8_H03_RAW_LOAD_REJECTED); /* CAN age exactly 15. */
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 7, 14, 1) ==
           LFJ8_H03_RAW_LOAD_REJECTED); /* Timestamp is still future. */
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x45, false, 9, 7, 14, 2) ==
           LFJ8_H03_RAW_LOAD_REJECTED); /* Remote/invalid control. */
    f[7] = 251u;
    f[6] = 0x12u;
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 8, 16, 2) ==
           LFJ8_H03_RAW_LOAD_REJECTED); /* Explicitly unready publisher. */
    f[6] = 0x16u;
    assert(lfj8_h03_raw_load_receive_basic(&rx, &timing, f, 0x41, false, 9, 8, 16, 2) ==
           LFJ8_H03_RAW_LOAD_RECEIVED); /* Admitted new CAN generation. */
}

int main(void)
{
    receive_cases();
    assert(lfj8_h03_raw_load_config_valid(&timing));
    now_us = 100u;
    registers();
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    assert(RBM_H03_PROFILE_RESET_TOYOTA_INPUTS());
    assert(!lfj8_h03_bench_input_load_ready_locked(&profile));
    rbm_h03_application.running = 1u;
    h03_can_owner = (Lfj8H03CanOwner){.initialized = true, .grant = 1u,
                                     .setup_generation = 42u, .admitted_generation = 42u};
    rbm_h03_tml0_1mhz_qualified = 1u;
    rbm_h03_sensor_state.feed.epoch = 3u;
    now_us = 110u;
    registers();
    assert(lfj8_h03_bench_input_rx_locked(&profile, frame, now_us, 2) ==
           LFJ8_H03_RAW_LOAD_RECEIVED);
    assert(lfj8_h03_bench_input_load_ready_locked(&profile));
    publish_selector(now_us - 2u);
    publish_selector(now_us - 1u);
    io->leave(io->context, saved);

    Lfj8H03CycleInput in = {0};
    Lfj8H03CycleLoad load = {0};
    const Lfj8H03SensorSnapshot sensors = {.capture.now_tml0 = now_us, .epoch = 3};
    assert(RBM_H03_PROFILE_CAPTURE_TOYOTA(NULL, &sensors, now_us, &in, &load));
    assert(in.qualified && !in.engine.coherent && in.selector == RBM_U340E_SELECTOR_D);
    assert(in.range_5722 == 4u && !in.inhibit_5250 && in.command_at == 80u);
    assert(load.sample && load.sample->sampled_at == 80u && load.sample->gp_8270 == -21);

    RbmU340eRuntime runtime = {.initialized = 1u};
    assert(rbm_u340e_runtime_publish_load(&runtime, load.sample, load.now_us, load.max_age_us));
    uint32_t gp_value;
    assert(factory_hydraulics_get(&runtime.gp, -8270, 2u, &gp_value) && gp_value == 65515u);

    old_local = 1;
    assert(!RBM_H03_PROFILE_CAPTURE_TOYOTA(NULL, &sensors, now_us, &in, &load));
    assert(!in.qualified && !load.sample);
    old_local = 0;
    projection = 0;
    assert(!RBM_H03_PROFILE_CAPTURE_TOYOTA(NULL, &sensors, now_us, &in, &load));
    projection = 1;
    driver_valid = 0;
    assert(!RBM_H03_PROFILE_CAPTURE_TOYOTA(NULL, &sensors, now_us, &in, &load));
    driver_valid = 1;
    can_status = 0x4000u; /* CAN0STAT bus-off. */
    registers();
    assert(!RBM_H03_PROFILE_CAPTURE_TOYOTA(NULL, &sensors, now_us, &in, &load));
    can_status = 0;
    registers();
    ++h03_can_owner.setup_generation;
    assert(!RBM_H03_PROFILE_CAPTURE_TOYOTA(NULL, &sensors, now_us, &in, &load));
    h03_can_owner.setup_generation = 42u;
    ++rbm_h03_sensor_state.feed.epoch;
    assert(!RBM_H03_PROFILE_CAPTURE_TOYOTA(NULL, &sensors, now_us, &in, &load));

    printf("TOY-02 native state=%u bytes, capture descriptor=%u bytes\n",
           (unsigned)sizeof state, (unsigned)sizeof lfj8_h03_bench_capture);
    puts("TOY-02 raw Bosch and native Toyota input profile PASS");
    return 0;
}
