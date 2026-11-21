"""Verify guarded CAN recovery and the native service in the H03 CPU model."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import check_h03_can_monitor_startup as startup
from check_h03_link import HERE, ROOT, TARGET, identify_h03
from check_h03_dtc_foreground import DIAGNOSTIC_SOURCES, LFJ8_SOURCES
from check_h03_storage import check as check_storage
from lfj8_h03_can_service_placement import SERVICE_MODULES, SERVICE_RAM_FIELDS, typed_alias_ranges
sys.path.insert(0, str(ROOT / "controller"))
from hydraulic_port import write_port


ALIASES = {
    **SERVICE_RAM_FIELDS,
    "rbm_h03_takeover_state": "control/takeover",
    "rbm_h03_runtime_state": "control/runtime",
    "rbm_h03_cycle_state": "control/cycle",
    "rbm_h03_toyota_release_state": "control/toyota_release",
    "rbm_h03_main_result": "communication/main_result",
    "fixture_shared_dtc": "communication/dtc",
    "rbm_h03_cycle_workspace": "workspace/toyota",
    "rbm_h03_cycle_input": "workspace/cycle_input",
}
FIXTURE_PROFILE = """\
#include "lfj8_h03_target_platform.h"
#include "lfj8_h03_target_service.h"
int fixture_initialize_inputs(void *);
int fixture_capture_toyota(void *, const Lfj8H03SensorSnapshot *, uint32_t,
                           Lfj8H03CycleInput *, Lfj8H03CycleLoad *);
extern const Lfj8H03TargetServiceConfig service_profile;
#define RBM_H03_PROFILE_PHASE_CONFIG {8u, 12u, 2u, 24u}
#define RBM_H03_PROFILE_STARTUP_RANGE {0}
#define RBM_H03_PROFILE_TOYOTA_MAX_PERIOD_TICKS 23u
#define RBM_H03_PROFILE_STARTUP_REQUEST_1120 0u
#define RBM_H03_PROFILE_READ_ADAPTATION NULL
#define RBM_H03_PROFILE_CAN_SERVICE_CONFIG service_profile
#define RBM_H03_PROFILE_TOYOTA_PERIOD_TICKS 16u
#define RBM_H03_PROFILE_TOYOTA_MAX_LATENESS_TICKS 2u
#define RBM_H03_PROFILE_INITIALIZE_INPUTS fixture_initialize_inputs
#define RBM_H03_PROFILE_CAPTURE_TOYOTA fixture_capture_toyota
"""
BINDINGS = r"""
#include "lfj8_h03_application.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_can_target.h"
#include "lfj8_h03_dtc_native.h"
#include "lfj8_h03_output_inhibit.h"
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"
#include "lfj8_h03_target_platform.h"
#include "lfj8_h03_target_service.h"

extern Lfj8H03Takeover rbm_h03_takeover_state;
extern Lfj8H03MainResult rbm_h03_main_result;
extern Lfj8H03FastOutput rbm_h03_fast_output;
extern volatile uint8_t rbm_h03_tml0_1mhz_qualified;
extern Lfj8H03DtcTarget rbm_h03_dtc_target;
extern Lfj8H03Can13 rbm_h03_can13;
extern CheryDtcState fixture_shared_dtc;
extern Lfj8H03TargetService rbm_h03_can_service;
extern const Lfj8H03Can13Input rbm_h03_can13_input;

const Lfj8H03SensorFeedConfig rbm_h03_sensor_config = {.atf_max_age_us = 90u};
static volatile Lfj8H03PhaseClock fixture_phase_clock;
const Lfj8H03ApplicationEngine rbm_h03_target_engine = {
    .target = {.dtc = &fixture_shared_dtc, .can_owner = &h03_can_owner,
               .io = &lfj8_h03_mmio, .now_us = rbm_h03_atf_now_us},
};

enum { ACTIVE, NO_RAM, COLD, STALE_OPS, SERVICE, PROGRAMMING, FLASH_MODE, REPEATED };
uint32_t fixture_behavior;
static unsigned apply_count;

int rbm_h03_target_ram_owned(void *context)
{
    (void)context;
    return fixture_behavior != NO_RAM;
}

static void fixture_apply(void *context)
{
    (void)context;
    ++apply_count;
}

const Lfj8H03TakeoverOps rbm_h03_target_takeover_ops = {
    .io = &lfj8_h03_mmio, .inhibit = lfj8_h03_output_inhibit_locked, .apply = fixture_apply,
    .clock_ticks = lfj8_h03_tml0ct_m32r, .phase_clock = &fixture_phase_clock,
};
static const Lfj8H03TakeoverOps stale = {
    .io = &simulated_io, .inhibit = fixture_apply, .apply = fixture_apply,
};

FactoryGearState rbm_h03_target_startup_gear;
FactoryHydraulics rbm_h03_target_startup_gp;

int rbm_h03_target_clock_ready(void *context)
{
    (void)context;
    return lfj8_h03_sensor_clock_registers_match();
}

int fixture_capture_toyota(void *context, const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
                           Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    (void)context;
    (void)sensors;
    (void)due_at;
    (void)input;
    (void)load;
    return 0;
}

static const uint32_t command_bytes[] = {0x8063d5, 0x8063d7, 0x8063d8, 0x8063da, 0x8063db, 0x8063dd};
static const unsigned count_bytes = sizeof command_bytes / sizeof command_bytes[0];

