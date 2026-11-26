#include "lfj8_h03_atf_feed.h"

#define CLOCK_HALF_RANGE UINT32_C(0x80000000)

int lfj8_h03_atf_feed(const Lfj8H03AtfSample *sample, uint32_t now_us, uint32_t max_age_us,
                      FactoryHydraulics *gp, uint32_t *command_at, Lfj8CheryTxInputs *telemetry)
{
    const int fresh = sample && max_age_us < CLOCK_HALF_RANGE &&
                      now_us - sample->acquired_us < max_age_us;
    if (telemetry) {
        telemetry->atf_valid = fresh;
        telemetry->atf_c = fresh ? sample->atf_c : 0;
    }
    if (!fresh || !gp || !command_at) {
        return 0;
    }

    const uint32_t command_age = now_us - *command_at;
    if (command_age >= CLOCK_HALF_RANGE ||
        !factory_hydraulics_set(gp, -7184, 2u, sample->toyota_gp_m7184)) {
        return 0;
    }
    if (now_us - sample->acquired_us > command_age) {
        *command_at = sample->acquired_us;
    }
    return 1;
}
