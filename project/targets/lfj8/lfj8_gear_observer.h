#ifndef RBM_LFJ8_GEAR_OBSERVER_H
#define RBM_LFJ8_GEAR_OBSERVER_H

#include "lfj8_donor_io.h"

enum { LFJ8_FORWARD_GEARS = 4, LFJ8_GEAR_RATIO_ONE = 1024 };

typedef struct {
    uint16_t minimum_q10;
    uint16_t maximum_q10;
} Lfj8GearRatioBand;

typedef struct {
    /* Multiplier on (S51 raw interval / S83 raw interval). Supply a reduced
     * positive fraction: (S83 timer Hz / S51 timer Hz) * (100/22) /
     * S83 accepted edges per turbine revolution. */
    uint16_t ratio_scale_num;
    uint16_t ratio_scale_den;
    /* Inclusive non-overlapping NT/differential ratios, in gear order 1..4. */
    Lfj8GearRatioBand band[LFJ8_FORWARD_GEARS];
    uint32_t max_age_us;
    uint32_t max_skew_us;
    uint8_t required_pairs;
} Lfj8GearCalibration;

typedef struct {
    Lfj8CaptureSnapshot nt;
    Lfj8CaptureSnapshot vss;
    uint32_t nt_at_us;
    uint32_t vss_at_us;
    uint32_t nt_edge_tick; /* Raw monotonic capture identity in the S83 timer. */
    uint16_t nt_alignment_error_us;
    /* Caller has qualified forward motion in a forward range, outside an
     * engagement or shift. Edge periods alone do not establish direction. */
    uint8_t steady_forward;
} Lfj8GearObservation;

typedef struct {
    Lfj8GearCalibration calibration;
    uint32_t last_nt_earliest_us;
    uint32_t last_nt_edge_tick;
    uint32_t last_vss_us;
    uint32_t inhibited_at_us;
    uint8_t have_pair;
    uint8_t need_post_inhibit_pair;
    uint8_t candidate;
    uint8_t matching_pairs;
} Lfj8GearObserver;

/* Repeat after clock reset, reconfiguration or a gap of half a clock wrap.
 * A rejected calibration clears the observer's configured state. */
int lfj8_gear_observer_init(Lfj8GearObserver *observer, const Lfj8GearCalibration *calibration);

/* Uses coherent one-edge S83/S51 intervals and the timestamps of the edges
 * terminating those intervals. All times must come from the same wrapping
 * monotonic clock. Supply the separate original NT timer stamp when the
 * conversion to the shared clock has uncertainty. Confirmation advances
 * only with two new edges. The first
 * pair after inhibition is used to establish interval provenance. Returns
 * an observed forward gear (1..4), or 0 when it is not established. */
uint8_t lfj8_gear_observe(Lfj8GearObserver *observer, const Lfj8GearObservation *sample,
                         uint32_t now_us);

/* Project an H03 pair from the shared 1 MHz clock into the gear observer. */
uint8_t lfj8_gear_observe_pair(Lfj8GearObserver *observer, const Lfj8CapturePair *pair,
                              uint8_t steady_forward);

#endif
