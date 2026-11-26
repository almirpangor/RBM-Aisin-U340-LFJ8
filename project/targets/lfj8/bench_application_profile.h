#ifndef RBM_LFJ8_H03_BENCH_APPLICATION_PROFILE_H
#define RBM_LFJ8_H03_BENCH_APPLICATION_PROFILE_H

#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_target_service.h"

enum {
    LFJ8_H03_BENCH_AN2_FITS_10_BITS = 1u,
    LFJ8_H03_BENCH_CLOCK_REGISTERS_MATCH_OEM = 2u,
    LFJ8_H03_BENCH_TML0_MOVED = 4u,
};

/* Read-only commissioning observations. AN2 is the last OEM RAM value,
 * not a newly timestamped ADC conversion. P1 and SFR bytes have no assigned
 * switch polarity here. Flags describe numeric observations, not qualified
 * P/N, load, range, conversion age or an independently measured clock.
 * API_ONLY permits a diagnostic consumer before Toyota startup is available. */
typedef struct {
    uint32_t first_tml0;
    uint32_t last_tml0;
    uint16_t an2_raw;
    uint8_t p1data;
    uint8_t prs1;
    uint8_t tml0_mode;
    uint8_t tml1_mode;
    uint8_t flags;
    uint8_t reserved;
} Lfj8H03BenchLocalRaw;

/* Holds only the native IRQ exclusion, reads no application RAM, consumes
 * no ADC mailbox and writes no device registers. Rejects changing observations or
 * an overlong/wrong-way TML0 bracket; failure leaves out unchanged. */
int rbm_h03_bench_raw_local_snapshot(Lfj8H03BenchLocalRaw *out);

#ifndef RBM_H03_BENCH_PROFILE_API_ONLY
#include "bench_sensor_profile.h"
#include "bench_engine_profile.h"
#include "bench_output_profile.h"

/* Include from the final, source-qualified application header. Toyota's
 * absolute cadence is independent of TOP10 and must be an explicit setting.
 * These settings are engineering bounds until bench measurements exist. */
#if !defined(RBM_H03_BENCH_TOYOTA_PERIOD_TICKS) || \
    !defined(RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS) || \
    !defined(RBM_H03_BENCH_TOYOTA_WATCHDOG_TICKS) || \
    !defined(RBM_H03_BENCH_STARTUP_RANGE) || !defined(RBM_H03_BENCH_STARTUP_REQUEST_1120)
#error "Supply the independent Toyota timing and source-qualified startup range/request"
#endif

_Static_assert(RBM_H03_BENCH_TOYOTA_PERIOD_TICKS > 0u &&
               RBM_H03_BENCH_TOYOTA_PERIOD_TICKS < UINT32_C(0x80000000),
               "Toyota period must fit the serial clock half range");
_Static_assert(RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS < RBM_H03_BENCH_TOYOTA_PERIOD_TICKS,
               "Toyota lateness cannot hide a second release");
_Static_assert((uint64_t)RBM_H03_BENCH_TOYOTA_WATCHDOG_TICKS >=
               (uint64_t)RBM_H03_BENCH_TOYOTA_PERIOD_TICKS + RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS &&
               RBM_H03_BENCH_TOYOTA_WATCHDOG_TICKS < UINT32_C(0x80000000),
               "Toyota watchdog must include its bounded release latency");

/* H03 publishes a phase every ten nominal 500-tick TOP10 intervals. The bench
 * profile allows one TOP10 interval either side of nominal. The phase age
 * is the window for using one publication and must expire before the next
 * valid release can arrive. The next-release deadline is max_period_ticks. */
#define RBM_H03_BENCH_PHASE_MIN_PERIOD_TICKS (LFJ8_H03_BENCH_PHASE_TICKS - LFJ8_H03_BENCH_TOP10_TICKS)
#define RBM_H03_BENCH_PHASE_MAX_AGE_TICKS (RBM_H03_BENCH_PHASE_MIN_PERIOD_TICKS - 1u)
_Static_assert(LFJ8_H03_BENCH_PHASE_TICKS > LFJ8_H03_BENCH_TOP10_TICKS + 1u,
               "H03 phase age needs a positive window before the next release");

