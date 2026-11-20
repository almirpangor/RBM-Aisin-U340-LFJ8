#include "ta2005_engine_qualifier.h"

/* State transitions from R3 research/probes/ta2005_chery_qualifier.c,
 * commit 7585de6945b4b6b3ef381c6062070a5f417cf588. S03 06E856/06ED70
 * publish FA62/E026.1 and F9B8/FD10.12 to the downstream Toyota input. */
enum {
    RPM_FAULT_THRESHOLD = 100,
    COOLANT_FAULT_THRESHOLD = 200,
    RESTORE_THRESHOLD = 250,
    BUS_FAULT_MASK = 0x84,
};

void ta2005_engine_qualifier_init(Ta2005EngineQualifier *state)
{
    *state = (Ta2005EngineQualifier){.flags = TA2005_ENGINE_RPM_FAILED};
}

static unsigned qualify_rpm(Ta2005EngineQualifier *state, uint16_t fad8)
{
    if (fad8 == UINT16_MAX) {
        if (state->flags & TA2005_ENGINE_RPM_LATCH) {
            state->rpm_count = 0;
        } else if (state->rpm_count <= RPM_FAULT_THRESHOLD) {
            ++state->rpm_count;
        } else {
            state->rpm_count = 0;
            state->fa62 = 0;
            state->flags |= TA2005_ENGINE_RPM_LATCH | TA2005_ENGINE_RPM_FAILED;
            return TA2005_ENGINE_NEW_RPM_DTC;
        }
        return 0;
    }
    if ((state->flags & TA2005_ENGINE_RPM_LATCH) && state->rpm_count <= RESTORE_THRESHOLD) {
        ++state->rpm_count;
        return 0;
    }
    state->rpm_count = 0;
    state->fa62 = fad8;
    state->flags &= (uint8_t)~(TA2005_ENGINE_RPM_LATCH | TA2005_ENGINE_RPM_FAILED);
    return 0;
}

static unsigned qualify_coolant(Ta2005EngineQualifier *state, uint8_t f9e9, unsigned can_enabled)
{
    if (f9e9 == UINT8_MAX) {
        if (!can_enabled) {
            return 0;
        }
        if (state->flags & TA2005_ENGINE_COOLANT_LATCH) {
            state->coolant_count = 0;
        } else if (state->coolant_count <= COOLANT_FAULT_THRESHOLD) {
            ++state->coolant_count;
        } else {
            state->coolant_count = 0;
            state->flags |= TA2005_ENGINE_COOLANT_LATCH;
            state->flags &= (uint8_t)~TA2005_ENGINE_COOLANT_VALID;
            return TA2005_ENGINE_NEW_COOLANT_DTC;
        }
        return 0;
    }
    if ((state->flags & TA2005_ENGINE_COOLANT_LATCH) && state->coolant_count <= RESTORE_THRESHOLD) {
        ++state->coolant_count;
        return 0;
    }
    state->coolant_count = 0;
    state->flags &= (uint8_t)~TA2005_ENGINE_COOLANT_LATCH;
    state->flags |= TA2005_ENGINE_COOLANT_VALID;
    return 0;
}

unsigned ta2005_engine_qualifier_task2(Ta2005EngineQualifier *state,
    const Ta2005CherySnapshot *raw, const Ta2005EngineQualificationContext *context,
    RbmU340eQualifiedEngineFeed *out)
{
    if (!state || !raw || !context || !out || context->coherent != 1u) {
        return 0;
    }
    const uint16_t fad8 = raw->usable & TA2005_CHERY_SPEED ? raw->speed_fad8 : UINT16_MAX;
    const uint8_t f9e9 = raw->usable & TA2005_CHERY_COOLANT ? raw->coolant_f9e9 : UINT8_MAX;
    const unsigned can_enabled = context->coolant_can_enabled == 1u;
    unsigned events = TA2005_ENGINE_EVALUATED;
    if (context->e02b & BUS_FAULT_MASK) {
        state->fa62 = 0;
        state->flags |= TA2005_ENGINE_RPM_FAILED;
        state->flags &= (uint8_t)~TA2005_ENGINE_COOLANT_VALID;
    } else {
        events |= qualify_rpm(state, fad8);
        events |= qualify_coolant(state, f9e9, can_enabled);
    }

    const unsigned use_can = can_enabled && (state->flags & TA2005_ENGINE_COOLANT_VALID);
    out->fa62 = state->fa62;
    out->fd10 = (uint16_t)((context->retained_fd10 & 0xEFFFu) | (use_can ? 0u : 0x1000u));
    out->f9b8 = use_can ? f9e9 : context->fallback_fa7b;
    out->e026 = (uint8_t)((context->retained_e026 & 0xFDu) |
                         ((state->flags & TA2005_ENGINE_RPM_FAILED) ? 0x02u : 0u));
    out->coherent = 1u;
    return events;
}
