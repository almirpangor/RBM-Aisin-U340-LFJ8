#include "lfj8_h03_torque.h"
#include "factory_hydraulics.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const Lfj8TorqueCalibration bench_profile = {
    .up = {{0}, {.levels = 1u << 5, .reduction_q8 = 32, .duration = 20}, {0}},
};

static void set(FactoryHydraulics *gp, int address, unsigned size, uint32_t value)
{
    assert(factory_hydraulics_set(gp, address, size, value));
}

static FactoryHydraulics initial_gp(void)
{
    FactoryHydraulics gp = {.data = {0}};
    set(&gp, -4851, 1, 1);
    set(&gp, -4852, 1, 1);
    set(&gp, -4846, 1, 128);
    set(&gp, -4842, 1, 2);
    set(&gp, -4843, 1, 4);
    set(&gp, -4548, 1, 50);
    set(&gp, -4545, 1, 1);
    set(&gp, -7158, 2, UINT16_MAX);
    set(&gp, -7204, 2, 10000);
    set(&gp, -7208, 2, 10000);
    assert(factory_hydraulics_torque_main(&gp));
    return gp;
}

static void request_donor_upshift(FactoryHydraulics *gp)
{
    Lfj8TorqueDemand demand;
    set(gp, -4852, 1, 2);
    assert(factory_hydraulics_torque_main(gp));
    assert(lfj8_h03_torque_demand(gp, &demand) && !demand.active);
    set(gp, -4851, 1, 2);
    for (unsigned i = 0; i < 22; ++i) {
        factory_hydraulics_counters_begin(gp);
        factory_hydraulics_counters_end(gp);
        assert(factory_hydraulics_torque_main(gp));
    }
    assert(lfj8_h03_torque_demand(gp, &demand));
    assert(demand.active && demand.from_gear == 2 && demand.to_gear == 3 && demand.level == 5);
}

static Lfj8TorqueInput input(const FactoryHydraulics *gp, uint32_t now)
{
    Lfj8TorqueInput value = {.captured_at_us = now, .engine_rpm = 2000,
                            .observed_gear = 2, .permitted = true};
    assert(lfj8_h03_torque_demand(gp, &value.demand));
    return value;
}

typedef struct {
    bool refuse;
    unsigned submitted;
    uint8_t frame[8];
} CanFixture;

static bool transmit(void *context, uint16_t id, const uint8_t data[8])
{
    CanFixture *can = context;
    assert(id == LFJ8_TORQUE_REQUEST_ID);
    if (can->refuse) {
        return false;
    }
    ++can->submitted;
    memcpy(can->frame, data, 8);
    return true;
}

static bool status(Lfj8H03Torque *link, uint32_t tick, uint16_t token,
                   uint8_t phase, uint8_t mask, uint8_t seq, uint8_t q8, uint8_t reason)
{
    uint8_t data[8] = {0xa4, (uint8_t)(phase | mask << 4), seq, q8,
                       (uint8_t)token, (uint8_t)(token >> 8), reason, 0xff};
    for (unsigned i = 0; i < 7; ++i) {
        data[7] ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            uint8_t polynomial = data[7] & 0x80 ? 0x1d : 0;
            data[7] = (uint8_t)((data[7] << 1) ^ polynomial);
        }
    }
    data[7] ^= 0xffu;
    return lfj8_h03_torque_receive(link, LFJ8_TORQUE_STATUS_ID, 8, data, tick);
}

static void tick(Lfj8H03Torque *link, const FactoryHydraulics *gp, uint32_t now,
                 const Lfj8TorqueCalibration *cal, CanFixture *can)
{
    const Lfj8TorqueInput sample = input(gp, now);
    lfj8_h03_torque_poll(link, &sample, cal, now, transmit, can);
}

