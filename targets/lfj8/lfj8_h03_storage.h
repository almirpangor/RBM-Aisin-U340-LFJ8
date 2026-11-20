#ifndef RBM_LFJ8_H03_STORAGE_H
#define RBM_LFJ8_H03_STORAGE_H

#include "lfj8_h03_cycle.h"
#include "lfj8_h03_engine_feed.h"
#include "lfj8_h03_can13.h"
#include "lfj8_h03_dtc_rx_queue.h"
#include "lfj8_h03_atf.h"
#include "lfj8_range_control.h"
#include "lfj8_gear_observer.h"

/* Typed inventory of CURRENT components, not approved RAM addresses or a
 * startup initializer. Initialize each component through its own API.
 * cycle owns its scheduler/range; can13 owns torque, diagnostic transport
 * and telemetry; engine_rx owns Chery inputs. Do not allocate them twice.
 * Owner/reset, journal, remaining Toyota stages and callback state must be
 * added when their storage contracts are defined. */
#define LFJ8_H03_CONTROL_FIELDS(X) \
    X(runtime, RbmU340eRuntime) \
    X(cycle, Lfj8H03Cycle) \
    X(takeover, Lfj8H03Takeover) \
    X(phase_clock, volatile Lfj8H03PhaseClock) \
    X(vss, volatile Lfj8RawVss) \
    X(nt, volatile Lfj8RawCapture) \
    X(atf, volatile Lfj8H03Atf) \
    X(selector_adc, volatile Lfj8SelectorAdc) \
    X(range_control, Lfj8RangeControl) \
    X(button_filter, Lfj8ButtonFilter) \
    X(gear_observer, Lfj8GearObserver)

#define LFJ8_H03_COMMUNICATION_FIELDS(X) \
    X(engine_rx, Lfj8H03EngineRx) \
    X(engine_qualifier, Ta2005EngineQualifier) \
    X(can13, Lfj8H03Can13) \
    X(dtc, CheryDtcState) \
    X(dtc_rx_queue, Lfj8H03DtcRxQueue) \
    X(main_result, Lfj8H03MainResult) \
    X(fast_output, Lfj8H03FastOutput)

/* One foreground owner, no ISR scratch users. Only the already checked
 * Toyota gear/GP union shares mutually exclusive views. Other objects
 * remain disjoint; no additional lifetime assumptions or overlays. */
#define LFJ8_H03_WORKSPACE_FIELDS(X) \
    X(toyota, Lfj8H03CycleWorkspace) \
    X(capture, Lfj8CapturePair) \
    X(cycle_input, Lfj8H03CycleInput) \
    X(load_feed, RbmU340eQualifiedLoadFeed) \
    X(button_reading, Lfj8ButtonReading) \
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
