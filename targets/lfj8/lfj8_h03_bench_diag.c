#include "lfj8_h03_bench_diag.h"

#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_can13.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

extern Lfj8H03Can13 rbm_h03_can13;

_Static_assert(CHERY_DTC_BITMAP_BYTES == 12 && CHERY_DTC_SNAPSHOT_COUNT == 5,
               "Readout v1 requires the S03 bitmap and five snapshot selectors");

static uint32_t pack_bytes(uint8_t first, uint8_t second, uint8_t third, uint8_t fourth)
{
    return (uint32_t)first << 24 | (uint32_t)second << 16 |
           (uint32_t)third << 8 | fourth;
}

static size_t capture_words(const volatile Lfj8RawCapture *source, uint32_t *words)
{
    if (!source->primed) {
        return 0u;
    }
    words[0] = rbm_h03_sensor_state.feed.epoch;
    words[1] = source->last_edge;
    words[2] = source->interval_ticks;
    return 3u;
}

static void output_qualifiers(const Lfj8RegisterIo *io, uint32_t *words)
{
    /* Low halfwords of the fixed H03 byte addresses, in wire order. */
    static const uint16_t status[][4] = {
        {0x63af, 0x63b7, 0x63c4, 0x6356},
        {0x63f2, 0x636e, 0x636f, 0x6370},
        {0x636d, 0x65ba, 0x65b8, 0x4887},
    };
    for (size_t i = 0; i < sizeof(status) / sizeof(status[0]); ++i) {
        uint32_t word = 0u;
        for (size_t j = 0; j < 4u; ++j) {
            word = word << 8 | io->read8(io->context, 0x800000u | status[i][j]);
        }
        words[i] = word;
    }
    words[3] = pack_bytes(io->read8(io->context, 0x8065b7u), io->read8(io->context, 0x8065b6u),
                          rbm_h03_tml0_1mhz_qualified, rbm_h03_cycle_state.faulted);
}

size_t lfj8_h03_bench_diag_read(const CheryDtcState *state, uint8_t page,
                              uint32_t words[CHERY_DTC_READOUT_MAX_WORDS])
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    void *const context = io->context;
    const volatile Lfj8H03Atf *const atf = &rbm_h03_atf_state;
    const Lfj8H03Takeover *const takeover = &rbm_h03_takeover_state;
    const Lfj8H03Torque *const torque = &rbm_h03_can13.torque.request;

    switch (page) {
    case 0x01:
        words[0] = rbm_h03_sensor_state.feed.epoch;
        words[1] = io->read32(context, 0x8003e0u);
        words[2] = io->read32(context, 0x800fe0u);
        words[3] = io->read32(context, 0x8003e0u);
        return 4u;
    case 0x02:
        return capture_words(&rbm_h03_sensor_state.s51, words);
    case 0x03:
        return capture_words(&rbm_h03_sensor_state.s83, words);
    case 0x04:
        if (!atf->adc_seen) {
            return 0u;
        }
        words[0] = rbm_h03_sensor_state.feed.epoch;
        words[1] = atf->last_adc_us;
        words[2] = atf->adc;
        return 3u;
    case 0x05:
        if (!atf->publication_seen) {
            return 0u;
        }
        words[0] = atf->last_publication_us;
        words[1] = atf->sampled_adc_us;
        words[2] = io->read32(context, 0x804f04u); /* OEM AN1 voltage bits. */
        words[3] = pack_bytes(atf->valid, io->read8(context, 0x8063e7u),
                              (uint8_t)(atf->toyota_gp_m7184 >> 8), (uint8_t)atf->toyota_gp_m7184);
        return 4u;
    case 0x06:
        words[0] = io->read32(context, 0x805094u); /* Post-arbiter pressure request bits. */
        words[1] = pack_bytes(io->read8(context, 0x800703u), takeover->pending,
                              takeover->have_generation, rbm_h03_application.running);
        words[2] = takeover->generation;
        words[3] = takeover->command_at;
        return 4u;
    case 0x07:
        output_qualifiers(io, words);
        return 4u;
    case 0x08:
        words[0] = pack_bytes(torque->phase, torque->status_phase, torque->seq, torque->ack_seq);
        words[1] = pack_bytes(torque->have_status, torque->have_ack, torque->status_reduction, torque->failed);
        words[2] = (uint32_t)torque->token << 16 | torque->status_token;
        words[3] = torque->last_status_at;
        return 4u;
    case 0x09:
        words[0] = pack_bytes(io->read8(context, 0x800203u), io->read8(context, 0x8003ebu),
                              io->read8(context, 0x800febu), rbm_h03_tml0_1mhz_qualified);
        return 1u;
    case 0x0a:
    case 0x0b: {
        const uint8_t *const bitmap = page == 0x0a ? state->current : state->history;
        for (size_t i = 0; i < 3u; ++i) {
            const uint8_t *const bytes = bitmap + 4u * i;
            words[i] = pack_bytes(bytes[0], bytes[1], bytes[2], bytes[3]);
        }
        return 3u;
    }
    case 0x0c:
        words[0] = pack_bytes(state->snapshot_index[0], state->snapshot_index[1],
                              state->snapshot_index[2], state->snapshot_index[3]);
        words[1] = pack_bytes(state->snapshot_index[4], state->clear_pending, 0u, 0u);
        return 2u;
    case 0x0d:
        words[0] = pack_bytes(io->read8(context, 0x800703u), io->read8(context, 0x80070du), 0u, 0u);
        return 1u;
    default:
        return 0u;
    }
}
