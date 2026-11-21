#include "lfj8_h03_bench_diag.h"
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_can13.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

/* Test-only producers. The production module resolves these through the
 * shared typed RAM inventory. */
Lfj8H03Application rbm_h03_application;
Lfj8H03Cycle rbm_h03_cycle_state;
Lfj8H03Takeover rbm_h03_takeover_state;
Lfj8H03Can13 rbm_h03_can13;
Lfj8H03SensorTarget rbm_h03_sensor_state;
volatile Lfj8H03Atf rbm_h03_atf_state;

#ifdef RBM_DTC_RX_BENCH_FIXTURE
uint32_t fixture_bench_repeat_rx;
#else
#undef NDEBUG
#include <assert.h>
#include <string.h>

volatile uint8_t rbm_h03_tml0_1mhz_qualified;

static size_t clock_reads;

static uint8_t read8(void *context, uint32_t address)
{
    (void)context;
    return (uint8_t)address;
}

static uint32_t read32(void *context, uint32_t address)
{
    (void)context;
    if (address == 0x8003e0u || address == 0x800fe0u) {
        assert(clock_reads < 3 && address == (clock_reads == 1 ? 0x800fe0u : 0x8003e0u));
        ++clock_reads;
        return UINT32_MAX - (uint32_t)(3u - clock_reads);
    }
    return address;
}

const Lfj8RegisterIo lfj8_h03_mmio = {.read8 = read8, .read32 = read32};

static void snapshots(void)
{
    CheryDtcState dtc;
    chery_dtc_init(&dtc);
    uint32_t words[CHERY_DTC_READOUT_MAX_WORDS];
    rbm_h03_sensor_state.feed.epoch = 42u;
    assert(lfj8_h03_bench_diag_read(&dtc, 1u, words) == 4u && clock_reads == 3u);
    assert(words[0] == 42u && words[1] == UINT32_MAX - 2u &&
           words[2] == UINT32_MAX - 1u && words[3] == UINT32_MAX);

    for (uint8_t page = 2; page <= 5; ++page) {
        assert(lfj8_h03_bench_diag_read(&dtc, page, words) == 0u);
    }
    rbm_h03_sensor_state.s51 = (Lfj8RawVss){0x01020304u, 116u, 1u};
    rbm_h03_sensor_state.s83 = (Lfj8RawCapture){18u, 9u, 1u};
    assert(lfj8_h03_bench_diag_read(&dtc, 2u, words) == 3u && words[0] == 42u &&
           words[1] == 0x01020304u && words[2] == 116u);
    assert(lfj8_h03_bench_diag_read(&dtc, 3u, words) == 3u && words[1] == 18u && words[2] == 9u);
    rbm_h03_atf_state = (Lfj8H03Atf){.last_adc_us = 63u, .last_publication_us = 70u,
        .sampled_adc_us = 48u, .adc = 511u, .toyota_gp_m7184 = 0xab01u,
        .adc_seen = 1u, .publication_seen = 1u, .valid = 1u};
    assert(lfj8_h03_bench_diag_read(&dtc, 4u, words) == 3u && words[1] == 63u && words[2] == 511u);
    assert(lfj8_h03_bench_diag_read(&dtc, 5u, words) == 4u && words[0] == 70u && words[1] == 48u &&
           words[2] == 0x804f04u && words[3] == 0x01e7ab01u);
    rbm_h03_takeover_state.generation = 0x100u;
    rbm_h03_takeover_state.command_at = 0x200u;
    rbm_h03_takeover_state.have_generation = 1u;
    assert(lfj8_h03_bench_diag_read(&dtc, 6u, words) == 4u && words[0] == 0x805094u &&
           words[1] == 0x03000100u && words[2] == 0x100u && words[3] == 0x200u);
    rbm_h03_tml0_1mhz_qualified = 1u;
    rbm_h03_cycle_state.faulted = 1u;
    assert(lfj8_h03_bench_diag_read(&dtc, 7u, words) == 4u && words[0] == 0xafb7c456u &&
           words[1] == 0xf26e6f70u && words[2] == 0x6dbab887u && words[3] == 0xb7b60101u);
    rbm_h03_can13.torque.request = (Lfj8H03Torque){.phase = 3u, .seq = 31u, .ack_seq = 30u,
        .status_phase = 2u, .have_ack = true, .have_status = true, .status_reduction = 12u,
        .token = 0x1200u, .status_token = 0x3344u, .last_status_at = 0xe000u};
    assert(lfj8_h03_bench_diag_read(&dtc, 8u, words) == 4u && words[0] == 0x03021f1eu &&
           words[1] == 0x01010c00u && words[2] == 0x12003344u && words[3] == 0xe000u);
    assert(lfj8_h03_bench_diag_read(&dtc, 9u, words) == 1u && words[0] == 0x03ebeb01u);
    assert(chery_dtc_raise_c0(&dtc, 0x15u, true));
    assert(chery_dtc_raise_c0(&dtc, 0x04u, false));
    assert(lfj8_h03_bench_diag_read(&dtc, 0x0au, words) == 3u && words[0] == 0x10002000u);
    assert(lfj8_h03_bench_diag_read(&dtc, 0x0bu, words) == 3u && words[0] == 0x10000000u);
    assert(lfj8_h03_bench_diag_read(&dtc, 0x0cu, words) == 2u &&
           words[0] == 0x04ffffffu && words[1] == 0xff000000u);
    assert(lfj8_h03_bench_diag_read(&dtc, 0x0du, words) == 1u && words[0] == 0x030d0000u);
    assert(lfj8_h03_bench_diag_read(&dtc, 0xffu, words) == 0u);
}

