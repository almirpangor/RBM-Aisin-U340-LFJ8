#include "lfj8_h03_can_owner.h"

#include <stddef.h>

_Static_assert(offsetof(Lfj8H03CanOwner, setup_generation) == LFJ8_CAN_OWNER_SETUP_GENERATION_OFFSET,
               "Native CAN setup generation offset");
_Static_assert(offsetof(Lfj8H03CanOwner, grant) == LFJ8_CAN_OWNER_GRANT_OFFSET,
               "Native CAN grant offset");

void lfj8_h03_can_owner_init(Lfj8H03CanOwner *owner)
{
    *owner = (Lfj8H03CanOwner){.initialized = true};
}

bool lfj8_h03_can_owner_rx_epoch(const Lfj8H03CanOwner *owner, uint32_t *generation)
{
    if (owner->grant != 1u) {
        return false;
    }
    *generation = owner->setup_generation;
    return true;
}

Lfj8H03Can13Result lfj8_h03_can_owner_poll(
    Lfj8H03CanOwner *owner, Lfj8H03Can13 *broker, Lfj8H03DtcRxQueue *queue,
    const Lfj8RegisterIo *io, Lfj8H03Can13Input *input, const uint16_t *can_now,
    bool native_ready)
{
    const bool ready = native_ready && can_now && input->dtc &&
                       queue->initialized && broker->initialized;
    const uint32_t saved_irq = io->enter(io->context);
    const uint32_t epoch = owner->setup_generation;
    if (!ready || !owner->initialized) {
        owner->grant = 0u;
    } else if (epoch != owner->admitted_generation && lfj8_h03_can0_epoch_drained(io)) {
        lfj8_h03_dtc_rx_queue_reset(queue, io, epoch);
        owner->admitted_generation = epoch;
        owner->grant = 1u;
    }
    io->leave(io->context, saved_irq);

    const uint32_t saved_generation = input->generation;
    const uint8_t saved_grant = input->owns_slot13;
    input->generation = owner->admitted_generation;
    input->owns_slot13 = owner->grant;
    const Lfj8H03Can13Result result = lfj8_h03_dtc_foreground_poll(
        broker, queue, io, input, owner->grant == 1u ? can_now : NULL);
    input->generation = saved_generation;
    input->owns_slot13 = saved_grant;
    if (!result.available) {
        owner->grant = 0u;
    }
    return result;
}
