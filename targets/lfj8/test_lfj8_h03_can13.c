#include "lfj8_h03_can13.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CNT = 0x801000, STAT = 0x801002, EXTID = 0x801004, TSTMP = 0x801008,
    SLIMK = 0x801010, MODE = 0x801018, GMSKS0 = 0x801028, GMSKS1 = 0x801029,
    MSC13 = 0x80105d, SLOT13 = 0x8011d0, OEM_STATE = 0x806ae6, TML0 = 0x8003e0,
};

typedef struct {
    Lfj8H03Can13 broker;
    CheryDtcState dtc;
    Lfj8H03DtcReceive head;
    Lfj8RegisterIo io;
    Lfj8RawVss vss;
    uint32_t time_us;
    uint32_t generation;
    uint16_t stat;
    uint16_t irq_mask;
    uint8_t slot[16];
    uint8_t control;
    bool lock;
    bool grant;
    bool demand;
    bool queued;
    bool busy_on_listener_pause;
    bool bus_off_before_tx_request;
    bool receive_starts_during_id_read;
    unsigned sent;
    unsigned aborts;
    unsigned writes;
} Fixture;

static uint16_t can_tick(uint32_t time_us)
{
    return (uint16_t)(0xff00u + time_us / 2u);
}

static uint16_t active_id(const Fixture *f)
{
    return (uint16_t)((uint16_t)f->slot[0] << 6 | f->slot[1]);
}

static uint8_t read8(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock);
    switch (address) {
        case OEM_STATE: return 6;
        case MODE: return 0;
        case GMSKS0: return 0x1f;
        case GMSKS1: return 0x3f;
        case MSC13: return f->control;
        default:
            assert(address >= SLOT13 && address < SLOT13 + 16u && !(f->control & 2u));
            if (address == SLOT13 + 1u && f->receive_starts_during_id_read) {
                f->control |= 2u;
                f->receive_starts_during_id_read = false;
            }
            return f->slot[address - SLOT13];
    }
}

static uint16_t read16(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock);
    switch (address) {
        case CNT: return 0x0008;
        case STAT: return f->stat;
        case EXTID: return 0;
        case TSTMP: return can_tick(f->time_us);
        case SLIMK: return f->irq_mask;
        default:
            assert(address == SLOT13 + 14u && !(f->control & 2u));
            return (uint16_t)((uint16_t)f->slot[14] << 8 | f->slot[15]);
    }
}

static uint32_t read32(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock && address == TML0);
    return f->time_us;
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    Fixture *f = context;
    assert(f->lock && f->grant && !(f->irq_mask & 4u) && !f->stat);
    ++f->writes;
    if (address != MSC13) {
        assert(address >= SLOT13 && address < SLOT13 + 14u && !f->control);
        f->slot[address - SLOT13] = value;
        if (f->bus_off_before_tx_request && address == SLOT13 + 13u) {
            f->stat = 0x4000u;
        }
    } else if (value == 0x0f) {
        assert(f->control == 0x80u || f->control == 0x82u);
        f->control &= 2u;
        ++f->aborts;
    } else if (value == 0x4e) {
        assert(f->control & 0x40u);
        f->control = 0x40;
    } else if (value == 0u && f->control == 0x40u && f->busy_on_listener_pause) {
        /* An asynchronous receive started before the listener could stop. */
        f->control = 0x42u;
    } else {
        assert(!(f->control & 2u) && (value == 0u || value == 0x40u || value == 0x80u));
        f->control = value;
        f->sent += value == 0x80u;
    }
}

static uint32_t enter(void *context)
{
    Fixture *f = context;
    assert(!f->lock);
    f->lock = true;
    return 17;
}

static void leave(void *context, uint32_t saved)
{
    Fixture *f = context;
    assert(f->lock && saved == 17u);
    f->lock = false;
}

