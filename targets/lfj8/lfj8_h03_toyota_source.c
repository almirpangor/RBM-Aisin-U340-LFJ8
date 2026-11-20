#include "lfj8_h03_toyota_source.h"
#include "lfj8_h03_mmio.h"

#define SERIAL_HALF_RANGE UINT32_C(0x80000000)
enum { RELEASE_RESET, RELEASE_ARMED, RELEASE_FAULT };

void lfj8_h03_toyota_source_reset(Lfj8H03ToyotaRelease *release)
{
    release->status = RELEASE_RESET;
}

static int valid_source(const Lfj8H03ToyotaSource *source)
{
    return source && source->release && source->application && source->ram_owned &&
           source->clock_ready && source->capture && source->period_ticks != 0u &&
           source->period_ticks < SERIAL_HALF_RANGE &&
           source->max_lateness_ticks < source->period_ticks &&
           source->period_ticks + source->max_lateness_ticks < SERIAL_HALF_RANGE;
}

static Lfj8H03ToyotaEvent take_locked(const Lfj8H03ToyotaSource *source, uint32_t *due_at,
                                      uint32_t *sequence)
{
    if (source->ram_owned(source->platform) != 1 || source->application->running != 1u) {
        return LFJ8_H03_TOYOTA_FAULT;
    }
    Lfj8H03ToyotaRelease *const release = source->release;
    if (source->clock_ready(source->platform) != 1) {
        release->status = RELEASE_FAULT;
        return LFJ8_H03_TOYOTA_FAULT;
    }
    if (release->status == RELEASE_RESET) {
        const uint32_t anchor = source->application->last_toyota_at;
        release->next_at = anchor + source->period_ticks;
        release->last_observed = anchor;
        release->sequence = UINT32_MAX;
        release->status = RELEASE_ARMED;
    }
    if (release->status != RELEASE_ARMED) {
        return LFJ8_H03_TOYOTA_FAULT;
    }
    const uint32_t now = lfj8_h03_tml0ct_m32r(NULL);
    if (now - release->last_observed >= SERIAL_HALF_RANGE) {
        release->status = RELEASE_FAULT;
        return LFJ8_H03_TOYOTA_FAULT;
    }
    release->last_observed = now;
    const uint32_t late = now - release->next_at;
    if (late >= SERIAL_HALF_RANGE) {
        return LFJ8_H03_TOYOTA_WAIT;
    }
    if (late > source->max_lateness_ticks) {
        release->status = RELEASE_FAULT;
        return LFJ8_H03_TOYOTA_FAULT;
    }
    *due_at = release->next_at;
    *sequence = ++release->sequence;
    release->next_at += source->period_ticks;
    return LFJ8_H03_TOYOTA_EVENT;
}

Lfj8H03ToyotaEvent lfj8_h03_toyota_source_take(void *context, const Lfj8H03SensorSnapshot *sensors,
                                               Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load,
                                               uint32_t *released_at)
{
    const Lfj8H03ToyotaSource *const source = context;
    if (!valid_source(source) || !sensors || !input || !load || !released_at) {
        return LFJ8_H03_TOYOTA_FAULT;
    }
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    uint32_t due_at = 0u;
    uint32_t sequence = 0u;
    uint32_t saved = io->enter(io->context);
    const Lfj8H03ToyotaEvent event = take_locked(source, &due_at, &sequence);
    io->leave(io->context, saved);
    if (event != LFJ8_H03_TOYOTA_EVENT) {
        return event;
    }

    const int captured = source->capture(source->platform, sensors, due_at, input, load);
    saved = io->enter(io->context);
    int still_qualified = 0;
    if (source->ram_owned(source->platform) == 1) {
        if (captured == 1 && source->application->running == 1u &&
            source->clock_ready(source->platform) == 1) {
            const uint32_t now = lfj8_h03_tml0ct_m32r(NULL);
            still_qualified = now - due_at <= source->max_lateness_ticks &&
                              now - source->release->last_observed < SERIAL_HALF_RANGE;
            if (still_qualified) {
                source->release->last_observed = now;
                input->event = sequence;
                *released_at = due_at;
            }
        }
        if (!still_qualified) {
            source->release->status = RELEASE_FAULT;
        }
    }
    io->leave(io->context, saved);
    return still_qualified ? LFJ8_H03_TOYOTA_EVENT : LFJ8_H03_TOYOTA_FAULT;
}
