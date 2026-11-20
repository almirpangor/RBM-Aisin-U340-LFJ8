#include "lfj8_h03_engine_rx.h"

#define CAN_CLOCK_HALF UINT16_C(0x8000)
#define MAXIMUM_POLL_GAP_US UINT16_C(30000)

static void reset_rx(Lfj8H03EngineRx *rx)
{
    ta2005_chery_inputs_reset(&rx->inputs);
    rx->phase = LFJ8_H03_RX_WAIT_FOR_OEM;
    rx->last_poll_us = 0u;
    rx->last_clock_advance_us = 0u;
    rx->last_can_tick = 0u;
    rx->time_ticks = 0u;
}

int lfj8_h03_engine_rx_init(Lfj8H03EngineRx *rx, uint16_t max_age_ticks,
                           uint16_t max_poll_gap_us)
{
    reset_rx(rx);
    rx->max_age_ticks = 0u;
    rx->max_poll_gap_us = 0u;
    if (max_age_ticks == 0u || max_age_ticks >= CAN_CLOCK_HALF ||
        max_poll_gap_us == 0u || max_poll_gap_us > MAXIMUM_POLL_GAP_US) {
        return 0;
    }
    rx->max_age_ticks = max_age_ticks;
    rx->max_poll_gap_us = max_poll_gap_us;
    return 1;
}

static void accept_frame(Lfj8H03EngineRx *rx, Lfj8CanRxResult result, const Lfj8CanData8 *frame,
                         uint16_t expected_id, uint8_t signal)
{
    if (result == LFJ8_CAN_RX_IDLE || result == LFJ8_CAN_RX_RETRY) {
        return;
    }
    if (result == LFJ8_CAN_RX_RECEIVED && frame->id == expected_id) {
        const uint16_t age = (uint16_t)(rx->last_can_tick - frame->timestamp);
        if (age < rx->max_age_ticks) {
            const uint32_t captured_at = rx->time_ticks - age;
            ta2005_chery_inputs_receive(&rx->inputs, frame->id, 8u, frame->payload, &captured_at);
            return;
        }
    }
    rx->inputs.received &= (uint8_t)~signal;
}

static int unavailable(Lfj8CanRxResult result)
{
    return result == LFJ8_CAN_RX_UNAVAILABLE || result == LFJ8_CAN_RX_WRONG_SLOT;
}

static void expire_inputs(Lfj8H03EngineRx *rx)
{
    if (rx->time_ticks - rx->inputs.speed_received_at >= rx->max_age_ticks) {
        rx->inputs.received &= (uint8_t)~TA2005_CHERY_SPEED;
    }
    if (rx->time_ticks - rx->inputs.coolant_received_at >= rx->max_age_ticks) {
        rx->inputs.received &= (uint8_t)~TA2005_CHERY_COOLANT;
    }
}

static void start_clock(Lfj8H03EngineRx *rx, uint32_t now_us, uint16_t tick)
{
    rx->phase = LFJ8_H03_RX_ACTIVE;
    rx->last_poll_us = now_us;
    rx->last_clock_advance_us = now_us;
    rx->last_can_tick = tick;
}

static void start_drain(Lfj8H03EngineRx *rx, uint16_t tick)
{
    reset_rx(rx);
    rx->phase = LFJ8_H03_RX_DRAIN_PENDING;
    rx->last_can_tick = tick;
}

static unsigned poll_rx(Lfj8H03EngineRx *rx, const Lfj8RegisterIo *io,
                        uint32_t now_us, uint8_t slots_owned, Ta2005CherySnapshot *snapshot)
{
    snapshot->speed_fad8 = UINT16_MAX;
    snapshot->coolant_f9e9 = UINT8_MAX;
    snapshot->usable = 0u;
    if (slots_owned != 1u || rx->max_age_ticks == 0u) {
        reset_rx(rx);
        return 0u;
    }
    uint16_t tick;
    if (!lfj8_h03_can0_read_timestamp(io, &tick)) {
        reset_rx(rx);
        return 0u;
    }
    if (rx->phase == LFJ8_H03_RX_WAIT_FOR_OEM) {
        if (lfj8_h03_can0_arm_engine_rx(io, slots_owned)) {
            start_clock(rx, now_us, tick);
        }
        return 0u;
    }
    if (rx->phase == LFJ8_H03_RX_ACTIVE &&
        now_us - rx->last_poll_us >= rx->max_poll_gap_us) {
        start_drain(rx, tick);
        return 0u;
    }

    Lfj8CanData8 rpm;
    Lfj8CanData8 coolant;
    const Lfj8CanRxResult rpm_result = lfj8_can0_receive8(io, LFJ8_H03_CAN0_RPM_SLOT, slots_owned, &rpm);
    const Lfj8CanRxResult coolant_result =
        lfj8_can0_receive8(io, LFJ8_H03_CAN0_COOLANT_SLOT, slots_owned, &coolant);
    if (unavailable(rpm_result) || unavailable(coolant_result) || !lfj8_h03_can0_read_timestamp(io, &tick)) {
        reset_rx(rx);
        return 0u;
    }
    if (rx->phase == LFJ8_H03_RX_DRAIN_PENDING) {
        if (tick != rx->last_can_tick && rpm_result != LFJ8_CAN_RX_RETRY &&
            coolant_result != LFJ8_CAN_RX_RETRY) {
            start_clock(rx, now_us, tick);
        }
        return 0u;
    }
    const uint16_t delta = (uint16_t)(tick - rx->last_can_tick);
    if (delta >= CAN_CLOCK_HALF ||
        (delta == 0u && now_us - rx->last_clock_advance_us >= rx->max_poll_gap_us)) {
        start_drain(rx, tick);
        return 0u;
    }
    if (delta != 0u) {
        rx->last_clock_advance_us = now_us;
    }
    rx->last_can_tick = tick;
    rx->time_ticks += delta;
    rx->last_poll_us = now_us;
    expire_inputs(rx);
    accept_frame(rx, rpm_result, &rpm, 0x0fau, TA2005_CHERY_SPEED);
    accept_frame(rx, coolant_result, &coolant, 0x278u, TA2005_CHERY_COOLANT);
    return ta2005_chery_inputs_snapshot(&rx->inputs, &rx->time_ticks, rx->max_age_ticks, snapshot);
}

unsigned lfj8_h03_engine_rx_poll(Lfj8H03EngineRx *rx, const Lfj8RegisterIo *io,
                                uint32_t now_us, uint8_t slots_owned,
                                Ta2005CherySnapshot *snapshot)
{
    const uint32_t saved = io->enter(io->context);
    const unsigned usable = poll_rx(rx, io, now_us, slots_owned, snapshot);
    io->leave(io->context, saved);
    return usable;
}
