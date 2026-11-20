#include "lfj8_h03_torque_can.h"
#include "lfj8_bridge.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CNT = 0x801000, STAT = 0x801002, EXTID = 0x801004, TSTMP = 0x801008,
    SLIMK = 0x801010, MODE = 0x801018, GMSKS0 = 0x801028, GMSKS1 = 0x801029,
    MSC13 = 0x80105d, SLOT13 = 0x8011d0, OEM_STATE = 0x806ae6,
};

typedef struct {
    uint8_t storage[16];
    uint8_t control;
    uint8_t global_mask;
    uint16_t tick;
    uint16_t stat;
    uint16_t ext_id;
    uint16_t irq_mask;
    unsigned sent;
    unsigned aborted;
    unsigned lock;
    unsigned writes;
} CanRegisters;

static uint8_t read_byte(void *context, uint32_t address)
{
    CanRegisters *can = context;
    assert(can->lock == 1u);
    switch (address) {
        case OEM_STATE: return 6;
        case MSC13: return can->control;
        case MODE: return 0;
        case GMSKS0: return can->global_mask;
        case GMSKS1: return 0x3f;
        default:
            assert(address >= SLOT13 && address < SLOT13 + 16u);
            assert((can->control & 2u) == 0u);
            return can->storage[address - SLOT13];
    }
}

static uint16_t read_halfword(void *context, uint32_t address)
{
    CanRegisters *can = context;
    assert(can->lock == 1u);
    switch (address) {
        case CNT: return 0x0008;
        case STAT: return can->stat;
        case EXTID: return can->ext_id;
        case TSTMP: return can->tick;
        case SLIMK: return can->irq_mask;
        default:
            assert(address == SLOT13 + 14u && (can->control & 2u) == 0u);
            return (uint16_t)((uint16_t)can->storage[14] << 8 | can->storage[15]);
    }
}

static void write_byte(void *context, uint32_t address, uint8_t value)
{
    CanRegisters *can = context;
    assert(can->lock == 1u && !(can->irq_mask & 4u) && !can->stat);
    ++can->writes;
    if (address != MSC13) {
        assert(address >= SLOT13 && address < SLOT13 + 14u && can->control == 0u);
        can->storage[address - SLOT13] = value;
    } else if (value == 0x4eu || value == 0x40u) {
        assert(can->control == 0u || (can->control & 0x40u));
        can->control = 0x40u;
    } else if (value == 0x0fu) {
        assert(can->control == 0x80u || can->control == 0x82u);
        can->control &= 2u;
        ++can->aborted;
    } else {
        assert(value == 0u || value == 0x80u);
        assert((can->control & 2u) == 0u);
        can->control = value;
        can->sent += value == 0x80u;
    }
}

static uint32_t lock_irq(void *context)
{
    CanRegisters *can = context;
    assert(!can->lock);
    can->lock = 1;
    return 0x41;
}

static void restore_irq(void *context, uint32_t state)
{
    CanRegisters *can = context;
    assert(can->lock == 1u && state == 0x41u);
    can->lock = 0;
}

static uint8_t crc(const uint8_t *bytes)
{
    uint8_t result = 0xff;
    for (unsigned i = 0; i < 7u; ++i) {
        result ^= bytes[i];
        for (unsigned j = 0; j < 8u; ++j) {
            result = (uint8_t)(((unsigned)result << 1) ^ ((result & 0x80u) ? 0x1du : 0u));
        }
    }
    return (uint8_t)(result ^ 0xffu);
}

static uint16_t tick_at(uint32_t step_us)
{
    return (uint16_t)(0xff00u + step_us / 2u);
}

static void stamp(CanRegisters *can, uint32_t step_us)
{
    const uint16_t stamp_tick = tick_at(step_us);
    can->storage[14] = (uint8_t)(stamp_tick >> 8);
    can->storage[15] = (uint8_t)stamp_tick;
}

static void finish(CanRegisters *can, uint32_t step_us)
{
    assert(can->control == 0x80u);
    stamp(can, step_us);
    can->control = 0x81u;
}

static void status(CanRegisters *can, uint32_t step_us, uint8_t phase,
                   uint8_t seq, uint8_t amount, uint8_t token)
{
    assert(can->control == 0x40u);
    assert(can->storage[0] == 0x17u && can->storage[1] == 0x29u);
    const uint8_t value[7] = {0xa4u, phase, seq, amount, token, 0u, 0u};
    memcpy(&can->storage[6], value, sizeof(value));
    can->storage[13] = crc(&can->storage[6]);
    stamp(can, step_us);
    can->control = 0x41u;
}

static void expect_request(const CanRegisters *can, uint8_t op, uint8_t seq)
{
    assert(can->control == 0x80u && can->storage[0] == 0x17u && can->storage[1] == 0x28u);
    assert(can->storage[5] == 8u && can->storage[6] == 0xa4u);
    assert(can->storage[7] == op && can->storage[8] == seq && can->storage[11] == 1u);
    assert(can->storage[13] == crc(&can->storage[6]));
}

static const Lfj8TorqueCalibration calibration = {.up = {[1] = {0x20, 32u, 20u}}};

