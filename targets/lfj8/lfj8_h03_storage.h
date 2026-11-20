#ifndef RBM_LFJ8_H03_STORAGE_H
#define RBM_LFJ8_H03_STORAGE_H

#include "lfj8_h03_cycle.h"
#include "lfj8_h03_engine_feed.h"
#include "lfj8_h03_can13.h"
#include "lfj8_h03_dtc_rx_queue.h"
#include "lfj8_h03_atf.h"
#include "lfj8_range_control.h"
#include "lfj8_gear_observer.h"
#include "lfj8_h03_slu.h"
#include "lfj8_h03_sensor_target.h"
#include "lfj8_h03_application.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_dtc_target.h"
#include "lfj8_h03_target_service.h"

/* Typed inventory of CURRENT components, not approved RAM addresses or a
 * startup initializer. Initialize each component through its own API.
 * cycle owns its scheduler/range; can13 owns torque, diagnostic transport
 * and telemetry; engine_rx owns Chery inputs. Do not allocate them twice.
 * sensor owns S51/S83/epoch. Application and CAN ownership are counted here.
 * NVM transaction buffers are on the stack; they are not free storage.
 * Remaining callback contexts must be added when their contracts are defined. */
#define LFJ8_H03_CONTROL_FIELDS(X) \
    X(runtime, RbmU340eRuntime) \
    X(cycle, Lfj8H03Cycle) \
    X(takeover, Lfj8H03Takeover) \
    X(phase_clock, volatile Lfj8H03PhaseClock) \
    X(sensors, Lfj8H03SensorTarget) \
    X(application, Lfj8H03Application) \
    X(clock_qualified, volatile uint8_t) \
    X(atf, volatile Lfj8H03Atf) \
    X(selector_adc, volatile Lfj8SelectorAdc) \
    X(range_control, Lfj8RangeControl) \
    X(button_filter, Lfj8ButtonFilter) \
    X(gear_observer, Lfj8GearObserver) \
    X(slu_baseline, Lfj8H03SluBaselineState) \
    X(slu_secondary, Lfj8H03SluSecondaryState)

#define LFJ8_H03_COMMUNICATION_FIELDS(X) \
    X(engine_rx, Lfj8H03EngineRx) \
    X(engine_qualifier, Ta2005EngineQualifier) \
    X(can13, Lfj8H03Can13) \
    X(can_owner, Lfj8H03CanOwner) \
    X(dtc, CheryDtcState) \
    X(dtc_target, Lfj8H03DtcTarget) \
    X(can_service, Lfj8H03TargetService) \
    X(main_result, Lfj8H03MainResult) \
    X(fast_output, Lfj8H03FastOutput)

/* One foreground owner, no ISR scratch users. Only the already checked
 * Toyota gear/GP union shares mutually exclusive views. Other objects
 * remain disjoint; no additional lifetime assumptions or overlays. */
#define LFJ8_H03_WORKSPACE_FIELDS(X) \
    X(toyota, Lfj8H03CycleWorkspace) \
    X(capture, Lfj8CapturePair) \
    X(sensor_snapshot, Lfj8H03SensorSnapshot) \
    X(input_proposal, Lfj8H03InputProposal) \
    X(cycle_input, Lfj8H03CycleInput) \
    X(load_feed, RbmU340eQualifiedLoadFeed) \
    X(button_reading, Lfj8ButtonReading) \
    X(range_inputs, Lfj8H03RangeInputs) \
    X(range_snapshot, Lfj8H03RangeSnapshot) \
    X(slu_input, Lfj8H03SluInput) \
    X(slu_command, Lfj8H03SluCommand) \
    X(slu_baseline_input, Lfj8H03SluBaselineInput) \
    X(slu_secondary_input, Lfj8H03SluSecondaryInput) \
    X(slu_secondary_result, Lfj8H03SluSecondaryResult) \
    X(dtc_delivery, Lfj8H03DtcRxDelivery) \
    X(atf_sample, Lfj8H03AtfSample) \
    X(engine_context, Ta2005EngineQualificationContext) \
    X(can13_input, Lfj8H03Can13Input) \
    X(tx_input, Lfj8CheryTxInputs) \
    X(oem_output, Lfj8H03OemOutputState) \
    X(torque_input, Lfj8TorqueInput) \
    X(gear_observation, Lfj8GearObservation)

#define RBM_STORAGE_FIELD(name, type) type name;
typedef struct { LFJ8_H03_CONTROL_FIELDS(RBM_STORAGE_FIELD) } Lfj8H03ControlStorage;
typedef struct { LFJ8_H03_COMMUNICATION_FIELDS(RBM_STORAGE_FIELD) } Lfj8H03CommunicationStorage;
typedef struct { LFJ8_H03_WORKSPACE_FIELDS(RBM_STORAGE_FIELD) } Lfj8H03WorkspaceStorage;
#undef RBM_STORAGE_FIELD

#endif
