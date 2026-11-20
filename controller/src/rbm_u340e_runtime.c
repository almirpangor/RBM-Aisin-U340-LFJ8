#include "rbm_u340e_runtime.h"

#include <stddef.h>
#include <string.h>

#include "rbm_u340e.h"
#include "factory_core.h"

typedef struct {
    int16_t gp;
    uint16_t offset;
    uint8_t width;
} SharedField;

typedef struct {
    uint16_t offset;
    uint16_t width;
} PrivateSpan;

#define MEMBER_SIZE(member) sizeof(((FactoryGearState *)0)->member)
#define FIELD(member, gp) \
    { gp, offsetof(FactoryGearState, member), MEMBER_SIZE(member) }

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

/* Contiguous gear-only runs between the shared fields, in native order. */
#define PRIVATE_SPANS(X) \
    X(v1304, v1360) \
    X(u7166, u7166) \
    X(u7128, thresholds) \
    X(b8880, b7419) \
    X(b7193, b5722) \
    X(b5297, b5153) \
    X(b4839, b4839) \
    X(b4837, b4837) \
    X(b4828, b4821) \
    X(b4535, b4850) \
    X(b4533, driver5302)

#define SPAN_WIDTH(first, last) \
    (offsetof(FactoryGearState, last) + MEMBER_SIZE(last) - offsetof(FactoryGearState, first))
#define SPAN_RECORD(first, last) { offsetof(FactoryGearState, first), SPAN_WIDTH(first, last) },
static const PrivateSpan private_spans[] = { PRIVATE_SPANS(SPAN_RECORD) };
#undef SPAN_RECORD

#define SPAN_SIZE(first, last) + SPAN_WIDTH(first, last)
enum { PRIVATE_BYTES = 0u PRIVATE_SPANS(SPAN_SIZE) };
#undef SPAN_SIZE
#undef SPAN_WIDTH
#undef PRIVATE_SPANS
#undef MEMBER_SIZE

_Static_assert(PRIVATE_BYTES + RBM_U340E_GEAR_SHARED_BYTES == sizeof(FactoryGearState),
               "Toyota gear storage excludes all shared GP bytes");

static void pack_private(uint8_t *packed, const FactoryGearState *gear)
{
    const unsigned char *native = (const unsigned char *)gear;
    for (size_t i = 0; i < sizeof private_spans / sizeof private_spans[0]; ++i) {
        const PrivateSpan *span = &private_spans[i];
        memcpy(packed, native + span->offset, span->width);
        packed += span->width;
    }
}

static void unpack_private(FactoryGearState *gear, const uint8_t *packed)
{
    unsigned char *native = (unsigned char *)gear;
    for (size_t i = 0; i < sizeof private_spans / sizeof private_spans[0]; ++i) {
        const PrivateSpan *span = &private_spans[i];
        memcpy(native + span->offset, packed, span->width);
        packed += span->width;
    }
}

/* The target uses a flat address space. Subtract the lower address to
 * avoid constructing a potentially overflowing one-past endpoint. */
static int overlaps(const void *first, size_t first_size, const void *second, size_t second_size)
{
    const uintptr_t a = (uintptr_t)first;
    const uintptr_t b = (uintptr_t)second;
    return a <= b ? b - a < first_size : a - b < second_size;
}

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
    if (!runtime || !gear || !gp || overlaps(runtime, sizeof *runtime, gear, sizeof *gear) ||
        (gp != &runtime->gp && overlaps(runtime, sizeof *runtime, gp, sizeof *gp))) {
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
    pack_private(runtime->gear_private, gear);
    runtime->initialized = 1u;
    return 1;
}

const FactoryAdaptation *rbm_u340e_s01_adaptation_baseline(void)
{
    /* The S01 group-7 fallback pointer table at 00B0E0 supplies zero
     * for all 34 bytes selected by FactoryAdaptation. */
    _Static_assert(sizeof(FactoryAdaptation) == 34u, "Recheck the S01 adaptation projection");
    static const FactoryAdaptation baseline = {0};
    return &baseline;
}

