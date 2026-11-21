#ifndef RBM_LFJ8_H03_TOYOTA_NVM_PROFILE_H
#define RBM_LFJ8_H03_TOYOTA_NVM_PROFILE_H

#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_nvm_native.h"

/* Include from the application profile after declaring its two qualified,
 * exclusive adaptation block numbers as a const uint8_t[2]. These cannot
 * share erase blocks with DTC, OEM, service or executable data. */
#ifndef RBM_H03_PROFILE_ADAPTATION_BLOCKS
#error "Name the qualified adaptation blocks in RBM_H03_PROFILE_ADAPTATION_BLOCKS"
#endif
_Static_assert(sizeof(RBM_H03_PROFILE_ADAPTATION_BLOCKS) == 2u * sizeof(uint8_t),
               "H03 adaptation storage requires two block numbers");

static inline const uint8_t *lfj8_h03_profile_read_adaptation(void *context, unsigned slot)
{
    (void)context;
    Lfj8H03CycleWorkspace *const work = &rbm_h03_cycle_workspace;

    /* The startup owner asks for slot 0 after cold projection, then slot 1.
     * Capture the pair together. Neither buffer is reused before restore. */
    if (slot == 0u) {
        work->adaptation.readable = lfj8_h03_nvm_native_read_adaptation(
            RBM_H03_PROFILE_ADAPTATION_BLOCKS, work->adaptation.slots);
        return work->adaptation.readable ? work->adaptation.slots[0] : NULL;
    }
    if (slot == 1u && work->adaptation.readable) {
        work->adaptation.readable = false;
        return work->adaptation.slots[1];
    }
    return NULL;
}

#define RBM_H03_PROFILE_READ_ADAPTATION lfj8_h03_profile_read_adaptation

#endif