static void init(Fixture *f, uint32_t period_1ae, uint32_t period_300)
{
    *f = (Fixture){.grant = true, .generation = 1, .irq_mask = 0x8003};
    f->io = (Lfj8RegisterIo){f, read8, read16, read32, write8, enter, leave};
    const Lfj8H03Can13Config config = {
        .period_1ae_us = period_1ae, .period_300_us = period_300,
        .torque_receive_age_bits = 4000, .diagnostic_receive_age_bits = 4000,
        .max_poll_gap_us = 10000, .bit_time_us = 2,
    };
    assert(lfj8_h03_can13_init(&f->broker, &config, UINT32_MAX - 199u));
    chery_dtc_init(&f->dtc);
}

static Lfj8H03Can13Result poll(Fixture *f, uint32_t time_us)
{
    static const Lfj8TorqueCalibration torque_cal = {.up = {[1] = {0x20, 32, 20}}};
    static const Lfj8VehicleCalibration vehicle = {1000000u, 10000u, 2000000u, 1, 1};
    static const Lfj8CheryTxInputs status = {
        .status_1ae = {.flag_fd18_4 = 1}, .atf_c = 70, .atf_valid = 1, .stopped = 1,
    };
    f->time_us = time_us;
    uint32_t now = UINT32_MAX - 199u + time_us;
    const Lfj8TorqueInput torque = {
        .demand = {(uint8_t)f->demand, 2, 3, 5},
        .captured_at_us = now, .engine_rpm = 2000, .observed_gear = 2, .permitted = true,
    };
    const Lfj8H03Can13Input input = {
        f->generation, now, UINT32_MAX - 5u + time_us / 100u, f->grant, &torque,
        &torque_cal, &f->dtc, f->queued ? &f->head : NULL, &f->vss, &vehicle, &status,
    };
    const Lfj8H03Can13Result result = lfj8_h03_can13_poll(&f->broker, &f->io, &input);
    assert(!f->lock);
    if (result.diagnostic_consumed) {
        assert(f->queued);
        f->queued = false;
    }
    return result;
}

static void capture(Fixture *f, uint32_t time_us, const uint8_t *bytes, uint8_t length)
{
    assert(!f->queued);
    f->head = (Lfj8H03DtcReceive){
        .frame = {.id = CHERY_DTC_CAN_REQUEST_ID, .length = length},
        .generation = f->generation, .can_timestamp = can_tick(time_us),
    };
    memcpy(f->head.frame.data, bytes, length);
    f->queued = true;
}

static void stamp(Fixture *f, uint32_t time_us)
{
    const uint16_t timestamp = can_tick(time_us);
    f->slot[14] = (uint8_t)(timestamp >> 8);
    f->slot[15] = (uint8_t)timestamp;
}

static void finish(Fixture *f, uint32_t time_us)
{
    assert((f->control & 0x82u) != 0u);
    stamp(f, time_us);
    f->control = 0x81;
}

static void torque_status(Fixture *f, uint32_t time_us, uint8_t phase,
                          uint8_t seq, uint8_t reduction, uint8_t token)
{
    assert(f->control == 0x40u && active_id(f) == LFJ8_TORQUE_STATUS_ID);
    uint8_t status[8] = {0xa4u, phase, seq, reduction, token, 0, 0, 0};
    uint8_t crc = 0xff;
    for (unsigned i = 0; i < 7; ++i) {
        crc ^= status[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1du : 0u));
        }
    }
    status[7] = (uint8_t)(crc ^ 0xffu);
    memcpy(&f->slot[6], status, sizeof(status));
    stamp(f, time_us);
    f->control = 0x41;
}

static void start_torque(Fixture *f)
{
    assert(poll(f, 0).available);
    poll(f, 100);
    torque_status(f, 120, 0, 0, 0, 0);
    poll(f, 300);
    f->demand = true;
    poll(f, 500);
    assert(active_id(f) == LFJ8_TORQUE_REQUEST_ID && f->slot[7] == 1 && f->slot[8] == 1);
}