static int adaptation_marker_erased(const uint8_t *record)
{
    /* The last four bytes of UFL1 are the commit marker, written after the
     * payload and CRC. This test requires a readable slot snapshot. */
    const uint8_t *marker = record + FACTORY_ADAPT_RECORD_BYTES - 4u;
    return (marker[0] & marker[1] & marker[2] & marker[3]) == UINT8_MAX;
}

RbmU340eAdaptationResult rbm_u340e_runtime_restore_adaptation(
    RbmU340eRuntime *runtime, const FactoryAdaptation *baseline,
    const uint8_t *slot0, const uint8_t *slot1)
{
    if (!runtime || runtime->initialized != 1u || !baseline ||
        overlaps(runtime, sizeof *runtime, baseline, sizeof *baseline) ||
        (slot0 && overlaps(runtime, sizeof *runtime, slot0, FACTORY_ADAPT_RECORD_BYTES)) ||
        (slot1 && overlaps(runtime, sizeof *runtime, slot1, FACTORY_ADAPT_RECORD_BYTES)) ||
        (slot0 && slot1 && overlaps(slot0, FACTORY_ADAPT_RECORD_BYTES, slot1, FACTORY_ADAPT_RECORD_BYTES)) ||
        !factory_adaptation_valid(baseline)) {
        return RBM_U340E_ADAPTATION_INVALID;
    }

    RbmU340eAdaptationResult result = RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED;
    FactoryAdaptation selected;
    const FactoryAdaptation *restore = baseline;
    if (slot0 && slot1) {
        uint32_t generation;
        const int slot = factory_adaptation_load(slot0, slot1, &selected, &generation);
        if (slot >= 0) {
            const uint8_t *other = slot == 0 ? slot1 : slot0;
            FactoryAdaptation checked;
            /* A damaged or partially written marker can conceal a newer
             * reset. Use the older slot only when the peer is unpublished
             * or the donor decoder can validate both generations. */
            if (adaptation_marker_erased(other) ||
                factory_adaptation_decode(other, &checked, &generation)) {
                restore = &selected;
                result = RBM_U340E_ADAPTATION_LOADED;
            }
        } else if (adaptation_marker_erased(slot0) && adaptation_marker_erased(slot1)) {
            result = RBM_U340E_ADAPTATION_BASELINE_UNPUBLISHED;
        }
    }
    if (!factory_hydraulics_restore(&runtime->gp, restore)) {
        return RBM_U340E_ADAPTATION_INVALID;
    }
    return result;
}

int rbm_u340e_runtime_snapshot_gears(const RbmU340eRuntime *runtime, FactoryGearState *work)
{
    if (!runtime || runtime->initialized != 1u || !work ||
        overlaps(runtime, sizeof *runtime, work, sizeof *work)) {
        return 0;
    }
    unpack_private(work, runtime->gear_private);
    return refresh_shared(&runtime->gp, work);
}

/* Entry generated in the verified, staged Toyota copy by controller/build.py. */
int rbm_factory_gears_outputs_step(FactoryGearState *work, FactoryGearWrites *writes,
                                   uint8_t requested_gear);

int rbm_u340e_runtime_gears_outputs_with_request(RbmU340eRuntime *runtime, FactoryGearState *work,
                                                 FactoryGearWrites *writes, uint8_t requested_gear)
{
    if (!writes || (runtime && overlaps(runtime, sizeof *runtime, writes, sizeof *writes)) ||
        (work && overlaps(work, sizeof *work, writes, sizeof *writes))) {
        return 0;
    }
    *writes = (FactoryGearWrites){0};
    if (!runtime || runtime->initialized != 1u || !work ||
        overlaps(runtime, sizeof *runtime, work, sizeof *work) ||
        !refresh_shared(&runtime->gp, work)) {
        return 0;
    }

    FactoryGearWrites proposal;
    if (!rbm_factory_gears_outputs_step(work, &proposal, requested_gear)) {
        return 0;
    }

    /* Both numeric accessors use the same address/width lookup. The
     * preceding refresh validated every span before anything was published. */
    for (size_t i = 0; i < SHARED_COUNT; ++i) {
        const SharedField *field = &shared_fields[i];
        (void)factory_hydraulics_set(&runtime->gp, field->gp, field->width, gear_value(work, field));
    }
    pack_private(runtime->gear_private, work);
    *writes = proposal;
    return 1;
}

