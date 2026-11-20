#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "lfj8_h03_takeover.h"

static const uint32_t shift_in[] = {0x8063D5, 0x8063D8, 0x8063DB};
static const uint32_t shift_out[] = {0x8063D7, 0x8063DA, 0x8063DD};
static const uint32_t word_in[] = {0x80508C, 0x804F6C, 0x804F78, 0x804F84, 0x804F94};
static const uint32_t word_out[] = {0x805094, 0x804F74, 0x804F80, 0x804F8C, 0x804F9C};

enum {
    P3DATA = 0x800703,
    BASE = 0x804000,
    LIMIT = 0x808020,
    SAVED_PSW = 0x41,
};

typedef struct {
    uint8_t ram[LIMIT - BASE];
    uint32_t now;
    unsigned arbitration_delay, publications, arbitrations, applies, inhibits;
    uint8_t locked, permitted, disturbed, p3;
} Fixture;

static uint8_t *cell(Fixture *f, uint32_t address)
{
    assert(f->locked && address >= BASE && address < LIMIT);
    return &f->ram[address - BASE];
}

static uint8_t read_byte(void *c, uint32_t address)
{
    Fixture *f = c;
    assert(f->locked);
    return address == P3DATA ? f->p3 : *cell(f, address);
}

static uint16_t read_halfword(void *c, uint32_t address)
{
    assert((address & 1u) == 0 && address <= LIMIT - sizeof(uint16_t));
    uint16_t result;
    memcpy(&result, cell(c, address), sizeof(result));
    return result;
}

static uint32_t read_word(void *c, uint32_t address)
{
    assert((address & 3u) == 0 && address <= LIMIT - sizeof(uint32_t));
    uint32_t result;
    memcpy(&result, cell(c, address), sizeof(result));
    return result;
}

static void write_byte(void *c, uint32_t address, uint8_t value)
{
    Fixture *f = c;
    *cell(f, address) = value;
    ++f->publications;
}

static void write_word(void *c, uint32_t address, uint32_t value)
{
    Fixture *f = c;
    assert((address & 3u) == 0 && address <= LIMIT - sizeof(value));
    memcpy(cell(f, address), &value, sizeof(value));
    ++f->publications;
}

static uint32_t enter(void *c)
{
    Fixture *f = c;
    assert(!f->locked);
    f->locked = 1;
    return SAVED_PSW;
}

static void leave(void *c, uint32_t saved)
{
    Fixture *f = c;
    assert(f->locked && saved == SAVED_PSW);
    f->locked = 0;
}

static uint32_t clock_ticks(void *c)
{
    const Fixture *f = c;
    assert(f->locked);
    return f->now;
}

static int permitted(void *c)
{
    const Fixture *f = c;
    assert(f->locked);
    return f->permitted;
}

static void arbitrate(void *c)
{
    Fixture *f = c;
    assert(f->locked && f->publications == 8u);
    ++f->arbitrations;
    assert(read_word(f, word_in[0]) == UINT32_C(0x3f000000));
    for (size_t i = 0; i < sizeof(shift_in) / sizeof(shift_in[0]); ++i) {
        *cell(f, shift_out[i]) = read_byte(f, shift_in[i]);
    }
    for (size_t i = 0; i < sizeof(word_in) / sizeof(word_in[0]); ++i) {
        const uint32_t value = read_word(f, word_in[i]);
        assert(i == 0u || value == 0u);
        memcpy(cell(f, word_out[i]), &value, sizeof(value));
    }
    if (f->disturbed) {
        *cell(f, shift_out[0]) ^= 1u;
    }
    f->now += f->arbitration_delay;
    f->publications = 0;
}

static void apply(void *c)
{
    Fixture *f = c;
    assert(f->locked && f->publications == 0u);
    f->p3 = (uint8_t)((f->p3 & 0x1fu) |
        ((unsigned)read_byte(f, shift_out[0]) << 7) |
        ((unsigned)read_byte(f, shift_out[1]) << 6) |
        ((unsigned)read_byte(f, shift_out[2]) << 5));
    ++f->applies;
}

static void inhibit(void *c)
{
    Fixture *f = c;
    assert(f->locked);
    ++f->inhibits;
}