static void test_full_dialogue(void)
{
    Lfj8H03Torque link;
    CanFixture can = {0};
    FactoryHydraulics gp = initial_gp();
    const uint32_t start = UINT32_MAX - 10000u;
    lfj8_h03_torque_init(&link);
    assert(status(&link, start - 1, 0, 0, 0, 0, 0, 0));
    tick(&link, &gp, start - 1, &bench_profile, &can);
    request_donor_upshift(&gp);
    can.refuse = true;
    tick(&link, &gp, start, &bench_profile, &can);
    assert(!can.submitted && link.phase == LFJ8_TORQUE_WAITING);
    can.refuse = false;
    tick(&link, &gp, start, &bench_profile, &can);
    const uint8_t recorded_start[] = {0xa4, 1, 1, 32, 20, 1, 0, 0x99};
    assert(!memcmp(can.frame, recorded_start, 8));
    assert(status(&link, start + 1000, 1, 2, 7, 1, 32, 0));
    assert(!lfj8_h03_torque_applied(&link, start + 1000));
    lfj8_h03_torque_tx_done(&link, true, start + 1001);
    assert(status(&link, start + 1002, 1, 2, 7, 0, 32, 0));
    assert(!lfj8_h03_torque_applied(&link, start + 1002));
    assert(status(&link, start + 2000, 1, 1, 7, 1, 25, 0));
    assert(link.phase == LFJ8_TORQUE_ACTIVE && !lfj8_h03_torque_applied(&link, start + 2000));
    assert(status(&link, start + 3000, 1, 2, 7, 1, 32, 0));
    assert(lfj8_h03_torque_applied(&link, start + 3000));
    assert(!status(&link, start + 2999, 1, 1, 0, 1, 0, 0));
    tick(&link, &gp, start + 19999, &bench_profile, &can);
    assert(can.submitted == 1);
    tick(&link, &gp, start + 20000, &bench_profile, &can);
    assert(can.submitted == 2 && can.frame[1] == 2 && can.frame[2] == 2);
    lfj8_h03_torque_tx_done(&link, true, start + 20001);
    assert(status(&link, start + 21000, 1, 2, 7, 2, 32, 0));
    assert(status(&link, start + 22000, 1, 1, 0, 1, 0, 0));
    assert(lfj8_h03_torque_applied(&link, start + 22000));
    set(&gp, -4842, 1, 0);
    assert(factory_hydraulics_torque_main(&gp));
    tick(&link, &gp, start + 30000, &bench_profile, &can);
    assert(can.submitted == 3 && can.frame[1] == 0 && can.frame[2] == 3);
    assert(can.frame[3] == 0 && can.frame[4] == 0);
    lfj8_h03_torque_tx_done(&link, true, start + 30000);
    assert(status(&link, start + 31000, 1, 0, 7, 2, 0, 8));
    assert(link.phase == LFJ8_TORQUE_RELEASING);
    assert(status(&link, start + 32000, 1, 3, 7, 3, 10, 8));
    assert(!lfj8_h03_torque_applied(&link, start + 32000));
    assert(status(&link, start + 33000, 1, 0, 7, 3, 0, 8));
    assert(link.phase == LFJ8_TORQUE_COMPLETE);
}

static void test_loss(void)
{
    Lfj8H03Torque link;
    CanFixture can = {0};
    FactoryHydraulics gp = initial_gp();
    lfj8_h03_torque_init(&link);
    assert(status(&link, 0, 65535, 0, 0, 0, 0, 0));
    tick(&link, &gp, 0, &bench_profile, &can);
    request_donor_upshift(&gp);
    tick(&link, &gp, 1, &bench_profile, &can);
    assert(can.frame[5] == 1 && can.frame[6] == 0);
    lfj8_h03_torque_tx_done(&link, true, 1);
    tick(&link, &gp, 60000, &bench_profile, &can);
    assert(can.submitted == 1);
    tick(&link, &gp, 60001, &bench_profile, &can);
    assert(link.phase == LFJ8_TORQUE_RELEASING && can.frame[1] == 0);
    lfj8_h03_torque_tx_done(&link, false, 60002);
    tick(&link, &gp, 80001, &bench_profile, &can);
    assert(can.submitted == 3 && can.frame[2] == 3);
    lfj8_h03_torque_tx_done(&link, true, 80002);
    tick(&link, &gp, 100001, &bench_profile, &can);
    lfj8_h03_torque_tx_done(&link, true, 100002);
    tick(&link, &gp, 560001, &bench_profile, &can);
    assert(link.phase == LFJ8_TORQUE_FAILED && can.submitted == 4);
    assert(status(&link, 561000, 1, 0, 0, 4, 0, 8));
    tick(&link, &gp, 561000, &bench_profile, &can);
    assert(can.submitted == 4); /* The original donor demand never stopped. */
}

