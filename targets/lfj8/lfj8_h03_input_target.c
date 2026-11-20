#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_selector_adc.h"

void rbm_h03_selector_adc_capture(uint16_t raw)
{
    uint32_t captured_us;
    if (rbm_h03_atf_now_us(&captured_us) == 1) {
        lfj8_selector_adc_publish_h03(&rbm_h03_selector_adc_state, &lfj8_h03_mmio, raw, captured_us);
    } else {
        lfj8_selector_adc_clock_lost(&rbm_h03_selector_adc_state, &lfj8_h03_mmio);
    }
}
