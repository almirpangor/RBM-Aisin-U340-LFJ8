"""Generate native-endian struct transfers from Toyota's canonical GP layout."""

from pathlib import Path
import re


ARRAY_MEMBERS = {
    "FactoryPhaseModes": {
        "phase.inputs_9728", "phase.learned_4579", "phase.learned_4554",
        "saved_p1464", "saved_p1470", "counts_4511",
    },
    "FactoryLearning": {
        "d9732", "w7222", "learned4619", "count4600", "count4594",
        "learned4579", "learned4554", "count4511",
    },
    "FactoryLoadInputs": {"history1104"},
    "FactoryTorque": {"targets", "queue", "captured7118", "captured7112", "count4703"},
}
TRANSFER_ROW = re.compile(r"\{(\d+),offsetof\((\w+),([^,)]+)\),(\d+)\}")
TRANSFER_CHUNK_BYTES = 16


def replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"Toyota source fragment did not match: {before}")
    return text.replace(before, after)


def write_port(vendor_src: Path, destination: Path) -> Path:
    source = (vendor_src / "factory_hydraulics.c").read_text(encoding="utf-8")
    mapping = (vendor_src / "hydraulic_mapping.h").read_text(encoding="utf-8")
    rows = TRANSFER_ROW.findall(mapping)
    if not rows or sum("(Factory" in line for line in mapping.splitlines()) != len(rows):
        raise ValueError("Toyota GP mapping contains an unrecognized transfer row")

    seen_arrays = set()
    assertions = []
    element_widths = {}
    for position, structure, member, length in rows:
        path = f"(({structure}*)0)->{member}"
        array = member in ARRAY_MEMBERS.get(structure, set())
        element = f"({path})[0]" if array else path
        if array:
            seen_arrays.add((structure, member))
        assertions.append(f'_Static_assert(sizeof({path}) == {length}, "layout of {structure}.{member}");')
        assertions.append(
            f'_Static_assert(sizeof({element}) == 1 || sizeof({element}) == 2 || '
            f'sizeof({element}) == 4, "element width of {structure}.{member}");'
        )
        assertions.append(
            f'_Static_assert(offsetof({structure},{member}) + {length} <= 256, '
            f'"native offset of {structure}.{member}");'
        )
        element_widths[(position, structure, member, length)] = f"sizeof({element})"

    expected_arrays = {(structure, member) for structure, fields in ARRAY_MEMBERS.items() for member in fields}
    if seen_arrays != expected_arrays:
        raise ValueError("Toyota GP array fields changed")

    def encode_row(match: re.Match) -> str:
        position, structure, member, length = match.groups()
        width = element_widths[match.groups()]
        size = int(length)
        offset = f"offsetof({structure},{member})"
        # 16 is a multiple of every supported element width, so splitting
        # an array never bisects an endian conversion.
        entries = []
        for start in range(0, size, TRANSFER_CHUNK_BYTES):
            chunk = min(TRANSFER_CHUNK_BYTES, size - start)
            entries.append(
                f"TRANSFER_ENTRY({int(position) + start}, {offset} + {start}, {width}, {chunk})"
            )
        return ",\n    ".join(entries)

    extent = max(int(position) + int(length) for position, _, _, length in rows)
    assertions.append(f'_Static_assert({extent}u <= sizeof(((FactoryHydraulics *)0)->data), "GP map extent");')
    converted_mapping = "#include <limits.h>\n_Static_assert(CHAR_BIT == 8, \"byte width\");\n"
    converted_mapping += "\n".join(assertions) + "\n"
    converted_mapping += TRANSFER_ROW.sub(encode_row, mapping)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "hydraulic_mapping_port.h").write_text(converted_mapping, encoding="utf-8", newline="\n")

    source = replace_once(
        source,
        '#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__\n#error Transfer tables require a little-endian host/target\n#endif',
        "#if !defined(__BYTE_ORDER__) || !defined(__ORDER_LITTLE_ENDIAN__) || "
        "!defined(__ORDER_BIG_ENDIAN__) || \\\n"
        "    (__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__ && __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__)\n"
        "#error Toyota GP transfers require a declared native byte order\n#endif",
    )
    source = replace_once(
        source,
        "typedef struct { uint16_t pos;uint8_t member,bytes; } Transfer;",
        """typedef struct { uint8_t gp_low, member, shape; } Transfer;
/* shape bits 1:0 are the upper GP offset, 3:2 the element reversal mask
 * (0, 1 or 3) and 7:4 the number of copied bytes minus one. */
enum { TRANSFER_GP_HIGH_MASK = 3u, TRANSFER_WIDTH_SHIFT = 2, TRANSFER_SIZE_SHIFT = 4 };
#define TRANSFER_ENTRY(pos, member_offset, width, bytes) \\
    { (uint8_t)(pos), (uint8_t)(member_offset), \\
      (uint8_t)(((pos) >> 8) | (((width) - 1u) << TRANSFER_WIDTH_SHIFT) | \\
                (((bytes) - 1u) << TRANSFER_SIZE_SHIFT)) }
_Static_assert(sizeof(Transfer) == 3, "GP transfer descriptor size");
_Static_assert(sizeof(((FactoryHydraulics *)0)->data) <= 1024, "GP offset width");""",
    )
    source = replace_once(
        source, '#include "hydraulic_mapping.h"', '#include "hydraulic_mapping_port.h"'
    )
    source = replace_once(
        source,
        """/* Keep one copy: LTO otherwise expands this loop into each hydraulic stage,
 * increasing the measured Cortex-M3 image by about 0.8 KiB. */
__attribute__((noinline)) static void transfer(FactoryHydraulics *s,void *object,const Transfer *map,unsigned n,int write) {
    uint8_t *p=object;
    for(unsigned i=0;i<n;++i) for(unsigned k=0;k<map[i].bytes;++k) {
        if(write) s->data[map[i].pos+k]=p[map[i].member+k];
        else p[map[i].member+k]=s->data[map[i].pos+k];
    }
}""",
        """/* GP bytes are canonical little endian. Each n-byte element, not each
 * entire record, is converted to the ABI's native order. */
static inline unsigned transfer_offset(const Transfer *entry)
{
    return ((entry->shape & TRANSFER_GP_HIGH_MASK) << 8) | entry->gp_low;
}

static inline unsigned transfer_bytes(const Transfer *entry)
{
    return (entry->shape >> TRANSFER_SIZE_SHIFT) + 1u;
}

static inline unsigned transfer_reversal_mask(const Transfer *entry)
{
#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    return (entry->shape >> TRANSFER_WIDTH_SHIFT) & 3u;
#else
    (void)entry;
    return 0u;
#endif
}

static void read_member(const FactoryHydraulics *s, void *object, const Transfer *entry)
{
    uint8_t *native = (uint8_t *)object + entry->member;
    const uint8_t *gp = s->data + transfer_offset(entry);
    const unsigned mask = transfer_reversal_mask(entry);
    const unsigned bytes = transfer_bytes(entry);
    for (unsigned i = 0; i < bytes; ++i) {
        native[i ^ mask] = gp[i];
    }
}

__attribute__((noinline)) static void transfer(FactoryHydraulics *s, void *object,
    const Transfer *map, unsigned count, int write)
{
    for (unsigned i = 0; i < count; ++i) {
        const Transfer *entry = &map[i];
        if (write) {
            uint8_t *gp = s->data + transfer_offset(entry);
            const uint8_t *native = (const uint8_t *)object + entry->member;
            const unsigned mask = transfer_reversal_mask(entry);
            const unsigned bytes = transfer_bytes(entry);
            for (unsigned j = 0; j < bytes; ++j) {
                gp[j] = native[j ^ mask];
            }
        } else {
            read_member(s, object, entry);
        }
    }
}""",
    )
    source = replace_once(
        source,
        "for(unsigned k=0;k<m->bytes;++k) ((uint8_t*)&value)[m->member+k]=s->data[m->pos+k];",
        "read_member(s, &value, m);",
    )
    source += """
/* The LFJ8 caller can reuse its expired gear snapshot for the atomic GP
 * transaction. The original one-argument API remains available. */
int rbm_u340e_hydraulics_control_main_workspace(FactoryHydraulics *state, FactoryHydraulics *workspace)
{
    if (!state || !workspace) {
        return 0;
    }
    const uintptr_t s = (uintptr_t)state;
    const uintptr_t w = (uintptr_t)workspace;
    if ((s < w ? w - s : s - w) < sizeof(*state)) {
        return 0;
    }
    *workspace = *state;
    if (!main_step(workspace) || !torque_step(workspace)) {
        return 0;
    }
    *state = *workspace;
    return 1;
}
"""
    source += test_source(rows)
    port = destination / "factory_hydraulics_port.c"
    port.write_text(source, encoding="utf-8", newline="\n")
    return port