static void test_admission(void)
{
    Lfj8H03Torque link;
    CanFixture can = {0};
    const Lfj8TorqueCalibration disabled = {.up = {{0}}, .down = {{0}}};
    FactoryHydraulics gp = initial_gp();
    FactoryHydraulics active = gp;
    request_donor_upshift(&active);
    lfj8_h03_torque_init(&link);
    assert(status(&link, 0, 0, 0, 0, 0, 0, 0));
    tick(&link, &active, 0, &bench_profile, &can);
    assert(!can.submitted); /* Startup presented an already active shift. */
    tick(&link, &gp, 1, &bench_profile, &can);
    tick(&link, &active, 2, &disabled, &can);
    tick(&link, &active, 3, &bench_profile, &can);
    assert(!can.submitted); /* No late start during an uncalibrated shift. */
    tick(&link, &gp, 4, &bench_profile, &can);
    Lfj8TorqueInput invalid = input(&active, 5);
    invalid.observed_gear = 3;
    lfj8_h03_torque_poll(&link, &invalid, &bench_profile, 5, transmit, &can);
    assert(!can.submitted);
    uint32_t flags;
    assert(factory_hydraulics_get(&active, -4833, 1, &flags));
    set(&active, -4833, 1, flags | 32u);
    tick(&link, &gp, 6, &bench_profile, &can);
    assert(input(&active, 7).demand.active && !input(&active, 7).demand.from_gear);
    tick(&link, &active, 7, &bench_profile, &can);
    assert(!can.submitted);
    tick(&link, &gp, 8, &bench_profile, &can);
    lfj8_h03_torque_poll(&link, NULL, &bench_profile, 9, transmit, &can);
    set(&active, -4833, 1, flags);
    tick(&link, &active, 10, &bench_profile, &can);
    assert(!can.submitted); /* Input loss invalidates the preceding idle sample. */
    tick(&link, &gp, 11, &bench_profile, &can);
    tick(&link, &active, 12, &bench_profile, &can);
    assert(can.submitted == 1);
    lfj8_h03_torque_tx_done(&link, true, 12);
    const uint8_t bad_payload[8] = {0xa4, 0x72, 1, 32, 1, 0, 0, 0};
    assert(!lfj8_h03_torque_receive(&link, 0x5e9, 8, bad_payload, 13));
    assert(!lfj8_h03_torque_receive(&link, 0x5e9, 7, bad_payload, 13));
    assert(!lfj8_h03_torque_receive(&link, 0x5e8, 8, bad_payload, 13));
    assert(status(&link, 13, 1, 2, 7, 1, 32, 0));
    assert(lfj8_h03_torque_applied(&link, 13));
    assert(status(&link, 14, 2, 2, 7, 1, 32, 0));
    tick(&link, &active, 15, &bench_profile, &can);
    assert(link.phase == LFJ8_TORQUE_FAILED && can.submitted == 1); /* Do not cancel a foreign pulse. */
}