int main(void)
{
    static Fixture fixture;
    const Lfj8RegisterIo io = {
        .context = &fixture, .read8 = read_byte, .read16 = read_halfword,
        .read32 = read_word, .write8 = write_byte,
        .enter = enter, .leave = leave,
    };
    Lfj8H03TakeoverOps ops = {
        .io = &io, .write32 = write_word, .clock_ticks = clock_ticks, .qualified = permitted,
        .arbitrate = arbitrate, .apply = apply, .inhibit = inhibit,
    };
    Lfj8H03Takeover state;
    assert(!lfj8_h03_takeover_init(&state, &ops, 8u));
    assert(!lfj8_h03_takeover_apply(&state, 0u));
    assert(!fixture.inhibits);
    ops.isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED;
    ops.inhibit = NULL;
    assert(!lfj8_h03_takeover_init(&state, &ops, 8u));
    ops.inhibit = inhibit;
    assert(!lfj8_h03_takeover_init(&state, &ops, 0u));
    assert(!lfj8_h03_takeover_init(&state, &ops, UINT32_C(0x80000000)));
    assert(lfj8_h03_takeover_init(&state, &ops, 8u));

    Lfj8H03OutputPlan plan = {
        .pressure_mailbox = 0x80508C, .pressure_binary32 = 0x3f000000,
        .pressure_request_ma = 500, .toyota_compare = 2200,
        .discrete = {{.mailbox = 0x8063DB, .on = 1}, {.mailbox = 0x8063D5, .on = 1}},
        .discrete_count = 2,
    };
    /* Retained flags before publication must not leave a PWM proposal live. */
    memset(&fixture.ram[word_in[1] - BASE], 0x5a, sizeof(uint32_t));
    uint16_t startup_count = 3u;
    memcpy(&fixture.ram[0x80621A - BASE], &startup_count, sizeof(startup_count));
    /* An early same-level F write can precede the only real D transition. */
    fixture.p3 = 0x33;
    fixture.now = 1u;
    fixture.permitted = 1;
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, UINT32_MAX, UINT32_MAX - 1u));
    assert(!fixture.applies && !fixture.inhibits);
    assert(fixture.ram[shift_in[2] - BASE] == 1u);
    assert(lfj8_h03_takeover_apply(&state, UINT32_MAX));
    assert(fixture.p3 == 0xB3);
    assert(!lfj8_h03_takeover_apply(&state, UINT32_MAX));
    assert(fixture.applies == 1u && fixture.inhibits == 1u);

    /* Allow generation wrap and a generation with no logical write events. */
    plan.discrete_count = 0;
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 0u, 1u));
    assert(lfj8_h03_takeover_apply(&state, 0u));
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 0u, 1u));
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, UINT32_MAX, 1u));

    fixture.now = 2u;
    plan.discrete_count = 2;
    plan.discrete[0] = (Lfj8H03DiscreteCommand){.mailbox = 0x8063D5, .on = 1};
    plan.discrete[1] = (Lfj8H03DiscreteCommand){.mailbox = 0x8063D5, .on = 0};
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 1u, 2u));
    plan.discrete_count = 1;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 1u, 2u));
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 2u, 3u));
    assert(!lfj8_h03_takeover_prepare(&state, NULL, 5u, 3u, 2u));
    ++plan.pressure_binary32;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 4u, 2u));
    --plan.pressure_binary32;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 8u, 5u, 2u));
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 6u, 2u));
    assert(!lfj8_h03_takeover_apply(&state, 7u));
    assert(!lfj8_h03_takeover_apply(&state, 6u));

    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 7u, 2u));
    fixture.ram[0x806356 - BASE] = 1;
    assert(!lfj8_h03_takeover_apply(&state, 7u));
    fixture.ram[0x806356 - BASE] = 0;
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 8u, 2u));
    fixture.ram[0x804887 - BASE] = 4;
    assert(!lfj8_h03_takeover_apply(&state, 8u));
    fixture.ram[0x804887 - BASE] = 0;

    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 9u, 2u));
    fixture.ram[word_out[4] - BASE] = 1;
    assert(!lfj8_h03_takeover_apply(&state, 9u));
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 10u, 2u));
    fixture.now = 10u;
    assert(!lfj8_h03_takeover_apply(&state, 10u));

    fixture.disturbed = 1;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 11u, 10u));
    fixture.disturbed = 0;
    fixture.arbitration_delay = 8;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 12u, 10u));
    fixture.permitted = 0;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 13u, 18u));
    fixture.permitted = 1;
    fixture.arbitration_delay = 0;
    plan.discrete_count = 2;
    plan.discrete[0] = (Lfj8H03DiscreteCommand){.mailbox = 0x8063DB, .on = 1};
    plan.discrete[1] = (Lfj8H03DiscreteCommand){.mailbox = 0x8063D5, .on = 1};
    fixture.p3 = 0x13;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 14u, 18u));
    fixture.p3 = 0xB3;
    plan.discrete_count = 0;
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 15u, 18u));
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 16u, 18u));
    assert(!lfj8_h03_takeover_apply(&state, 16u));
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 18u, 18u));
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 19u, 18u));
    assert(lfj8_h03_takeover_apply(&state, 19u));
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 20u, 18u));
    fixture.ram[0x80801C - BASE] = 1;
    assert(!lfj8_h03_takeover_apply(&state, 20u));
    fixture.ram[0x80801C - BASE] = 0;
    startup_count = UINT16_MAX;
    memcpy(&fixture.ram[0x80621A - BASE], &startup_count, sizeof(startup_count));
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 21u, 18u));
    startup_count = 3u;
    memcpy(&fixture.ram[0x80621A - BASE], &startup_count, sizeof(startup_count));
    fixture.p3 = 0x13;
    assert(!lfj8_h03_takeover_prepare(&state, &plan, 5u, 22u, 18u));

    plan.discrete_count = 2;
    plan.discrete[0] = (Lfj8H03DiscreteCommand){.mailbox = 0x8063D5, .on = 1};
    plan.discrete[1] = (Lfj8H03DiscreteCommand){.mailbox = 0x8063DB, .on = 1};
    assert(lfj8_h03_takeover_prepare(&state, &plan, 5u, 23u, 18u));
    fixture.p3 ^= 0x20u;
    assert(!lfj8_h03_takeover_apply(&state, 23u));

    plan.discrete_count = 0;
    assert(lfj8_h03_takeover_prepare(&state, &plan, 4u, 24u, 18u));
    fixture.p3 ^= 1u;
    assert(lfj8_h03_takeover_apply(&state, 24u));
    assert(fixture.applies == 4u && fixture.arbitrations == 14u && fixture.inhibits == 26u);
    assert(!fixture.locked);
    puts("H03 takeover: 8 proposals, P3 transition replay, guarded apply and generation/clock wrap PASS");
    return 0;
}