int rbm_u340e_runtime_gears_outputs(RbmU340eRuntime *runtime, FactoryGearState *work,
                                    FactoryGearWrites *writes)
{
    return rbm_u340e_runtime_gears_outputs_with_request(runtime, work, writes, 0u);
}

enum {
    TOYOTA_COOLANT_FALLBACK = 0x10,
    TA2005_COOLANT_FALLBACK = 0x1000,
    TA2005_ENGINE_SPEED_FAILED = 0x02,
};

static uint8_t *coolant_source_flags(RbmU340eRuntime *runtime)
{
    const size_t member = offsetof(FactoryGearState, b8677);
    uint8_t *packed = runtime->gear_private;
    for (size_t i = 0; i < sizeof private_spans / sizeof private_spans[0]; ++i) {
        const PrivateSpan *span = &private_spans[i];
        if (member >= span->offset && member - span->offset < span->width) {
            return packed + (member - span->offset);
        }
        packed += span->width;
    }
    return NULL;
}

int rbm_u340e_runtime_prepare_engine(RbmU340eRuntime *runtime,
                                    const RbmU340eQualifiedEngineFeed *qualified,
                                    RbmU340eMainEngineInputs *prepared)
{
    if (!runtime || runtime->initialized != 1u || !qualified || qualified->coherent != 1u || !prepared ||
        overlaps(runtime, sizeof *runtime, prepared, sizeof *prepared)) {
        return 0;
    }
    uint8_t *flags = coolant_source_flags(runtime);
    if (!flags) {
        return 0;
    }

    /* TA2005_QUALIFIED_ENGINE_FEED_RU at upstream 08c01a01. Keep the input
     * words separate so each MAIN consumer still owns its publication. */
    const unsigned coolant = qualified->f9b8;
    const unsigned above_minus_40 = coolant >= 10u ? coolant - 10u : 0u;
    const RbmU340eMainEngineInputs result = {
        .speed_9306 = qualified->e026 & TA2005_ENGINE_SPEED_FAILED ? 0u :
            (uint16_t)(((uint32_t)qualified->fa62 * 4u) / 25u),
        .coolant_9006 = (uint16_t)(above_minus_40 * 8u / 5u - 64u),
    };
    uint8_t updated = *flags & (uint8_t)~TOYOTA_COOLANT_FALLBACK;
    if ((qualified->fd10 & TA2005_COOLANT_FALLBACK) || coolant == UINT8_MAX) {
        updated |= TOYOTA_COOLANT_FALLBACK;
    }
    *prepared = result;
    *flags = updated;
    return 1;
}

int rbm_u340e_runtime_main_coolant(RbmU340eRuntime *runtime,
                                 const RbmU340eMainEngineInputs *prepared)
{
    if (!runtime || runtime->initialized != 1u || !prepared) {
        return 0;
    }
    const uint8_t *flags = coolant_source_flags(runtime);
    if (!flags) {
        return 0;
    }
    /* 055336 uses a truncated intermediate halfword before scaling. */
    const uint16_t intermediate = (uint16_t)(((uint32_t)prepared->coolant_9006 + 64u) << 7);
    const uint16_t coolant = *flags & TOYOTA_COOLANT_FALLBACK ? 30720u :
        (uint16_t)(((uint32_t)intermediate * 40960u) >> 15);
    return factory_hydraulics_set(&runtime->gp, -7164, 2u, coolant);
}

