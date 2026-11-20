/* Simulator supplies only the platform binding. The callbacks are target code. */
#include "lfj8_h03_application.h"
#include "lfj8_h03_mmio.h"

enum {
    STOCK, OWNED, INVALID_PERIOD, UNOWNED, BAD_HEADER, BAD_TRAILER, PARTIAL,
    STOPPED_H03, DUPLICATE, TOYOTA_GAP, RESTART, STOPPED_TOYOTA, BAD_CLOCK,
    NO_PROVIDER, COALESCED, OVERTAKEN,
};

static volatile uint32_t *const timer = (volatile uint32_t *)0x8003e0;
static volatile uint8_t *const oem_flag = (volatile uint8_t *)0x804ade;
static volatile Lfj8H03PhaseClock phase = {.min_period = 0xba};
static Lfj8H03Takeover takeover = {.command_at = 0xdead, .pending = 1u};
static Lfj8H03Cycle cycle;
static RbmU340eRuntime runtime;
static FactoryHydraulics startup_gp;
static Lfj8H03CycleWorkspace workspace;
static Lfj8H03MainResult main_result;
static Lfj8H03CycleInput input;
static RbmU340eQualifiedLoadFeed load_feed = {.coherent = 1u};
static const FactoryGearState gear = {
    .driver5302 = {1, 1}, .u7184 = 20000, .u7164 = 26000, .u7186 = 3072,
    .periods = {65535, 65535, 65535, 65535, 65535, 65535},
};

Lfj8H03Application rbm_h03_application = {.running = 1u}; /* Retained RAM. */
uint32_t boot_context[19];
unsigned cold_inhibit, initialize_calls, inhibit_calls, phase_calls, main_calls;
static unsigned source_calls, advances;
static uint32_t last_release;
static int unexpected, wake_after_inhibit, replay_old;

void fixture_publish_first_phase(void);
void fixture_run_wait(void);
void fixture_run_foreground(void);

static int ram_owned(void *context)
{
    (void)context;
    return BOOT_CASE != UNOWNED;
}

static int clock_ready(void *context)
{
    (void)context;
    return BOOT_CASE != BAD_CLOCK;
}

static void unexpected_action(void *context)
{
    (void)context;
    unexpected = 1;
}

static int output_qualified(void *context)
{
    unexpected_action(context);
    return 0;
}

static void unexpected_write(void *context, uint32_t address, uint32_t value)
{
    (void)address;
    (void)value;
    unexpected_action(context);
}

static void inhibit(void *context)
{
    (void)context;
    ++inhibit_calls;
    if (*(volatile const uint8_t *)0x1200 == 0u) {
        ++cold_inhibit;
        rbm_h03_phase_release_callback(*timer);
        if (phase.min_period != 0xbau || phase.have_release || rbm_h03_application.running ||
            takeover.pending || takeover.ops) {
            unexpected = 1;
        }
    }
    if (wake_after_inhibit) {
        /* Observe the inhibit with the OEM flag still low, then end the wait. */
        if (*oem_flag != 0u) {
            unexpected = 1;
        }
        *oem_flag = 1u;
    }
}

static int initialize(void *context)
{
    (void)context;
    ++initialize_calls;
    if (*(volatile const uint8_t *)0x1200 != 1u ||
        lfj8_h03_mmio.read16(0, 0x80481a) != 7u || rbm_h03_application.running ||
        takeover.pending || takeover.ops || runtime.initialized) {
        unexpected = 1;
        return 0;
    }
    source_calls = advances = 0u;
    return BOOT_CASE != PARTIAL &&
        factory_hydraulics_set(&startup_gp, -7184, 2u, gear.u7184) &&
        factory_hydraulics_set(&startup_gp, -7164, 2u, gear.u7164) &&
        factory_hydraulics_set(&startup_gp, -7186, 2u, gear.u7186);
}

