#include "lfj8_h03_sensor_target.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_input_lifecycle.h"
#include "lfj8_h03_mmio.h"

static void clear_clock_epoch_locked(void)
{
    rbm_h03_tml0_1mhz_qualified = 0u;
    ++rbm_h03_sensor_state.feed.epoch;
    rbm_h03_sensor_state.feed.epoch_seen = 0u;
    rbm_h03_sensor_state.feed.tml1_offset_seen = 0u;
}

static void revoke_locked(void)
{
    clear_clock_epoch_locked();
    lfj8_9e1c_raw_vss_init(&rbm_h03_sensor_state.s51);
    lfj8_9e1c_raw_nt_init(&rbm_h03_sensor_state.s83);
    lfj8_h03_atf_init(&rbm_h03_atf_state);
}

static uint8_t clock_ready_locked(void)
{
    if (lfj8_h03_sensor_clock_ready_locked()) {
        return 1u;
    }
    /* ATF may have revoked the shared qualification before this call. */
    if (rbm_h03_sensor_state.feed.epoch_seen) {
        revoke_locked();
    }
    return 0u;
}

int rbm_h03_sensor_clock_rebase(uint8_t physical_1mhz)
{
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    revoke_locked();
    const int qualified = physical_1mhz == 1u && lfj8_h03_sensor_clock_registers_match();
    rbm_h03_sensor_state.feed.epoch_seen = (uint8_t)qualified;
    rbm_h03_tml0_1mhz_qualified = (uint8_t)qualified;
    io->leave(io->context, saved);
    return qualified;
}

void rbm_h03_s51_capture_callback(void)
{
    if (lfj8_h03_application_running_locked() && clock_ready_locked() == 1u) {
        lfj8_9e1c_raw_vss_after_capture_store(&rbm_h03_sensor_state.s51, &lfj8_h03_mmio,
                                            rbm_h03_sensor_config.s51_timeout_ticks);
    }
}

void rbm_h03_s83_capture_callback(void)
{
    if (lfj8_h03_application_running_locked() && clock_ready_locked() == 1u) {
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
    if (qualified && result == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE) {
        /* Feed already cleared the raw producers under the same exclusion. */
        clear_clock_epoch_locked();
    }
    io->leave(io->context, saved);
    return result;
}
