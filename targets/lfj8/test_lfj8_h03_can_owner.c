#include "lfj8_h03_can_owner.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CNT = 0x801000, STAT = 0x801002, EXTID = 0x801004, TSTMP = 0x801008,
    SLIST = 0x80100c, SLIMK = 0x801010, MODE = 0x801018,
    GMSKS0 = 0x801028, GMSKS1 = 0x801029, MSC13 = 0x80105d, MSC14 = 0x80105e,
    MSC15 = 0x80105f, SLOT13 = 0x8011d0, SLOT14 = 0x8011e0,
    OEM_STATE = 0x806ae6,
};

typedef struct {
    Lfj8H03Can13 broker;
    Lfj8H03DtcRxQueue queue;
    CheryDtcState dtc;
    Lfj8RegisterIo io;
    Lfj8RawVss vss;
    uint32_t now_us;
    unsigned locks;
    unsigned sends;
    uint16_t stat;
    uint16_t slist;
    uint16_t slimk;
    uint8_t msc[3];
    uint8_t slots[2][16];
    bool irq_after_grant;
    bool demand;
} Fixture;

Lfj8H03CanOwner h03_can_owner;

static uint16_t can_tick(const Fixture *f)
{
    return (uint16_t)(f->now_us / 2u);
}

static bool capture(Fixture *f)
{
    assert(f->locks == 0u);
    uint32_t generation;
    if (!lfj8_h03_can_owner_rx_epoch(&h03_can_owner, &generation)) {
        return false;
    }
    return lfj8_h03_dtc_rx_queue_capture_basic(&f->queue, &f->io, 14, generation,
                                               f->now_us, can_tick(f)) == LFJ8_H03_DTC_RX_QUEUED;
}

static void stage_request(Fixture *f)
{
    const uint16_t stamp = can_tick(f);
    const uint8_t bytes[16] = {
        0x1c, 0x32, 0, 0, 0, 3, 2, 0x10, 0x86, 0, 0, 0, 0, 0,
        (uint8_t)(stamp >> 8), (uint8_t)stamp,
    };
    memcpy(f->slots[1], bytes, sizeof(bytes));
    f->msc[1] = 0x41;
    f->slist |= 2u;
}

static bool dispatch_irq(Fixture *f)
{
    const bool queued = capture(f);
    f->msc[1] = 0x40;
    f->msc[2] = 0x40;
    f->slist &= (uint16_t)~3u;
    return queued;
}

static uint8_t read8(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->locks);
    switch (address) {
        case OEM_STATE: return 7;
        case MODE: return 0;
        case GMSKS0: return 0x1f;
        case GMSKS1: return 0x3f;
        case MSC13:
        case MSC14:
        case MSC15: return f->msc[address - MSC13];
        default:
            assert(address >= SLOT13 && address < SLOT14 + 16u);
            return f->slots[(address - SLOT13) / 16u][address % 16u];
    }
}

static uint16_t read16(void *context, uint32_t address)
{
    Fixture *f = context;
    switch (address) {
        case CNT: return 8;
        case STAT: return f->stat;
        case EXTID: return 0;
        case TSTMP: return can_tick(f);
        case SLIST: return f->slist;
        case SLIMK: return f->slimk;
        default:
            return (uint16_t)((uint16_t)read8(context, address) << 8) |
                   read8(context, address + 1u);
    }
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    Fixture *f = context;
    assert(f->locks && h03_can_owner.grant == 1u);
    if (address == MSC13) {
        f->msc[0] = value == 0x4e ? 0x40 : value;
        f->sends += value == 0x80;
    } else {
        assert(address >= SLOT13 && address < SLOT13 + 14u);
        f->slots[0][address - SLOT13] = value;
    }
}

static uint32_t enter(void *context)
{
    Fixture *f = context;
    return f->locks++;
}

static void leave(void *context, uint32_t saved)
{
    Fixture *f = context;
    assert(f->locks == saved + 1u);
    f->locks = saved;
    if (!saved && f->irq_after_grant && h03_can_owner.grant == 1u) {
        f->irq_after_grant = false;
        assert(f->queue.generation == h03_can_owner.setup_generation && !f->queue.count);
        stage_request(f);
        assert(dispatch_irq(f));
    }
}