int rbm_u340e_runtime_main_engine_speed(RbmU340eRuntime *runtime,
                                      const RbmU340eMainEngineInputs *prepared)
{
    if (!runtime || runtime->initialized != 1u || !prepared) {
        return 0;
    }
    const uint16_t speed = (uint16_t)((uint32_t)prepared->speed_9306 << 1);
    return factory_hydraulics_set(&runtime->gp, -7186, 2u, speed);
}

int rbm_u340e_runtime_publish_load(RbmU340eRuntime *runtime,
                                  const RbmU340eQualifiedLoadFeed *feed,
                                  uint32_t now, uint32_t max_age)
{
    if (!runtime || runtime->initialized != 1u || !feed ||
        overlaps(runtime, sizeof *runtime, feed, sizeof *feed) ||
        feed->coherent != 1u || feed->fallback_5299_bit1 > 1u ||
        max_age >= UINT32_C(0x80000000) || now - feed->sampled_at > max_age) {
        return 0;
    }

    FactoryHydraulics *gp = &runtime->gp;
    uint32_t flags;
    if (!factory_hydraulics_get(gp, -5299, 1u, &flags)) {
        return 0;
    }
    static const int16_t offsets[] = {-8270, -8272, -8306, -8298, -8302, -8310, -9044, -9030};
    const int16_t values[] = {
        feed->gp_8270, feed->gp_8272, feed->gp_8306, feed->gp_8298,
        feed->gp_8302, feed->gp_8310, feed->gp_9044, feed->gp_9030,
    };

    /* Validate every span before writing any operand. The static GP map
     * uses the same span lookup for reads and writes. */
    for (size_t i = 0; i < sizeof offsets / sizeof offsets[0]; ++i) {
        uint32_t unused;
        if (!factory_hydraulics_get(gp, offsets[i], 2u, &unused)) {
            return 0;
        }
    }
    for (size_t i = 0; i < sizeof offsets / sizeof offsets[0]; ++i) {
        (void)factory_hydraulics_set(gp, offsets[i], 2u, (uint16_t)values[i]);
    }
    flags = (flags & ~UINT32_C(2)) | ((uint32_t)feed->fallback_5299_bit1 << 1);
    (void)factory_hydraulics_set(gp, -5299, 1u, flags);
    return 1;
}

static uint8_t qualify_load_bit(uint8_t request, unsigned pending_mask, int32_t load,
                                int32_t release_threshold, int force_low)
{
    const unsigned previous = request & pending_mask;
    unsigned pending = previous;
    if (force_low || load < 80) {
        pending = pending_mask;
    } else if (load >= release_threshold) {
        pending = 0;
    }

    /* The published bit changes only on the second matching sample. */
    if (pending == previous) {
        const unsigned published_mask = pending_mask << 1;
        return (uint8_t)((request & ~published_mask) | (pending << 1));
    }
    return (uint8_t)((request & ~pending_mask) | pending);
}

