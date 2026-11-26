#include "bench_engine_profile.h"
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"
#include "bosch_replay.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum { CAN = 0x801000, SLOTS = CAN + 0x5b, DATA = CAN + 0x1b0, SLOT_BYTES = 16 };

Lfj8H03SensorTarget rbm_h03_sensor_state;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;
Lfj8H03CanOwner h03_can_owner;
Lfj8H03CycleInput rbm_h03_cycle_input;
CheryDtcState rbm_h03_dtc_state;

static uint32_t time_us;
static uint16_t ticks, conf = 0x95a0;
static uint8_t brp = 4u, service_mode, programming, flash_mode, stopped_clock;
static uint8_t slots[2], data[2 * SLOT_BYTES], span_us, context_span_us, context_reads, read_can, lock_depth;
static Lfj8H03EngineRx rx;
static Ta2005EngineQualifier qualifier;

static uint32_t enter(void *context)
{
    (void)context;
    return lock_depth++;
}

static void leave(void *context, uint32_t previous)
{
    (void)context;
    assert(lock_depth && --lock_depth == previous);
}

static uint8_t read8(void *context, uint32_t address)
{
    (void)context;
    assert(lock_depth);
    switch (address) {
    case 0x804887: return service_mode;
    case 0x80801c: return programming;
    case 0x8007e2: return flash_mode;
    case 0x800203: return 9u;
    case 0x8003eb: return 0x01u;
    case 0x800feb: return stopped_clock ? 0u : 0x31u;
    case CAN + 0x16: return brp;
    case CAN + 0x18: return 0;
    case 0x806ae6: return 6u;
    case CAN + 0x28: return 0x1fu;
    case CAN + 0x29: return 0x3fu;
    default:
        if (address >= SLOTS && address < SLOTS + 2) return slots[address - SLOTS];
        assert(address >= DATA && address < DATA + sizeof data);
        return data[address - DATA];
    }
}

static uint16_t read16(void *context, uint32_t address)
{
    (void)context;
    assert(lock_depth);
    switch (address) {
    case CAN: case CAN + 2: case CAN + 4: case CAN + 0x10: return 0u;
    case CAN + 6: return conf;
    case CAN + 8: read_can = 1u; return ticks;
    default:
        assert(address == DATA + 14 || address == DATA + 30);
        return (uint16_t)(((uint16_t)data[address - DATA] << 8) | data[address - DATA + 1u]);
    }
}

static uint32_t read32(void *context, uint32_t address)
{
    (void)context;
    assert(lock_depth && address == 0x8003e0u);
    const uint8_t offset = read_can ? span_us : (context_reads++ ? context_span_us : 0u);
    return time_us + offset;
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    (void)context;
    assert(lock_depth);
    if (address >= SLOTS && address < SLOTS + 2) {
        slots[address - SLOTS] = value == 0x4eu ? 0x40u : value;
    } else {
        assert(address >= DATA && address < DATA + sizeof data);
        data[address - DATA] = value;
    }
}

const Lfj8RegisterIo lfj8_h03_mmio = {
    .read8 = read8, .read16 = read16, .read32 = read32, .write8 = write8, .enter = enter, .leave = leave
};

static const Lfj8H03EngineFeedTarget target = {
    .rx = &rx, .qualifier = &qualifier, .dtc = &rbm_h03_dtc_state,
    .can_owner = &h03_can_owner, .io = &lfj8_h03_mmio,
    .now_us = rbm_h03_atf_now_us, .bit_time_us = RBM_H03_PROFILE_ENGINE_BIT_TIME_US,
    .max_can_sample_span_us = RBM_H03_PROFILE_ENGINE_MAX_CAN_SAMPLE_SPAN_US,
};

static uint32_t oldest;
static Ta2005EngineQualificationContext engine;
static RbmU340eQualifiedEngineFeed out;
static bool inhibit;

