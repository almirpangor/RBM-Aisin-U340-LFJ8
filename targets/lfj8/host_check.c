#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "lfj8_chery_tx.h"

typedef struct {
    uint32_t freshness;
    uint32_t interval;
    uint32_t formats;
    uint32_t capture_timer;
    uint16_t edge_count;
    uint16_t pulse_count;
    uint16_t can_control;
    uint16_t can_status;
    uint8_t slot_control;
    uint8_t can_mode;
    uint8_t last_sid[2];
    uint8_t last_dlc;
    uint8_t last_data[8];
    unsigned lock_count;
    unsigned lock_depth;
    unsigned writes;
    unsigned submissions;
    uint8_t slot_clear_fails;
} Fixture;

static uint32_t lock(void *context)
{
    Fixture *f = context;
    assert(f->lock_depth++ == 0u);
    ++f->lock_count;
    return 42u;
}

static void unlock(void *context, uint32_t state)
{
    Fixture *f = context;
    assert(state == 42u);
    assert(f->lock_depth-- == 1u);
}

static uint8_t read8(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock_depth == 1u);
    assert(address == 0x80105Du || address == 0x801018u);
    return address == 0x80105Du ? f->slot_control : f->can_mode;
}

static uint16_t read16(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock_depth == 1u);
    switch (address) {
    case 0x801000u: return f->can_control;
    case 0x801002u: return f->can_status;
    case 0x8061C4u: return f->edge_count;
    case 0x8061CCu: return f->pulse_count;
    default: assert(0); return 0;
    }
}

static uint32_t read32(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->lock_depth == 1u);
    switch (address) {
    case 0x80101Cu: return f->formats;
    case 0x8003E0u: return f->capture_timer;
    case 0x804EC4u: return f->freshness;
    case 0x806164u: return f->interval;
    default: assert(0); return 0;
    }
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    Fixture *f = context;
    assert(f->lock_depth == 1u);
    ++f->writes;
    switch (address) {
    case 0x80105Du:
        assert(value == 0u || value == 0x80u);
        f->slot_control = value == 0u && f->slot_clear_fails != 0u ? 2u : value;
        if (value == 0x80u) {
            ++f->submissions;
        }
        break;
    case 0x8011D0u:
    case 0x8011D1u:
        f->last_sid[address - 0x8011D0u] = value;
        break;
    case 0x8011D5u:
        f->last_dlc = value;
        break;
    default:
        assert(address >= 0x8011D6u && address <= 0x8011DDu);
        f->last_data[address - 0x8011D6u] = value;
        break;
    }
}

