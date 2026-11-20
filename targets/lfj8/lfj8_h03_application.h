#ifndef RBM_LFJ8_H03_APPLICATION_H
#define RBM_LFJ8_H03_APPLICATION_H

#include "lfj8_h03_cycle.h"
#include "lfj8_h03_phase_startup.h"

typedef struct {
    uint32_t last_toyota_at;
    uint8_t running;
} Lfj8H03Application;

typedef enum {
    LFJ8_H03_TOYOTA_WAIT,
    LFJ8_H03_TOYOTA_EVENT,
    LFJ8_H03_TOYOTA_FAULT,
} Lfj8H03ToyotaEvent;

typedef struct {
    const Lfj8H03TakeoverOps *takeover_ops;
    Lfj8H03PhaseStartupConfig phase_config;
    Lfj8H03Takeover *takeover;
    Lfj8H03Cycle *cycle;
    RbmU340eRuntime *runtime;
    Lfj8H03CycleWorkspace *workspace;
    Lfj8H03MainResult *main;
    Lfj8H03CycleInput *input;
    const FactoryGearState *startup_gear;
    const FactoryHydraulics *startup_gp;
    RbmU340eRangeState startup_range;
    uint32_t toyota_max_period_ticks;
    uint8_t startup_request_1120;

    /* Called under takeover_ops->io's nestable interrupt lock. ram_owned
     * must be independent of the reserved RAM. The linker/boot path must
     * guarantee that the cold gate runs before any application IRQ can
     * read retained RAM. If unavailable there, access must stay blocked
     * until startup can clear the gate. Keep ownership while running. */
    int (*ram_owned)(void *context);
    int (*clock_ready)(void *context);

    /* Called in serialized foreground with the gate closed and outputs
     * inhibited. Reset producer queues and initialize their single objects,
     * including any persisted GP restore inputs, before returning success. */
    int (*initialize)(void *context);

    /* Nonblocking read of the independent Toyota timer source. Return one
     * coherent input/load snapshot and its producer timestamp in TML0CT
     * ticks. Keep input.command_at and the load timestamps in microseconds.
     * Report any lost release, including loss before the first delivery.
     * A repeated sequence must retain its original producer timestamp.
     * Keep load->sample stable until the consumer returns. */
    Lfj8H03ToyotaEvent (*take_toyota)(void *context, Lfj8H03CycleInput *input,
                                     Lfj8H03CycleLoad *load, uint32_t *released_at);

    /* Serialized foreground, with interrupts enabled as in the OEM caller.
     * main is valid only during this call and is NULL unless this turn ran
     * Toyota MAIN. Output consumers must recheck the event under the output
     * lock, convert sample ages and use the takeover guard. */
    void (*service_phase)(void *context, const Lfj8H03PhaseEvent *phase,
                          const Lfj8H03MainResult *main);
} Lfj8H03ApplicationBinding;

/* The integrating target supplies one immutable binding and one gate in its
 * reserved RAM. All storage addresses and the bootstrap I/O, lock and RAM
 * ownership probe must be valid even on the cold path. The inhibit callback
 * must work before the takeover and GP objects are initialized. */
extern const Lfj8H03ApplicationBinding rbm_h03_application_binding;
extern Lfj8H03Application rbm_h03_application;

/* Tests the lifecycle gate under the same interrupt lock used by startup.
 * Hardware qualifications and the output takeover checks are still required. */
int lfj8_h03_application_running_locked(void);
void rbm_h03_application_cold_gate(void);
void rbm_h03_phase_startup_callback(void);
void rbm_h03_phase_wait_callback(void);
void rbm_h03_application_foreground_callback(void);

#endif