static bool get_context(uint32_t epoch, uint32_t when)
{
    const Lfj8H03SensorSnapshot sensors = {.epoch = epoch, .capture = {.now_tml0 = when}};
    const uint32_t saved = enter(NULL);
    read_can = 0;
    context_reads = 0u;
    const int ready = RBM_H03_PROFILE_ENGINE_CONTEXT(NULL, &sensors, &engine, &inhibit, &oldest);
    leave(NULL, saved);
    return ready == 1;
}

static void frame(unsigned index, const uint8_t bytes[8], uint8_t dlc, uint16_t captured)
{
    assert(slots[index] == 0x40u);
    slots[index] = 0x41u;
    uint8_t *const buffer = &data[index * SLOT_BYTES];
    buffer[5] = dlc;
    memcpy(buffer + 6, bytes, 8);
    buffer[14] = (uint8_t)(captured >> 8);
    buffer[15] = (uint8_t)captured;
}

static void step(uint32_t elapsed, uint16_t delta)
{
    time_us += elapsed;
    ticks = (uint16_t)(ticks + delta);
    assert(get_context(rbm_h03_sensor_state.feed.epoch, time_us - 1u));
    assert(lfj8_h03_engine_feed_target_task2(&target, &engine, inhibit, &out, NULL, &oldest)
           == TA2005_ENGINE_EVALUATED);
    assert(!lock_depth);
}

