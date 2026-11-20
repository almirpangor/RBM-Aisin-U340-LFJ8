#include "lfj8_h03_sensor_target.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"

#define H03_PRS1 UINT32_C(0x800203)
#define H03_TML0CR UINT32_C(0x8003EB)
#define H03_TML1CR UINT32_C(0x800FEB)

static int clock_registers_match(void)
{
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    return io->read8(io->context, H03_PRS1) == 9u &&
           io->read8(io->context, H03_TML0CR) == 0x01u &&
           io->read8(io->context, H03_TML1CR) == 0x31u;
}

static void revoke_locked(void)
{
    rbm_h03_tml0_1mhz_qualified = 0u;
    ++rbm_h03_sensor_state.feed.epoch;
    rbm_h03_sensor_state.feed.epoch_seen = 0u;
    lfj8_9e1c_raw_vss_init(&rbm_h03_sensor_state.s51);
    lfj8_9e1c_raw_nt_init(&rbm_h03_sensor_state.s83);
    lfj8_h03_atf_init(&rbm_h03_atf_state);
}

static uint8_t clock_ready_locked(void)
{
    if (rbm_h03_tml0_1mhz_qualified == 1u && !clock_registers_match()) {
        revoke_locked();
    }
    return rbm_h03_tml0_1mhz_qualified;
}

int rbm_h03_sensor_clock_rebase(uint8_t physical_1mhz)
{
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    revoke_locked();
    const int qualified = physical_1mhz == 1u && clock_registers_match();
    rbm_h03_sensor_state.feed.epoch_seen = (uint8_t)qualified;
    rbm_h03_tml0_1mhz_qualified = (uint8_t)qualified;
    io->leave(io->context, saved);
    return qualified;
}

void rbm_h03_s51_capture_callback(void)
{
    if (clock_ready_locked() == 1u) {
        lfj8_9e1c_raw_vss_after_capture_store(&rbm_h03_sensor_state.s51, &lfj8_h03_mmio,
                                            rbm_h03_sensor_config.s51_timeout_ticks);
    }
}

void rbm_h03_s83_capture_callback(void)
{
    if (clock_ready_locked() == 1u) {
        lfj8_9e1c_raw_nt_after_capture_store(&rbm_h03_sensor_state.s83, &lfj8_h03_mmio,
                                           rbm_h03_sensor_config.s83_timeout_ticks);
    }
}

Lfj8H03SensorResult rbm_h03_sensor_foreground(uint8_t standstill_confirmed,
                                             Lfj8H03SensorSnapshot *snapshot)
{
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    const uint8_t qualified = clock_ready_locked();
    const Lfj8H03SensorClock clock = {
        .epoch = rbm_h03_sensor_state.feed.epoch,
        .qualified_1mhz = qualified,
        .standstill_confirmed = standstill_confirmed,
    };
    const Lfj8H03SensorSources sources = {
        .s51 = &rbm_h03_sensor_state.s51,
        .s83 = &rbm_h03_sensor_state.s83,
        .atf = &rbm_h03_atf_state,
    };
    const Lfj8H03SensorResult result = lfj8_h03_sensor_feed_snapshot(
        &rbm_h03_sensor_state.feed, &sources, io, &rbm_h03_sensor_config, clock, snapshot);
    io->leave(io->context, saved);
    return result;
}
