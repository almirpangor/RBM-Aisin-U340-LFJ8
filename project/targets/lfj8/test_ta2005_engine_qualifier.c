#include "ta2005_engine_qualifier.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const Ta2005EngineQualificationContext normal = {
    .retained_fd10 = 0xD234, .fallback_fa7b = 86, .retained_e026 = 0xA7,
    .coolant_can_enabled = 1, .coherent = 1,
};

static void check_receive_age_and_recovery(void)
{
    Ta2005CheryInputs receiver;
    Ta2005CherySnapshot raw;
    Ta2005EngineQualifier state;
    RbmU340eQualifiedEngineFeed out;
    assert(sizeof(state) == 6);
    ta2005_chery_inputs_reset(&receiver);
    ta2005_engine_qualifier_init(&state);
    uint32_t now = UINT32_MAX - 4;
    const uint8_t rpm[8] = {0x12, 0xC0};
    const uint8_t coolant[8] = {180};
    assert(!ta2005_chery_inputs_snapshot(&receiver, &now, 10, &raw));
    assert(ta2005_engine_qualifier_task2(&state, &raw, &normal, &out) == TA2005_ENGINE_EVALUATED);
    assert(out.fa62 == 0 && out.e026 == 0xA7 && out.fd10 == 0xD234 && out.f9b8 == 86);

    assert(ta2005_chery_inputs_receive(&receiver, 0x0FA, 8, rpm, &now) == TA2005_CHERY_SPEED);
    now = 4;
    assert(ta2005_chery_inputs_receive(&receiver, 0x278, 8, coolant, &now) == TA2005_CHERY_COOLANT);
    assert(ta2005_chery_inputs_snapshot(&receiver, &now, 10, &raw) == 3);
    assert(ta2005_engine_qualifier_task2(&state, &raw, &normal, &out) == TA2005_ENGINE_EVALUATED);
    assert(out.fa62 == 9600 && out.f9b8 == 137 && out.fd10 == 0xC234 &&
           out.e026 == 0xA5 && out.coherent == 1);

    ++now;
    assert(ta2005_chery_inputs_snapshot(&receiver, &now, 10, &raw) == TA2005_CHERY_COOLANT);
    for (unsigned tick = 1; tick <= 203; ++tick) {
        if (tick >= 10) {
            ta2005_chery_snapshot_clear(&raw);
        }
        unsigned want = TA2005_ENGINE_EVALUATED;
        if (tick == 102) {
            want |= TA2005_ENGINE_NEW_RPM_DTC;
        }
        assert(ta2005_engine_qualifier_task2(&state, &raw, &normal, &out) == want);
        assert(out.fa62 == (tick < 102 ? 9600 : 0) &&
               out.e026 == (tick < 102 ? 0xA5 : 0xA7));
        assert(out.f9b8 == (tick < 10 ? 137 : UINT8_MAX) && out.fd10 == 0xC234);
    }
    for (unsigned tick = 204; tick <= 211; ++tick) {
        unsigned want = TA2005_ENGINE_EVALUATED;
        if (tick == 211) {
            want |= TA2005_ENGINE_NEW_COOLANT_DTC;
        }
        assert(ta2005_engine_qualifier_task2(&state, &raw, &normal, &out) == want);
        assert(out.f9b8 == (tick == 211 ? 86 : UINT8_MAX));
    }
    assert(out.fd10 == 0xD234);

    raw = (Ta2005CherySnapshot){.speed_fad8 = 8400, .coolant_f9e9 = 134, .usable = 3};
    for (unsigned tick = 1; tick <= 252; ++tick) {
        assert(ta2005_engine_qualifier_task2(&state, &raw, &normal, &out) == TA2005_ENGINE_EVALUATED);
        assert(out.fa62 == (tick < 252 ? 0 : 8400) && out.f9b8 == (tick < 252 ? 86 : 134));
    }
    assert(state.flags == TA2005_ENGINE_COOLANT_VALID && out.fd10 == 0xC234 && out.e026 == 0xA5);
}