def test_source(rows: list[tuple[str, ...]]) -> str:
    checks = {}
    for position, structure, member, length in rows:
        fields = checks.setdefault(structure, [])
        expression = f"value.{member}"
        if member in ARRAY_MEMBERS.get(structure, set()):
            field = f"{expression}[i]"
            fields.append(
                f"    for (unsigned i = 0; i < {length} / sizeof({field}); ++i) {{\n"
                f"        test_assert_equal((uint32_t){field} & test_width_mask(sizeof({field})),\n"
                f"            test_gp_value(state, {position} + i * sizeof({field}), sizeof({field})));\n"
                "    }"
            )
        else:
            fields.append(
                f"    test_assert_equal((uint32_t){expression} & test_width_mask({length}),\n"
                f"        test_gp_value(state, {position}, {length}));"
            )

    code = """
#ifdef RBM_TEST_TRANSFERS
#undef NDEBUG
#include <assert.h>

static uint32_t test_width_mask(unsigned width)
{
    return UINT32_MAX >> (32u - width * 8u);
}

__attribute__((noinline)) static void test_assert_equal(uint32_t observed, uint32_t expected)
{
    assert(observed == expected);
}

static uint32_t test_gp_value(const FactoryHydraulics *state, unsigned index, unsigned width)
{
    uint32_t value = 0;
    while (width) {
        value = (value << 8) | state->data[index + --width];
    }
    return value;
}
"""
    for structure, fields in checks.items():
        code += f"""
static void test_{structure}(FactoryHydraulics *state)
{{
    {structure} value;
    transfer(state, &value, map_{structure}, sizeof map_{structure} / sizeof map_{structure}[0], 0);
"""
        code += "\n".join(fields)
        code += f"""
    FactoryHydraulics encoded = {{0}};
    transfer(&encoded, &value, map_{structure}, sizeof map_{structure} / sizeof map_{structure}[0], 1);
    for (unsigned i = 0; i < sizeof map_{structure} / sizeof map_{structure}[0]; ++i) {{
        const Transfer *entry = &map_{structure}[i];
        const unsigned offset = transfer_offset(entry);
        for (unsigned j = 0; j < transfer_bytes(entry); ++j) {{
            assert(encoded.data[offset + j] == state->data[offset + j]);
        }}
    }}
}}
"""
    code += """
unsigned rbm_test_hydraulic_transfer(void)
{
    FactoryHydraulics state;
    for (unsigned i = 0; i < sizeof state.data; ++i) {
        /* Distinct values at equal offsets across the three GP pages. */
        state.data[i] = (uint8_t)(47u + 37u * i + 23u * (i >> 8));
    }
"""
    code += "".join(f"    test_{structure}(&state);\n" for structure in checks)
    return code + f"    return {len(rows)}u;\n}}\n#endif\n"
