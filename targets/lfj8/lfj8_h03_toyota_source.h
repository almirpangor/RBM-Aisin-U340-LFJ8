#ifndef RBM_LFJ8_H03_TOYOTA_SOURCE_H
#define RBM_LFJ8_H03_TOYOTA_SOURCE_H

#include "lfj8_h03_application.h"

typedef struct {
    uint32_t next_at;
    uint32_t last_observed;
    uint32_t sequence;
    uint8_t status;
} Lfj8H03ToyotaRelease;

/* An immutable platform context. The release state belongs to one foreground
 * caller. RAM and the clock are checked with maskable interrupts excluded.
 * Supply measured timing for the independent Toyota cadence in TML0 ticks. */
typedef struct {
    Lfj8H03ToyotaRelease *release;
    const Lfj8H03Application *application;
    uint32_t period_ticks;
    uint32_t max_lateness_ticks;
    void *platform;
    int (*ram_owned)(void *platform);
    int (*clock_ready)(void *platform);
    int (*capture)(void *platform, const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
                   Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load);
} Lfj8H03ToyotaSource;

/* During application initialization, under exclusive ownership with the
 * lifecycle gate closed. The first take anchors to the running application's
 * startup timestamp even if it is called late. No backlog is emitted. */
void lfj8_h03_toyota_source_reset(Lfj8H03ToyotaRelease *release);

/* Lfj8H03ApplicationBinding.take_toyota adapter. The I/O context points to the
 * immutable source. It uses qualified continuous TML0CT, never the OEM phase
 * flag. capture runs in serialized foreground and must return a stable, valid
 * snapshot whose producer timestamps are preserved. No result is usable
 * unless EVENT is returned. Stop and reinitialize on fault or ownership loss. */
Lfj8H03ToyotaEvent lfj8_h03_toyota_source_take(void *context, const Lfj8H03SensorSnapshot *sensors,
                                               Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load,
                                               uint32_t *released_at);

#endif
