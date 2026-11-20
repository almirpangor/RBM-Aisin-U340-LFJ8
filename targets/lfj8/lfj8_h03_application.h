#ifndef RBM_LFJ8_H03_APPLICATION_H
#define RBM_LFJ8_H03_APPLICATION_H

#include "lfj8_h03_cycle.h"
#include "lfj8_h03_engine_feed.h"
#include "lfj8_h03_phase_startup.h"
#include "lfj8_h03_sensor_feed.h"

typedef struct {
    uint32_t last_toyota_at;
    uint8_t running;
    uint8_t adaptation_status; /* RbmU340eAdaptationResult, valid while running. */
} Lfj8H03Application;

typedef enum {
    LFJ8_H03_TOYOTA_WAIT,
    LFJ8_H03_TOYOTA_EVENT,
    LFJ8_H03_TOYOTA_FAULT,
} Lfj8H03ToyotaEvent;

typedef struct {
    Lfj8H03EngineFeedTarget target;
    uint16_t max_age_ticks;
    uint16_t max_poll_gap_us;
    /* Called under the application I/O lock on an admitted Task 2 release.
     * Return 1 with coherent qualifier context, history policy and a
     * conservative oldest TML0 timestamp for the context operands, including
     * fallback inputs. The receiver adds its CAN and retained RPM timestamps.
     * Refuse if the context bound is unavailable.
     * This callback must not advance the qualifier or consume a CAN frame. */
    int (*context_for_task2)(void *context, const Lfj8H03SensorSnapshot *sensors,
        Ta2005EngineQualificationContext *engine, bool *inhibit_history, uint32_t *oldest_us);
} Lfj8H03ApplicationEngine;

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
    /* Optional CAN source. Use the same locked I/O, CAN owner and shared DTC
     * state as the application. initialize brings up those shared owners.
     * When set, the lifecycle owns input.engine and merges its age; the
     * take_toyota provider supplies the age of the other cycle operands. */
    const Lfj8H03ApplicationEngine *engine;

    /* Called under takeover_ops->io's nestable interrupt lock. ram_owned
     * must be independent of the reserved RAM. The linker/boot path must
     * guarantee that the cold gate runs before any application IRQ can
     * read retained RAM. If unavailable there, access must stay blocked
     * until startup can clear the gate. Once granted, keep ownership
     * through startup and while the application is running. */
    int (*ram_owned)(void *context);
    /* Independently qualify continuous TML0 and TML1 at 1 MHz. The
     * application owns the sensor epoch. Close its gate before resetting or
     * reconfiguring either timer, then use the normal startup path to rearm.
     * The platform must use the native H03 lock for all sensor producers. */
    int (*clock_ready)(void *context);

    /* Called in serialized foreground with the gate closed and outputs
     * inhibited. Reset producer queues and initialize their single objects,
     * including any adaptation read state. Return RBM_U340E_STARTUP_PREPARED
     * for a complete snapshot, RBM_U340E_STARTUP_S01_COLD only when the
     * platform has qualified the S01 cold precondition, or
     * RBM_U340E_STARTUP_UNQUALIFIED on failure. Both successful kinds need
     * complete startup_gear and startup_gp snapshots. */
    int (*initialize)(void *context);

    /* Optional service close, under the native lock and owned RAM. Called
     * before invalidating the shared clock, including cold and failed start.
     * It must tolerate retained/uninitialized service state and repetition. */
    void (*stop_service_locked)(void);

    /* Optional read-only startup source. Return FACTORY_ADAPT_RECORD_BYTES
     * raw bytes for slot 0 or 1, even when erased or damaged. NULL denotes
     * a failed read. Keep both snapshots distinct, separate from runtime,
     * and stable until restore completes. Called in serialized foreground
     * with outputs inhibited and outside the takeover interrupt lock.
     * Without a reader, restore uses the S01 cold baseline. */
    FactoryAdaptRead read_adaptation;

    /* Nonblocking read of the independent Toyota timer source. Return one
     * coherent input/load snapshot and its producer timestamp in TML0CT
     * ticks. Keep input.command_at and the load timestamps in microseconds.
     * Report any lost release, including loss before the first delivery.
     * A repeated sequence must retain its original producer timestamp.
     * Keep load->sample stable until the consumer returns. sensors is valid
     * during the call; qualify its individual channels before using them. */
    Lfj8H03ToyotaEvent (*take_toyota)(void *context, const Lfj8H03SensorSnapshot *sensors,
                                     Lfj8H03CycleInput *input,
                                     Lfj8H03CycleLoad *load, uint32_t *released_at);

    /* Serialized foreground, with interrupts enabled as in the OEM caller.
     * main is valid only during this call and is NULL unless this turn ran
     * Toyota MAIN. Output consumers must recheck the event under the output
     * lock, convert sample ages and use the takeover guard. sensors is the
     * same snapshot as take_toyota received and is valid only during this call. */
    void (*service_phase)(void *context, const Lfj8H03PhaseEvent *phase,
                          const Lfj8H03SensorSnapshot *sensors,
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
