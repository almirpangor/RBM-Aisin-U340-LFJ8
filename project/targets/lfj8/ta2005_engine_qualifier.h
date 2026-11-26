#ifndef RBM_TA2005_ENGINE_QUALIFIER_H
#define RBM_TA2005_ENGINE_QUALIFIER_H

#include "rbm_u340e_runtime.h"
#include "ta2005_chery_inputs.h"

typedef struct {
    uint16_t fa62;
    uint8_t rpm_count;
    uint8_t coolant_count;
    uint8_t flags;
} Ta2005EngineQualifier;

enum {
    TA2005_ENGINE_RPM_LATCH = 1u,
    TA2005_ENGINE_COOLANT_LATCH = 2u,
    TA2005_ENGINE_RPM_FAILED = 4u,
    TA2005_ENGINE_COOLANT_VALID = 8u,
};

typedef struct {
    uint16_t retained_fd10;
    uint8_t fallback_fa7b;
    uint8_t retained_e026;
    uint8_t e02b;
    uint8_t coolant_can_enabled;
    uint8_t coherent;
} Ta2005EngineQualificationContext;

enum {
    TA2005_ENGINE_EVALUATED = 1u,
    TA2005_ENGINE_NEW_RPM_DTC = 2u,     /* Native diagnostic index 0x15. */
    TA2005_ENGINE_NEW_COOLANT_DTC = 4u, /* Native diagnostic index 0x14. */
};

/* Cold project state has no qualified RPM or CAN temperature. */
void ta2005_engine_qualifier_init(Ta2005EngineQualifier *state);

/* One evaluation per eligible task 2 release. The caller provides a coherent
 * receiver snapshot with frame age already applied, independent bus faults,
 * and a qualified FA7B fallback (FF when unavailable). Use 1 for an enabled
 * CAN temperature source. The caller owns DTC history and output admission.
 * Pointers refer to distinct objects. A refusal leaves state and out intact. */
unsigned ta2005_engine_qualifier_task2(Ta2005EngineQualifier *state,
    const Ta2005CherySnapshot *raw, const Ta2005EngineQualificationContext *context,
    RbmU340eQualifiedEngineFeed *out);

#endif