void fixture_initialize_outputs(void)
{
    rbm_h03_application.running = 1u;
    h03_can_owner = (Lfj8H03CanOwner){.setup_generation = 42u, .admitted_generation = 42u,
                                     .grant = 1u, .initialized = true, .setup_permitted = true,
                                     .tx13_fenced = 1u};
    rbm_h03_main_result.valid = 1u;
    rbm_h03_fast_output.valid = 1u;
    rbm_h03_takeover_state = (Lfj8H03Takeover){.ops = &rbm_h03_target_takeover_ops, .generation = 7u,
                                            .have_generation = 1u, .pending = 1u};

    BYTE(0x800703) = 0xff;
    BYTE(0x80070a) = 0xff;
    BYTE(0x80074a) = 0xff;
    HALF(0x8048cc) = 0xaaaa;
    HALF(0x800344) = 0xaaaa;
    HALF(0x800346) = 0xaaaa;
    WORD(0x80508c) = 0x3f000000u;
    WORD(0x805094) = 0x3f000000u;
    for (unsigned i = 0; i < count_bytes; ++i) {
        BYTE(command_bytes[i]) = 1u;
    }
}

static int released_output_state(int inhibited)
{
    const uint8_t p3 = inhibited ? 0x1f : 0xff;
    const uint8_t p7 = inhibited ? 0xfe : 0xff;
    const uint16_t mode = inhibited ? 1u : 0xaaaau;
    const uint16_t period = inhibited ? 2998u : 0xaaaau;
    const uint16_t width = inhibited ? 0u : 0xaaaau;
    const uint32_t pressure = inhibited ? 0u : 0x3f000000u;
    if (BYTE(0x800703) != p3 || BYTE(0x80070a) != p7 || BYTE(0x80074a) != p7 ||
        HALF(0x8048cc) != mode || HALF(0x800344) != period || HALF(0x800346) != width ||
        WORD(0x80508c) != pressure || WORD(0x805094) != pressure) {
        return 0;
    }
    for (unsigned i = 0; i < count_bytes; ++i) {
        if (BYTE(command_bytes[i]) != !inhibited) {
            return 0;
        }
    }
    return 1;
}

int __real_rbm_h03_can_monitor_cold_owner_init_locked(void);
void __real_rbm_h03_can_monitor_revoke_locked(void);

int __wrap_rbm_h03_can_monitor_cold_owner_init_locked(void)
{
    require_lock();
    if (release_count || !(HALF(CAN0 + 2) & 0x0100u) || !(HALF(CAN1 + 2) & 0x0100u)) {
        ++unsafe_writes;
    }
    const Lfj8H03CanOwner retained = h03_can_owner;
    const int ready = __real_rbm_h03_can_monitor_cold_owner_init_locked();
    if (ready && (!h03_can_owner.initialized || h03_can_owner.grant || h03_can_owner.setup_permitted ||
                  h03_can_owner.tx13_fenced || h03_can_owner.setup_generation ||
                  h03_can_owner.admitted_generation)) {
        ++unsafe_writes;
    }
    if (!ready && (h03_can_owner.initialized != retained.initialized ||
                   h03_can_owner.setup_permitted != retained.setup_permitted ||
                   h03_can_owner.grant != retained.grant ||
                   h03_can_owner.tx13_fenced != retained.tx13_fenced ||
                   h03_can_owner.setup_generation != retained.setup_generation ||
                   h03_can_owner.admitted_generation != retained.admitted_generation)) {
        ++unsafe_writes;
    }
    return ready;
}

void __wrap_rbm_h03_can_monitor_revoke_locked(void)
{
    require_lock();
    ++revoke_count;
    const uint32_t generation = h03_can_owner.setup_generation;
    const uint32_t admitted = h03_can_owner.admitted_generation;
    const uint8_t grant = h03_can_owner.grant;
    const bool permit = h03_can_owner.setup_permitted;
    __real_rbm_h03_can_monitor_revoke_locked();

    const int owned = fixture_behavior != NO_RAM;
    const int inhibited = fixture_behavior == ACTIVE || fixture_behavior == REPEATED;
    const int active = inhibited || !owned;
    const int granted = !owned && grant == 1u;
    uint32_t epoch = UINT32_MAX;
    if (h03_can_owner.grant != (owned ? 0u : grant) || h03_can_owner.setup_generation != generation ||
        h03_can_owner.setup_permitted != (!owned && permit) ||
        h03_can_owner.admitted_generation != admitted ||
        lfj8_h03_can_owner_rx_epoch(&h03_can_owner, &epoch) != granted ||
        epoch != (granted ? generation : UINT32_MAX) ||
        rbm_h03_takeover_state.pending != !owned || rbm_h03_takeover_state.generation != 7u ||
        rbm_h03_application.running != active ||
        rbm_h03_takeover_state.ops != (active ? &rbm_h03_target_takeover_ops : 0) ||
        rbm_h03_main_result.valid != !owned || rbm_h03_fast_output.valid != !owned ||
        !released_output_state(inhibited)) {
        ++unsafe_writes;
    }
}

void fixture_revoke_once(void)
{
    switch (fixture_behavior) {
    case COLD: rbm_h03_application.running = 0u; break;
    case STALE_OPS: rbm_h03_takeover_state.ops = &stale; break;
    case SERVICE: BYTE(0x804887) = 4u; break;
    case PROGRAMMING: BYTE(0x80801c) = 1u; break;
    case FLASH_MODE: BYTE(0x8007e2) = 1u; break;
    default: break;
    }

    const uint32_t saved = simulated_io.enter(0);
    __wrap_rbm_h03_can_monitor_revoke_locked();
    if (fixture_behavior == REPEATED) {
        __wrap_rbm_h03_can_monitor_revoke_locked();
    }
    simulated_io.leave(0, saved);
    if (fixture_behavior != NO_RAM &&
        (lfj8_h03_takeover_apply(&rbm_h03_takeover_state, 7u) || apply_count ||
         !released_output_state(fixture_behavior == ACTIVE || fixture_behavior == REPEATED))) {
        ++unsafe_writes;
    }
}