static void test_torque_priority_and_cancel(void)
{
    Fixture f;
    init(&f, 2000, 0);
    start_torque(&f);
    capture(&f, 600, (const uint8_t[]){2, 0x10, 0x86}, 3);
    assert(!poll(&f, 800).diagnostic_consumed);
    finish(&f, 900);
    assert(!poll(&f, 1000).diagnostic_consumed);
    torque_status(&f, 1400, 0x72, 1, 32, 1);
    const Lfj8H03Can13Result loan = poll(&f, 2500);
    assert(loan.status_submitted == LFJ8_DUE_1AE && !loan.diagnostic_consumed);
    assert(active_id(&f) == LFJ8_CAN_1AE && f.broker.torque.request.full_reduction);
    assert(f.broker.status.counter_f8e4 == 1u);
    f.control = 0x82;
    f.demand = false;
    poll(&f, 2600);
    assert(f.aborts == 1 && f.control == 2 && !f.broker.torque.request.full_reduction);
    assert(f.broker.torque.request.phase == LFJ8_TORQUE_RELEASING);
    poll(&f, 2700);
    assert(f.aborts == 1 && f.sent == 2 && f.queued);
    f.control = 0;
    poll(&f, 2800);
    assert(f.broker.status.counter_f8e4 == 0u);
    assert(active_id(&f) == LFJ8_TORQUE_REQUEST_ID && f.slot[7] == 0 && f.slot[8] == 2);
    finish(&f, 3100);
    poll(&f, 3200);
    torque_status(&f, 3400, 4, 2, 0, 1);
    assert(poll(&f, 3500).diagnostic_consumed && active_id(&f) == CHERY_DTC_CAN_REPLY_ID);
    assert(f.broker.torque.request.phase == LFJ8_TORQUE_COMPLETE);
    assert(f.slot[7] == 0x50 && f.sent == 4);
}

static void test_telemetry_loan_expires_before_slot_is_idle(void)
{
    Fixture f;
    init(&f, 2000, 0);
    start_torque(&f);
    finish(&f, 900);
    poll(&f, 1000);
    torque_status(&f, 1400, 0x72, 1, 32, 1);
    assert(poll(&f, 2500).status_submitted == LFJ8_DUE_1AE);
    assert(f.broker.torque.request.full_reduction && f.broker.status.counter_f8e4 == 1u);

    f.control = 0x82;
    const uint32_t deadline = 2500u + f.broker.torque.max_poll_gap_us;
    assert(poll(&f, deadline - 1u).available && !f.aborts);
    assert(f.broker.torque.request.full_reduction);
    assert(poll(&f, deadline).available && f.aborts == 1 && f.control == 2);
    assert(!f.broker.torque.request.full_reduction);
    assert(f.broker.torque.request.phase == LFJ8_TORQUE_RELEASING);
    assert(f.broker.status_in_flight == LFJ8_DUE_1AE);

    poll(&f, deadline + 100u);
    assert(f.aborts == 1 && f.sent == 2 && !f.broker.torque.request.full_reduction);
    f.control = 0;
    assert(poll(&f, deadline + 200u).available);
    assert(f.broker.status.counter_f8e4 == 0u);
    assert(active_id(&f) == LFJ8_TORQUE_REQUEST_ID && f.slot[7] == 0 && f.slot[8] == 2);
}