static void setup(void)
{
#if defined(__m32r__)
    extern void h03_can0_setup_hook(void);
    h03_can0_setup_hook();
#else
    h03_can_owner.grant = 0u;
    ++h03_can_owner.setup_generation;
#endif
}

#if defined(__m32r__)
void h03_oem_can0_setup(void)
{
    assert(!h03_can_owner.grant);
}
#endif

static void init(Fixture *f, uint32_t period_300)
{
    *f = (Fixture){.stat = 0x0800, .slimk = 0x8003, .msc = {0, 0x40, 0x40}};
    f->io = (Lfj8RegisterIo){.context = f, .read8 = read8, .read16 = read16,
                           .write8 = write8, .enter = enter, .leave = leave};
    const Lfj8H03Can13Config config = {
        .period_300_us = period_300, .torque_receive_age_bits = 4000,
        .diagnostic_receive_age_bits = 4000, .max_poll_gap_us = 10000, .bit_time_us = 2,
    };
    lfj8_h03_can_owner_init(&h03_can_owner);
    assert(lfj8_h03_can13_init(&f->broker, &config, 0));
    assert(lfj8_h03_dtc_rx_queue_init(&f->queue, 0, 4000, 2));
    chery_dtc_init(&f->dtc);
}

static Lfj8H03Can13Result poll(Fixture *f, uint32_t now_us, bool native_ready)
{
    static const Lfj8TorqueCalibration cal = {.up = {[1] = {0x20, 32, 20}}};
    static const Lfj8VehicleCalibration vehicle = {0};
    static const Lfj8CheryTxInputs status = {.atf_valid = 1};
    const Lfj8TorqueInput torque = {
        .demand = {(uint8_t)f->demand, 2, 3, 5}, .captured_at_us = now_us,
        .engine_rpm = 2000, .observed_gear = 2, .permitted = true,
    };
    f->now_us = now_us;
    const uint16_t stamp = can_tick(f);
    Lfj8H03Can13Input input = {
        .generation = 42, .owns_slot13 = 17, .now_us = now_us, .diagnostic_tick = now_us / 100u,
        .torque = &torque, .torque_calibration = &cal, .dtc = &f->dtc,
        .vss = &f->vss, .vehicle = &vehicle, .status = &status,
    };
    const Lfj8H03Can13Result result = lfj8_h03_can_owner_poll(
        &h03_can_owner, &f->broker, &f->queue, &f->io, &input, &stamp, native_ready);
    assert(!f->locks && input.generation == 42u && input.owns_slot13 == 17u);
    return result;
}

static void finish(Fixture *f, uint32_t now_us)
{
    f->now_us = now_us;
    const uint16_t stamp = can_tick(f);
    f->slots[0][14] = (uint8_t)(stamp >> 8);
    f->slots[0][15] = (uint8_t)stamp;
    f->msc[0] = 0x81;
}

