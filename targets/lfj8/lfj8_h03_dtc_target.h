#ifndef RBM_LFJ8_H03_DTC_TARGET_H
#define RBM_LFJ8_H03_DTC_TARGET_H

#include "lfj8_h03_atf_fault.h"
#include "lfj8_h03_dtc_foreground.h"

/* Read admission with IE already masked in the RX callbacks. The poll
 * callback is the application's only CAN13 foreground owner. */
typedef struct {
    bool (*rx_epoch)(void *owner, uint32_t *generation);
    Lfj8H03Can13Result (*poll)(void *owner, Lfj8H03Can13 *broker, Lfj8H03DtcRxQueue *queue,
                              const Lfj8RegisterIo *io, Lfj8H03Can13Input *input,
                              const uint16_t *can_now, bool native_ready);
    void *owner;
} Lfj8H03DtcCanOwnerOps;

typedef struct {
    uint32_t max_age_us;
    /* Return 1 with a qualified wrapping time in the same epoch as RX.
     * Called with IE masked. H03 uses rbm_h03_atf_now_us. */
    int (*now_us_locked)(uint32_t *now_us);
    /* Project the diagnostic owner's history policy using io->context.
     * Called in foreground, only for a fresh active fault. */
    bool (*inhibit_history)(void *context);
} Lfj8H03DtcAtfConfig;

typedef struct {
    Lfj8H03DtcRxQueue queue;
    Lfj8H03DtcRxDispatch dispatch;
    Lfj8H03Can13 *broker;
    const Lfj8RegisterIo *io;
    const Lfj8H03DtcCanOwnerOps *can_owner;
    uint32_t (*clock_us)(void *context);
    const Lfj8H03DtcAtfConfig *atf_config;
    volatile uint32_t atf_observed_us;
    volatile uint8_t atf_pending;
    uint16_t max_clock_span_us;
} Lfj8H03DtcTarget;

/* The application owns this storage and the single CAN13 broker. Before
 * enabling any hooked IRQ at cold or warm start, clear the IRQ binding.
 * Initialize the broker first. The clock uses io->context, runs in IRQ
 * and foreground, and must be qualified as continuous microseconds.
 * All I/O locks must preserve nesting and prior IRQ state. The bound CAN
 * owner grants RX epochs, resets the queue before publishing a new epoch
 * and runs the single foreground broker. Keep the ops and context alive.
 * Serialize initialization and removal with both IRQ and foreground. */
void lfj8_h03_dtc_target_unbind(void);
bool lfj8_h03_dtc_target_init(Lfj8H03DtcTarget *target, Lfj8H03Can13 *broker,
                            const Lfj8RegisterIo *io, const Lfj8H03DtcCanOwnerOps *can_owner,
                            uint32_t (*clock_us)(void *), uint16_t max_clock_span_us);

/* Enable capture once per binding for the installed AN1 monitor hook,
 * after successful target init and before releasing producers.
 * Keep config alive and immutable.
 * max_age_us is in the same qualified continuous clock as DTC RX, in
 * (0, 2^31), and the owner must service the target more often than half
 * a clock wrap. Clock loss discards capture and suspends ATF publication
 * until unbind, init and enable in the new clock epoch.
 * Like init, serialize this operation with IRQ and foreground. */
bool lfj8_h03_dtc_target_enable_atf(Lfj8H03DtcTarget *target,
                                  const Lfj8H03DtcAtfConfig *config);

/* Called once per CAN foreground turn, even with TX busy or grant revoked.
 * The application supplies dtc, diagnostic_tick (continuous T6), and
 * optional torque/status data. This supplies now_us. The CAN owner
 * receives native_ready after setup and TX gating are available.
 * An incoherent clock pair is passed as NULL, so the CAN owner can
 * withdraw admission. The application must report clock discontinuities
 * to the CAN owner before it admits RX again. */
Lfj8H03Can13Result lfj8_h03_dtc_target_poll(Lfj8H03DtcTarget *target,
                                         Lfj8H03Can13Input *input, bool native_ready);

/* ABI of the resident H03 RX wrappers. Both run with IE masked.
 * These callbacks never acknowledge the hardware slots. */
void rbm_h03_dtc_rx_begin(uint16_t pending);
void rbm_h03_dtc_rx_observe(uint8_t slot);
/* Called with IE masked, immediately after the OEM ATF monitor snapshot. */
void rbm_h03_dtc_atf_capture(Lfj8H03AtfCircuitStatus status);

#endif