static void test_bus_off_during_telemetry_submission(void)
{
    Fixture f;
    init(&f, 2000, 0);
    start_torque(&f);
    finish(&f, 900);
    poll(&f, 1000);
    torque_status(&f, 1400, 0x72, 1, 32, 1);

    /* The new torque confirmation opens the telemetry window in this poll.
     * Inject BusOff after staging 0x1AE, before arming transmission. */
    f.bus_off_before_tx_request = true;
    const Lfj8H03Can13Result result = poll(&f, 2500);
    assert(f.stat == 0x4000u && active_id(&f) == LFJ8_CAN_1AE);
    assert(f.sent == 1u && f.control == 0u && f.broker.status.counter_f8e4 == 0u);
    assert(!result.available && f.broker.lease_lost && !result.status_submitted);
    assert(!f.broker.torque.request.full_reduction);

    f.bus_off_before_tx_request = false;
    f.stat = 0;
    const unsigned writes = f.writes;
    assert(!poll(&f, 2600).available && f.writes == writes);
    f.demand = false;
    ++f.generation;
    assert(poll(&f, 2700).available && f.control == 0x40 && !f.broker.lease_lost);
}

static void test_bus_off_during_torque_refresh(void)
{
    Fixture f;
    init(&f, 0, 0);
    start_torque(&f);
    finish(&f, 900);
    poll(&f, 1000);
    torque_status(&f, 1400, 0x72, 1, 32, 1);
    assert(poll(&f, 1500).available && f.broker.torque.request.full_reduction);
    assert(poll(&f, 8000).available);
    assert(poll(&f, 16000).available);

    f.bus_off_before_tx_request = true;
    const Lfj8H03Can13Result result = poll(&f, 20500);
    assert(f.stat == 0x4000u && active_id(&f) == LFJ8_TORQUE_REQUEST_ID);
    assert(f.slot[7] == 2u && f.sent == 1u && f.control == 0u);
    assert(!result.available && f.broker.lease_lost && f.broker.torque.lease_lost);
    assert(!f.broker.torque.request.full_reduction && !f.broker.torque.request.have_status);
    assert(!f.broker.torque.request.pending && f.broker.torque.request.tx_seq == 1u);
    assert(f.broker.torque.request.phase == LFJ8_TORQUE_RELEASING);

    f.bus_off_before_tx_request = false;
    f.stat = 0;
    const unsigned writes = f.writes;
    assert(!poll(&f, 20600).available && f.writes == writes);
    ++f.generation;
    assert(poll(&f, 20700).available && f.control == 0x40 && !f.broker.lease_lost);
    assert(poll(&f, 20800).available && f.sent == 1u && !f.broker.torque.request.have_status);
    f.demand = false;
    torque_status(&f, 20900, 0, 0, 0, 0);
    assert(poll(&f, 21000).available && f.broker.torque.request.have_status);
    f.demand = true;
    assert(poll(&f, 21100).available && f.sent == 2u && f.slot[7] == 1u && f.slot[8] == 1u);
}

static void test_torque_retries_when_listener_is_busy(void)
{
    Fixture f;
    init(&f, 0, 0);
    assert(poll(&f, 0).available);
    poll(&f, 100);
    torque_status(&f, 120, 0, 0, 0, 0);
    poll(&f, 300);

    f.demand = true;
    f.busy_on_listener_pause = true;
    assert(poll(&f, 500).available && f.control == 0x42u);
    assert(!f.broker.lease_lost && !f.broker.torque.lease_lost);
    assert(f.sent == 0u && !f.broker.torque.request.pending && f.broker.torque.request.tx_seq == 0u);

    f.busy_on_listener_pause = false;
    f.control = 0x40u;
    assert(poll(&f, 600).available && f.sent == 1u && f.broker.torque.request.pending);
    assert(active_id(&f) == LFJ8_TORQUE_REQUEST_ID && f.slot[7] == 1u && f.slot[8] == 1u);
}

