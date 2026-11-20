#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_dtc_target.h"
#include "lfj8_h03_mmio.h"

#define RAM8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define RAM16(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define RAM32(address) (*(volatile uint32_t *)(uintptr_t)(address))

enum {
    VOLTAGE = 0x804F04, DELTA = 0x805F10, MONITOR_TIMER = 0x805E8C,
    HIGH_REMAINING = 0x805EE4, LOW_REMAINING = 0x805EE8, GOOD_REMAINING = 0x805EFC,
    ACTIVE = 0x8063E7, HIGH = 0x8065EB, LOW = 0x8065EC, RECOVERED = 0x8065F0,
    ENABLE = 0x8065F3, SERVICE_CLEAR = 0x80637C, OEM_CLEAR = 0x072390,
    STEP_5000 = 0x459C4000, LONG_DELAY = 0x48127C00, RECOVERY_DELAY = 0x44FA0000,
    UPPER_LIMIT = 0x0165D8, LOWER_LIMIT = 0x0165DC, VOLTAGE_GOOD = 0x40000000,
    CNT = 0x801000, STAT = 0x801002, TIMESTAMP = 0x801008, TML0 = 0x8003E0,
    PRS1 = 0x800203, TML0_MODE = 0x8003EB, TML1_MODE = 0x800FEB,
    GMSKS0 = 0x801028, GMSKS1 = 0x801029,
    MSC13 = 0x80105d, MSC14 = 0x80105e, MSC15 = 0x80105f,
    TX = 0x8011d0, RX = 0x8011e0, OEM_STATE = 0x806ae6,
    ATF_BIT = 0x10, MAX_AGE = 8,
};

static CheryDtcState dtc;
static Lfj8H03DtcTarget target;
static Lfj8H03Can13 broker;
static Lfj8H03CanOwner owner;
static bool inhibit;
static bool capture_during_can;
static uint32_t diagnostic_tick;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;

/* Execute the word at the original OEM call site through its unmodified
 * continuation. The shim supplies the containing OEM frame's saved pair. */
void fixture_native_atf_turn(void);

static bool inhibit_history(void *context)
{
    (void)context;
    return inhibit;
}

static bool rx_epoch(void *context, uint32_t *generation)
{
    return lfj8_h03_can_owner_rx_epoch(context, generation);
}

static Lfj8H03Can13Result poll_owner(void *context, Lfj8H03Can13 *can13, Lfj8H03DtcRxQueue *queue,
                                    const Lfj8RegisterIo *io, Lfj8H03Can13Input *input,
                                    const uint16_t *can_now, bool native_ready)
{
    if (capture_during_can) {
        capture_during_can = false;
        fixture_native_atf_turn();
    }
    return lfj8_h03_can_owner_poll(context, can13, queue, io, input, can_now, native_ready);
}

static const Lfj8H03DtcCanOwnerOps owner_ops = {rx_epoch, poll_owner, &owner};
static const Lfj8H03DtcAtfConfig atf_config = {
    .max_age_us = MAX_AGE,
    .now_us_locked = rbm_h03_atf_now_us,
    .inhibit_history = inhibit_history,
};

static void qualify_clock(void)
{
    RAM8(PRS1) = 9;
    RAM8(TML0_MODE) = 0x01;
    RAM8(TML1_MODE) = 0x31;
    rbm_h03_tml0_1mhz_qualified = 1;
}

static void monitor(uint32_t voltage)
{
    RAM32(VOLTAGE) = voltage;
    RAM32(DELTA) = STEP_5000;
    RAM32(MONITOR_TIMER) = 0;
    fixture_native_atf_turn();
}

static void reset_native_monitor(void)
{
    RAM8(ACTIVE) = 0;
    RAM8(HIGH) = 0;
    RAM8(LOW) = 0;
    RAM8(RECOVERED) = 0;
    RAM8(ENABLE) = 1;
    RAM32(HIGH_REMAINING) = LONG_DELAY;
    RAM32(LOW_REMAINING) = LONG_DELAY;
    RAM32(GOOD_REMAINING) = RECOVERY_DELAY;
}

static Lfj8H03Can13Result poll(void)
{
    Lfj8H03Can13Input input = {.dtc = &dtc, .diagnostic_tick = diagnostic_tick++};
    return lfj8_h03_dtc_target_poll(&target, &input, true);
}

static bool bind_target(void)
{
    return lfj8_h03_dtc_target_init(&target, &broker, &lfj8_h03_mmio, &owner_ops,
                                   lfj8_h03_tml0ct_m32r, 4);
}

