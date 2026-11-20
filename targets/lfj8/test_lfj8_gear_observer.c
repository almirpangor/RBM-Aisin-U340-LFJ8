#include "lfj8_bridge.h"
#include "lfj8_gear_observer.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

static Lfj8GearCalibration example_calibration(void)
{
    /* Synthetic fixture centers, neither road nor OEM calibration. */
    return (Lfj8GearCalibration){
        .ratio_scale_num = 5u,
        .ratio_scale_den = 44u,
        .band = {{10238u, 10242u}, {8190u, 8194u}, {5118u, 5122u}, {4094u, 4098u}},
        .max_age_us = 100u,
        .max_skew_us = 20u,
        .required_pairs = 2u,
    };
}

static Lfj8GearObservation sample_at(uint32_t nt_at, uint32_t vss_at, uint32_t vss_period)
{
    return (Lfj8GearObservation){
        .nt = {100u, 1u, LFJ8_VSS_VALID},
        .vss = {vss_period, 1u, LFJ8_VSS_VALID},
        .nt_at_us = nt_at,
        .vss_at_us = vss_at,
        .nt_edge_tick = nt_at,
        .steady_forward = 1u,
    };
}

static void check_calibration_and_four_gears(void)
{
    Lfj8GearObserver observer;
    Lfj8GearCalibration calibration = example_calibration();
    calibration.ratio_scale_den = 0;
    assert(!lfj8_gear_observer_init(&observer, &calibration));
    Lfj8GearObservation sample = sample_at(10, 11, 8800u);
    assert(lfj8_gear_observe(&observer, &sample, 11) == 0);
    calibration = example_calibration();
    calibration.band[1].maximum_q10 = calibration.band[0].minimum_q10;
    assert(!lfj8_gear_observer_init(&observer, &calibration));
    calibration = example_calibration();
    calibration.max_age_us = UINT32_C(0x80000000);
    assert(!lfj8_gear_observer_init(&observer, &calibration));

    calibration = example_calibration();
    const uint32_t periods[] = {8800u, 7040u, 4400u, 3520u};
    for (unsigned i = 0; i < sizeof periods / sizeof periods[0]; ++i) {
        assert(lfj8_gear_observer_init(&observer, &calibration));
        sample = sample_at(10, 11, periods[i]);
        assert(lfj8_gear_observe(&observer, &sample, 11) == 0);
        assert(lfj8_gear_observe(&observer, &sample, 12) == 0);
        sample.nt_at_us = 13; /* VSS has not advanced yet. */
        sample.nt_edge_tick = 13;
        assert(lfj8_gear_observe(&observer, &sample, 13) == 0);
        sample.vss_at_us = 14;
        assert(lfj8_gear_observe(&observer, &sample, 14) == i + 1u);
        assert(lfj8_gear_observe(&observer, &sample, 15) == i + 1u);
    }
}

static void check_inhibition_and_old_capture(void)
{
    Lfj8GearObserver observer;
    Lfj8GearCalibration calibration = example_calibration();
    assert(lfj8_gear_observer_init(&observer, &calibration));

    Lfj8GearObservation sample = sample_at(10, 11, 8800u);
    assert(!lfj8_gear_observe(&observer, &sample, 11));
    sample = sample_at(12, 13, 8800u);
    assert(lfj8_gear_observe(&observer, &sample, 13) == 1);

    sample.steady_forward = 0; /* Standstill, non-forward or an active shift. */
    assert(!lfj8_gear_observe(&observer, &sample, 14));
    sample.steady_forward = 1;
    assert(!lfj8_gear_observe(&observer, &sample, 15));
    sample.nt_at_us = 16; /* One signal is still from before inhibition. */
    sample.nt_edge_tick = 16;
    assert(!lfj8_gear_observe(&observer, &sample, 16));
    sample.vss_at_us = 17;
    assert(!lfj8_gear_observe(&observer, &sample, 17));
    sample = sample_at(18, 19, 7040u); /* Conflicting new ratio resets dwell. */
    assert(!lfj8_gear_observe(&observer, &sample, 19));
    sample = sample_at(20, 21, 7040u);
    assert(lfj8_gear_observe(&observer, &sample, 21) == 2);

    sample.vss.interval_ticks = 6534u; /* Out of band on the new S51 edge. */
    sample.vss_at_us = 22;
    assert(!lfj8_gear_observe(&observer, &sample, 22));
    sample = sample_at(23, 24, 7040u);
    assert(!lfj8_gear_observe(&observer, &sample, 24));
    sample = sample_at(25, 26, 7040u);
    assert(lfj8_gear_observe(&observer, &sample, 26) == 2);

    sample.nt_at_us = 24; /* Out of order even though still inside the age bound. */
    sample.nt_edge_tick = 24;
    assert(!lfj8_gear_observe(&observer, &sample, 27));
    sample = sample_at(28, 50, 7040u); /* Excess edge skew. */
    assert(!lfj8_gear_observe(&observer, &sample, 50));
    sample = sample_at(51, 52, 7040u);
    assert(!lfj8_gear_observe(&observer, &sample, 52));
    sample = sample_at(53, 54, 7040u);
    assert(!lfj8_gear_observe(&observer, &sample, 54)); /* First pair wholly after inhibition. */
    sample = sample_at(55, 56, 7040u);
    assert(lfj8_gear_observe(&observer, &sample, 56) == 2);
    assert(!lfj8_gear_observe(&observer, &sample, 155)); /* NT age equals maximum. */

    sample = sample_at(157, 158, 7040u);
    sample.vss.state = LFJ8_VSS_STOPPED;
    assert(!lfj8_gear_observe(&observer, &sample, 158));
    sample = sample_at(159, 160, 7040u);
    sample.nt.pulse_window = 4;
    assert(!lfj8_gear_observe(&observer, &sample, 160));
    sample = sample_at(161, 162, 7040u);
    sample.nt.interval_ticks = 0;
    assert(!lfj8_gear_observe(&observer, &sample, 162));
}

