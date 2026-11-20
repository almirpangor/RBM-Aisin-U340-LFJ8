#include "lfj8_h03_dtc_native.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_mmio.h"

static bool native_rx_epoch(void *context, uint32_t *generation)
{
    Lfj8H03CanOwner *const owner = context;
    if (!lfj8_h03_can_owner_rx_epoch(owner, generation)) {
        return false;
    }
    if (!lfj8_h03_sensor_clock_ready_locked()) {
        owner->grant = 0u;
        return false;
    }
    return true;
}

static Lfj8H03Can13Result native_poll_owner(void *context, Lfj8H03Can13 *broker,
                                           Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                                           Lfj8H03Can13Input *input, const uint16_t *can_now,
                                           bool native_ready)
{
    return lfj8_h03_can_owner_poll(context, broker, queue, io, input, can_now, native_ready);
}

static const Lfj8H03DtcCanOwnerOps native_owner_ops = {
    .rx_epoch = native_rx_epoch,
    .poll = native_poll_owner,
    .owner = &h03_can_owner,
};

static const Lfj8RegisterIo *const io = &lfj8_h03_mmio;

void lfj8_h03_dtc_native_cold_init(void)
{
    const uint32_t saved = io->enter(io->context);
    lfj8_h03_dtc_target_unbind();
    lfj8_h03_can_owner_init(&h03_can_owner);
    io->leave(io->context, saved);
}

void lfj8_h03_dtc_native_unbind(void)
{
    const uint32_t saved = io->enter(io->context);
    h03_can_owner.grant = 0u;
    lfj8_h03_dtc_target_unbind();
    io->leave(io->context, saved);
}

bool lfj8_h03_dtc_native_bind(Lfj8H03DtcTarget *target, Lfj8H03Can13 *broker,
                              uint16_t max_clock_span_us)
{
    const uint32_t saved = io->enter(io->context);
    const bool bound = h03_can_owner.initialized && lfj8_h03_sensor_clock_ready_locked() &&
        lfj8_h03_dtc_target_init(target, broker, io, &native_owner_ops,
                                lfj8_h03_tml0ct_m32r, max_clock_span_us);
    io->leave(io->context, saved);
    return bound;
}

static Lfj8H03Can13Result poll_locked(Lfj8H03DtcTarget *target, Lfj8H03Can13Input *input,
                                      bool ready)
{
    const Lfj8H03Can13Result result = lfj8_h03_dtc_target_poll(target, input, ready);
    if (!result.available) {
        h03_can_owner.grant = 0u;
    }
    return result;
}

Lfj8H03Can13Result lfj8_h03_dtc_native_poll(Lfj8H03DtcTarget *target,
                                          Lfj8H03Can13Input *input, bool native_ready)
{
    const uint32_t saved = io->enter(io->context);
    const bool clock_ready = lfj8_h03_sensor_clock_ready_locked() == 1;
    const Lfj8H03Can13Result result = poll_locked(target, input, native_ready && clock_ready);
    io->leave(io->context, saved);
    return result;
}

static bool valid_t6_config(const Lfj8H03DtcT6Config *config)
{
    /* Bound the scaled gap plus a full fractional remainder to 32 bits. */
    return config && config->period_us_denominator != 0u &&
        config->period_us_numerator >= config->period_us_denominator &&
        config->max_sample_gap_us != 0u && config->max_sample_gap_us < UINT32_C(0x80000000) &&
        config->max_sample_gap_us <=
            (UINT32_MAX - (config->period_us_numerator - 1u)) / config->period_us_denominator;
}

bool lfj8_h03_dtc_native_start_t6(Lfj8H03DtcT6Clock *clock,
                                  const Lfj8H03DtcT6Config *config, uint32_t initial_tick)
{
    const uint32_t saved = io->enter(io->context);
    bool started = false;
    if (clock && h03_can_owner.grant == 0u) {
        clock->active = false;
        if (h03_can_owner.initialized && valid_t6_config(config) &&
            lfj8_h03_sensor_clock_ready_locked() == 1) {
            *clock = (Lfj8H03DtcT6Clock){
                .config = *config,
                .sampled_us = lfj8_h03_tml0ct_m32r(io->context),
                .tick = initial_tick,
                .active = true,
            };
            started = true;
        }
    }
    io->leave(io->context, saved);
    return started;
}

static bool sample_t6(Lfj8H03DtcT6Clock *clock, Lfj8H03Can13Input *input, bool clock_ready)
{
    if (!clock || !clock->active) {
        return false;
    }
    if (!input || !clock_ready) {
        clock->active = false;
        return false;
    }
    const uint32_t now = lfj8_h03_tml0ct_m32r(io->context);
    const uint32_t elapsed = now - clock->sampled_us;
    const Lfj8H03DtcT6Config *const config = &clock->config;
    if (elapsed > config->max_sample_gap_us) {
        clock->active = false;
        return false;
    }
    const uint32_t scaled = elapsed * config->period_us_denominator + clock->remainder;
    const uint32_t ticks = scaled / config->period_us_numerator;
    clock->remainder = scaled - ticks * config->period_us_numerator;
    clock->sampled_us = now;
    clock->tick += ticks;
    input->diagnostic_tick = clock->tick;
    return true;
}

Lfj8H03Can13Result lfj8_h03_dtc_native_poll_t6(Lfj8H03DtcTarget *target,
                                             Lfj8H03Can13Input *input, bool native_ready,
                                             Lfj8H03DtcT6Clock *clock)
{
    const uint32_t saved = io->enter(io->context);
    const bool clock_ready = lfj8_h03_sensor_clock_ready_locked() == 1;
    const bool tick_ready = sample_t6(clock, input, clock_ready);
    const Lfj8H03Can13Result result = poll_locked(target, input, native_ready && tick_ready);
    io->leave(io->context, saved);
    return result;
}
