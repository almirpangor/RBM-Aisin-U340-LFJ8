#include "lfj8_selector_adc.h"

#define LFJ8_SELECTOR_RAW_ADDRESS UINT32_C(0x804BC6)
#define LFJ8_SELECTOR_ADC_MAX UINT16_C(1023)

void lfj8_selector_adc_init(volatile Lfj8SelectorAdc *adc)
{
    adc->pending_raw = UINT16_MAX;
    adc->pending_event = LFJ8_SELECTOR_ADC_NONE;
}

static void publish_locked(volatile Lfj8SelectorAdc *adc, uint16_t raw)
{
    if (adc->pending_event != LFJ8_SELECTOR_ADC_NONE) {
        adc->pending_raw = UINT16_MAX;
        adc->pending_event = LFJ8_SELECTOR_ADC_OVERRUN;
    } else if (raw > LFJ8_SELECTOR_ADC_MAX) {
        adc->pending_raw = UINT16_MAX;
        adc->pending_event = LFJ8_SELECTOR_ADC_INVALID;
    } else {
        adc->pending_raw = raw;
        adc->pending_event = LFJ8_SELECTOR_ADC_VALUE;
    }
}

void lfj8_selector_adc_publish(volatile Lfj8SelectorAdc *adc,
                               const Lfj8RegisterIo *io, uint16_t raw)
{
    const uint32_t saved_state = io->enter(io->context);
    publish_locked(adc, raw);
    io->leave(io->context, saved_state);
}

static void publish_stock_sample(volatile Lfj8SelectorAdc *adc,
                                 const Lfj8RegisterIo *io, uint8_t valid)
{
    const uint32_t saved_state = io->enter(io->context);
    const uint16_t raw = valid ? io->read16(io->context, LFJ8_SELECTOR_RAW_ADDRESS)
                               : UINT16_MAX;
    publish_locked(adc, raw);
    io->leave(io->context, saved_state);
}

void lfj8_selector_adc_publish_9e1b(volatile Lfj8SelectorAdc *adc,
                                    const Lfj8RegisterIo *io, uint8_t valid)
{
    publish_stock_sample(adc, io, valid);
}

void lfj8_selector_adc_publish_9e1c(volatile Lfj8SelectorAdc *adc,
                                    const Lfj8RegisterIo *io, uint8_t valid)
{
    publish_stock_sample(adc, io, valid);
}

Lfj8SelectorAdcReading lfj8_selector_adc_take(volatile Lfj8SelectorAdc *adc,
                                              const Lfj8RegisterIo *io)
{
    Lfj8SelectorAdcReading reading;
    const uint32_t saved_state = io->enter(io->context);
    reading.raw = adc->pending_raw;
    reading.event = adc->pending_event;
    lfj8_selector_adc_init(adc);
    io->leave(io->context, saved_state);
    return reading;
}
