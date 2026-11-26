#ifndef RBM_LFJ8_SELECTOR_ADC_H
#define RBM_LFJ8_SELECTOR_ADC_H

#include "lfj8_donor_io.h"

#define LFJ8_H03_P1DATA_ADDRESS UINT32_C(0x800701)

typedef enum {
    LFJ8_SELECTOR_ADC_NONE,
    LFJ8_SELECTOR_ADC_VALUE,
    LFJ8_SELECTOR_ADC_INVALID,
    LFJ8_SELECTOR_ADC_OVERRUN,
    LFJ8_SELECTOR_ADC_CLOCK_LOST,
} Lfj8SelectorAdcEvent;

typedef struct {
    uint32_t captured_us;
    uint16_t raw;
    uint8_t p1data;
    uint8_t p1_valid;
    Lfj8SelectorAdcEvent event;
} Lfj8SelectorAdcReading;

typedef struct {
    uint32_t pending_us;
    uint16_t pending_raw;
    uint8_t pending_p1data;
    uint8_t pending_p1_valid;
    Lfj8SelectorAdcEvent pending_event;
} Lfj8SelectorAdc;

/* Initialize in the caller-owned state before enabling the producer. */
void lfj8_selector_adc_init(volatile Lfj8SelectorAdc *adc);

/* Publish once per actual conversion event with its capture time in microseconds.
 * Use UINT16_MAX for invalid data.
 * Producer and consumer must share the same exclusion mechanism in io.
 */
void lfj8_selector_adc_publish(volatile Lfj8SelectorAdc *adc,
                               const Lfj8RegisterIo *io, uint16_t raw, uint32_t captured_us);

/* H03 only. Capture P1DATA together with a fresh AN2 conversion under the
 * same lock. p1_valid marks the raw byte and implies no GPIO pin assignment. */
void lfj8_selector_adc_publish_h03(volatile Lfj8SelectorAdc *adc,
    const Lfj8RegisterIo *io, uint16_t raw, uint32_t captured_us);

/* Discard an unconsumed value. The untimed loss stays pending until taken
 * even if the clock provides fresh timestamps before the next poll. */
void lfj8_selector_adc_clock_lost(volatile Lfj8SelectorAdc *adc, const Lfj8RegisterIo *io);

/* Read-only binding to the verified 9E1B map. Call once after the ADC0 channel 2
 * store at 0x040370. Callers may mark an event invalid to skip the RAM read.
 * Any other revision requires independent verification of this binding.
 */
void lfj8_selector_adc_publish_9e1b(volatile Lfj8SelectorAdc *adc,
                                    const Lfj8RegisterIo *io, uint8_t valid, uint32_t captured_us);

/* Read-only binding to LFJ8-T-D.bin with embedded 9E1C identity. Call once
 * after confirmation of a fresh channel 2 conversion and its store at
 * 0x040370. A zero valid flag publishes INVALID without reading stock RAM.
 */
void lfj8_selector_adc_publish_9e1c(volatile Lfj8SelectorAdc *adc,
                                    const Lfj8RegisterIo *io, uint8_t valid, uint32_t captured_us);

/* Consume a pending event once. The raw value is UINT16_MAX for every event
 * except VALUE. OVERRUN discards the values and reports the latest event time.
 * CLOCK_LOST invalidates the decoder without using its timestamp.
 * NONE is ordinary idle polling.
 */
Lfj8SelectorAdcReading lfj8_selector_adc_take(volatile Lfj8SelectorAdc *adc,
                                              const Lfj8RegisterIo *io);

/* H03 startup binds and initializes this symbol in the existing selector
 * storage before enabling the 0x040370 hook. The hook runs with IRQs masked. */
extern volatile Lfj8SelectorAdc rbm_h03_selector_adc_state;
void rbm_h03_selector_adc_capture(uint16_t raw);

#endif