static Lfj8H03ToyotaEvent take_toyota(void *context, Lfj8H03CycleInput *result,
                                    Lfj8H03CycleLoad *load, uint32_t *released_at)
{
    (void)context;
    if (lfj8_h03_mmio.read16(0, 0x804bc6) != 347u) {
        unexpected = 1;
        return LFJ8_H03_TOYOTA_FAULT;
    }
    ++source_calls;
    if (replay_old) {
        *released_at = last_release;
    } else if (BOOT_CASE == DUPLICATE && source_calls == 3u) {
        *released_at = last_release;
    } else if (!(source_calls & 1u) || BOOT_CASE == STOPPED_TOYOTA) {
        return LFJ8_H03_TOYOTA_WAIT;
    } else {
        ++advances;
        last_release = *timer - 2u; /* Separate producer timestamp. */
        *released_at = last_release;
    }

    const uint32_t sample_us = *timer + 0x01000000u;
    *result = (Lfj8H03CycleInput){
        .engine = {.fa62 = 9600, .f9b8 = 137, .coherent = 1u},
        .command_at = sample_us - 1u,
        .event = advances - 2u + (BOOT_CASE == TOYOTA_GAP && advances == 2u),
        .selector = main_calls < 2u ? RBM_U340E_SELECTOR_N : RBM_U340E_SELECTOR_D,
        .range_5722 = main_calls < 2u ? 5u : 1u,
        .qualified = 1u,
    };
    load_feed.sampled_at = sample_us - 3u;
    load_feed.gp_8270 = 79;
    *load = (Lfj8H03CycleLoad){.sample = &load_feed, .now_us = sample_us, .max_age_us = 3u};
    if (BOOT_CASE == OVERTAKEN && source_calls == 1u) {
        *timer += 8u;
        fixture_publish_first_phase();
    }
    return LFJ8_H03_TOYOTA_EVENT;
}

static void service_phase(void *context, const Lfj8H03PhaseEvent *event,
                          const Lfj8H03MainResult *result)
{
    (void)context;
    if (event->sequence != phase.consumed || event->released_at != *timer ||
        *oem_flag != 0u || !rbm_h03_application.running) {
        unexpected = 1;
    }
    ++phase_calls;
    if (result) {
        ++main_calls;
        if (!result->valid || result->command_at != load_feed.sampled_at ||
            (main_calls == 3u && (result->gear_4848 != 1u || result->shift.count != 2u ||
                                 result->shift.writes[0].value != 1u ||
                                 result->shift.writes[1].value != 0u))) {
            unexpected = 1;
        }
    }
}

static const Lfj8H03TakeoverOps ops = {
    .io = &lfj8_h03_mmio, .clock_ticks = lfj8_h03_tml0ct_m32r,
    .write32 = unexpected_write, .qualified = output_qualified,
    .arbitrate = unexpected_action, .apply = unexpected_action, .inhibit = inhibit,
    .phase_clock = &phase, .isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED,
};

const Lfj8H03ApplicationBinding rbm_h03_application_binding = {
    .takeover_ops = &ops,
    .phase_config = {8u, BOOT_CASE == INVALID_PERIOD ? 16u : 12u, 2u, 24u},
    .takeover = &takeover, .cycle = &cycle, .runtime = &runtime, .workspace = &workspace,
    .main = &main_result, .input = &input, .startup_gear = &gear, .startup_gp = &startup_gp,
    .toyota_max_period_ticks = 23u,
    .ram_owned = ram_owned, .clock_ready = clock_ready, .initialize = initialize,
    .take_toyota = BOOT_CASE == NO_PROVIDER ? NULL : take_toyota,
    .service_phase = service_phase,
};

static void next_phase(void)
{
    *timer += 8u;
    fixture_publish_first_phase();
    fixture_run_wait();
    fixture_run_foreground();
}

static int still_stale(void)
{
    return rbm_h03_application.running && phase.min_period == 0xbau &&
        takeover.command_at == 0xdeadu && takeover.pending && !takeover.ops;
}

static int rejected(void)
{
    return !rbm_h03_application.running && !takeover.pending && phase.faulted &&
        !main_result.valid && cycle.faulted && !runtime.initialized;
}