static void test_profile_revocation(const Lfj8TorqueCalibration *replacement, bool start_pending)
{
    Lfj8H03Torque link;
    CanFixture can = {0};
    FactoryHydraulics gp = initial_gp();
    Lfj8TorqueCalibration equivalent = bench_profile;
    equivalent.down[0] = bench_profile.up[1]; /* A different pair does not affect this shift. */
    const uint32_t start = 1000u;
    const uint32_t revoked_at = start + 20000u;

    lfj8_h03_torque_init(&link);
    assert(status(&link, start - 1u, 0, 0, 0, 0, 0, 0));
    tick(&link, &gp, start - 1u, &bench_profile, &can);
    request_donor_upshift(&gp);
    tick(&link, &gp, start, &bench_profile, &can);
    assert(can.submitted == 1 && can.frame[1] == 1);
    if (!start_pending) {
        lfj8_h03_torque_tx_done(&link, true, start);
        assert(status(&link, start + 2000u, 1, 2, 7, 1, 32, 0));
        tick(&link, &gp, start + 3000u, &equivalent, &can);
        assert(lfj8_h03_torque_applied(&link, start + 3000u));
    }

    tick(&link, &gp, revoked_at, replacement, &can);
    assert(!lfj8_h03_torque_applied(&link, revoked_at));
    assert(link.phase == LFJ8_TORQUE_RELEASING && link.failed);
    if (start_pending) {
        assert(can.submitted == 1); /* The accepted START still owns the transmitter. */
        lfj8_h03_torque_tx_done(&link, true, revoked_at);
        assert(status(&link, revoked_at, 1, 2, 7, 1, 32, 0));
        assert(!lfj8_h03_torque_applied(&link, revoked_at));
        tick(&link, &gp, revoked_at, &bench_profile, &can);
    }

    const uint8_t cancel[] = {0xa4, 0, 2, 0, 0, 1, 0};
    assert(can.submitted == 2 && !memcmp(can.frame, cancel, sizeof cancel));
    lfj8_h03_torque_tx_done(&link, true, revoked_at + 1u);
    assert(status(&link, revoked_at + 1000u, 1, 0, 7, 2, 0, 8));
    assert(link.phase == LFJ8_TORQUE_FAILED);

    /* Restoring the profile cannot start another pulse for the same demand. */
    const uint32_t later = start + 600000u;
    assert(status(&link, later, 1, 0, 7, 2, 0, 8));
    tick(&link, &gp, later, &bench_profile, &can);
    assert(can.submitted == 2);
}

static int bosch_fixture(void)
{
    Lfj8H03Torque link;
    CanFixture can = {0};
    FactoryHydraulics gp = initial_gp();
    lfj8_h03_torque_init(&link);
    unsigned long tick_us;
    char rx[17];
    while (scanf("%lu %16s", &tick_us, rx) == 2) {
        const uint32_t now = (uint32_t)tick_us;
        if (now == 400000) {
            request_donor_upshift(&gp);
        }
        if (now == 520000) {
            set(&gp, -4842, 1, 0);
            assert(factory_hydraulics_torque_main(&gp));
        }
        if (rx[0] != '-') {
            uint8_t bytes[8];
            assert(strlen(rx) == 16);
            for (unsigned i = 0; i < 8; ++i) {
                unsigned byte;
                assert(sscanf(rx + 2 * i, "%2x", &byte) == 1);
                bytes[i] = (uint8_t)byte;
            }
            assert(lfj8_h03_torque_receive(&link, LFJ8_TORQUE_STATUS_ID, 8, bytes, now - 2000));
        }
        const unsigned sent = can.submitted;
        tick(&link, &gp, now, &bench_profile, &can);
        if (can.submitted != sent) {
            for (unsigned i = 0; i < 8; ++i) {
                printf("%02x", can.frame[i]);
            }
            lfj8_h03_torque_tx_done(&link, true, now);
        } else {
            printf("-");
        }
        printf(" %u %u\n", (unsigned)link.phase, (unsigned)lfj8_h03_torque_applied(&link, now));
        fflush(stdout);
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--bosch")) {
        return bosch_fixture();
    }
    test_full_dialogue();
    test_loss();
    test_admission();
    const Lfj8TorqueCalibration disabled = {0};
    Lfj8TorqueCalibration changed = bench_profile;
    test_profile_revocation(&disabled, true);
    test_profile_revocation(&disabled, false);
    changed.up[1].reduction_q8 = 16;
    test_profile_revocation(&changed, false);
    changed = bench_profile;
    changed.up[1].duration = 10;
    test_profile_revocation(&changed, false);
    changed = bench_profile;
    changed.up[1].levels |= 1u << 4;
    test_profile_revocation(&changed, false);
    test_profile_revocation(NULL, false);
    puts("H03 shift torque provenance, protocol and release passed.");
    return 0;
}
