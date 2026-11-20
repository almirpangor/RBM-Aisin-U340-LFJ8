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

Lfj8H03Can13Result lfj8_h03_dtc_native_poll(Lfj8H03DtcTarget *target,
                                          Lfj8H03Can13Input *input, bool native_ready)
{
    const uint32_t saved = io->enter(io->context);
    const bool clock_ready = lfj8_h03_sensor_clock_ready_locked() == 1;
    const Lfj8H03Can13Result result = lfj8_h03_dtc_target_poll(target, input, native_ready && clock_ready);
    if (!result.available) {
        h03_can_owner.grant = 0u;
    }
    io->leave(io->context, saved);
    return result;
}
