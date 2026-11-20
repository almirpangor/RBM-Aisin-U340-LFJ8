#include "lfj8_gear_observer.h"
#include "lfj8_bridge.h"

#define CLOCK_HALF_RANGE UINT32_C(0x80000000)

int lfj8_gear_observer_init(Lfj8GearObserver *observer, const Lfj8GearCalibration *calibration)
{
    if (!observer) {
        return 0;
    }
    if (!calibration || !calibration->ratio_scale_num || !calibration->ratio_scale_den ||
        !calibration->required_pairs || !calibration->max_age_us ||
        calibration->max_age_us >= CLOCK_HALF_RANGE || calibration->max_skew_us > calibration->max_age_us) {
        observer->calibration.required_pairs = 0;
        return 0;
    }
    for (unsigned i = 0; i < LFJ8_FORWARD_GEARS; ++i) {
        const Lfj8GearRatioBand band = calibration->band[i];
        if (!band.minimum_q10 || band.minimum_q10 > band.maximum_q10 ||
            (i && calibration->band[i - 1u].minimum_q10 <= band.maximum_q10)) {
            observer->calibration.required_pairs = 0;
            return 0;
        }
    }

    observer->calibration.ratio_scale_num = calibration->ratio_scale_num;
    observer->calibration.ratio_scale_den = calibration->ratio_scale_den;
    for (unsigned i = 0; i < LFJ8_FORWARD_GEARS; ++i) {
        observer->calibration.band[i] = calibration->band[i];
    }
    observer->calibration.max_age_us = calibration->max_age_us;
    observer->calibration.max_skew_us = calibration->max_skew_us;
    observer->calibration.required_pairs = calibration->required_pairs;
    observer->last_nt_earliest_us = 0;
    observer->last_nt_edge_tick = 0;
    observer->last_vss_us = 0;
    observer->inhibited_at_us = 0;
    observer->have_pair = 0;
    observer->need_post_inhibit_pair = 0;
    observer->candidate = 0;
    observer->matching_pairs = 0;
    return 1;
}

static uint8_t gear_in_band(const Lfj8GearCalibration *calibration, const Lfj8GearObservation *sample)
{
    /* Compare the exact fraction directly. A product uses at most one 32-bit
     * period and two 16-bit factors, which fits uint64_t. */
    const uint64_t scaled_nt = (uint64_t)sample->vss.interval_ticks *
        calibration->ratio_scale_num * LFJ8_GEAR_RATIO_ONE;
    const uint64_t differential = (uint64_t)sample->nt.interval_ticks * calibration->ratio_scale_den;
    for (unsigned i = 0; i < LFJ8_FORWARD_GEARS; ++i) {
        const Lfj8GearRatioBand band = calibration->band[i];
        if (scaled_nt >= differential * band.minimum_q10 &&
            scaled_nt <= differential * band.maximum_q10) {
            return (uint8_t)(i + 1u);
        }
    }
    return 0;
}

static uint8_t inhibit(Lfj8GearObserver *observer, uint32_t now_us)
{
    observer->inhibited_at_us = now_us;
    observer->need_post_inhibit_pair = 1;
    observer->have_pair = 0;
    observer->candidate = 0;
    observer->matching_pairs = 0;
    return 0;
}

static int after(uint32_t time, uint32_t previous)
{
    const uint32_t delta = time - previous;
    return delta && delta < CLOCK_HALF_RANGE;
}

static int previous_pair_expired(const Lfj8GearObserver *observer, uint32_t now_us)
{
    return now_us - observer->last_nt_earliest_us >= observer->calibration.max_age_us ||
           now_us - observer->last_vss_us >= observer->calibration.max_age_us;
}