static void stage_dtc_request(void)
{
    BYTE(CAN0 + 0x5eu) = 0x41u;
    HALF(CAN0 + 0x0cu) = 2u;
    BYTE(CAN0 + 0x1e0u) = 0x1cu;
    BYTE(CAN0 + 0x1e1u) = 0x32u;
    BYTE(CAN0 + 0x1e5u) = 8u;
    BYTE(CAN0 + 0x1e6u) = 2u;
    BYTE(CAN0 + 0x1e7u) = 0x10u;
    BYTE(CAN0 + 0x1e8u) = 0x86u;
    HALF(CAN0 + 0x1eeu) = HALF(CAN0 + 8u);
}

unsigned fixture_shared_steps;

void fixture_shared_can_path(void)
{
    Lfj8H03DtcTarget *const target = &rbm_h03_dtc_target;
    Lfj8H03Can13 *const broker = &rbm_h03_can13;
    const Lfj8H03Can13Config config = {
        .torque_receive_age_bits = 4000u, .diagnostic_receive_age_bits = 1024u,
        .max_poll_gap_us = 5000u, .bit_time_us = 2u,
    };
    const uint32_t saved = simulated_io.enter(0);
    BYTE(0x800203u) = 9u;
    BYTE(0x8003ebu) = 0x01u;
    BYTE(0x800febu) = 0x31u;
    WORD(0x8003e0u) = 1000u;
    rbm_h03_tml0_1mhz_qualified = 1u;
    chery_dtc_init(&fixture_shared_dtc);
    if (!lfj8_h03_can13_init(broker, &config, 1000u) ||
        !lfj8_h03_dtc_native_bind(target, broker, 4u)) {
        goto finish;
    }
    ++fixture_shared_steps;

    HALF(CAN0 + 2u) = HALF(CAN1 + 2u) = 0x0100u;
    if (!__wrap_rbm_h03_can_monitor_cold_owner_init_locked() ||
        !lfj8_h03_dtc_native_bind(target, broker, 4u)) {
        goto finish;
    }
    ++fixture_shared_steps;

    HALF(CAN0) = 8u;
    HALF(CAN0 + 2u) = 0x0800u;
    HALF(CAN0 + 0x10u) = 0x8003u;
    BYTE(CAN0 + 0x28u) = 0x1fu;
    BYTE(CAN0 + 0x29u) = 0x3fu;
    BYTE(CAN0 + 0x5eu) = BYTE(CAN0 + 0x5fu) = 0x40u;
    BYTE(0x806ae6u) = 6u;
    Lfj8H03Can13Input input = {.dtc = &fixture_shared_dtc, .diagnostic_tick = 10u};
    h03_can_owner.setup_generation = 1u; /* Stale, never admitted into foreground. */
    if (lfj8_h03_can_target_poll(target, &input, true).available || h03_can_owner.grant) {
        goto finish;
    }
    ++fixture_shared_steps;
    rbm_h03_can_monitor_publish_setup_locked();
    if (lfj8_h03_can_target_poll(target, &input, false).available || h03_can_owner.grant ||
        !lfj8_h03_can_target_poll(target, &input, true).available ||
        h03_can_owner.grant != 1u || target->queue.generation != 2u || input.now_us != 1000u) {
        goto finish;
    }
    ++fixture_shared_steps;

    WORD(0x8003e0u) = 1020u;
    HALF(CAN0 + 8u) = 10u;
    stage_dtc_request();
    rbm_h03_dtc_rx_observe(14u);
    if (target->queue.count != 1u || target->queue.entries[0].captured_at_us != 1020u) {
        goto finish;
    }
    ++fixture_shared_steps;
    BYTE(CAN0 + 0x5eu) = 0x40u; /* OEM acknowledges the slot. */
    HALF(CAN0 + 0x0cu) = 0u;
    WORD(0x8003e0u) = 1040u;
    HALF(CAN0 + 8u) = 20u;
    if (!lfj8_h03_can_target_poll(target, &input, true).available || target->queue.count ||
        input.now_us != 1040u || input.diagnostic_tick != 10u ||
        BYTE(CAN0 + 0x1d0u) != 0x1cu || BYTE(CAN0 + 0x1d1u) != 0x22u) {
        goto finish;
    }
    ++fixture_shared_steps;

    BYTE(0x8003ebu) = 0x02u;
    if (lfj8_h03_can_target_poll(target, &input, true).available || h03_can_owner.grant) {
        goto finish;
    }
    stage_dtc_request();
    rbm_h03_dtc_rx_observe(14u);
    if (target->queue.count == 0u) {
        ++fixture_shared_steps;
    }
finish:
    simulated_io.leave(0, saved);
}

static bool fixture_status(void *context, const Lfj8H03SensorSnapshot *sensors,
                            const Lfj8H03MainResult *main, Lfj8CheryTxInputs *status)
{
    (void)context;
    (void)sensors;
    (void)main;
    status->status_1ae.flag_fd18_4 = 1u;
    status->status0_300 = 0x0fu;
    status->stopped = 1u; /* The target must not use this as standstill evidence. */
    return true;
}

static unsigned fixture_demand;

static bool fixture_torque(void *context, const Lfj8H03SensorSnapshot *sensors,
                           const Lfj8H03MainResult *main, Lfj8TorqueInput *torque)
{
    (void)context;
    (void)main;
    *torque = (Lfj8TorqueInput){
        .demand = {(uint8_t)(fixture_demand == 1u), 2u, 3u, 5u},
        .captured_at_us = sensors->capture.now_tml0, .engine_rpm = 2000u,
        .observed_gear = 2u, .permitted = true,
    };
    return fixture_demand != 2u;
}