static void check_blocked_channels(void)
{
    Ta2005EngineQualifier state = {8000, 101, 201, TA2005_ENGINE_COOLANT_VALID};
    const Ta2005CherySnapshot input = {.speed_fad8 = 6400, .coolant_f9e9 = 120, .usable = 0};
    Ta2005EngineQualificationContext context = normal;
    RbmU340eQualifiedEngineFeed out = {1, 2, 3, 4, 5};
    const Ta2005EngineQualifier prior = state;
    const RbmU340eQualifiedEngineFeed retained = out;
    context.coherent = 2;
    assert(!ta2005_engine_qualifier_task2(&state, &input, &context, &out));
    assert(!ta2005_engine_qualifier_task2(&state, NULL, &normal, &out));
    assert(state.fa62 == prior.fa62 && state.rpm_count == prior.rpm_count &&
           state.coolant_count == prior.coolant_count && state.flags == prior.flags);
    assert(out.fa62 == retained.fa62 && out.fd10 == retained.fd10 && out.f9b8 == retained.f9b8 &&
           out.e026 == retained.e026 && out.coherent == retained.coherent);

    context = normal;
    context.coolant_can_enabled = 0;
    context.e02b = 0x80;
    assert(ta2005_engine_qualifier_task2(&state, &input, &context, &out) == TA2005_ENGINE_EVALUATED);
    assert(state.fa62 == 0 && state.rpm_count == 101 && state.coolant_count == 201);
    assert(out.f9b8 == normal.fallback_fa7b && out.fd10 == 0xD234);
    context.e02b = 0x04;
    assert(ta2005_engine_qualifier_task2(&state, &input, &context, &out) == TA2005_ENGINE_EVALUATED);
    assert(state.rpm_count == 101 && state.coolant_count == 201);

    context.e02b = 0;
    assert(ta2005_engine_qualifier_task2(&state, &input, &context, &out) ==
           (TA2005_ENGINE_EVALUATED | TA2005_ENGINE_NEW_RPM_DTC));
    assert(state.coolant_count == 201);
    context.coolant_can_enabled = 1;
    assert(ta2005_engine_qualifier_task2(&state, &input, &context, &out) ==
           (TA2005_ENGINE_EVALUATED | TA2005_ENGINE_NEW_COOLANT_DTC));
    state = prior;
    assert(ta2005_engine_qualifier_task2(&state, &input, &context, &out) ==
           (TA2005_ENGINE_EVALUATED | TA2005_ENGINE_NEW_RPM_DTC | TA2005_ENGINE_NEW_COOLANT_DTC));
}

static int compare_vectors(void)
{
    unsigned speed, rpm, coolant, flags, raw_speed, temperature, usable, fd10, fallback, e026, bus, can;
    int count;
    while ((count = scanf("%u%u%u%u%u%u%u%u%u%u%u%u", &speed, &rpm, &coolant, &flags,
                          &raw_speed, &temperature, &usable, &fd10, &fallback, &e026, &bus, &can)) == 12) {
        Ta2005EngineQualifier state = {(uint16_t)speed, (uint8_t)rpm, (uint8_t)coolant, (uint8_t)flags};
        const Ta2005CherySnapshot raw = {
            .speed_fad8 = (uint16_t)raw_speed, .coolant_f9e9 = (uint8_t)temperature, .usable = (uint8_t)usable,
        };
        const Ta2005EngineQualificationContext context = {
            .retained_fd10 = (uint16_t)fd10, .fallback_fa7b = (uint8_t)fallback, .retained_e026 = (uint8_t)e026,
            .e02b = (uint8_t)bus, .coolant_can_enabled = (uint8_t)can, .coherent = 1,
        };
        RbmU340eQualifiedEngineFeed out;
        unsigned events = ta2005_engine_qualifier_task2(&state, &raw, &context, &out);
        printf("%u %u %u %u %u %u %u %u %u\n", events, (unsigned)state.fa62,
               (unsigned)state.rpm_count, (unsigned)state.coolant_count, (unsigned)state.flags,
               (unsigned)out.fd10, (unsigned)out.f9b8, (unsigned)out.e026, (unsigned)out.coherent);
    }
    return count == EOF ? 0 : 1;
}

int main(int argc, char **argv)
{
#if defined(TA2005_ENGINE_NATIVE_VECTORS)
    /* The M32R simulator startup does not forward program arguments. */
    return compare_vectors();
#endif
    if (argc == 2 && strcmp(argv[1], "--native-vectors") == 0) {
        return compare_vectors();
    }
    check_receive_age_and_recovery();
    check_blocked_channels();
    puts("TA2005 engine qualification passes reception age, fault thresholds and recovery");
    return 0;
}