uint8_t lfj8_gear_observe(Lfj8GearObserver *observer, const Lfj8GearObservation *sample,
                         uint32_t now_us)
{
    if (!observer || !observer->calibration.required_pairs) {
        return 0;
    }
    if (!sample || sample->steady_forward != 1u ||
        sample->nt.state != LFJ8_VSS_VALID || sample->vss.state != LFJ8_VSS_VALID ||
        sample->nt.pulse_window != 1u || sample->vss.pulse_window != 1u ||
        !sample->nt.interval_ticks || !sample->vss.interval_ticks) {
        return inhibit(observer, now_us);
    }

    const Lfj8GearCalibration *calibration = &observer->calibration;
    const uint32_t nt_age = now_us - sample->nt_at_us;
    const uint32_t vss_age = now_us - sample->vss_at_us;
    const uint32_t skew = nt_age >= vss_age ? nt_age - vss_age : vss_age - nt_age;
    if (nt_age >= calibration->max_age_us ||
        sample->nt_alignment_error_us >= calibration->max_age_us - nt_age ||
        vss_age >= calibration->max_age_us) {
        return inhibit(observer, now_us);
    }
    if (skew > calibration->max_skew_us ||
        sample->nt_alignment_error_us > calibration->max_skew_us - skew) {
        if (observer->have_pair && previous_pair_expired(observer, now_us)) {
            observer->matching_pairs = 0;
        }
        return observer->matching_pairs >= calibration->required_pairs ? observer->candidate : 0;
    }
    if (observer->need_post_inhibit_pair) {
        if (after(sample->nt_at_us - sample->nt_alignment_error_us, observer->inhibited_at_us) &&
            after(sample->vss_at_us, observer->inhibited_at_us)) {
            /* The first post-inhibit edge on either channel may terminate an
             * interval begun during the inhibited phase. Prime only. */
            observer->last_nt_earliest_us = sample->nt_at_us - sample->nt_alignment_error_us;
            observer->last_nt_edge_tick = sample->nt_edge_tick;
            observer->last_vss_us = sample->vss_at_us;
            observer->have_pair = 1;
            observer->need_post_inhibit_pair = 0;
        }
        return 0;
    }

    const uint8_t gear = gear_in_band(calibration, sample);
    if (observer->have_pair) {
        const uint32_t nt_delta = sample->nt_edge_tick - observer->last_nt_edge_tick;
        const uint32_t vss_delta = sample->vss_at_us - observer->last_vss_us;
        if (nt_delta >= CLOCK_HALF_RANGE || vss_delta >= CLOCK_HALF_RANGE) {
            return inhibit(observer, now_us);
        }
        if (gear != observer->candidate || previous_pair_expired(observer, now_us)) {
            observer->matching_pairs = 0;
        }
        if (!nt_delta || !vss_delta) {
            return observer->matching_pairs >= calibration->required_pairs ? observer->candidate : 0;
        }
    }

    observer->last_nt_earliest_us = sample->nt_at_us - sample->nt_alignment_error_us;
    observer->last_nt_edge_tick = sample->nt_edge_tick;
    observer->last_vss_us = sample->vss_at_us;
    observer->have_pair = 1;
    observer->need_post_inhibit_pair = 0;
    observer->candidate = gear;
    if (!gear) {
        observer->matching_pairs = 0;
    } else if (observer->matching_pairs < calibration->required_pairs) {
        ++observer->matching_pairs;
    }
    return observer->matching_pairs >= calibration->required_pairs ? gear : 0;
}

uint8_t lfj8_gear_observe_pair(Lfj8GearObserver *observer, const Lfj8CapturePair *pair,
                              uint8_t steady_forward)
{
    const Lfj8GearObservation sample = {
        .nt = pair->nt,
        .vss = pair->vss,
        .nt_at_us = pair->nt_at_tml0,
        .vss_at_us = pair->vss_at_tml0,
        .nt_edge_tick = pair->nt_edge_tml1,
        .nt_alignment_error_us = pair->nt_alignment_error_ticks,
        .steady_forward = steady_forward,
    };
    return lfj8_gear_observe(observer, &sample, pair->now_tml0);
}