static Lfj8H03TorqueCanSlot poll(Lfj8H03TorqueCan *link, const Lfj8RegisterIo *io,
                                uint32_t step_us, bool demand, bool yield, uint8_t lease,
                                uint32_t generation)
{
    CanRegisters *can = io->context;
    can->tick = tick_at(step_us);
    const uint32_t now_us = UINT32_MAX - 999u + step_us;
    const Lfj8TorqueInput input = {
        .demand = {(uint8_t)demand, 2u, 3u, 5u},
        .captured_at_us = now_us, .engine_rpm = 2000u, .observed_gear = 2u, .permitted = true,
    };
    const Lfj8H03TorqueCanSlot result =
        lfj8_h03_torque_can_poll(link, io, lease, yield, generation, now_us, &input, &calibration);
    assert(!can->lock);
    return result;
}

int main(void)
{
    CanRegisters can = {.irq_mask = 0x8007, .global_mask = 0x1f};
    const Lfj8RegisterIo io = {.context = &can, .read8 = read_byte, .read16 = read_halfword,
                             .write8 = write_byte, .enter = lock_irq, .leave = restore_irq};
    Lfj8H03TorqueCan link;
    assert(!lfj8_h03_torque_can_init(&link, 0x8000u, 10000u, 2u));
    assert(lfj8_h03_torque_can_init(&link, 4000u, 10000u, 2u));

    /* Even a claimed software lease cannot bypass a stock slot IRQ. */
    assert(poll(&link, &io, 0u, false, false, 1, 1u) == LFJ8_H03_TORQUE_CAN_UNAVAILABLE);
    can.irq_mask = 0x8003;
    can.ext_id = 4;
    assert(poll(&link, &io, 100u, false, false, 1, 1u) == LFJ8_H03_TORQUE_CAN_UNAVAILABLE);
    can.ext_id = 0;
    can.global_mask = 0x18;
    assert(poll(&link, &io, 200u, false, false, 1, 1u) == LFJ8_H03_TORQUE_CAN_UNAVAILABLE);
    assert(!can.writes);

    can.global_mask = 0x1f;
    assert(poll(&link, &io, 2000u, false, false, 1, 1u) == LFJ8_H03_TORQUE_CAN_RESERVED);
    status(&can, 2100u, 0, 0, 0, 0);
    poll(&link, &io, 4000u, false, false, 1, 1u);
    status(&can, 4100u, 0, 0, 0, 0);
    poll(&link, &io, 5000u, false, false, 1, 1u);
    assert(link.request.have_status && link.request.armed);
    poll(&link, &io, 6000u, true, false, 1, 1u);
    expect_request(&can, 1, 1);
    assert(poll(&link, &io, 8000u, true, true, 1, 1u) == LFJ8_H03_TORQUE_CAN_RESERVED);

    finish(&can, 9000u);
    assert(poll(&link, &io, 10000u, true, true, 1, 1u) == LFJ8_H03_TORQUE_CAN_RELEASED);
    const uint8_t telemetry[8] = {0};
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, telemetry) == LFJ8_CAN_SUBMITTED);
    assert(poll(&link, &io, 12000u, true, true, 1, 1u) == LFJ8_H03_TORQUE_CAN_RESERVED);
    finish(&can, 13000u);

    poll(&link, &io, 14000u, true, false, 1, 1u);
    /* An old status inside the general RX age window predates START completion. */
    status(&can, 8998u, 0x72, 1, 32, 1);
    poll(&link, &io, 16000u, true, false, 1, 1u);
    assert(!link.request.have_ack);
    status(&can, 17000u, 0x72, 1, 32, 1);
    poll(&link, &io, 18000u, true, false, 1, 1u);
    assert(link.request.full_reduction);

    poll(&link, &io, 22000u, false, false, 1, 1u);
    expect_request(&can, 0, 2);
    finish(&can, 23000u);
    poll(&link, &io, 24000u, false, false, 1, 1u);
    status(&can, 25000u, 0x04, 2, 0, 1);
    poll(&link, &io, 26000u, false, false, 1, 1u);
    assert(link.request.phase == LFJ8_TORQUE_COMPLETE && !link.request.pending && can.sent == 3u);

    /* Restart after a drain. Pending TX plus a reporting gap requests abort.
     * Losing the lease blocks access until the owner's next generation. */
    can.control = 0;
    poll(&link, &io, 28000u, false, false, 1, 2u);
    poll(&link, &io, 30000u, false, false, 1, 2u);
    status(&can, 31000u, 0, 0, 0, 0);
    poll(&link, &io, 32000u, false, false, 1, 2u);
    poll(&link, &io, 34000u, true, false, 1, 2u);
    expect_request(&can, 1, 1);
    can.control = 0x82u;
    poll(&link, &io, 46000u, true, false, 1, 2u);
    assert(can.aborted == 1u && can.control == 2u && link.request.pending);
    const unsigned writes = can.writes;
    assert(poll(&link, &io, 48000u, true, false, 0, 2u) == LFJ8_H03_TORQUE_CAN_UNAVAILABLE);
    assert(poll(&link, &io, 50000u, true, false, 1, 2u) == LFJ8_H03_TORQUE_CAN_UNAVAILABLE);
    assert(can.writes == writes && !link.request.full_reduction);
    can.control = 0;
    assert(poll(&link, &io, 52000u, false, false, 1, 3u) == LFJ8_H03_TORQUE_CAN_RESERVED);
    assert(!link.lease_lost && !link.request.pending && !link.request.have_status);

    puts("H03 torque CAN13: lease, TX/RX switch, freshness, arbitration, release and restart PASS");
    return 0;
}