static void test_diagnostic_flow_and_status_handoff(void)
{
    Fixture f;
    init(&f, 1000, 1500);
    assert(chery_dtc_store_snapshot(&f.dtc, 0, 0x10));
    assert(chery_dtc_store_snapshot(&f.dtc, 1, 0x12));
    poll(&f, 0);
    capture(&f, 400, (const uint8_t[]){2, 0x10, 0x86}, 3);
    assert(poll(&f, 500).diagnostic_consumed);
    finish(&f, 700);
    poll(&f, 750);
    capture(&f, 950, (const uint8_t[]){3, 0x17, 0xff, 0}, 4);
    const Lfj8H03Can13Result first = poll(&f, 1000);
    assert(first.diagnostic_consumed && !first.status_submitted);
    assert(active_id(&f) == CHERY_DTC_CAN_REPLY_ID && f.slot[6] == 0x10);
    capture(&f, 1004, (const uint8_t[]){0x30, 0, 0}, 3);
    assert(!poll(&f, 1100).diagnostic_consumed);
    finish(&f, 1200);
    const Lfj8H03Can13Result early = poll(&f, 1250);
    assert(early.diagnostic_consumed && early.status_submitted == LFJ8_DUE_1AE);
    assert(f.broker.diagnostic.link.phase == CHERY_DTC_LINK_AWAITING_FLOW_CONTROL);
    capture(&f, 1300, (const uint8_t[]){0x30, 0, 0}, 3);
    assert(!poll(&f, 1400).diagnostic_consumed && active_id(&f) == LFJ8_CAN_1AE);
    finish(&f, 1450);
    const Lfj8H03Can13Result continued = poll(&f, 1500);
    assert(continued.diagnostic_consumed && !continued.status_submitted);
    assert(active_id(&f) == CHERY_DTC_CAN_REPLY_ID && f.slot[6] == 0x21);
    assert(f.broker.status.counter_f8e4 == 1u);
    finish(&f, 1550);
    assert(poll(&f, 1600).status_submitted == LFJ8_DUE_300 && active_id(&f) == LFJ8_CAN_300);
}

static void test_timeout_and_generation(void)
{
    Fixture f;
    init(&f, 0, 0);
    f.irq_mask |= 4u;
    assert(!poll(&f, 0).available && !f.writes);
    f.irq_mask &= (uint16_t)~4u;
    capture(&f, 190, (const uint8_t[]){2, 0x10, 0x86}, 3);
    assert(poll(&f, 200).diagnostic_consumed);
    f.control = 0x82;
    poll(&f, 7500);
    poll(&f, 15000);
    poll(&f, 18100);
    assert(!f.aborts);
    poll(&f, 18200);
    assert(f.aborts == 1 && f.control == 2 && f.sent == 1);
    f.stat = 0x4000;
    const unsigned writes = f.writes;
    assert(!poll(&f, 18300).available && f.broker.lease_lost && f.writes == writes);
    f.stat = 0;
    f.control = 0;
    assert(!poll(&f, 18400).available && f.writes == writes);
    capture(&f, 18450, (const uint8_t[]){2, 0x10, 0x86}, 3);
    ++f.generation;
    assert(poll(&f, 18500).diagnostic_consumed && f.sent == 1);
    capture(&f, 18550, (const uint8_t[]){2, 0x10, 0x86}, 3);
    assert(poll(&f, 18600).diagnostic_consumed && f.sent == 2);
}

static void test_receive_lease_loss_requires_generation(void)
{
    Fixture f;
    init(&f, 0, 0);
    start_torque(&f);
    finish(&f, 900);
    poll(&f, 1000);
    torque_status(&f, 1400, 0x72, 1, 32, 1);
    assert(poll(&f, 1500).available);
    assert(f.control == 0x40 && f.broker.torque.request.full_reduction &&
           !f.broker.torque.request.pending);
    const unsigned writes = f.writes;
    f.stat = 0x4000;
    assert(!poll(&f, 1600).available && !f.broker.torque.request.full_reduction);
    f.stat = 0;
    assert(!poll(&f, 1700).available && f.writes == writes && f.broker.lease_lost);
    f.control = 0;
    f.demand = false;
    ++f.generation;
    assert(poll(&f, 1800).available && f.control == 0x40);
    assert(!f.broker.torque.request.have_status && !f.broker.lease_lost);
}

