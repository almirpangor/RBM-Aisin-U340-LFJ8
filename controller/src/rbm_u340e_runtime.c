#include "rbm_u340e_runtime.h"

#include <stddef.h>
#include <string.h>

typedef struct {
    int16_t gp;
    uint16_t offset;
    uint8_t width;
} SharedField;

#define FIELD(member, gp) \
    { gp, offsetof(FactoryGearState, member), sizeof(((FactoryGearState *)0)->member) }

/* Intersection of pinned factory_gears_state.h and hydraulic_mapping.h.
 * b9748 is one byte of a larger hydraulic flags word. d9732 shares only
 * the four elements present in FactoryGearState. */
static const SharedField shared_fields[] = {
    FIELD(d9732[0], -9732),
    FIELD(d9732[1], -9728),
    FIELD(d9732[2], -9724),
    FIELD(d9732[3], -9720),
    FIELD(u7208, -7208),
    FIELD(u7204, -7204),
    FIELD(u7202, -7202),
    FIELD(u7196, -7196),
    FIELD(u7186, -7186),
    FIELD(u7184, -7184),
    FIELD(u7164, -7164),
    FIELD(u7154, -7154),
    FIELD(b9748, -9748),
    FIELD(b7252, -7252),
    FIELD(b7250, -7250),
    FIELD(b5299, -5299),
    FIELD(b4862, -4862),
    FIELD(b4856, -4856),
    FIELD(b4854, -4854),
    FIELD(b4853, -4853),
    FIELD(b4852, -4852),
    FIELD(b4851, -4851),
    FIELD(b4848, -4848),
    FIELD(b4847, -4847),
    FIELD(b4846, -4846),
    FIELD(b4845, -4845),
    FIELD(b4844, -4844),
    FIELD(b4843, -4843),
    FIELD(b4842, -4842),
    FIELD(b4841, -4841),
    FIELD(b4840, -4840),
    FIELD(b4838, -4838),
    FIELD(b4835, -4835),
    FIELD(b4834, -4834),
    FIELD(b4831, -4831),
    FIELD(b4813, -4813),
    FIELD(b4775, -4775),
    FIELD(b4774, -4774),
    FIELD(b4773, -4773),
    FIELD(b4772, -4772),
    FIELD(b4771, -4771),
    FIELD(b4770, -4770),
    FIELD(b4769, -4769),
    FIELD(b4768, -4768),
    FIELD(b4766, -4766),
    FIELD(b4765, -4765),
    FIELD(b4760, -4760),
    FIELD(b4759, -4759),
    FIELD(b4758, -4758),
    FIELD(b4756, -4756),
    FIELD(b4755, -4755),
    FIELD(b4733, -4733),
    FIELD(b4726, -4726),
    FIELD(b4725, -4725),
    FIELD(b4724, -4724),
    FIELD(b4723, -4723),
    FIELD(b4722, -4722),
    FIELD(b4721, -4721),
    FIELD(b4720, -4720),
    FIELD(b4719, -4719),
    FIELD(b4718, -4718),
    FIELD(b4717, -4717),
    FIELD(b4716, -4716),
    FIELD(b4715, -4715),
    FIELD(b4714, -4714),
    FIELD(b4662, -4662),
    FIELD(b4661, -4661),
    FIELD(b4660, -4660),
    FIELD(b4659, -4659),
    FIELD(b4658, -4658),
    FIELD(b4634, -4634),
    FIELD(b4549, -4549),
    FIELD(b4548, -4548),
};

#undef FIELD

#define SHARED_COUNT (sizeof shared_fields / sizeof shared_fields[0])
_Static_assert(SHARED_COUNT == 73u, "Toyota gear and hydraulic GP element count");
_Static_assert(sizeof(FactoryGearState) <= UINT16_MAX, "native gear field offset");

static uint32_t gear_value(const FactoryGearState *gear, const SharedField *field)
{
    const unsigned char *address = (const unsigned char *)gear + field->offset;
    if (field->width == 1u) {
        return *address;
    }
    if (field->width == 2u) {
        uint16_t value;
        memcpy(&value, address, sizeof value);
        return value;
    }
    uint32_t value;
    memcpy(&value, address, sizeof value);
    return value;
}

static void set_gear_value(FactoryGearState *gear, const SharedField *field, uint32_t value)
{
    unsigned char *address = (unsigned char *)gear + field->offset;
    if (field->width == 1u) {
        *address = (uint8_t)value;
    } else if (field->width == 2u) {
        const uint16_t word = (uint16_t)value;
        memcpy(address, &word, sizeof word);
    } else {
        memcpy(address, &value, sizeof value);
    }
}

static int refresh_shared(const FactoryHydraulics *gp, FactoryGearState *gear)
{
    for (size_t i = 0; i < SHARED_COUNT; ++i) {
        const SharedField *field = &shared_fields[i];
        uint32_t value;
        if (!factory_hydraulics_get(gp, field->gp, field->width, &value)) {
            return 0;
        }
        set_gear_value(gear, field, value);
    }
    return 1;
}

int rbm_u340e_runtime_init(RbmU340eRuntime *runtime, const FactoryGearState *gear,
                           const FactoryHydraulics *gp)
{
    if (!runtime || !gear || !gp) {
        return 0;
    }
    for (size_t i = 0; i < SHARED_COUNT; ++i) {
        const SharedField *field = &shared_fields[i];
        uint32_t value;
        if (!factory_hydraulics_get(gp, field->gp, field->width, &value) ||
            value != gear_value(gear, field)) {
            return 0;
        }
    }
    runtime->gp = *gp;
    runtime->gear_state = *gear;
    runtime->initialized = 1u;
    return 1;
}

int rbm_u340e_runtime_snapshot_gears(const RbmU340eRuntime *runtime, FactoryGearState *work)
{
    if (!runtime || runtime->initialized != 1u || !work || work == &runtime->gear_state) {
        return 0;
    }
    *work = runtime->gear_state;
    return refresh_shared(&runtime->gp, work);
}

int rbm_u340e_runtime_gears_outputs(RbmU340eRuntime *runtime, FactoryGearState *work,
                                    FactoryGearWrites *writes)
{
    if (!writes) {
        return 0;
    }
    *writes = (FactoryGearWrites){0};
    if (!runtime || runtime->initialized != 1u || !work || work == &runtime->gear_state ||
        !refresh_shared(&runtime->gp, work)) {
        return 0;
    }

    FactoryGearWrites proposal;
    if (!factory_gears_outputs_step(work, &proposal)) {
        return 0;
    }

    /* Both numeric accessors use the same address/width lookup. The
     * preceding refresh validated every span before anything was published. */
    for (size_t i = 0; i < SHARED_COUNT; ++i) {
        const SharedField *field = &shared_fields[i];
        (void)factory_hydraulics_set(&runtime->gp, field->gp, field->width, gear_value(work, field));
    }
    runtime->gear_state = *work;
    *writes = proposal;
    return 1;
}