static void test_reset_and_irq_orders(void)
{
    Fixture f;
    init(&f, 1000);
    assert(!poll(&f, 0, true).available && !f.sends);
    setup();
    assert(poll(&f, 100, true).available);

    /* IRQ before foreground. Establish the diagnostic session. */
    f.now_us = 200;
    stage_request(&f);
    assert(dispatch_irq(&f));
    assert(poll(&f, 220, true).diagnostic_consumed && f.sends == 1u);
    assert(f.slots[0][7] == 0x50);
    finish(&f, 250);
    assert(poll(&f, 300, true).available);
    assert(f.broker.diagnostic.link.session.permission_bits == 8u);
    assert(poll(&f, 1100, true).status_submitted == LFJ8_DUE_300);
    assert(f.sends == 2u);
    f.now_us = 1200;
    stage_request(&f);
    assert(dispatch_irq(&f) && f.queue.count == 1u);

    setup();
    assert(!h03_can_owner.grant);
    stage_request(&f);
    f.msc[2] = 0x45;
    assert(!poll(&f, 1220, true).available && f.queue.count == 1u);
    assert(f.broker.diagnostic.link.session.permission_bits == 0x11u);
    assert(!dispatch_irq(&f) && f.queue.count == 1u);
    assert(!poll(&f, 1230, true).available && f.sends == 2u); /* TX still pending. */
    finish(&f, 1250);
    f.slist = 1u;
    assert(!poll(&f, 1260, true).available && !h03_can_owner.grant);
    f.slist = 0;
    f.irq_after_grant = true;
    assert(!poll(&f, 1270, false).available && f.irq_after_grant);
    /* Foreground grants, then IRQ interrupts before the broker consumes. */
    assert(poll(&f, 1280, true).diagnostic_consumed && f.sends == 3u);
    assert(!f.irq_after_grant && !f.queue.count && f.queue.next_ticket == 3u);
    assert(f.slots[0][7] == 0x50);
    assert(f.broker.generation == 2u);

    finish(&f, 1300);
    f.slots[0][0] = 0x231u >> 6;
    f.slots[0][1] = 0x231u & 0x3fu;
    assert(!poll(&f, 1310, true).available && !h03_can_owner.grant);
    assert(f.broker.diagnostic.link.session.permission_bits == 0x11u);
    f.msc[0] = 0;
    assert(!poll(&f, 1320, true).available && f.sends == 3u);
}

static void test_torque_fault_and_generation_wrap(void)
{
    Fixture f;
    init(&f, 0);
    h03_can_owner.setup_generation = UINT32_MAX - 1u;
    h03_can_owner.admitted_generation = UINT32_MAX - 1u;
    setup();
    assert(!h03_can_owner.grant && h03_can_owner.setup_generation == UINT32_MAX);
    f.slimk |= 4u;
    assert(!poll(&f, 10, true).available);
    f.slimk &= (uint16_t)~4u;
    assert(poll(&f, 20, true).available);
    assert(h03_can_owner.grant && f.queue.generation == UINT32_MAX);
    assert(poll(&f, 80, true).available);

    /* An accepted heartbeat lets the broker start an RB torque request. */
    memcpy(&f.slots[0][6], (const uint8_t[]){0xa4, 0, 0, 0, 0, 0, 0, 0xad}, 8);
    finish(&f, 100);
    f.msc[0] = 0x41;
    assert(poll(&f, 150, true).available);
    f.demand = true;
    assert(poll(&f, 200, true).available && f.sends == 1u);
    assert(f.slots[0][7] == 1u);
    finish(&f, 250);
    assert(poll(&f, 300, true).available);

    memcpy(&f.slots[0][6], (const uint8_t[]){0xa4, 0x72, 1, 32, 1, 0, 0, 0xe2}, 8);
    finish(&f, 320);
    f.msc[0] = 0x41;
    assert(poll(&f, 350, true).available && f.broker.torque.request.full_reduction);

    /* BusOff revokes the confirmed reduction without accepting a new request. */
    f.stat |= 0x4000u;
    assert(!poll(&f, 400, true).available && !h03_can_owner.grant);
    assert(!f.broker.torque.request.full_reduction && f.broker.lease_lost);
    f.stat = 0x0800;
    f.msc[0] = 0;
    assert(!poll(&f, 500, true).available && f.sends == 1u);

    setup();
    stage_request(&f);
    assert(!poll(&f, 600, true).available);
    assert(!dispatch_irq(&f));
    assert(poll(&f, 700, true).available && f.queue.generation == 0u);
    assert(h03_can_owner.grant && f.sends == 1u && !f.broker.torque.request.have_status);
}

int main(void)
{
    test_reset_and_irq_orders();
    test_torque_fault_and_generation_wrap();
    printf("H03 CAN owner: setup, BasicCAN drain, both IRQ orders, TX13 and BusOff PASS\n");
    printf("CAN owner state: %u bytes\n", (unsigned)sizeof(Lfj8H03CanOwner));
    return 0;
}
