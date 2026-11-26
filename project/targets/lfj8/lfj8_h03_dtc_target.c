#include "lfj8_h03_dtc_target.h"

#include <stddef.h>

enum {
    ATF_CIRCUIT_DTC = 0x04,
    ATF_CLOCK_LOST = UINT8_MAX - 1u,
    ATF_CAPTURE_SUSPENDED = UINT8_MAX,
};

static Lfj8H03DtcTarget *volatile irq_target;

bool lfj8_h03_dtc_rx_clock_span_valid(uint16_t span_us, uint16_t age_bits, uint16_t bit_time_us)
{
    return span_us && span_us < (uint32_t)age_bits * bit_time_us;
}

bool lfj8_h03_dtc_atf_config_valid(const Lfj8H03DtcAtfConfig *config)
{
    return config && config->now_us_locked && config->inhibit_history &&
        config->max_age_us && config->max_age_us < UINT32_C(0x80000000);
}

void lfj8_h03_dtc_target_unbind(void)
{
    irq_target = NULL;
}

bool lfj8_h03_dtc_target_init(Lfj8H03DtcTarget *target, Lfj8H03Can13 *broker,
                            const Lfj8RegisterIo *io, const Lfj8H03DtcCanOwnerOps *can_owner,
                            uint32_t (*clock_us)(void *), uint16_t max_clock_span_us)
{
    if (!target || !broker || !broker->initialized || !io || !io->read8 ||
        !io->read16 || !io->write8 || !io->enter || !io->leave || !clock_us ||
        !can_owner || !can_owner->rx_epoch || !can_owner->poll || irq_target) {
        return false;
    }
    const uint16_t age_bits = broker->diagnostic.max_receive_age_bits;
    const uint16_t bit_time_us = broker->torque.bit_time_us;
    if (!lfj8_h03_dtc_rx_clock_span_valid(max_clock_span_us, age_bits, bit_time_us) ||
        !lfj8_h03_dtc_rx_queue_init(&target->queue, 0, age_bits, bit_time_us)) {
        return false;
    }
    target->dispatch = (Lfj8H03DtcRxDispatch){0};
    target->broker = broker;
    target->io = io;
    target->can_owner = can_owner;
    target->clock_us = clock_us;
    target->atf_config = NULL;
    target->atf_pending = LFJ8_H03_ATF_CIRCUIT_UNKNOWN;
    target->max_clock_span_us = max_clock_span_us;
    const uint32_t saved = io->enter(io->context);
    irq_target = target;
    io->leave(io->context, saved);
    return true;
}

bool lfj8_h03_dtc_target_enable_atf(Lfj8H03DtcTarget *target,
                                  const Lfj8H03DtcAtfConfig *config)
{
    if (!target || irq_target != target || !lfj8_h03_dtc_atf_config_valid(config)) {
        return false;
    }
    const Lfj8RegisterIo *io = target->io;
    const uint32_t saved = io->enter(io->context);
    uint32_t now_us;
    const bool enabled = !target->atf_config && config->now_us_locked(&now_us) == 1;
    if (enabled) {
        target->atf_pending = LFJ8_H03_ATF_CIRCUIT_UNKNOWN;
        target->atf_config = config;
    }
    io->leave(io->context, saved);
    return enabled;
}

static bool sample_atf_clock_locked(Lfj8H03DtcTarget *target, uint32_t *now_us)
{
    if (target->atf_pending == ATF_CLOCK_LOST) {
        return false;
    }
    if (target->atf_config->now_us_locked(now_us) != 1) {
        target->atf_pending = ATF_CLOCK_LOST;
        return false;
    }
    return true;
}

void rbm_h03_dtc_atf_capture(Lfj8H03AtfCircuitStatus status)
{
    Lfj8H03DtcTarget *target = irq_target;
    uint32_t now_us;
    if (target && target->atf_config && sample_atf_clock_locked(target, &now_us) &&
        target->atf_pending != ATF_CAPTURE_SUSPENDED) {
        if (status != LFJ8_H03_ATF_CIRCUIT_UNKNOWN) {
            target->atf_observed_us = now_us;
        }
        target->atf_pending = (uint8_t)status;
    }
}

