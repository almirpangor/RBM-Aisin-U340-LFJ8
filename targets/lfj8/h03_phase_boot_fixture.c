/* State and callbacks for the simulator only. No actuator driver is linked. */
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_phase_startup.h"

enum { STOCK = 0, OWNED = 1, INVALID_PERIOD = 2, UNOWNED = 3, BAD_HEADER = 4, BAD_TRAILER = 5 };

static volatile uint32_t *const timer = (volatile uint32_t *)0x8003e0;
static volatile Lfj8H03PhaseClock phase = {.min_period = 0xba};
static Lfj8H03Takeover takeover = {.command_at = 0xdead};
static unsigned calls;
static int armed;
static int unexpected;
uint32_t boot_context[19];

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

static const Lfj8H03TakeoverOps ops = {
    .io = &lfj8_h03_mmio, .clock_ticks = lfj8_h03_tml0ct_m32r,
    .write32 = unexpected_write, .qualified = output_qualified,
    .arbitrate = unexpected_action, .apply = unexpected_action, .inhibit = unexpected_action,
    .phase_clock = &phase, .isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED,
};

void fixture_start_native_phase(void)
{
    ++calls;
    if (*(volatile const uint8_t *)0x1200 != 1 ||
        lfj8_h03_mmio.read16(0, 0x80481a) != 7u) {
        unexpected = 1;
        return;
    }
    if (BOOT_CASE == UNOWNED) {
        return;
    }
    const Lfj8H03PhaseStartupConfig config = {
        .min_period_ticks = 8u,
        .max_period_ticks = BOOT_CASE == INVALID_PERIOD ? 16u : 12u,
        .phase_max_age_ticks = 2u,
        .command_max_age_ticks = 24u,
    };
    armed = lfj8_h03_phase_startup(&takeover, &ops, &config);
}

void fixture_publish_first_phase(void);

void rbm_h03_phase_release_callback(uint32_t now)
{
    if (!armed || lfj8_h03_mmio.read8(0, 0x804ade) != 1u ||
        lfj8_h03_mmio.read8(0, 0x804862) != 10u || now != lfj8_h03_tml0ct_m32r(0)) {
        unexpected = 1;
        return;
    }
    lfj8_h03_phase_clock_release(&phase, now);
}

int fixture_complete(void)
{
    if (unexpected || lfj8_h03_mmio.read8(0, 0x804ade) != 0u ||
        calls != (BOOT_CASE == STOCK ? 0u : 1u)) {
        return 1;
    }
    if (BOOT_CASE == STOCK || BOOT_CASE == UNOWNED) {
        return armed || phase.min_period != 0xbau || takeover.command_at != 0xdeadu;
    }
    if (BOOT_CASE == INVALID_PERIOD) {
        return armed || takeover.ops || !phase.faulted || phase.min_period || takeover.pending;
    }
    const uint32_t now = lfj8_h03_tml0ct_m32r(0);
    if (!armed || phase.latest.released_at != now || phase.have_release || takeover.pending ||
        lfj8_h03_takeover_check_phase(&takeover) != LFJ8_H03_PHASE_WAIT) {
        return 2;
    }

    /* Deliver the first project's phase after the stock flag was cleared. */
    *timer = now + 8;
    fixture_publish_first_phase();
    Lfj8H03PhaseEvent event;
    return lfj8_h03_takeover_take_phase(&takeover, &event) != LFJ8_H03_PHASE_EVENT ||
        event.sequence != 1 || event.released_at != now + 8 || unexpected;
}

int fixture_recovery(void)
{
    return (BOOT_CASE != BAD_HEADER && BOOT_CASE != BAD_TRAILER) ||
        calls || armed || unexpected || *(volatile const uint8_t *)0x1200 ||
        phase.min_period != 0xbau || takeover.command_at != 0xdeadu;
}
