#ifndef RBM_LFJ8_H03_ENGINE_CONTEXT_H
#define RBM_LFJ8_H03_ENGINE_CONTEXT_H

#include "lfj8_h03_application.h"

/* The CAN-only H03 bench context. The application calls this under its
 * native interrupt lock. Retained status comes from the previous coherent
 * engine feed; E02B comes from shared DTC state. The unavailable independent
 * coolant fallback remains FF. The engine feed widens the TML0 anchor with
 * dates for qualified CAN operands. */
int rbm_h03_engine_context_for_task2(void *context, const Lfj8H03SensorSnapshot *sensors,
    Ta2005EngineQualificationContext *engine, bool *inhibit_history, uint32_t *oldest_us);

#endif
