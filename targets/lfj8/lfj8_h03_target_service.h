#ifndef RBM_LFJ8_H03_TARGET_SERVICE_H
#define RBM_LFJ8_H03_TARGET_SERVICE_H

#include "lfj8_h03_application.h"
#include "lfj8_h03_dtc_native.h"

typedef struct {
    Lfj8H03Can13Config can13;
    Lfj8H03DtcT6Config t6;
    uint32_t initial_t6_tick;
    uint16_t max_clock_span_us;
    bool status_from_t6; /* S03 4/12-tick cadence; requires both CAN13 status periods to be zero. */
    const Lfj8VehicleCalibration *vehicle; /* Optional; absent means unavailable S51 speed. */
    const Lfj8TorqueCalibration *torque_calibration;
    const Lfj8H03DtcAtfConfig *atf_diagnostic;
    /* Optional bounded, read-only projections under native IRQ exclusion.
     * Return true only with qualified Chery status operands or a qualified
     * torque input from the current authority and timebase. main may be NULL.
     * The service owns S51/ATF encoding inputs and never infers standstill. */
    bool (*status)(void *context, const Lfj8H03SensorSnapshot *sensors,
                   const Lfj8H03MainResult *main, Lfj8CheryTxInputs *status);
    bool (*torque)(void *context, const Lfj8H03SensorSnapshot *sensors,
                   const Lfj8H03MainResult *main, Lfj8TorqueInput *torque);
} Lfj8H03TargetServiceConfig;

typedef struct {
    Lfj8H03DtcT6Clock t6;
    const Lfj8H03TargetServiceConfig *config;
    uint32_t sensor_epoch;
    bool start_pending;
} Lfj8H03TargetService;

/* Under native IRQ exclusion, with owned RAM and the application gate closed.
 * The guarded cold path has initialized CAN ownership. The config and its
 * referents have static lifetime. The first qualified phase starts T6 and
 * binds the IRQ target after the application rebases its sensor epoch. A
 * warm takeover needs a fresh guarded CAN setup to regain an expired grant.
 * The platform retains ownership of the shared DTC state and its restoration. */
bool lfj8_h03_target_service_prepare_locked(const Lfj8H03TargetServiceConfig *config);

/* Under the same lock, before rebasing clocks or discarding owned RAM.
 * The guarded cold entry must already have initialized the CAN owner.
 * Retire the fenced TX13 slot after withdrawing software authority.
 * If retirement cannot be confirmed, the fence remains through recovery. */
void lfj8_h03_target_service_stop_locked(void);

#endif
