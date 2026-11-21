#include "lfj8_h03_bench_input.h"

#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_input_lifecycle.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

#define HALF_RANGE UINT32_C(0x80000000)

static bool live_epoch(uint32_t *generation, uint32_t *now)
{
    uint16_t can_tick;
    return lfj8_h03_application_running_locked() && h03_can_owner.initialized &&
        lfj8_h03_can_owner_rx_epoch(&h03_can_owner, generation) &&
        *generation == h03_can_owner.admitted_generation && rbm_h03_atf_now_us(now) == 1 &&
        lfj8_h03_can0_read_timestamp(&lfj8_h03_mmio, &can_tick);
}

int lfj8_h03_bench_input_ram_owned(void *context)
{
    (void)context;
    return rbm_h03_target_ram_owned(lfj8_h03_mmio.context);
}

int lfj8_h03_bench_input_reset_locked(const Lfj8H03BenchInputProfile *profile)
{
    if (!profile || !profile->state || !lfj8_h03_raw_load_config_valid(profile->raw_config) ||
        !lfj8_h03_bench_input_ram_owned(NULL) || rbm_h03_application.running ||
        !lfj8_h03_sensor_clock_registers_match()) {
        return 0;
    }
    lfj8_h03_raw_load_reset(&profile->state->raw, lfj8_h03_tml0ct_m32r(lfj8_h03_mmio.context));
    return 1;
}

Lfj8H03RawLoadResult lfj8_h03_bench_input_rx_locked(
    const Lfj8H03BenchInputProfile *profile, const uint8_t slot[16], uint32_t now_us,
    uint16_t can_now)
{
    uint32_t generation, now;
    if (!profile || !profile->state || !live_epoch(&generation, &now) ||
        now - now_us >= HALF_RANGE) {
        return LFJ8_H03_RAW_LOAD_REJECTED;
    }
    return lfj8_h03_raw_load_receive_basic(&profile->state->raw, profile->raw_config,
        slot, 0x41u, false, rbm_h03_sensor_state.feed.epoch, generation, now_us, can_now);
}

static bool has_conversion(const Lfj8H03BenchInputProfile *profile)
{
    return profile && profile->state && profile->raw_config && profile->read_local &&
        profile->project_load && profile->driver_max_age_us && profile->driver_max_age_us < HALF_RANGE;
}

int lfj8_h03_bench_input_load_ready_locked(const Lfj8H03BenchInputProfile *profile)
{
    uint32_t generation, now;
    return has_conversion(profile) && live_epoch(&generation, &now) &&
        lfj8_h03_raw_load_snapshot(&profile->state->raw, profile->raw_config,
            rbm_h03_sensor_state.feed.epoch, generation, now) != NULL;
}

int lfj8_h03_bench_input_read(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due_at, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, Lfj8H03InputSources *sources)
{
    const Lfj8H03BenchInputProfile *const profile = context;
    uint32_t generation, now;
    if (!sensors || !input || !load || !sources || !has_conversion(profile) ||
        !live_epoch(&generation, &now) || sensors->epoch != rbm_h03_sensor_state.feed.epoch ||
        now - due_at >= HALF_RANGE || now - sensors->capture.now_tml0 >= HALF_RANGE) {
        return 0;
    }

    Lfj8H03BenchInputState *const state = profile->state;
    const Lfj8H03RawLoadSample *const raw = lfj8_h03_raw_load_snapshot(&state->raw,
        profile->raw_config, sensors->epoch, generation, now);
    if (!raw) {
        return 0;
    }

    uint32_t driver_at = now - HALF_RANGE;
    state->driver = (RbmU340eInput){0};
    state->range = (Lfj8H03RangeInputs){0};
    state->load = (RbmU340eQualifiedLoadFeed){.sampled_at = raw->oldest_us};
    if (profile->read_local(sensors, now, &state->driver, &state->range, &driver_at) != 1 ||
        now - driver_at >= profile->driver_max_age_us ||
        profile->project_load(raw, &state->load) != 1 || state->load.fallback_5299_bit1 > 1u) {
        return 0;
    }

    /* A conversion must never make the source appear newer. */
    uint32_t load_age = now - state->load.sampled_at;
    if (load_age < now - raw->oldest_us) {
        state->load.sampled_at = raw->oldest_us;
        load_age = now - raw->oldest_us;
    }
    if (load_age >= profile->raw_config->max_age_us) {
        return 0;
    }

    state->load.coherent = 1u;
    *input = (Lfj8H03CycleInput){
        .qualified = 1u,
        .command_at = now - driver_at > load_age ? driver_at : state->load.sampled_at,
    };
    *load = (Lfj8H03CycleLoad){
        .sample = &state->load, .now_us = now, .max_age_us = profile->raw_config->max_age_us,
        .generation = sensors->epoch,
    };
    sources->driver = &state->driver;
    sources->range = &state->range;
    return 1;
}

int lfj8_h03_bench_input_take(const Lfj8H03ToyotaInputCapture *capture,
    const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    if (!load) {
        return 0;
    }
    *load = (Lfj8H03CycleLoad){0};
    if (!capture || !capture->binding || capture->binding->io != &lfj8_h03_mmio) {
        return 0;
    }
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    const int admitted = lfj8_h03_input_capture_toyota((void *)capture, sensors, due_at, input, load);
    if (!admitted) {
        *load = (Lfj8H03CycleLoad){0};
        if (input && lfj8_h03_bench_input_ram_owned(NULL)) {
            input->qualified = 0u;
        }
    }
    io->leave(io->context, saved);
    return admitted;
}