static void transport(void)
{
    CheryDtcLink link;
    CheryDtcState state;
    CheryDtcLinkTx tx;
    chery_dtc_link_init(&link);
    chery_dtc_init(&state);
    CheryDtcCanFrame request = {.id = CHERY_DTC_CAN_REQUEST_ID, .length = 8,
        .data = {6u, 0xa5u, 'R', 'B', 'M', 1u, 9u}};
    assert(chery_dtc_link_receive_with_readout(&link, &state, &request, 1, &tx, NULL,
        lfj8_h03_bench_diag_read) == CHERY_DTC_LINK_IGNORED && link.session_steps_left == 0);
    const CheryDtcCanFrame open = {.id = CHERY_DTC_CAN_REQUEST_ID, .length = 3,
        .data = {2u, 0x10u, 0x86u}};
    assert(chery_dtc_link_receive(&link, &state, &open, 2, &tx) == CHERY_DTC_LINK_FRAME_READY);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 3, &tx) == CHERY_DTC_LINK_COMPLETE);
    assert(!chery_dtc_link_session_step(&link));
    request.length = 6;
    assert(chery_dtc_link_receive_with_readout(&link, &state, &request, 4, &tx, NULL,
        lfj8_h03_bench_diag_read) == CHERY_DTC_LINK_IGNORED && link.session_steps_left == 8);
    request.length = 8;
    request.data[6] = 0xffu;
    assert(chery_dtc_link_receive_with_readout(&link, &state, &request, 5, &tx, NULL,
        lfj8_h03_bench_diag_read) == CHERY_DTC_LINK_IGNORED && link.session_steps_left == 8);
    request.data[6] = 9u;
    static const uint8_t single[] = {7, 0xe5, 1, 9, 3, 0xeb, 0xeb, 1};
    assert(chery_dtc_link_receive_with_readout(&link, &state, &request, 6, &tx, NULL,
        lfj8_h03_bench_diag_read) == CHERY_DTC_LINK_FRAME_READY && link.session_steps_left == 9);
    assert(tx.frame.id == CHERY_DTC_CAN_REPLY_ID && memcmp(tx.frame.data, single, sizeof(single)) == 0);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 7, &tx) == CHERY_DTC_LINK_COMPLETE);

    request.data[6] = 1u;
    clock_reads = 0;
    assert(chery_dtc_link_receive_with_readout(&link, &state, &request, 8, &tx, NULL,
        lfj8_h03_bench_diag_read) == CHERY_DTC_LINK_FRAME_READY && clock_reads == 3u);
    static const uint8_t first[] = {0x10, 19, 0xe5, 1, 1, 0, 0, 0};
    static const uint8_t second[] = {0x21, 42, 0xff, 0xff, 0xff, 0xfd, 0xff, 0xff};
    static const uint8_t third[] = {0x22, 0xff, 0xfe, 0xff, 0xff, 0xff, 0xff, 0};
    assert(memcmp(tx.frame.data, first, sizeof(first)) == 0);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 9, &tx) == CHERY_DTC_LINK_WAITING);
    assert(chery_dtc_link_receive_with_readout(&link, &state, &request, 10, &tx, NULL,
        lfj8_h03_bench_diag_read) == CHERY_DTC_LINK_IGNORED && clock_reads == 3u);
    const CheryDtcCanFrame flow = {.id = CHERY_DTC_CAN_REQUEST_ID, .length = 3, .data = {0x30}};
    assert(chery_dtc_link_receive(&link, &state, &flow, 11, &tx) == CHERY_DTC_LINK_FRAME_READY);
    assert(memcmp(tx.frame.data, second, sizeof(second)) == 0);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 12, &tx) == CHERY_DTC_LINK_FRAME_READY);
    assert(memcmp(tx.frame.data, third, sizeof(third)) == 0);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 13, &tx) == CHERY_DTC_LINK_COMPLETE);
}

int main(void)
{
    snapshots();
    transport();
    return 0;
}
#endif
