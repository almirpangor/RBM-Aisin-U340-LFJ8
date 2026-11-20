#include "chery_atf_circuit.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void expect_reply(CheryDtcState *dtc, const uint8_t request[3],
                         const uint8_t *expected, size_t expected_length)
{
    const CheryDtcSession session = {.mode_bits = 0x10, .permission_bits = 2};
    uint8_t reply[CHERY_DTC_MAX_REPLY_BYTES];
    size_t length;
    assert(chery_dtc_respond(dtc, session, request, 3, reply, sizeof(reply), &length)
           == CHERY_DTC_REPLIED);
    assert(length == expected_length);
    assert(memcmp(reply, expected, length) == 0);
}

int main(void)
{
    const uint8_t read[] = {0x17, 0xFF, 0x00};
    const uint8_t clear[] = {0x14, 0xFF, 0x00};
    const uint8_t empty[] = {0x57, 0x00};
    const uint8_t active[] = {0x57, 0x01, 0x07, 0x10, 0x74};
    const uint8_t recovered[] = {0x57, 0x01, 0x07, 0x10, 0x54};
    const uint8_t cleared[] = {0x54, 0xFF, 0x00};
    CheryDtcState dtc;
    CheryAtfCircuit monitor;
    chery_dtc_init(&dtc);
    chery_atf_circuit_reset(&monitor);

    for (unsigned i = 0; i < 126u; ++i) {
        chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_OUT_OF_RANGE, false);
    }
    assert(monitor.count == 126u && dtc.current[0] == 0);
    chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_SKIPPED, false);
    assert(monitor.count == 126u && dtc.current[0] == 0);
    chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_IN_RANGE, false);
    assert(monitor.count == 0 && dtc.current[0] == 0);

    for (unsigned i = 0; i < 127u; ++i) {
        chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_OUT_OF_RANGE, true);
    }
    assert(monitor.count == 125u && dtc.current[0] == 0x10u);
    expect_reply(&dtc, read, empty, sizeof(empty));
    chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_OUT_OF_RANGE, false);
    expect_reply(&dtc, read, empty, sizeof(empty));

    expect_reply(&dtc, clear, cleared, sizeof(cleared));
    assert(dtc.clear_pending);
    chery_atf_circuit_reset(&monitor);
    dtc.clear_pending = false;
    expect_reply(&dtc, read, empty, sizeof(empty));
    assert(monitor.count == 0 && dtc.current[0] == 0 && dtc.history[0] == 0);

    for (unsigned i = 0; i < 127u; ++i) {
        chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_OUT_OF_RANGE, false);
    }
    expect_reply(&dtc, read, active, sizeof(active));
    chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_IN_RANGE, false);
    assert(monitor.count == 124u);
    chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_OUT_OF_RANGE, false);
    assert(monitor.count == 125u);
    for (unsigned i = 0; i < 125u; ++i) {
        chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_IN_RANGE, false);
    }
    assert(monitor.count == 0);
    chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_SKIPPED, false);
    expect_reply(&dtc, read, active, sizeof(active));
    chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_IN_RANGE, false);
    expect_reply(&dtc, read, recovered, sizeof(recovered));

    for (unsigned i = 0; i < 127u; ++i) {
        chery_atf_circuit_step(&monitor, &dtc, CHERY_ATF_CIRCUIT_OUT_OF_RANGE, false);
    }
    expect_reply(&dtc, read, active, sizeof(active));
    assert(dtc.snapshot_index[0] == 4 && dtc.snapshot_index[1] == UINT8_MAX);

    puts("PASS P0710 debounce, service 17, history inhibit, recovery and diagnostic clear");
    return 0;
}