int rbm_u340e_runtime_secondary_load_qualify(const RbmU340eRuntime *runtime,
                                             uint8_t inhibit_5250, uint8_t *request_1120)
{
    if (!runtime || runtime->initialized != 1u || !request_1120 ||
        overlaps(runtime, sizeof *runtime, request_1120, sizeof *request_1120)) {
        return 0;
    }
    uint32_t rpm, fallback;
    const FactoryHydraulics *gp = &runtime->gp;
    if (!factory_hydraulics_get(gp, -7186, 2u, &rpm) ||
        !factory_hydraulics_get(gp, -5299, 1u, &fallback)) {
        return 0;
    }

    int32_t primary = 786;
    int32_t limited = 786;
    if (!(fallback & 2u)) {
        /* 054CA6 and 054C2C clamp signed load operands. Apply floors
         * before ceilings, including if the donor limits cross. */
        enum { PRIMARY, LIMITED, COMMON_FLOOR, FLOOR, CEILING1, CEILING2 };
        static const int16_t gp_fields[] = {-8270, -8272, -8306, -8298, -8302, -8310};
        int32_t value[sizeof gp_fields / sizeof gp_fields[0]];
        for (size_t i = 0; i < sizeof gp_fields / sizeof gp_fields[0]; ++i) {
            uint32_t word;
            if (!factory_hydraulics_get(gp, gp_fields[i], 2u, &word)) {
                return 0;
            }
            value[i] = word < 32768u ? (int32_t)word : (int32_t)word - 65536;
        }
        primary = value[PRIMARY] < value[COMMON_FLOOR] ? value[COMMON_FLOOR] : value[PRIMARY];
        limited = value[LIMITED] < value[COMMON_FLOOR] ? value[COMMON_FLOOR] : value[LIMITED];
        if (limited < value[FLOOR]) {
            limited = value[FLOOR];
        }
        if (limited > value[CEILING1]) {
            limited = value[CEILING1];
        }
        if (limited > value[CEILING2]) {
            limited = value[CEILING2];
        }
        if (primary < 0) {
            primary = 0;
        }
        if (limited < 0) {
            limited = 0;
        }
    }

    /* S01 ROM 000D64. Interpolation returns Q8; 05518C shifts by four. */
    static const uint8_t threshold[] = {3, 40, 50, 60, 4, 11, 22};
    const int32_t release_threshold = (factory_interp1((uint16_t)rpm, threshold) >> 4) + 80;
    uint8_t request = *request_1120;
    request = qualify_load_bit(request, 0x04u, limited, release_threshold, 0);
    request = qualify_load_bit(request, 0x01u, primary, release_threshold, 0);
    request = qualify_load_bit(request, 0x10u, primary, release_threshold, inhibit_5250 & 4u);
    *request_1120 = request;
    return 1;
}

static uint8_t project_range(uint8_t selector)
{
    static const uint8_t masks[] = {0, 0x01, 0x02, 0x04, 0x08, 0x40, 0x80};
    return selector <= RBM_U340E_SELECTOR_L ? masks[selector] : 0;
}

static uint8_t set_flag(uint8_t value, unsigned mask, unsigned set)
{
    return (uint8_t)((value & ~mask) | (set ? mask : 0u));
}

int rbm_u340e_range_fast(RbmU340eRangeState *range, const RbmU340eRangeInputs *inputs)
{
    if (!range || !inputs) {
        return 0;
    }
    const uint8_t selector_5720 = project_range(inputs->selector);
    if (!selector_5720) {
        return 0;
    }
    /* 054EB2. This selector has no separate position 3 (GP-5720.5). */
    range->count_1112 = 0;
    if (!(inputs->range_5722 & 4u) && !(selector_5720 & 2u)) {
        if (!(selector_5720 & 8u)) {
            range->count_1113 = 0;
        } else if (range->count_1113 < 255u) {
            ++range->count_1113;
        }
        if (range->count_1113 >= 2u) {
            range->flags_1115 |= 1u;
        }
    } else {
        range->count_1113 = 0;
        range->flags_1115 &= (uint8_t)~3u;
    }
    if (inputs->range_5722 & 4u) {
        range->flags_1115 |= 4u;
    }
    if (inputs->range_5722 & 2u) {
        range->flags_1115 &= (uint8_t)~4u;
    }
    return 1;
}

static unsigned range_read(const FactoryHydraulics *gp, int address)
{
    /* Each operand below occupies one byte in hydraulic_mapping.h. */
    uint32_t value = 0;
    (void)factory_hydraulics_get(gp, address, 1, &value);
    return value;
}

static void range_write(FactoryHydraulics *gp, int address, unsigned value)
{
    (void)factory_hydraulics_set(gp, address, 1, value);
}

