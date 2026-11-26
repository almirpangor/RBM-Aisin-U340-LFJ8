#ifndef RBM_LFJ8_H03_ATF_TARGET_H
#define RBM_LFJ8_H03_ATF_TARGET_H

#include "lfj8_h03_atf.h"

/* Target startup binds this symbol to the one ATF object in the control
 * storage and initializes it before allowing any of the hooks to run. */
extern volatile Lfj8H03Atf rbm_h03_atf_state;

/* Platform-owned, IRQ-safe clock. Return 1 with the current wrapping
 * microsecond timestamp, or 0 until it is qualified. A new clock epoch
 * requires restarting the application with the hooks quiescent. */
int rbm_h03_atf_now_us(uint32_t *now_us);

/* Only the application clock owner may set the native qualification. Start
 * at zero, qualify both physical 1 MHz clocks and revoke before any known
 * counter reinitialization. The native time provider can also revoke it. */
extern volatile uint8_t rbm_h03_tml0_1mhz_qualified;

/* Native clock checks shared by ATF and the capture target, under the H03
 * interrupt lock. An observed mismatch latches readiness off until rebase. */
int lfj8_h03_sensor_clock_registers_match(void);
int lfj8_h03_sensor_clock_ready_locked(void);

/* Entry points from h03_atf_hooks.S, with maskable interrupts excluded. */
void rbm_h03_atf_adc_callback(void);
int rbm_h03_atf_source_callback(uint16_t raw, uint32_t *acquired_us);
void rbm_h03_atf_publish_callback(uint32_t site, const uint32_t *acquired_us);

/* Foreground consumer. Time, current ATF validity and the measured value
 * are captured under the same exclusion. Failure clears the sample. */
int lfj8_h03_atf_target_snapshot(uint32_t max_age_us, Lfj8H03AtfSample *sample);

#endif