static void check_wrap_and_exact_bounds(void)
{
    Lfj8GearObserver observer;
    Lfj8GearCalibration calibration = example_calibration();
    assert(lfj8_gear_observer_init(&observer, &calibration));
    Lfj8GearObservation sample = sample_at(UINT32_MAX - 2u, UINT32_MAX - 1u, 4400u);
    assert(!lfj8_gear_observe(&observer, &sample, UINT32_MAX));
    sample = sample_at(0u, 1u, 4400u);
    assert(lfj8_gear_observe(&observer, &sample, 1u) == 3);

    calibration.ratio_scale_num = 1;
    calibration.ratio_scale_den = 1;
    calibration.required_pairs = 1;
    assert(lfj8_gear_observer_init(&observer, &calibration));
    sample = sample_at(10, 10, calibration.band[0].maximum_q10);
    sample.nt.interval_ticks = LFJ8_GEAR_RATIO_ONE;
    assert(lfj8_gear_observe(&observer, &sample, 10) == 1);
    sample = sample_at(11, 11, 2u * calibration.band[0].maximum_q10 + 1u);
    sample.nt.interval_ticks = LFJ8_GEAR_RATIO_ONE * 2u;
    assert(!lfj8_gear_observe(&observer, &sample, 11)); /* Half a count over the bound. */

    calibration.ratio_scale_num = UINT16_MAX;
    calibration.ratio_scale_den = UINT16_MAX;
    calibration.band[0] = (Lfj8GearRatioBand){65000u, UINT16_MAX};
    calibration.band[2] = (Lfj8GearRatioBand){1020u, 1030u};
    calibration.band[3] = (Lfj8GearRatioBand){700u, 900u};
    assert(lfj8_gear_observer_init(&observer, &calibration));
    sample = sample_at(30, 31, UINT32_MAX);
    sample.nt.interval_ticks = UINT32_MAX;
    assert(lfj8_gear_observe(&observer, &sample, 31) == 3);
}

static void check_alignment_jitter(void)
{
    Lfj8GearObserver observer;
    const Lfj8GearCalibration calibration = example_calibration();
    assert(lfj8_gear_observer_init(&observer, &calibration));
    Lfj8GearObservation sample = sample_at(10u, 11u, 8800u);
    sample.nt_edge_tick = 1000u;
    sample.nt_alignment_error_us = 1u;
    assert(!lfj8_gear_observe(&observer, &sample, 11u));
    sample.nt_at_us = 12u;
    sample.vss_at_us = 13u;
    assert(!lfj8_gear_observe(&observer, &sample, 13u));
    sample.nt_edge_tick = 1001u;
    assert(lfj8_gear_observe(&observer, &sample, 14u) == 1);
    sample.nt_alignment_error_us = 20u; /* Skew could exceed the configured bound. */
    assert(lfj8_gear_observe(&observer, &sample, 15u) == 1);
    assert(!lfj8_gear_observe(&observer, &sample, 95u));
}

static void check_h03_pair(void)
{
    Lfj8GearObserver observer;
    const Lfj8GearCalibration calibration = example_calibration();
    assert(lfj8_gear_observer_init(&observer, &calibration));
    Lfj8CapturePair pair = {
        .nt = {100u, 1u, LFJ8_VSS_VALID},
        .vss = {8800u, 1u, LFJ8_VSS_VALID},
        .now_tml0 = 25u,
        .vss_at_tml0 = 24u,
        .nt_at_tml0 = 23u,
        .nt_edge_tml1 = 0xfffffff0u,
        .nt_alignment_error_ticks = 3u,
    };
    assert(!lfj8_gear_observe_pair(&observer, &pair, 1u));
    pair.now_tml0 = 35u;
    pair.vss_at_tml0 = 34u;
    pair.nt_at_tml0 = 33u;
    pair.nt_edge_tml1 = 2u;
    assert(lfj8_gear_observe_pair(&observer, &pair, 1u) == 1u);
    assert(!lfj8_gear_observe_pair(&observer, &pair, 0u));
}

static void check_asynchronous_edges(void)
{
    Lfj8GearObserver observer;
    const Lfj8GearCalibration calibration = example_calibration();
    assert(lfj8_gear_observer_init(&observer, &calibration));
    Lfj8GearObservation sample = sample_at(10u, 11u, 8800u);
    assert(!lfj8_gear_observe(&observer, &sample, 11u));
    sample.nt_at_us = 40u;
    sample.nt_edge_tick = 40u;
    assert(!lfj8_gear_observe(&observer, &sample, 40u)); /* Only S83 has advanced. */
    sample = sample_at(60u, 61u, 8800u);
    assert(lfj8_gear_observe(&observer, &sample, 61u) == 1u);
    sample.nt_at_us = 100u;
    sample.nt_edge_tick = 100u;
    assert(lfj8_gear_observe(&observer, &sample, 100u) == 1u);
    assert(!lfj8_gear_observe(&observer, &sample, 160u)); /* Previous NT timestamp expired. */
}

int main(void)
{
    check_calibration_and_four_gears();
    check_inhibition_and_old_capture();
    check_wrap_and_exact_bounds();
    check_alignment_jitter();
    check_h03_pair();
    check_asynchronous_edges();
    puts("H03 measured gear: four ranges, independent epochs, inhibition and exact ratio passed.");
    return 0;
}