int fixture_complete(void)
{
    if (unexpected || *oem_flag != 0u) {
        return 1;
    }
    if (BOOT_CASE == STOCK || BOOT_CASE == UNOWNED) {
        return !still_stale() || initialize_calls || inhibit_calls;
    }
    if (cold_inhibit != 1u || inhibit_calls != 2u) {
        return 2;
    }
    if (BOOT_CASE == INVALID_PERIOD || BOOT_CASE == PARTIAL ||
        BOOT_CASE == BAD_CLOCK || BOOT_CASE == NO_PROVIDER) {
        const unsigned expected_init = BOOT_CASE == INVALID_PERIOD || BOOT_CASE == PARTIAL;
        return rbm_h03_application.running || runtime.initialized || takeover.ops ||
            takeover.pending || initialize_calls != expected_init ||
            (BOOT_CASE == INVALID_PERIOD && !phase.faulted);
    }
    if (!rbm_h03_application.running || !runtime.initialized || phase.have_release ||
        initialize_calls != 1u || takeover.pending || lfj8_h03_takeover_check_phase(&takeover) !=
        LFJ8_H03_PHASE_WAIT) {
        return 3;
    }
    fixture_run_foreground(); /* OEM startup bit has no project event. */
    if (phase_calls || source_calls) {
        return 4;
    }
    if (BOOT_CASE == COALESCED) {
        takeover.pending = 1u;
        *timer += 8u;
        fixture_publish_first_phase();
        next_phase();
        return unexpected || !rejected() || phase.consumed || phase_calls || source_calls ||
            inhibit_calls != 3u;
    }
    next_phase();
    if (BOOT_CASE == OVERTAKEN) {
        *oem_flag = 0u;
        return unexpected || !rejected() || phase.consumed != 1u || phase.latest.sequence != 2u ||
            phase_calls || source_calls != 1u || inhibit_calls != 3u;
    }
    if (phase.consumed != 1u || source_calls != 1u || phase_calls != 1u ||
        (BOOT_CASE != STOPPED_TOYOTA && cycle.last_event != UINT32_MAX)) {
        return 5;
    }
    if (BOOT_CASE == STOPPED_H03) {
        takeover.pending = 1u;
        wake_after_inhibit = 1;
        *timer += 13u;
        fixture_run_wait();
        wake_after_inhibit = 0;
        fixture_publish_first_phase();
        fixture_run_foreground();
        *oem_flag = 0u;
        return unexpected || !rejected() || phase_calls != 1u || inhibit_calls != 3u;
    }
    next_phase();
    if (BOOT_CASE == STOPPED_TOYOTA) {
        takeover.pending = 1u;
        next_phase(); /* H03 continues at the same cadence. */
        return unexpected || !rejected() || source_calls != 2u || phase_calls != 2u ||
            inhibit_calls != 3u;
    }
    if (BOOT_CASE == RESTART) {
        takeover.pending = 1u;
        rbm_h03_phase_startup_callback();
        if (!rbm_h03_application.running || takeover.pending || cycle.have_event ||
            main_result.valid || initialize_calls != 2u || inhibit_calls != 3u) {
            return 6;
        }
        replay_old = 1;
        next_phase();
        return unexpected || !rejected() || phase_calls != 2u || inhibit_calls != 4u;
    }
    takeover.pending = BOOT_CASE == TOYOTA_GAP;
    next_phase();
    if (BOOT_CASE == TOYOTA_GAP) {
        return unexpected || !rejected() || cycle.last_event != UINT32_MAX ||
            phase_calls != 2u || inhibit_calls != 3u;
    }
    if (BOOT_CASE == DUPLICATE) {
        return unexpected || !rbm_h03_application.running || cycle.last_event != UINT32_MAX ||
            rbm_h03_application.last_toyota_at != last_release || phase_calls != 3u ||
            inhibit_calls != 2u;
    }
    if (cycle.last_event != 0u || phase_calls != 3u) {
        return 7;
    }
    while (rbm_h03_application.running && main_calls < 3u && phase_calls < 90u) {
        next_phase();
    }
    return unexpected || !rbm_h03_application.running || main_calls != 3u || inhibit_calls != 2u;
}

int fixture_recovery(void)
{
    return (BOOT_CASE != BAD_HEADER && BOOT_CASE != BAD_TRAILER) ||
        initialize_calls || inhibit_calls || unexpected || *(volatile const uint8_t *)0x1200 ||
        !still_stale();
}
