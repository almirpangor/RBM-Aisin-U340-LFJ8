#ifndef RBM_LFJ8_H03_ATF_FEED_H
#define RBM_LFJ8_H03_ATF_FEED_H

#include "factory_hydraulics.h"
#include "lfj8_chery_tx.h"
#include "lfj8_h03_atf.h"

/* Pass a successful ATF snapshot, or NULL if acquisition was unavailable.
 * Use the same wrapping microsecond clock for now_us and the oldest timestamp
 * in command_at. Expire ATF when its age reaches max_age_us (0 < max < 2^31).
 * Optional telemetry receives only the ATF fields, independently of Toyota.
 * A return of 1 updates GP-7184 and includes ATF in the oldest command time.
 * A return of 0 leaves both Toyota fields untouched and disqualifies the cycle.
 * The caller serializes publication to both consumers. */
int lfj8_h03_atf_feed(const Lfj8H03AtfSample *sample, uint32_t now_us, uint32_t max_age_us,
                      FactoryHydraulics *gp, uint32_t *command_at, Lfj8CheryTxInputs *telemetry);

#endif