static void qualify_range(FactoryHydraulics *gp, FactoryGearState *work,
                          RbmU340eRangeState *range, unsigned mode, unsigned selector_7251)
{
    /* S01 ROM D24 and D44, with two 15-byte interpolation rows in each. */
    static const uint8_t l_delay[2][15] = {
        {7, 10, 25, 40, 60, 80, 120, 160, 8, 8, 8, 8, 8, 8, 8},
        {7, 10, 25, 40, 60, 80, 110, 160, 122, 122, 122, 73, 31, 18, 18},
    };
    static const uint8_t second_delay[2][15] = {
        {7, 10, 25, 40, 60, 80, 110, 160, 8, 8, 8, 8, 8, 8, 8},
        {7, 10, 25, 40, 60, 80, 110, 160, 49, 37, 31, 24, 18, 18, 18},
    };
    const uint8_t selector = work->b7252;
    uint8_t flags = work->b4845;
    if (selector & 2u) {
        range_write(gp, -4783, 0);
    }
    if (selector & 4u) {
        range_write(gp, -4782, 0);
    }
    if (range_read(gp, -4782) >= (factory_interp1(work->u7184, l_delay[mode]) >> 8)) {
        flags &= (uint8_t)~4u;
    }
    if (range_read(gp, -4783) >= (factory_interp1(work->u7184, second_delay[mode]) >> 8) &&
        ((selector & 13u) || (selector_7251 & 4u) || !(range->flags_1115 & 2u))) {
        flags &= (uint8_t)~2u;
    }
    if (!(flags & 4u) && (selector & 2u)) {
        flags |= 2u;
    }
    if (!(flags & 2u) && (selector & 4u)) {
        flags |= 4u;
    }
    range->mode_1114 = (uint8_t)mode;
    if ((selector & 9u) || (flags & 6u)) {
        flags &= (uint8_t)~1u;
        work->b4846 &= (uint8_t)~128u;
    } else {
        if (range_read(gp, -4784) < 8u) {
            flags |= 1u;
        } else if ((selector_7251 & 4u) || !(range->flags_1115 & 1u)) {
            flags &= (uint8_t)~1u;
        }
        work->b4846 = set_flag(work->b4846, 128u, !(flags & 1u));
    }
    const unsigned neutral = work->b4844 & 1u ? selector & 1u : range->flags_1115 & 4u;
    work->b4845 = set_flag(flags, 8u, neutral);
    range->flags_1115 &= (uint8_t)~4u;
}

static void range_output_override(FactoryHydraulics *gp, FactoryGearState *work,
                                  RbmU340eRangeState *range)
{
    /* 057694 followed by 05780E. All four S01 ROM entries 1334..1337
     * have value 1. Both ages at 133A are 244 and the count limit is 0. */
    work->b4838 &= (uint8_t)~16u;
    unsigned age = range_read(gp, -4764);
    if (!(work->b4845 & 8u) && (work->b4844 & 1u) && work->u7184 >= 10240u) {
        age = 0;
        range->flags_1376 = (uint8_t)((range->flags_1376 & 0xfcu) |
            (work->u7184 >= 15360u ? (work->b7252 & 32u ? 3u : 1u) : 0u));
    }
    if (age != 255u && ((range_read(gp, -4830) & 6u) == 2u || age >= 244u)) {
        age = 255u;
        range_write(gp, -4763, 0);
    }
    if (work->b4548 < 10u && (work->b4844 & 8u) &&
        ((work->b4846 & 128u) || (work->b4845 & 3u)) &&
        !(work->b4846 & 16u) && age != 255u) {
        work->b4837 |= 4u;
        work->b4838 |= 16u;
        work->b4850 = 1u;
    } else {
        work->b4837 &= (uint8_t)~4u;
        age = 255u;
        range_write(gp, -4763, 255u);
    }
    range_write(gp, -4764, age);
}