static const Lfj8VehicleCalibration fixture_vehicle = {
    .tick_hz = 1000000u, .vss_timeout_ticks = 500u, .wheel_um = 1900000u,
    .wheel_num = 1u, .wheel_den = 1u,
};
static const Lfj8TorqueCalibration fixture_torque_cal = {.up = {[1] = {0x20u, 32u, 20u}}};
const Lfj8H03TargetServiceConfig service_profile = {
    .can13 = {.period_1ae_us = 100u, .period_300_us = 160u, .torque_receive_age_bits = 4000u,
              .diagnostic_receive_age_bits = 1024u, .max_poll_gap_us = 5000u, .bit_time_us = 2u},
    .t6 = {.period_us_numerator = 10u, .period_us_denominator = 1u, .max_sample_gap_us = 250u},
    .initial_t6_tick = 10u, .max_clock_span_us = 4u,
    .vehicle = &fixture_vehicle, .status = fixture_status,
    .torque_calibration = &fixture_torque_cal, .torque = fixture_torque,
};

int fixture_initialize_inputs(void *context)
{
    (void)context;
    chery_dtc_init(&fixture_shared_dtc);
    return 1;
}

static void service_turn(uint32_t now)
{
    WORD(0x8003e0u) = now;
    HALF(CAN0 + 8u) = (uint16_t)((now - 1000u) / 2u);
    ++fixture_phase_clock.consumed;
    const Lfj8H03PhaseEvent phase = {.sequence = fixture_phase_clock.consumed, .released_at = now};
    fixture_phase_clock.latest = phase;
    fixture_phase_clock.max_age = 8u;
    const Lfj8H03SensorSnapshot sensors = {
        .epoch = rbm_h03_sensor_state.feed.epoch,
        .capture = {.now_tml0 = now, .vss = {.state = LFJ8_VSS_STOPPED}},
        .atf_valid = 1u, .atf = {.acquired_us = 1090u, .atf_c = 40},
    };
    rbm_h03_application_binding.service_phase(NULL, &phase, &sensors, NULL);
}

unsigned fixture_service_steps;
unsigned fixture_redirects_expected;
extern void stock_tx_writer(void);

