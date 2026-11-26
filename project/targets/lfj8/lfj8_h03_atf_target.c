#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_input_lifecycle.h"
#include "lfj8_h03_mmio.h"

static int read_time(uint32_t *now_us)
{
    if (rbm_h03_atf_now_us(now_us) == 1) {
        return 1;
    }
    /* Keep the timestamp watermarks so a retry cannot revive this reading. */
    rbm_h03_atf_state.pending_adc = 0;
    rbm_h03_atf_state.valid = 0;
    return 0;
}

void rbm_h03_atf_adc_callback(void)
{
    uint32_t now_us;
    if (lfj8_h03_application_running_locked() && read_time(&now_us)) {
        lfj8_h03_atf_after_adc_store(&rbm_h03_atf_state, &lfj8_h03_mmio, now_us);
    }
}

int rbm_h03_atf_source_callback(uint16_t raw, uint32_t *acquired_us)
{
    return lfj8_h03_application_running_locked() &&
           lfj8_h03_atf_capture_source(&rbm_h03_atf_state, raw, acquired_us);
}

void rbm_h03_atf_publish_callback(uint32_t site, const uint32_t *acquired_us)
{
    uint32_t now_us;
    if (lfj8_h03_application_running_locked() && read_time(&now_us)) {
        lfj8_h03_atf_after_store(&rbm_h03_atf_state, &lfj8_h03_mmio, site, acquired_us, now_us);
    }
}

int lfj8_h03_atf_target_snapshot(uint32_t max_age_us, Lfj8H03AtfSample *sample)
{
    if (!sample) {
        return 0;
    }
    const uint32_t saved = lfj8_h03_mmio.enter(lfj8_h03_mmio.context);
    uint32_t now_us;
    int valid = 0;
    if (lfj8_h03_application_running_locked() && read_time(&now_us)) {
        valid = lfj8_h03_atf_snapshot(&rbm_h03_atf_state, &lfj8_h03_mmio,
                                      now_us, max_age_us, sample);
    } else {
        *sample = (Lfj8H03AtfSample){0};
    }
    lfj8_h03_mmio.leave(lfj8_h03_mmio.context, saved);
    return valid;
}