int main(void)
{
    rbm_h03_tml0_1mhz_qualified = 1u;
    rbm_h03_sensor_state.feed.epoch = 7u;
    time_us = UINT32_MAX - 5u;
    ticks = UINT16_MAX - 3u;
    assert(get_context(7u, time_us - 11u) && oldest == time_us - 11u);
    assert(inhibit && engine.coherent && !engine.coolant_can_enabled && engine.fallback_fa7b == UINT8_MAX);

    h03_can_owner = (Lfj8H03CanOwner){.initialized = true, .grant = 1, .setup_generation = 3,
                                       .admitted_generation = 3};
    assert(get_context(7u, time_us) && !inhibit && engine.coolant_can_enabled);
    rbm_h03_cycle_input.engine = (RbmU340eQualifiedEngineFeed){
        .fd10 = 0xd234u, .e026 = 0xa7u, .coherent = 1u,
    };
    assert(get_context(7u, time_us) && engine.retained_fd10 == 0u && engine.retained_e026 == 0u);
    rbm_h03_cycle_input.qualified = 1u;
    rbm_h03_dtc_state.current[3] = 0x84u;
    assert(get_context(7u, time_us - 11u));
    assert(engine.retained_fd10 == 0xd234u && engine.retained_e026 == 0xa7u);
    assert(engine.e02b == 0x84u && inhibit && oldest == time_us - 11u);
    rbm_h03_dtc_state.current[3] = 0u;
    assert(get_context(7u, time_us) && !inhibit && engine.e02b == 0u);
    context_span_us = RBM_H03_PROFILE_ENGINE_MAX_CAN_SAMPLE_SPAN_US;
    assert(get_context(7u, time_us));
    context_span_us = RBM_H03_PROFILE_ENGINE_MAX_CAN_SAMPLE_SPAN_US + 1u;
    assert(!get_context(7u, time_us));
    context_span_us = 0u;
    rbm_h03_cycle_input.qualified = 0u;
    rbm_h03_cycle_input.engine = (RbmU340eQualifiedEngineFeed){0};
    assert(!get_context(6u, time_us) && !get_context(7u, time_us + 1u));
    assert(!get_context(7u, time_us - RBM_H03_PROFILE_ENGINE_MAX_POLL_GAP_US));
    conf ^= 1u;
    assert(!get_context(7u, time_us));
    conf ^= 1u;
    brp = 8u;
    assert(!get_context(7u, time_us));
    brp = 4u;
    service_mode = 4u;
    assert(!get_context(7u, time_us));
    service_mode = 0u;
    programming = 1u;
    assert(!get_context(7u, time_us));
    programming = 0u;
    flash_mode = 1u;
    assert(!get_context(7u, time_us));
    flash_mode = 0u;
    stopped_clock = 1u;
    assert(!get_context(7u, time_us) && !rbm_h03_tml0_1mhz_qualified);
    stopped_clock = 0u;
    rbm_h03_tml0_1mhz_qualified = 1u;

    chery_dtc_init(&rbm_h03_dtc_state);
    assert(lfj8_h03_engine_feed_target_init(&target, RBM_H03_PROFILE_ENGINE_MAX_AGE_TICKS,
                                            RBM_H03_PROFILE_ENGINE_MAX_POLL_GAP_US));
    step(0u, 0u);
    assert(!out.fa62 && out.f9b8 == UINT8_MAX && rx.phase == LFJ8_H03_RX_CLOCK_WARMUP);
    const uint16_t next_tick = (uint16_t)(ticks + 5u);
    frame(0, bosch_rpm, 8u, next_tick);
    frame(1, bosch_ect, 8u, next_tick);
    span_us = RBM_H03_PROFILE_ENGINE_MAX_CAN_SAMPLE_SPAN_US;
    step(10u, 5u);
    assert(time_us == 4u && ticks == 1u && out.fa62 == 9600u && out.f9b8 == 137u);
    assert(oldest == time_us - RBM_H03_PROFILE_ENGINE_BIT_TIME_US);

    frame(0, bosch_rpm, 7u, (uint16_t)(ticks + 1u));
    const uint8_t invalid_coolant[8] = {255u};
    frame(1, invalid_coolant, 8u, (uint16_t)(ticks + 1u));
    step(2u, 1u);
    assert(out.f9b8 == UINT8_MAX && out.fa62 == 9600u && !(rx.inputs.received & TA2005_CHERY_SPEED));

    for (unsigned i = 0; i < 27u; ++i) step(2000u, 1000u);
    assert(!out.fa62 && (out.e026 & 2u) && !rx.rpm_stamp_valid &&
           !(rbm_h03_dtc_state.current[2] & 0x30u));

    frame(0, bosch_rpm, 8u, (uint16_t)(ticks + 1000u - RBM_H03_PROFILE_ENGINE_MAX_AGE_TICKS));
    step(2000u, 1000u);
    assert(!out.fa62 && !(rx.inputs.received & TA2005_CHERY_SPEED));

    frame(0, bosch_rpm, 8u, (uint16_t)(ticks + 1000u));
    frame(1, bosch_ect, 8u, (uint16_t)(ticks + 1000u));
    step(2000u, 1000u);
    assert(out.fa62 == 9600u && out.f9b8 == 137u);

    step(2000u, 50u);
    assert(rx.phase == LFJ8_H03_RX_DRAIN_PENDING && !out.fa62 && out.f9b8 == UINT8_MAX);
    frame(0, bosch_rpm, 8u, (uint16_t)(ticks - 1u));
    step(2000u, 1000u);
    assert(rx.phase == LFJ8_H03_RX_CLOCK_WARMUP && !out.fa62);
    frame(0, bosch_rpm, 8u, (uint16_t)(ticks + 1000u));
    step(2000u, 1000u);
    assert(out.fa62 == 9600u);

    step(100u, 700u);
    assert(rx.phase == LFJ8_H03_RX_DRAIN_PENDING && !out.fa62);
    step(2000u, 1000u);
    span_us = RBM_H03_PROFILE_ENGINE_MAX_CAN_SAMPLE_SPAN_US + 1u;
    step(2000u, 1000u);
    assert(rx.phase == LFJ8_H03_RX_DRAIN_PENDING && !out.fa62);

    span_us = 0u;
    step(2000u, 1000u);
    step(RBM_H03_PROFILE_ENGINE_MAX_POLL_GAP_US, 5000u);
    assert(rx.phase == LFJ8_H03_RX_DRAIN_PENDING && !out.fa62);
    ++h03_can_owner.setup_generation;
    step(2000u, 1000u);
    assert(inhibit && !engine.coolant_can_enabled && rx.phase == LFJ8_H03_RX_WAIT_FOR_OEM &&
           !out.fa62 && !rx.inputs.received);
    puts("H03 native Task 2: proven context, Bosch replay, expiry, CAN clock and generation PASS");
    return 0;
}