int rbm_u340e_runtime_main_range(RbmU340eRuntime *runtime, RbmU340eRangeState *range,
                                 const RbmU340eRangeInputs *inputs, FactoryGearState *work)
{
    if (!runtime || !range || !inputs || !work ||
        overlaps(runtime, sizeof *runtime, range, sizeof *range) ||
        overlaps(runtime, sizeof *runtime, inputs, sizeof *inputs) ||
        overlaps(work, sizeof *work, range, sizeof *range) ||
        overlaps(work, sizeof *work, inputs, sizeof *inputs) ||
        overlaps(range, sizeof *range, inputs, sizeof *inputs)) {
        return 0;
    }
    const uint8_t selector_5720 = project_range(inputs->selector);
    if (!selector_5720 || !rbm_u340e_runtime_snapshot_gears(runtime, work)) {
        return 0;
    }
    work->b5722 = inputs->range_5722;
    const unsigned selector_7251 = selector_5720 & 0x28u ? 4u : 0u;
    work->b7252 = (uint8_t)((work->b7252 & (uint8_t)~47u) |
        ((inputs->range_5722 & 6u) ? 1u : 0u) | ((selector_5720 >> 5) & 6u) |
        ((selector_5720 & 2u) << 2) | ((inputs->range_5722 & 8u) << 2));
    const unsigned mode = (work->b4842 & 32u) ? 1u : (work->b7252 & 6u) ? 0u : range->mode_1114;
    if (mode > 1u) {
        return 0;
    }
    const unsigned enabled = !(work->b5299 & 2u);
    work->b4844 = set_flag(work->b4844, 8u, enabled && (inputs->request_1120 & 2u));
    work->b4844 = set_flag(work->b4844, 32u, enabled && (inputs->request_1120 & 8u));
    work->b4844 = set_flag(work->b4844, 128u, enabled && (inputs->inhibit_5250 & 4u));
    work->b4843 = set_flag(work->b4843, 2u, enabled && (inputs->request_1120 & 32u));

    range_write(&runtime->gp, work->b7252 & 32u ? -4734 : -4733, 0);
    qualify_range(&runtime->gp, work, range, mode, selector_7251);
    range_output_override(&runtime->gp, work, range);
    range_write(&runtime->gp, -7252, work->b7252);
    range_write(&runtime->gp, -4846, work->b4846);
    range_write(&runtime->gp, -4845, work->b4845);
    range_write(&runtime->gp, -4844, work->b4844);
    range_write(&runtime->gp, -4843, work->b4843);
    range_write(&runtime->gp, -4838, work->b4838);
    return 1;
}

int rbm_u340e_runtime_main_range_complete(RbmU340eRuntime *runtime)
{
    if (!runtime || runtime->initialized != 1u) {
        return 0;
    }
    FactoryHydraulics *gp = &runtime->gp;
    const unsigned flags_4846 = range_read(gp, -4846);
    const unsigned flags_4845 = range_read(gp, -4845);
    const unsigned flags_4844 = range_read(gp, -4844);
    const unsigned flags_4842 = range_read(gp, -4842);
    const unsigned flags_4841 = range_read(gp, -4841);
    range_write(gp, -7250, range_read(gp, -7252));
    range_write(gp, -4842, (flags_4842 & ~0x54u) | ((flags_4842 & 0x2au) << 1));
    range_write(gp, -4841, set_flag(flags_4841, 2u, flags_4841 & 1u));
    range_write(gp, -4844, (flags_4844 & ~0x51u) | ((flags_4845 & 8u) >> 3) |
        ((flags_4844 & 0x28u) << 1));
    range_write(gp, -4845, (flags_4845 & 15u) | ((flags_4846 & 128u) >> 3) |
        ((flags_4845 & 7u) << 5));
    range_write(gp, -4843, set_flag(range_read(gp, -4843), 1u, flags_4844 & 128u));
    range_write(gp, -4840, (range_read(gp, -4840) & ~0x39u) | ((flags_4841 & 0x70u) >> 1));
    range_write(gp, -4853, range_read(gp, -4854));
    range_write(gp, -4851, range_read(gp, -4852));
    range_write(gp, -4847, range_read(gp, -4848));
    return 1;
}