static void test_speed(void)
{
    assert(lfj8_vss_raw_1ae(26400u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(52800u, 2u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(105600u, 4u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(26400u, 1u, 1000000u, 2100000u, 2u, 3u, LFJ8_VSS_VALID) == 4200u);
    assert(lfj8_vss_raw_1ae(52800u, 4u, 1000000u, 2000000u, 1u, 2u, LFJ8_VSS_VALID) == 6000u);
    assert(lfj8_vss_raw_1ae(26401u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 5999u);
    assert(lfj8_vss_raw_1ae(1u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(0u, 0u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_STOPPED) == 0u);
    assert(lfj8_vss_raw_1ae(1u, 1u, 1000000u, 2000000u, 1u, 0u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(100u, 3u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(26400u, 1u, 1000000u, 2000000u, 1u, 1u, LFJ8_VSS_UNAVAILABLE) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(1u, 4u, UINT32_MAX, UINT32_MAX, UINT16_MAX, 1u, LFJ8_VSS_VALID) == 0xFFFFu);
    assert(lfj8_vss_raw_1ae(UINT32_MAX, 1u, 1000000u, 2000000u, 1u, UINT16_MAX, LFJ8_VSS_VALID) == 0u);
}

static void test_packers(void)
{
    uint8_t payload[8];
    Lfj8Chery1ae status = {0};
    const uint8_t expected_1ae[] = {0x0F, 0x00, 0x11, 0x0F, 0x00, 0x00, 0x17, 0x70};
    const uint8_t expected_300[] = {0x0F, 0x00, 0x40, 0x01, 0x00, 0x00, 0x00, 0x00};

    status.flag_fd18_4 = 1u;
    assert(lfj8_pack_1ae(payload, &status, 6000u) == 1u);
    assert(memcmp(payload, expected_1ae, sizeof payload) == 0);
    status.raw_fa5f = 128u;
    status.counter_f8e4 = 255u;
    assert(lfj8_pack_1ae(payload, &status, 6000u) == 0u && payload[5] == 254u);
    status.flag_e026_0 = 1u;
    assert(lfj8_pack_1ae(payload, &status, 0xFFFFu) == 0u && payload[5] == 255u);
    lfj8_pack_300(payload, 0x0Fu, 0u, 1u, -39, 1u);
    assert(memcmp(payload, expected_300, sizeof payload) == 0);
    lfj8_pack_300(payload, 0u, 0u, 0u, 300, 1u);
    assert(payload[3] == 144u);
    lfj8_pack_300(payload, 0u, 0u, 0u, -300, 1u);
    assert(payload[3] == 0u);
    lfj8_pack_300(payload, 0u, 0u, 0u, 0, 0u);
    assert(payload[3] == 255u);

    assert(lfj8_relay_mask('R') == 3u);
    assert(lfj8_relay_mask('L') == 2u);
    assert(lfj8_relay_mask('D') == 0u && lfj8_relay_mask('N') == 0u && lfj8_relay_mask('P') == 0u);
}

static void test_schedule(void)
{
    Lfj8CherySchedule schedule;
    lfj8_schedule_init(&schedule, UINT32_MAX - 4000u, 10000u, 30000u);
    assert(lfj8_schedule_poll(&schedule, 5998u) == 0u);
    assert(lfj8_schedule_poll(&schedule, 5999u) == LFJ8_DUE_1AE);
    assert(lfj8_schedule_poll(&schedule, 26999u) == (LFJ8_DUE_1AE | LFJ8_DUE_300));
    assert(lfj8_schedule_poll(&schedule, 26999u) == 0u);
    assert(lfj8_schedule_poll(&schedule, 36000u) == LFJ8_DUE_1AE);

    lfj8_schedule_init(&schedule, 100u, 0u, 200u);
    assert(lfj8_schedule_poll(&schedule, 300u) == LFJ8_DUE_300);
}

static void test_donor_io(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    const uint8_t payload[8] = {0, 1, 2, 3, 4, 5, 6, 7};
    const uint8_t blocked_values[] = {0x02u, 0x40u, 0x80u, 0x82u, 0x83u};

    f.interval = 26400u;
    f.pulse_count = 1u;
    f.freshness = 0x43610000u; /* 225.0f */
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_VALID);
    f.edge_count = 1u;
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);
    f.edge_count = 0u;
    f.freshness = 0x80000000u;
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);
    f.freshness = 0x7FC00000u;
    assert(lfj8_9e1b_capture_snapshot(&io).state == LFJ8_VSS_UNAVAILABLE);
    assert(f.lock_count == 4u);

    assert(lfj8_can0_slot13_submit(&io, 0u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_NOT_OWNED);
    assert(lfj8_can0_slot13_submit(&io, 1u, 0x123u, payload) == LFJ8_CAN_WRONG_FRAME);
    assert(f.lock_count == 4u);
    f.can_control = 1u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_CONTROLLER_UNAVAILABLE);
    f.can_control = 0u;
    f.can_status = 0x4000u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_CONTROLLER_UNAVAILABLE);
    f.can_status = 0u;
    f.formats = 0x40000u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_NOT_STANDARD);
    f.formats = 0u;
    f.can_mode = 2u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_CONTROLLER_UNAVAILABLE);
    f.can_mode = 0u;
    for (unsigned i = 0u; i < sizeof blocked_values; ++i) {
        f.slot_control = blocked_values[i];
        assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_BUSY);
    }
    assert(f.writes == 0u);
    f.slot_control = 0x81u;
    f.slot_clear_fails = 1u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SLOT_BUSY);
    assert(f.writes == 1u && f.submissions == 0u);
    f.slot_control = 0x81u;
    f.slot_clear_fails = 0u;
    assert(lfj8_can0_slot13_submit(&io, 1u, LFJ8_CAN_1AE, payload) == LFJ8_CAN_SUBMITTED);
    assert(f.last_sid[0] == 0x06u && f.last_sid[1] == 0x2Eu && f.last_dlc == 8u);
    assert(memcmp(f.last_data, payload, sizeof payload) == 0);
    assert(f.writes == 14u && f.submissions == 1u && f.lock_depth == 0u);
}

