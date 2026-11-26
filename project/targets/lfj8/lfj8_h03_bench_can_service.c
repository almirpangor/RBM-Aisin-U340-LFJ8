#include "lfj8_h03_bench_can_service.h"

static Lfj8H03BenchCanSampleResult age_result(uint32_t now, uint32_t at, uint32_t maximum)
{
    const uint32_t age = now - at;
    if (age >= UINT32_C(0x80000000)) {
        return LFJ8_H03_CAN_SAMPLE_FUTURE;
    }
    return age > maximum ? LFJ8_H03_CAN_SAMPLE_STALE : LFJ8_H03_CAN_SAMPLE_QUALIFIED;
}

static Lfj8H03BenchCanSampleResult sample_ready(const Lfj8H03BenchCanStamp *stamp,
    const Lfj8H03SensorSnapshot *sensors, uint32_t epoch, uint32_t now, uint32_t maximum)
{
    if (!stamp || !sensors) {
        return LFJ8_H03_CAN_SAMPLE_UNAVAILABLE;
    }
    if (!maximum || maximum >= UINT32_C(0x80000000)) {
        return LFJ8_H03_CAN_SAMPLE_INVALID;
    }
    if (stamp->epoch != epoch || sensors->epoch != epoch) {
        return LFJ8_H03_CAN_SAMPLE_EPOCH;
    }
    const Lfj8H03BenchCanSampleResult source = age_result(now, stamp->oldest_us, maximum);
    return source == LFJ8_H03_CAN_SAMPLE_QUALIFIED
        ? age_result(now, sensors->capture.now_tml0, maximum) : source;
}

Lfj8H03BenchCanSampleResult lfj8_h03_bench_can_status_project(
    const Lfj8H03BenchCanStatusSample *sample, const Lfj8H03SensorSnapshot *sensors,
    uint32_t epoch, uint32_t now_us, uint32_t max_age_us, Lfj8CheryTxInputs *out)
{
    if (!sample || !out) {
        return LFJ8_H03_CAN_SAMPLE_UNAVAILABLE;
    }
    if (sample->known_fields != LFJ8_H03_CAN_KNOWN_STATUS) {
        return LFJ8_H03_CAN_SAMPLE_UNAVAILABLE;
    }
    const Lfj8H03BenchCanSampleResult ready = sample_ready(&sample->stamp, sensors,
                                                          epoch, now_us, max_age_us);
    if (ready != LFJ8_H03_CAN_SAMPLE_QUALIFIED) {
        return ready;
    }
    const Lfj8Chery1ae *const raw = &sample->value.status_1ae;
    if (raw->byte3_high > 15u || raw->raw_f8e1 > 3u || raw->flag_f842_5 > 1u ||
        raw->flag_fd18_4 > 1u || raw->flag_fd10_7 > 1u || raw->flag_f83e_4 > 1u ||
        raw->flag_e026_0 > 1u || sample->value.flag_fd18_9 > 1u) {
        return LFJ8_H03_CAN_SAMPLE_INVALID;
    }
    Lfj8CheryTxInputs value = sample->value;
    value.status_1ae.counter_f8e4 = 0u; /* The TX broker owns this counter. */
    value.s51_capture = NULL;
    value.stopped = 0u;
    value.atf_valid = 0u;
    value.atf_c = 0; /* The common service replaces ATF before publication. */
    *out = value;
    return LFJ8_H03_CAN_SAMPLE_QUALIFIED;
}

Lfj8H03BenchCanSampleResult lfj8_h03_bench_can_torque_project(
    const Lfj8H03BenchCanTorqueSample *sample, const Lfj8H03SensorSnapshot *sensors,
    const Lfj8H03MainResult *main, uint32_t epoch, uint32_t now_us,
    uint32_t max_age_us, Lfj8TorqueInput *out)
{
    if (!sample || !out || sample->known_fields != LFJ8_H03_CAN_KNOWN_TORQUE_INPUT) {
        return LFJ8_H03_CAN_SAMPLE_UNAVAILABLE;
    }
    const Lfj8H03BenchCanSampleResult ready = sample_ready(&sample->stamp, sensors,
                                                          epoch, now_us, max_age_us);
    if (ready != LFJ8_H03_CAN_SAMPLE_QUALIFIED) {
        return ready;
    }
    if (!main || main->valid != 1u) {
        return LFJ8_H03_CAN_SAMPLE_NO_MAIN;
    }
    const Lfj8H03BenchCanSampleResult main_age = age_result(now_us, main->command_at, max_age_us);
    if (main_age != LFJ8_H03_CAN_SAMPLE_QUALIFIED) {
        return main_age;
    }
    if (sample->engine_rpm > 10000u || sample->observed_gear < 1u || sample->observed_gear > 4u ||
        sample->ignition_on > 1u || sample->forward_selected > 1u || sample->can_current > 1u ||
        sample->shift_owned > 1u || main->torque.active > 1u || main->torque.level > 7u ||
        main->torque.from_gear > 4u || main->torque.to_gear > 4u) {
        return LFJ8_H03_CAN_SAMPLE_INVALID;
    }
    const uint32_t main_elapsed = now_us - main->command_at;
    const uint32_t source_elapsed = now_us - sample->stamp.oldest_us;
    *out = (Lfj8TorqueInput){
        .demand = main->torque,
        .captured_at_us = main_elapsed > source_elapsed ? main->command_at : sample->stamp.oldest_us,
        .engine_rpm = sample->engine_rpm, .observed_gear = sample->observed_gear,
        .permitted = sample->engine_rpm != 0u && sample->ignition_on == 1u &&
            sample->forward_selected == 1u && sample->can_current == 1u && sample->shift_owned == 1u,
    };
    return LFJ8_H03_CAN_SAMPLE_QUALIFIED;
}

