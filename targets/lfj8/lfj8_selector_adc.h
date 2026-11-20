#ifndef RBM_LFJ8_SELECTOR_ADC_H
#define RBM_LFJ8_SELECTOR_ADC_H

#include "lfj8_donor_io.h"

typedef enum {
    LFJ8_SELECTOR_ADC_NONE,
    LFJ8_SELECTOR_ADC_VALUE,
    LFJ8_SELECTOR_ADC_INVALID,
    LFJ8_SELECTOR_ADC_OVERRUN,
} Lfj8SelectorAdcEvent;

typedef struct {
    uint16_t raw;
    Lfj8SelectorAdcEvent event;
} Lfj8SelectorAdcReading;

typedef struct {
    uint16_t pending_raw;
    Lfj8SelectorAdcEvent pending_event;
} Lfj8SelectorAdc;

/* Initialize in the caller-owned state before enabling the producer. */
void lfj8_selector_adc_init(volatile Lfj8SelectorAdc *adc);

/* Publish once per actual conversion event. Use UINT16_MAX for invalid data.
 * Producer and consumer must share the same exclusion mechanism in io.
 */
void lfj8_selector_adc_publish(volatile Lfj8SelectorAdc *adc,
                               const Lfj8RegisterIo *io, uint16_t raw);

/* Read-only binding to the verified 9E1B map. Call once after the ADC0 channel 2
 * store at 0x040370. Callers may mark an event invalid to skip the RAM read.
 * Any other revision requires independent verification of this binding.
 */
void lfj8_selector_adc_publish_9e1b(volatile Lfj8SelectorAdc *adc,
                                    const Lfj8RegisterIo *io, uint8_t valid);

/* Consume a pending event once. The raw value is UINT16_MAX for every event
 * except VALUE. OVERRUN drops all pending samples because their order is lost.
 * Pass VALUE/INVALID/OVERRUN to the decoder. NONE is ordinary idle polling.
 */
Lfj8SelectorAdcReading lfj8_selector_adc_take(volatile Lfj8SelectorAdc *adc,
                                              const Lfj8RegisterIo *io);

#endif