static void test_raw_capture(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    volatile Lfj8RawVss tracker;
    const uint32_t expiry = 500000u;
    Lfj8CaptureSnapshot sample;

    lfj8_9e1b_raw_vss_init(&tracker);
    f.capture_timer = UINT32_MAX - 149999u;
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    assert(lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
    f.capture_timer = 150000u;
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    sample = lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry);
    assert(sample.state == LFJ8_VSS_VALID && sample.pulse_window == 1u);
    assert(sample.interval_ticks == 300000u);
    assert(lfj8_vss_raw_1ae(sample.interval_ticks, 1u, 1000000u, 2000000u,
                           1u, 1u, sample.state) == 528u);
    f.capture_timer += expiry + 1u;
    assert(lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
    lfj8_9e1b_raw_vss_edge(&tracker, f.capture_timer, expiry);
    assert(lfj8_9e1b_raw_vss_snapshot(&tracker, &io, expiry).state == LFJ8_VSS_UNAVAILABLE);
}

static void test_pipeline(void)
{
    Fixture f = {0};
    const Lfj8RegisterIo io = {&f, read8, read16, read32, write8, lock, unlock};
    const Lfj8VehicleCalibration cal = {1000000u, 500000u, 2000000u, 1u, 1u};
    Lfj8CheryTxInputs inputs = {0};
    Lfj8CheryTx tx;
    volatile Lfj8RawVss vss;

    lfj8_chery_tx_init(&tx, 0u, 10000u, 30000u);
    lfj8_9e1b_raw_vss_init(&vss);
    lfj8_9e1b_raw_vss_edge(&vss, 0u, cal.vss_timeout_ticks);
    lfj8_9e1b_raw_vss_edge(&vss, 26400u, cal.vss_timeout_ticks);
    f.capture_timer = 26400u;
    inputs.status_1ae.flag_fd18_4 = 1u;
    inputs.status0_300 = 0x0Fu;
    inputs.flag_fd18_9 = 1u;
    inputs.atf_c = 80;
    inputs.atf_valid = 1u;

    assert(lfj8_chery_tx_poll(&tx, &io, 9999u, 1u, &vss, &cal, &inputs) == 0u);
    f.slot_control = 0x80u;
    assert(lfj8_chery_tx_poll(&tx, &io, 10000u, 1u, &vss, &cal, &inputs) == 0u);
    assert(tx.pending == LFJ8_DUE_1AE && tx.counter_f8e4 == 0u);
    f.slot_control = 0u;
    assert(lfj8_chery_tx_poll(&tx, &io, 10001u, 1u, &vss, &cal, &inputs) == LFJ8_DUE_1AE);
    assert(f.last_data[6] == 0x17u && f.last_data[7] == 0x70u && tx.counter_f8e4 == 1u);

    f.slot_control = 0x81u;
    assert(lfj8_chery_tx_poll(&tx, &io, 30000u, 1u, &vss, &cal, &inputs) == LFJ8_DUE_300);
    assert(f.last_sid[0] == 0x0Cu && f.last_sid[1] == 0u);
    assert(f.last_data[3] == 120u && tx.pending == LFJ8_DUE_1AE && tx.counter_f8e4 == 1u);
    f.slot_control = 0x81u;
    f.capture_timer += cal.vss_timeout_ticks + 1u;
    assert(lfj8_chery_tx_poll(&tx, &io, 30001u, 1u, &vss, &cal, &inputs) == LFJ8_DUE_1AE);
    assert(f.last_data[6] == 0xFFu && f.last_data[7] == 0xFFu && tx.counter_f8e4 == 2u);
    assert(lfj8_chery_tx_poll(&tx, &io, 40000u, 0u, &vss, &cal, &inputs) == 0u);
    assert(tx.pending == 0u && tx.counter_f8e4 == 0u && f.submissions == 3u);
}

int main(void)
{
    test_speed();
    test_packers();
    test_schedule();
    test_donor_io();
    test_raw_capture();
    test_pipeline();
    puts("LFJ8 host: VSS, Chery encoders, relays, schedule, CAN0 and integrated pipeline passed");
    return 0;
}