void fixture_target_service_path(void)
{
    const uint32_t saved = lfj8_h03_mmio.enter(NULL);
    rbm_h03_application.running = 0u;
    BYTE(0x800203u) = 9u;
    BYTE(0x8003ebu) = 0x01u;
    BYTE(0x800febu) = 0x31u;
    rbm_h03_tml0_1mhz_qualified = 0u;
    rbm_h03_sensor_state.feed.epoch = 8u;
    lfj8_h03_dtc_native_cold_init();
    rbm_h03_toyota_release_state.status = UINT8_MAX;
    lfj8_h03_mmio.leave(NULL, saved);
    const bool prepared = rbm_h03_application_binding.initialize(NULL) == 1;
    if (!fixture_redirects_expected) {
        fixture_service_steps = !prepared && rbm_h03_toyota_release_state.status == UINT8_MAX &&
                                !h03_can_owner.grant &&
                                !rbm_h03_can_service.config;
        return;
    }
    if (!prepared || rbm_h03_toyota_release_state.status != 0u ||
        !rbm_h03_can_service.start_pending || h03_can_owner.grant) {
        return;
    }
    ++fixture_service_steps;

    HALF(CAN0) = 8u;
    HALF(CAN0 + 2u) = 0x0800u;
    HALF(CAN0 + 0x10u) = 0x8003u;
    BYTE(CAN0 + 0x28u) = 0x1fu;
    BYTE(CAN0 + 0x29u) = 0x3fu;
    BYTE(CAN0 + 0x5eu) = BYTE(CAN0 + 0x5fu) = 0x40u;
    BYTE(0x806ae6u) = 6u;
    rbm_h03_application.running = 1u;
    service_turn(1000u);
    if (h03_can_owner.grant || !rbm_h03_can_service.start_pending) {
        return;
    }
    ++fixture_service_steps;
    rbm_h03_tml0_1mhz_qualified = 1u;
    service_turn(1000u);
    if (h03_can_owner.grant || rbm_h03_can_service.start_pending ||
        !rbm_h03_can_service.t6.active || rbm_h03_can_service.t6.tick != 10u) {
        return;
    }
    ++fixture_service_steps;

    rbm_h03_can_monitor_publish_setup_locked();
    service_turn(1000u);
    if (!h03_can_owner.grant || rbm_h03_dtc_target.queue.generation != 1u ||
        rbm_h03_can13_input.now_us != 1000u) {
        return;
    }
    ++fixture_service_steps;
    service_turn(1100u);
    stock_tx_writer();
    if (rbm_h03_can13.status_in_flight != LFJ8_DUE_1AE ||
        BYTE(CAN0 + 0x5du) != 0x80u ||
        BYTE(CAN0 + 0x1d0u) != 0x06u || BYTE(CAN0 + 0x1d1u) != 0x2eu ||
        BYTE(CAN0 + 0x1dcu) != 0xffu || BYTE(CAN0 + 0x1ddu) != 0xffu) {
        return;
    }
    ++fixture_service_steps;
    BYTE(CAN0 + 0x5du) = 0x81u; /* Model a completed telemetry TX with TRFIN. */
    service_turn(1160u);
    if (rbm_h03_can13.status_in_flight != LFJ8_DUE_300 ||
        BYTE(CAN0 + 0x1d0u) != 0x0cu || BYTE(CAN0 + 0x1d1u) != 0u ||
        BYTE(CAN0 + 0x1d9u) != 80u) {
        return;
    }
    ++fixture_service_steps;
    BYTE(CAN0 + 0x5du) = 0x81u;
    WORD(0x8003e0u) = 1180u;
    HALF(CAN0 + 8u) = 90u;
    stage_dtc_request();
    rbm_h03_dtc_rx_observe(14u);
    if (rbm_h03_dtc_target.queue.count != 1u ||
        rbm_h03_dtc_target.queue.entries[0].captured_at_us != 1180u) {
        return;
    }
    BYTE(CAN0 + 0x5eu) = 0x40u;
    HALF(CAN0 + 0x0cu) = 0u;
    service_turn(1180u);
    if (rbm_h03_dtc_target.queue.count || rbm_h03_can13_input.diagnostic_tick != 28u ||
        BYTE(CAN0 + 0x1d0u) != 0x1cu || BYTE(CAN0 + 0x1d1u) != 0x22u) {
        return;
    }
    ++fixture_service_steps;

    /* An old BasicCAN capture must not survive guarded recovery. */
    stage_dtc_request();
    rbm_h03_dtc_rx_observe(14u);
    if (rbm_h03_dtc_target.queue.count != 1u) {
        return;
    }
    const uint32_t recovery_saved = simulated_io.enter(NULL);
    rbm_h03_can_monitor_revoke_locked();
    simulated_io.leave(NULL, recovery_saved);
    service_turn(1190u);
    if (h03_can_owner.grant || !rbm_h03_can13.lease_lost) {
        return;
    }
    BYTE(CAN0 + 0x5du) = 0u;
    BYTE(CAN0 + 0x5eu) = 0x40u;
    HALF(CAN0 + 0x0cu) = 0u;
    rbm_h03_can_monitor_publish_setup_locked();
    service_turn(1200u);
    if (!h03_can_owner.grant || rbm_h03_dtc_target.queue.count ||
        rbm_h03_dtc_target.queue.generation != 2u || rbm_h03_can13.lease_lost) {
        return;
    }
    ++fixture_service_steps;

    /* The CPU simulator has no CAN RX acknowledgement side effects. Seed
     * accepted idle status after the adapter has observed a distinct tick. */
    service_turn(1220u);
    static const uint8_t idle_status[] = {0xa4u, 0u, 0u, 0u, 0u, 0u, 0u, 0xadu};
    if (!lfj8_h03_torque_receive(&rbm_h03_can13.torque.request, 0x5e9u,
                                 sizeof idle_status, idle_status, 1220u)) {
        return;
    }
    fixture_demand = 1u;
    service_turn(1240u);
    if (BYTE(CAN0 + 0x1d7u) != 1u ||
        rbm_h03_can13.torque.request.phase != LFJ8_TORQUE_WAITING) {
        return;
    }
    ++fixture_service_steps;
    BYTE(CAN0 + 0x5du) = 0x81u;
    HALF(CAN0 + 0x1deu) = 127u;
    fixture_demand = 2u;
    service_turn(1260u);
    if (BYTE(CAN0 + 0x1d7u) != 0u ||
        rbm_h03_can13.torque.request.phase != LFJ8_TORQUE_RELEASING ||
        !rbm_h03_can13.torque.request.pending) {
        return;
    }
    ++fixture_service_steps;

    service_turn(1511u);
    if (h03_can_owner.grant || rbm_h03_can_service.t6.active ||
        !rbm_h03_can13.lease_lost || !h03_can_owner.tx13_fenced || BYTE(CAN0 + 0x5du) != 0x0fu) {
        return;
    }
    ++fixture_service_steps;
    ++rbm_h03_sensor_state.feed.epoch;
    service_turn(1520u);
    if (h03_can_owner.grant || rbm_h03_can_service.config) {
        return;
    }
    ++fixture_service_steps;

    /* An application restart may prepare CAN, but cannot re-admit the
     * generation whose lease was withdrawn. The guarded permit does that. */
    rbm_h03_application.running = 0u;
    BYTE(CAN0 + 0x5du) = 0u;
    if (rbm_h03_application_binding.initialize(NULL) != 1) {
        return;
    }
    rbm_h03_application.running = 1u;
    service_turn(1530u);
    if (h03_can_owner.grant) {
        return;
    }
    rbm_h03_can_monitor_publish_setup_locked();
    service_turn(1540u);
    if (!h03_can_owner.grant || rbm_h03_dtc_target.queue.generation != 3u) {
        return;
    }
    ++fixture_service_steps;

    /* Emulate an active TR just before the real application closes. The
     * memory-backed controller retains the abort command until readback
     * is driven below. The OEM writer must remain excluded in between. */
    BYTE(CAN0 + 0x5du) = 0x82u;
    WORD(CAN0 + 0x1d0u) = 0x171e0000u;
    WORD(CAN0 + 0x1d8u) = 0x12345678u;
    rbm_h03_application_cold_gate();
    stock_tx_writer();
    stage_dtc_request();
    rbm_h03_dtc_rx_observe(14u);
    if (h03_can_owner.grant || rbm_h03_can_service.config || rbm_h03_dtc_target.queue.count ||
        rbm_h03_tml0_1mhz_qualified || rbm_h03_application.running || !h03_can_owner.tx13_fenced ||
        BYTE(CAN0 + 0x5du) != 0x0fu || WORD(CAN0 + 0x1d0u) != 0x171e0000u ||
        WORD(CAN0 + 0x1d8u) != 0x12345678u) {
        return;
    }
    ++fixture_service_steps;

    const uint32_t restore_saved = lfj8_h03_mmio.enter(NULL);
    BYTE(CAN0 + 0x5du) = 0x80u;
    HALF(0x8007f2u) = 0x8000u;
    rbm_h03_can_monitor_retire_tx13_locked();
    const bool bank_blocked = h03_can_owner.tx13_fenced && BYTE(CAN0 + 0x5du) == 0x80u;
    HALF(0x8007f2u) = 0u;
    lfj8_h03_mmio.leave(NULL, restore_saved);
    if (!bank_blocked) {
        return;
    }
    ++fixture_service_steps;

    const uint32_t permit_saved = lfj8_h03_mmio.enter(NULL);
    BYTE(CAN0 + 0x5eu) = 0x40u;
    HALF(CAN0 + 0x0cu) = 0u;
    BYTE(CAN0 + 0x5du) = 0x02u;
    rbm_h03_can_monitor_publish_setup_locked();
    const bool pending_kept = h03_can_owner.tx13_fenced && !h03_can_owner.grant;
    BYTE(CAN0 + 0x5du) = 0x81u;
    rbm_h03_can_monitor_publish_setup_locked();
    const bool complete_released = !h03_can_owner.tx13_fenced && !h03_can_owner.grant;
    lfj8_h03_mmio.leave(NULL, permit_saved);
    if (pending_kept && complete_released) {
        ++fixture_service_steps;
    }
}
"""


def aliases_for(base, compiler, storage_report):
    expected = json.loads(storage_report.read_text(encoding="utf-8"))
    actual = check_storage(base, compiler)
    for field in ("base", "artifact_kind", "blocks", "fields", "input_sha256"):
        if expected[field] != actual[field]:
            raise ValueError(f"The H03 RAM report differs from a fresh M32R inventory: {field}")
    addresses = typed_alias_ranges(actual, ALIASES)
    text = "\n".join(f".global {symbol}\n.set {symbol}, {start:#x}"
                     for symbol, (start, _) in addresses.items()) + "\n"
    return addresses, text


def probe_binding(base, compiler, aliases, addresses):
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identify_h03(base)["sha256"]:
        raise ValueError("H03 changed before the binding probe")
    if not all(int.from_bytes(rom[address:address + 4], "big") == value
               for address, value in startup.native_words().items()):
        raise ValueError("A native word changed before the binding probe")
    asm = startup.FIXTURE.replace("    ld24 fp,#0x808000\nfixture_ready:",
                                  "    ld24 fp,#0x808000\n    bl.l fixture_initialize_outputs\nfixture_ready:")
    if asm == startup.FIXTURE or not startup.BACKEND.endswith(startup.OWNER_STUBS):
        raise ValueError("The parent simulator entry has changed")
    stub = startup.BACKEND.removesuffix(startup.OWNER_STUBS) + BINDINGS

    with TemporaryDirectory(prefix="rbm-h03-can-revoke-probe-") as directory:
        work = Path(directory)
        for name, data in (("h03-before.dat", rom[:startup.CANDIDATE_START]),
                           ("h03-after.dat", rom[startup.CANDIDATE_END:])):
            (work / name).write_bytes(data)
        stock = ("stock_recovery_body = 0x00B850; stock_tx_writer = 0x00C34C;\n"
                 "h03_tx_writer_resume = 0x00C350;\n"
                 "h03_dtc_rx_resume = 0x001538; h03_dtc_rx_entry = 0x0013F0;\n")
        for name, text in (("fixture.S", asm), ("fixture.c", stub), ("parked.S", startup.PARKED_SETUP),
                           ("service-profile.h", FIXTURE_PROFILE),
                           ("aliases.S", aliases),
                           ("fixture.ld", startup.LAYOUT + startup.LINK_SYMBOLS + stock)):
            (work / name).write_text(text, encoding="ascii")

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        includes = (HERE, ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                    ROOT / "diagnostics")
        sources = (
            "lfj8_h03_can_monitor_revoke.c", "lfj8_h03_can_monitor_startup.c", "lfj8_h03_monitor_quiesce.c",
            "h03_can_monitor_startup_hooks.S", "lfj8_h03_mmio.c", "lfj8_h03_takeover.c",
            "lfj8_h03_can_owner.c", "lfj8_h03_output_inhibit.c",
            "lfj8_h03_atf_tml0.c", "lfj8_h03_dtc_native.c", "lfj8_h03_can_target.c",
            "lfj8_h03_target_service.c", "h03_can13_tx_gate.S",
            "h03_dtc_rx_hook.S", "lfj8_h03_application_binding.c",
            "lfj8_h03_target_platform.c", "lfj8_h03_toyota_source.c",
            "lfj8_h03_application.c", "lfj8_h03_sensor_target.c",
        )
        flags = (
            *TARGET, "-Os", "-g", "-std=c11", "-ffreestanding", "-fno-builtin",
            "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections",
            *(option for folder in includes for option in ("-I", folder)),
        )
        dtc_sources = (
            *(HERE / name for name in LFJ8_SOURCES if not name.startswith("test_")),
            HERE / "lfj8_h03_atf_feed.c",
            HERE / "lfj8_h03_atf.c",
            HERE / "lfj8_selector_adc.c",
            write_port(ROOT / "controller/vendor/toyota/src", work),
            *(ROOT / "diagnostics" / name for name in DIAGNOSTIC_SOURCES),
        )
        run(compiler, *flags, "-Wno-missing-braces", "-Wno-missing-field-initializers", "-c", *dtc_sources)
        run(compiler, *flags, "-Wconversion", "-Wsign-conversion",
            "-nostdlib", "-DRBM_H03_MONITOR_STARTUP_SIMULATOR",
            "-I.", '-DRBM_H03_APPLICATION_PROFILE="service-profile.h"',
            "-Wl,--gc-sections,-T,fixture.ld,--wrap=rbm_h03_can_monitor_revoke_locked",
            "-Wl,--wrap=rbm_h03_can_monitor_cold_owner_init_locked",
            "-Wl,--undefined=fixture_recovery,--undefined=fixture_fault,--undefined=fixture_revoke_once",
            "-Wl,--undefined=fixture_shared_can_path",
            "-Wl,--undefined=fixture_target_service_path",
            *(f"-Wl,--undefined={name}" for _, _, name, _ in startup.PATCHES),
            "fixture.S", "fixture.c", "parked.S", "aliases.S", *(HERE / name for name in sources),
            *(p.with_suffix(".o").name for p in dtc_sources),
            "-lc", "-lgcc", "-o", "fixture.elf")
        nm = compiler.with_name(f"m32r-elf-nm{compiler.suffix}")
        symbols = {row[2].decode(): (int(row[0], 16), row[1]) for row in
                   (line.split() for line in run(nm, "-g", "--defined-only", "fixture.elf").splitlines())
                   if len(row) == 3}
        for name, (start, _) in addresses.items():
            if symbols[name] != (start, b"A"):
                raise ValueError(f"{name} allocated new storage or changed address")
        native = startup.observations(run, work, compiler, can_owner=addresses["h03_can_owner"][0])
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        results = []
        for mode, name in enumerate(("active", "denied_ram", "cold", "stale_takeover_ops",
                                     "service_mode", "programming_gate", "virtual_flash", "repeat")):
            flags = (("unsigned int", symbols["fixture_behavior"][0], mode),)
            observed, = startup.read_probe(run, work, debugger, "&fixture_revoke_once", flags,
                                           ((symbols["fixture_done"][0],),), 0)
            if observed[1:4] != (0, 0, 2 if name == "repeat" else 1):
                raise ValueError(f"Unexpected output/lease state for {name}: {observed}")
            results.append({"case": name, "software_grant_withdrawn": name != "denied_ram",
                            "inhibit_mmio_verified": name in ("active", "repeat")})
        owner_address = addresses["h03_can_owner"][0]
        denied_ram = ("unsigned int", symbols["fixture_behavior"][0], 1)
        generation = f"*(unsigned int*){owner_address:#x}"
        grant = f"*(unsigned char*){owner_address + 4:#x}"
        memory = (*startup.seed(), *startup.patch_words(run, compiler))
        # Bypass unrelated application startup with a fixture-only BRA.L.
        app_bridge = ("unsigned int", 0x008100, 0xFF000000 | ((0x00B7CC - 0x008100) // 4))
        cold, initial_permit = startup.read_probe(
            run, work, debugger, "0x003DC8", (*memory, app_bridge),
            ((0x008100, 0x0047D8), (0x00B7FC,)), 0, (generation, grant),
        )
        if (cold[0], cold[1:4], cold[-2:]) != (0x008100, (2, 0, 0), (0, 0)):
            raise ValueError(f"Cold entry did not initialize the CAN owner before releasing RX: {cold}")
        if initial_permit[1:4] != (4, 0, 1) or initial_permit[-2:] != (1, 0):
            raise ValueError(f"First stock permit did not publish generation one with TX revoked: {initial_permit}")
        denied, = startup.read_probe(
            run, work, debugger, "0x003DC8", (*memory, denied_ram),
            ((0x008100, 0x0047D8),), 0, (generation, grant),
        )
        if (denied[0], denied[1:4], denied[-2:]) != (0x0047D8, (0, 0, 0), (42, 1)) or not (
            denied[4] & 0x11 and denied[5] & 0x11
        ):
            raise ValueError(f"Cold permit without RAM ownership released CAN or wrote retained state: {denied}")
        preserved, = startup.read_probe(
            run, work, debugger, "0x00B7CC",
            (*memory, denied_ram),
            ((0x00B7FC,),), 0, (generation,),
        )
        if preserved[1:4] != (2, 0, 1) or preserved[-1] != 42:
            raise ValueError(f"Successful stock permit without RAM ownership published target state: {preserved}")
        shared, = startup.read_probe(
            run, work, debugger, "&fixture_shared_can_path", (), ((symbols["fixture_done"][0],),), 0,
            ("fixture_shared_steps",),
        )
        if shared[2] or shared[-1] != 7:
            raise ValueError(f"Shared CAN owner and TML0 route failed: {shared}")
        service_patches = []
        for site, name, opcode in (
            (0x00C34C, "h03_can13_tx_gate", 0xFF000000),
            (0x001534, "rbm_h03_dtc_rx_hook", 0xFF000000),
            (0x004738, "rbm_h03_dtc_rx_dispatch_hook", 0xFE000000),
        ):
            target = symbols[name][0]
            service_patches.append(("unsigned int", site, opcode | (((target - site) // 4) & 0xFFFFFF)))
        service_cases = []
        fixture_flag = ("unsigned int", symbols["fixture_redirects_expected"][0], 1)
        for name, patch_set, expected in (
            ("stock_writers", (), 1),
            ("missing_dtc_dispatch", service_patches[:-1], 1),
            ("native_service", (*service_patches, fixture_flag), 16),
        ):
            observed, = startup.read_probe(run, work, debugger, "&fixture_target_service_path",
                                           patch_set, ((symbols["fixture_done"][0],),), 0,
                                           ("fixture_service_steps",))
            if observed[2] or observed[-1] != expected:
                raise ValueError(f"Target service {name} failed: {observed}")
            service_cases.append({"case": name, "steps": observed[-1]})
    return {"direct_cases": results, "native_entry_cases": native,
            "cold_owner_initialized_while_both_can_parked": True,
            "first_native_setup_generation": 1,
            "cold_ram_denial_keeps_rx_parked": True,
            "native_permit_preserves_unowned_generation": True,
            "shared_irq_and_foreground_checks": shared[-1],
            "target_service": service_cases,
            "used_actual_inhibit_implementation": True, "physical_output_verified": False}


def aggregate_placement(args, aliases):
    sys.path.insert(0, str(ROOT))
    from tools import check_h03_image_layout as layout

    rom = args.base.read_bytes()
    if rom[0xC34C:0xC350] != bytes.fromhex("2e7f2a7f"):
        raise ValueError("Unexpected OEM TX13 writer entry")
    old_modules = layout.BINDING_MODULES
    build = layout.build

    def include_resident_rx(options):
        options.with_dtc_rx = True
        return build(options)

    local = ROOT / "local"
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="rbm-can-revoke-placement-", dir=local) as directory:
        alias_path = Path(directory) / "h03-typed-aliases.S"
        alias_path.write_text(aliases + "\n.global h03_tx_writer_resume\n.set h03_tx_writer_resume, 0xC350\n",
                              encoding="ascii")
        layout.BINDING_MODULES += (*SERVICE_MODULES, "h03_can13_tx_gate.S",
                                   Path(os.path.relpath(alias_path, HERE)).as_posix())
        layout.build = include_resident_rx
        try:
            result = startup.aggregate_placement(args)
        finally:
            layout.BINDING_MODULES = old_modules
            layout.build = build
    # startup's summary knows only the upper windows. The RX closure has
    # a separate low window included in the placement above.
    room = layout.dtc_rx.RX_WINDOW.end - layout.dtc_rx.RX_WINDOW.start
    for row in result.values():
        row["capacity_bytes"] += room
        row["nominal_flash_margin_before_alignment_and_missing_material"] += room
    result["service_and_resident_rx_without_monitor_veneers"] = result.pop("main_baseline")
    return result


def profiled_service_placement(args, addresses):
    """Measure the real CAN service with the profiled application and resident RX."""
    sys.path.insert(0, str(ROOT))
    from tools import check_h03_image_layout as layout

    local = ROOT / "local"
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="rbm-profiled-can-", dir=local) as directory:
        work = Path(directory)
        profile = work / "service-profile.h"
        profile.write_text(FIXTURE_PROFILE, encoding="ascii")
        out = work / "placement"
        out.mkdir()
        options = argparse.Namespace(
            base=args.base.resolve(), gcc=args.gcc.resolve(), controller=args.controller.resolve(),
            bridge=args.bridge.resolve(), storage_report=args.storage_report.resolve(), out=out,
            profile="padding-candidate", memory_model="medium", with_bindings=True,
            with_dtc_rx=True, with_can_service=True, with_dma4_guard=True,
            application_profile=profile, cpu_test=False,
        )
        try:
            report = layout.build(options)
        except ValueError:
            report_path = out / "layout.json"
            if not report_path.is_file():
                raise
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report["status"] != "FAIL_BINDINGS":
                raise

    entries = {
        "lfj8_h03_target_service_prepare_locked", "rbm_h03_target_service_phase",
        "lfj8_h03_target_service_stop_locked", "rbm_h03_can_monitor_retire_tx13_locked", "h03_can13_tx_gate",
    }
    missing = set(report.get("unresolved_symbols", ()))
    aliases = report["can_service"]["typed_aliases"]
    expected = {name: addresses[name] for name in SERVICE_RAM_FIELDS}
    if (not entries.issubset(report["required_roots"]) or missing & (entries | expected.keys()) or
            {name: tuple(span) for name, span in aliases.items()} != expected):
        raise ValueError("The profiled address model is missing a CAN service entry or RAM alias")
    if not report["can_service"]["tx13"]["elf_words_verified"] or not report["early_irq_model"]:
        raise ValueError("The profile did not verify linked TX13 and early IRQ/DMA4")
    candidate = report.get("known_sections_candidate_plan", {})
    if not report["accepted_layout"] and "sections" not in candidate:
        raise ValueError("The retained CAN service composition did not fit the H03 address model")
    return {"status": report["status"], "known_flash_bytes": report["flash_payload_bytes"],
            "known_static_ram_bytes": report["new_static_ram_bytes"], "service_entries": sorted(entries),
            "typed_addresses": {name: [f"0x{start:06X}", f"0x{end:06X}"]
                                for name, (start, end) in aliases.items()},
            "tx13": report["can_service"]["tx13"], "early_irq_model": report["early_irq_model"],
            "missing_symbols": sorted(missing), "hardware_verified": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "storage-report", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("controller", "bridge"):
        parser.add_argument("--" + name, type=Path, help="also recheck the aggregate application placement")
    args = parser.parse_args()
    if bool(args.controller) != bool(args.bridge):
        parser.error("aggregate placement requires both --controller and --bridge")
    inputs = (args.base, args.storage_report, *(path for path in (args.controller, args.bridge) if path))
    if args.out.suffix.lower() != ".json" or any(args.out.resolve() == path.resolve() for path in inputs):
        parser.error("--out must be a separate JSON report")
    try:
        compiler = args.gcc.resolve()
        addresses, assembly = aliases_for(args.base, compiler, args.storage_report)
        report = {"base": identify_h03(args.base),
                  "aliases": {name: [f"0x{start:06X}", f"0x{end:06X}"] for name, (start, end) in addresses.items()},
                  "aliases_allocate_new_ram": False, "hardware_ram_ownership_verified": False,
                  "fixture": probe_binding(args.base, compiler, assembly, addresses), "flashable_image": None}
        if args.controller:
            report["aggregate_placement"] = aggregate_placement(args, assembly)
            report["profiled_service_placement"] = profiled_service_placement(args, addresses)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error).encode()).decode(errors="replace")
        parser.exit(1, detail + "\n")
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