#define RBM_H03_PROFILE_PHASE_CONFIG { \
    RBM_H03_BENCH_PHASE_MIN_PERIOD_TICKS, \
    LFJ8_H03_BENCH_PHASE_TICKS + LFJ8_H03_BENCH_TOP10_TICKS, \
    RBM_H03_BENCH_PHASE_MAX_AGE_TICKS, 2u * LFJ8_H03_BENCH_PHASE_TICKS }
#define RBM_H03_PROFILE_TOYOTA_PERIOD_TICKS RBM_H03_BENCH_TOYOTA_PERIOD_TICKS
#define RBM_H03_PROFILE_TOYOTA_MAX_LATENESS_TICKS RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS
#define RBM_H03_PROFILE_TOYOTA_MAX_PERIOD_TICKS RBM_H03_BENCH_TOYOTA_WATCHDOG_TICKS
#define RBM_H03_PROFILE_STARTUP_RANGE RBM_H03_BENCH_STARTUP_RANGE
#define RBM_H03_PROFILE_STARTUP_REQUEST_1120 RBM_H03_BENCH_STARTUP_REQUEST_1120

/* This commissioning profile uses the existing native output backend with
 * isolated_pwm_mask=0. Both phase redirects must call the guarded revoke.
 * Do not define the OUTPUT_ISOLATION_MASK / OUTPUT_PHASE_CLOCK opt-in. */
#if defined(RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK) || defined(RBM_H03_PROFILE_OUTPUT_PHASE_CLOCK)
#error "The first bench profile does not attest physical output isolation"
#endif

/* Mandatory native providers, supplied by their owners, with static lifetime.
 * A capture includes real read_local/project_load sources and reserved state;
 * it is not a value fixture. Its read callback must refuse incomplete input.
 * Startup must establish every GP/gear byte required by the runtime and reset
 * the one shared DTC owner, returning a real RbmU340eStartupKind.
 * The CAN config owns the real RX/TX13/T6 contracts, never another CAN owner. */
extern const Lfj8H03ToyotaInputCapture rbm_h03_bench_native_input_capture;
extern const Lfj8H03InputStartup rbm_h03_bench_native_input_startup;
extern const Lfj8H03TargetServiceConfig rbm_h03_bench_native_can_service;
int rbm_h03_bench_prepare_startup_inputs(void *context);

int rbm_h03_bench_profile_reset_inputs(void);
int rbm_h03_bench_profile_sample_inputs(uint32_t now, uint8_t previous_gear);
int rbm_h03_bench_profile_capture(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due_at, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load);

#define RBM_H03_PROFILE_INITIALIZE_INPUTS rbm_h03_bench_prepare_startup_inputs
#define RBM_H03_PROFILE_CAN_SERVICE_CONFIG rbm_h03_bench_native_can_service
#define RBM_H03_PROFILE_TOYOTA_INPUT_STARTUP rbm_h03_bench_native_input_startup
#define RBM_H03_PROFILE_RESET_TOYOTA_INPUTS rbm_h03_bench_profile_reset_inputs
#define RBM_H03_PROFILE_SAMPLE_TOYOTA_INPUTS rbm_h03_bench_profile_sample_inputs
#define RBM_H03_PROFILE_CAPTURE_TOYOTA rbm_h03_bench_profile_capture

/* NVM media has no proved writable block pair for this first bench profile.
 * A real startup seed remains mandatory. The runtime's read-only cold
 * adaptation fallback does not acknowledge persistent erase or write. */
#define RBM_H03_PROFILE_READ_ADAPTATION NULL

#endif /* !RBM_H03_BENCH_PROFILE_API_ONLY */
#endif