static uint32_t gcd(uint32_t a, uint32_t b)
{
    while (b) {
        const uint32_t rest = a % b;
        a = b;
        b = rest;
    }
    return a;
}

bool lfj8_h03_bench_can_t6_from_cpu(uint32_t cpu_hz, uint32_t max_sample_gap_us,
                                  Lfj8H03DtcT6Config *out)
{
    if (!cpu_hz || !out) {
        return false;
    }
    uint32_t divisor = gcd(cpu_hz, 80000u);
    const uint32_t first = 80000u / divisor;
    uint32_t denominator = cpu_hz / divisor;
    divisor = gcd(denominator, 1000000u);
    const uint32_t second = 1000000u / divisor;
    denominator /= divisor;
    if (first > UINT32_MAX / second) {
        return false;
    }
    const Lfj8H03DtcT6Config result = {
        .period_us_numerator = first * second,
        .period_us_denominator = denominator,
        .max_sample_gap_us = max_sample_gap_us,
    };
    if (!lfj8_h03_dtc_t6_config_valid(&result)) {
        return false;
    }
    *out = result;
    return true;
}

static bool calibration_valid(const Lfj8TorqueCalibration *cal)
{
    if (!cal) {
        return false;
    }
    for (unsigned direction = 0; direction != 2u; ++direction) {
        for (unsigned gear = 0; gear != 3u; ++gear) {
            const Lfj8TorqueProfile *const profile = direction ? &cal->down[gear] : &cal->up[gear];
            if ((profile->levels & 1u) || (profile->levels &&
                (!profile->reduction_q8 || profile->reduction_q8 > 64u ||
                 !profile->duration || profile->duration > 30u))) {
                return false;
            }
        }
    }
    return true;
}

bool lfj8_h03_bench_can_policy_valid(const Lfj8H03BenchCanPolicy *policy)
{
    if (!policy || (policy->timing_basis != LFJ8_H03_CAN_BASIS_SOURCE &&
                    policy->timing_basis != LFJ8_H03_CAN_BASIS_ENGINEERING) ||
        policy->status_mapping_basis != LFJ8_H03_CAN_BASIS_SOURCE ||
        policy->torque_calibration_basis != LFJ8_H03_CAN_BASIS_SOURCE ||
        policy->known_status_fields != LFJ8_H03_CAN_KNOWN_STATUS ||
        policy->known_torque_pairs != LFJ8_H03_CAN_KNOWN_TORQUE_PAIRS ||
        !policy->status_max_age_us || policy->status_max_age_us >= UINT32_C(0x80000000) ||
        !policy->torque_max_age_us || policy->torque_max_age_us >= UINT32_C(0x80000000)) {
        return false;
    }
    const Lfj8H03TargetServiceConfig *const cfg = &policy->service;
    const Lfj8H03Can13Config *const can = &cfg->can13;
    if (!cfg->status || !cfg->torque || !calibration_valid(cfg->torque_calibration) ||
        !lfj8_h03_dtc_t6_config_valid(&cfg->t6) ||
        !can->torque_receive_age_bits || can->torque_receive_age_bits >= 0x8000u ||
        !can->diagnostic_receive_age_bits || can->diagnostic_receive_age_bits >= 0x8000u ||
        !can->max_poll_gap_us || can->max_poll_gap_us > 30000u || !can->bit_time_us ||
        (uint32_t)can->torque_receive_age_bits * can->bit_time_us >= 100000u ||
        (uint32_t)can->max_poll_gap_us >= UINT32_C(0x8000) * can->bit_time_us ||
        !lfj8_h03_dtc_rx_clock_span_valid(cfg->max_clock_span_us,
            can->diagnostic_receive_age_bits, can->bit_time_us) ||
        (cfg->status_from_t6 && (can->period_1ae_us || can->period_300_us)) ||
        (!cfg->status_from_t6 && (!can->period_1ae_us || !can->period_300_us ||
            can->period_1ae_us >= UINT32_C(0x80000000) ||
            can->period_300_us >= UINT32_C(0x80000000))) ||
        (cfg->atf_diagnostic && !lfj8_h03_dtc_atf_config_valid(cfg->atf_diagnostic))) {
        return false;
    }
    return true;
}

bool lfj8_h03_bench_can_make_config(const Lfj8H03BenchCanPolicy *policy,
                                   Lfj8H03TargetServiceConfig *out)
{
    if (!out || !lfj8_h03_bench_can_policy_valid(policy)) {
        return false;
    }
    *out = policy->service;
    return true;
}