static bool rebind_atf(void)
{
    lfj8_h03_dtc_target_unbind();
    owner.grant = 0;
    /* Model the idle TX13 produced by the next OEM CAN setup. */
    RAM8(MSC13) = 0;
    ++owner.setup_generation;
    return bind_target() && lfj8_h03_dtc_target_enable_atf(&target, &atf_config);
}

static void qualify(uint32_t voltage)
{
    for (unsigned i = 0; i < 30; ++i) {
        monitor(voltage);
    }
}

static bool send(uint8_t service, uint8_t byte_a, uint8_t byte_b, uint8_t request_size,
                 const uint8_t *reply, uint8_t reply_size)
{
    const uint16_t time = ++RAM16(TIMESTAMP);
    RAM8(RX) = 0x1c;
    RAM8(RX + 1) = 0x32;
    RAM8(RX + 5) = (uint8_t)(request_size + 1);
    RAM8(RX + 6) = request_size;
    RAM8(RX + 7) = service;
    RAM8(RX + 8) = byte_a;
    RAM8(RX + 9) = byte_b;
    RAM16(RX + 14) = time;
    RAM8(MSC14) = 0x41;
    const uint32_t saved = lfj8_h03_mmio.enter(lfj8_h03_mmio.context);
    rbm_h03_dtc_rx_observe(14);
    lfj8_h03_mmio.leave(lfj8_h03_mmio.context, saved);
    RAM8(MSC14) = 0x40; /* Simulated hardware/OEM acknowledgement. */

    if (!poll().diagnostic_consumed || RAM8(MSC13) != 0x80 || RAM8(TX + 6) != reply_size) {
        return false;
    }
    for (uint8_t i = 0; i < reply_size; ++i) {
        if (RAM8(TX + 7 + i) != reply[i]) {
            return false;
        }
    }
    RAM16(TX + 14) = ++RAM16(TIMESTAMP);
    RAM8(MSC13) = 0x81; /* Transmit completion in the simulated slot. */
    return service == 0x14 || poll().available;
}