static void test_status_timeout_and_wrong_completion(void)
{
    Fixture f;
    init(&f, 1000, 0);
    poll(&f, 0);
    assert(poll(&f, 1000).status_submitted == LFJ8_DUE_1AE);
    f.control = 0x82;
    assert(poll(&f, 10999).available && !f.aborts);
    assert(poll(&f, 11000).available && f.aborts == 1 && f.control == 2);
    const unsigned writes = f.writes;
    finish(&f, 11050);
    f.slot[0] = CHERY_DTC_CAN_REPLY_ID >> 6;
    f.slot[1] = CHERY_DTC_CAN_REPLY_ID & 0x3f;
    assert(!poll(&f, 11100).available && f.broker.lease_lost && f.writes == writes);
}

static void test_foreign_queued_tx_is_not_aborted(void)
{
    Fixture f;
    init(&f, 2000, 0);
    start_torque(&f);
    finish(&f, 900);
    poll(&f, 1000);
    torque_status(&f, 1400, 0x72, 1, 32, 1);
    assert(poll(&f, 2500).status_submitted == LFJ8_DUE_1AE);
    assert(f.broker.torque.request.full_reduction && f.control == 0x80u);

    /* A different sender now owns the waiting request, without TRSTAT. */
    f.slot[0] = CHERY_DTC_CAN_REPLY_ID >> 6;
    f.slot[1] = CHERY_DTC_CAN_REPLY_ID & 0x3fu;
    const unsigned writes = f.writes;
    const uint32_t deadline = 2500u + f.broker.torque.max_poll_gap_us;
    assert(!poll(&f, deadline).available && f.broker.lease_lost);
    assert(!f.broker.torque.request.full_reduction);
    assert(f.control == 0x80u && !f.aborts && f.writes == writes);
    assert(active_id(&f) == CHERY_DTC_CAN_REPLY_ID);
}

static void test_foreign_listener_keeps_its_slot(void)
{
    Fixture f;
    init(&f, 0, 0);
    assert(poll(&f, 0).available);
    f.slot[0] = CHERY_DTC_CAN_REPLY_ID >> 6;
    f.slot[1] = CHERY_DTC_CAN_REPLY_ID & 0x3fu;
    const unsigned writes = f.writes;
    assert(lfj8_h03_can0_torque_yield(&f.io, 1u) == LFJ8_CAN_SLOT_NOT_OWNED);
    assert(!poll(&f, 100).available && f.broker.lease_lost);
    assert(f.control == 0x40u && f.writes == writes);
    assert(active_id(&f) == CHERY_DTC_CAN_REPLY_ID);
}

static void test_listener_busy_during_id_read(void)
{
    Fixture f;
    init(&f, 0, 0);
    assert(poll(&f, 0).available);
    f.receive_starts_during_id_read = true;
    const unsigned writes = f.writes;
    assert(lfj8_h03_can0_torque_yield(&f.io, 1u) == LFJ8_CAN_SLOT_BUSY);
    assert(f.control == 0x42u && f.writes == writes);
    assert(poll(&f, 100).available && !f.broker.lease_lost);
    f.control = 0x40u;
    assert(lfj8_h03_can0_torque_yield(&f.io, 1u) == LFJ8_CAN_READY && !f.control);
}

int main(void)
{
    test_torque_priority_and_cancel();
    test_telemetry_loan_expires_before_slot_is_idle();
    test_bus_off_during_telemetry_submission();
    test_bus_off_during_torque_refresh();
    test_torque_retries_when_listener_is_busy();
    test_diagnostic_flow_and_status_handoff();
    test_timeout_and_generation();
    test_receive_lease_loss_requires_generation();
    test_status_timeout_and_wrong_completion();
    test_foreign_queued_tx_is_not_aborted();
    test_foreign_listener_keeps_its_slot();
    test_listener_busy_during_id_read();
    puts("H03 CAN13 broker: torque preemption, diagnostic FC and generation recovery PASS");
    return 0;
}