static void service_atf(Lfj8H03DtcTarget *target, CheryDtcState *dtc)
{
    const Lfj8RegisterIo *io = target->io;
    const uint32_t saved = io->enter(io->context);
    uint32_t now_us;
    if (!sample_atf_clock_locked(target, &now_us)) {
        io->leave(io->context, saved);
        return;
    }
    const uint8_t pending = target->atf_pending;
    const bool ready = !dtc->clear_pending;
    const bool fresh = ready && pending != ATF_CAPTURE_SUSPENDED &&
        pending != LFJ8_H03_ATF_CIRCUIT_UNKNOWN &&
        now_us - target->atf_observed_us < target->atf_config->max_age_us;
    target->atf_pending = ready ? LFJ8_H03_ATF_CIRCUIT_UNKNOWN : ATF_CAPTURE_SUSPENDED;
    io->leave(io->context, saved);
    if (!fresh) {
        return;
    }
    switch ((Lfj8H03AtfCircuitStatus)pending) {
    case LFJ8_H03_ATF_CIRCUIT_LOW:
    case LFJ8_H03_ATF_CIRCUIT_HIGH:
    case LFJ8_H03_ATF_CIRCUIT_BOTH:
        chery_dtc_raise_c0(dtc, ATF_CIRCUIT_DTC, target->atf_config->inhibit_history(io->context));
        break;
    case LFJ8_H03_ATF_CIRCUIT_NO_CURRENT_FAULT:
        chery_dtc_set_current(dtc, ATF_CIRCUIT_DTC, false);
        break;
    default:
        break;
    }
}

static bool sample_clocks(const Lfj8H03DtcTarget *target, uint32_t *now_us, uint16_t *can_now)
{
    const Lfj8RegisterIo *io = target->io;
    const uint32_t saved = io->enter(io->context);
    const uint32_t before = target->clock_us(io->context);
    const bool can_running = lfj8_h03_can0_read_timestamp(io, can_now) != 0;
    const uint32_t after = target->clock_us(io->context);
    io->leave(io->context, saved);
    /* Use the earlier bound so pairing cannot extend the lifetime of RX. */
    *now_us = before;
    return can_running && after - before <= target->max_clock_span_us;
}

void rbm_h03_dtc_rx_begin(uint16_t pending)
{
    Lfj8H03DtcTarget *target = irq_target;
    if (!target) {
        return;
    }
    target->dispatch.paired_slots = 0;
    const uint16_t both = LFJ8_H03_DTC_RX14_PENDING | LFJ8_H03_DTC_RX15_PENDING;
    const Lfj8H03DtcCanOwnerOps *owner = target->can_owner;
    uint32_t generation;
    uint32_t now_us;
    uint16_t can_now;
    if ((pending & both) == both && owner->rx_epoch(owner->owner, &generation) &&
        sample_clocks(target, &now_us, &can_now)) {
        lfj8_h03_dtc_rx_dispatch_begin(&target->dispatch, &target->queue, target->io,
                                       pending, generation, now_us, can_now);
    }
}

void rbm_h03_dtc_rx_observe(uint8_t slot)
{
    Lfj8H03DtcTarget *target = irq_target;
    if (!target || slot < 14u || slot > 15u) {
        return;
    }
    const Lfj8H03DtcCanOwnerOps *owner = target->can_owner;
    uint32_t generation;
    if (!owner->rx_epoch(owner->owner, &generation)) {
        target->dispatch.paired_slots = 0;
        return;
    }
    uint32_t now_us;
    uint16_t can_now;
    if (!lfj8_h03_dtc_rx_dispatch_skip_paired(&target->dispatch, slot, generation) &&
        sample_clocks(target, &now_us, &can_now)) {
        lfj8_h03_dtc_rx_queue_capture_basic(&target->queue, target->io, slot, generation,
                                          now_us, can_now);
    }
}

Lfj8H03Can13Result lfj8_h03_dtc_target_poll(Lfj8H03DtcTarget *target,
                                         Lfj8H03Can13Input *input, bool native_ready)
{
    if (!target || irq_target != target || !input) {
        return (Lfj8H03Can13Result){0};
    }
    uint16_t can_now;
    const bool paired = sample_clocks(target, &input->now_us, &can_now);
    CheryDtcState *const dtc = input->dtc;
    const bool atf_enabled = target->atf_config && dtc;
    if (atf_enabled) {
        service_atf(target, dtc);
    }
    const Lfj8H03DtcCanOwnerOps *owner = target->can_owner;
    const Lfj8H03Can13Result result = owner->poll(
        owner->owner, target->broker, &target->queue, target->io,
        input, paired ? &can_now : NULL, native_ready);
    if (atf_enabled && dtc->clear_pending) {
        /* Drop captures from the CAN transaction and suspend until foreground
         * observes that the engine qualification owner consumed the clear. */
        const Lfj8RegisterIo *io = target->io;
        const uint32_t saved = io->enter(io->context);
        if (target->atf_pending != ATF_CLOCK_LOST) {
            target->atf_pending = ATF_CAPTURE_SUSPENDED;
        }
        io->leave(io->context, saved);
    }
    return result;
}