int main(void)
{
    const Lfj8H03Can13Config can_config = {
        .torque_receive_age_bits = 4000, .diagnostic_receive_age_bits = 100,
        .max_poll_gap_us = 5000, .bit_time_us = 2,
    };
    const uint8_t session_reply[] = {0x50, 0x86};
    const uint8_t empty_reply[] = {0x57, 0x00};
    const uint8_t active_reply[] = {0x57, 0x01, 0x07, 0x10, 0x74};
    const uint8_t recovered_reply[] = {0x57, 0x01, 0x07, 0x10, 0x54};
    const uint8_t clear_reply[] = {0x54, 0xff, 0x00};

    lfj8_h03_dtc_target_unbind();
    reset_native_monitor();
    qualify(RAM32(UPPER_LIMIT));
    if (!RAM8(ACTIVE) || dtc.current[0]) {
        return 1;
    }
    chery_dtc_init(&dtc);
    lfj8_h03_can_owner_init(&owner);
    owner.setup_generation = 1;
    RAM16(CNT) = 8;
    RAM16(STAT) = 0x0800;
    RAM8(OEM_STATE) = 6;
    RAM8(GMSKS0) = 0x1f;
    RAM8(GMSKS1) = 0x3f;
    RAM8(MSC14) = RAM8(MSC15) = 0x40;

    RAM32(TML0) = UINT32_MAX - (MAX_AGE + 5);
    if (!lfj8_h03_can13_init(&broker, &can_config, RAM32(TML0)) || !bind_target()) {
        return 2;
    }
    if (lfj8_h03_dtc_target_enable_atf(&target, &atf_config)) {
        return 15;
    }
    qualify_clock();
    if (!lfj8_h03_dtc_target_enable_atf(&target, &atf_config) || !poll().available ||
        !send(0x10, 0x86, 0, 2, session_reply, sizeof(session_reply))) {
        return 2;
    }
    if (dtc.current[0] || !send(0x17, 0xff, 0, 3, empty_reply, sizeof(empty_reply))) {
        return 3;
    }

    reset_native_monitor();
    for (unsigned i = 0; i < 29; ++i) {
        monitor(RAM32(UPPER_LIMIT));
        poll();
        if (dtc.current[0]) {
            return 4;
        }
    }
    monitor(RAM32(UPPER_LIMIT));
    RAM32(TML0) += MAX_AGE;
    poll();
    if (dtc.current[0]) {
        return 5;
    }
    RAM32(TML0) = UINT32_MAX - 1;
    monitor(RAM32(UPPER_LIMIT));
    RAM32(TML0) = 2;
    if (!send(0x17, 0xff, 0, 3, active_reply, sizeof(active_reply)) ||
        dtc.current[0] != ATF_BIT || dtc.snapshot_index[0] != 4) {
        return 6;
    }
    qualify(RAM32(LOWER_LIMIT));
    if (!RAM8(HIGH) || !RAM8(LOW) ||
        !send(0x17, 0xff, 0, 3, active_reply, sizeof(active_reply)) ||
        dtc.snapshot_index[1] != UINT8_MAX) {
        return 7;
    }
    monitor(VOLTAGE_GOOD);
    if (!send(0x17, 0xff, 0, 3, recovered_reply, sizeof(recovered_reply)) ||
        dtc.current[0] || dtc.history[0] != ATF_BIT) {
        return 8;
    }

    qualify(RAM32(LOWER_LIMIT));
    capture_during_can = true;
    if (!send(0x14, 0xff, 0, 3, clear_reply, sizeof(clear_reply)) || !dtc.clear_pending ||
        dtc.current[0] || dtc.history[0]) {
        return 9;
    }
    monitor(RAM32(LOWER_LIMIT));
    /* The application may consume the clear before the next DTC turn. */
    dtc.clear_pending = false;
    if (!send(0x17, 0xff, 0, 3, empty_reply, sizeof(empty_reply)) || dtc.current[0]) {
        return 10;
    }
    inhibit = true;
    monitor(RAM32(LOWER_LIMIT));
    if (!send(0x17, 0xff, 0, 3, empty_reply, sizeof(empty_reply)) ||
        dtc.current[0] != ATF_BIT || dtc.history[0]) {
        return 11;
    }

    reset_native_monitor();
    monitor(VOLTAGE_GOOD);
    void (*service_clear)(void) = (void (*)(void))(uintptr_t)OEM_CLEAR;
    RAM8(SERVICE_CLEAR) = 1;
    service_clear();
    monitor(RAM32(LOWER_LIMIT));
    poll();
    if (dtc.current[0] != ATF_BIT) {
        return 12;
    }
    reset_native_monitor();
    monitor(VOLTAGE_GOOD);
    if (!rebind_atf()) {
        return 13;
    }
    poll();
    if (dtc.current[0] != ATF_BIT) {
        return 14;
    }

    monitor(VOLTAGE_GOOD);
    RAM8(TML0_MODE) = 0x02;
    poll();
    if (rbm_h03_tml0_1mhz_qualified || dtc.current[0] != ATF_BIT || dtc.history[0]) {
        return 16;
    }
    qualify_clock();
    monitor(VOLTAGE_GOOD);
    if (lfj8_h03_dtc_target_enable_atf(&target, &atf_config) ||
        !send(0x10, 0x86, 0, 2, session_reply, sizeof(session_reply)) ||
        !send(0x17, 0xff, 0, 3, empty_reply, sizeof(empty_reply)) || dtc.current[0] != ATF_BIT) {
        return 17;
    }
    if (!rebind_atf() || !poll().available || dtc.current[0] != ATF_BIT) {
        return 18;
    }
    monitor(VOLTAGE_GOOD);
    if (!poll().available || dtc.current[0] || dtc.history[0]) {
        return 18;
    }

    inhibit = false;
    RAM8(TML1_MODE) = 0;
    reset_native_monitor();
    qualify(RAM32(LOWER_LIMIT));
    if (!RAM8(ACTIVE) || rbm_h03_tml0_1mhz_qualified) {
        return 19;
    }
    qualify_clock();
    if (!send(0x10, 0x86, 0, 2, session_reply, sizeof(session_reply)) ||
        !send(0x17, 0xff, 0, 3, empty_reply, sizeof(empty_reply)) ||
        dtc.current[0] || dtc.history[0]) {
        return 19;
    }
    if (!rebind_atf() || !poll().available ||
        !send(0x10, 0x86, 0, 2, session_reply, sizeof(session_reply))) {
        return 20;
    }
    monitor(RAM32(LOWER_LIMIT));
    if (!send(0x17, 0xff, 0, 3, active_reply, sizeof(active_reply)) ||
        dtc.current[0] != ATF_BIT || dtc.history[0] != ATF_BIT) {
        return 20;
    }
    return 0;
}
