"""Native capture and ATF redirects for the pinned LFJ8-18-9E1C H03."""

CAPTURE_HOOKS = ((0xAA0C, "s51", "2244f000"), (0xAA70, "s83", "2045f000"))
ATF_HOOKS = (
    (0x03B110, "begin", "2e7f287f"),
    (0x040178, "adc", "20252eef"),
    (0x03B138, "read", "20b4f000"),
    (0x03B178, "fault", "20467f29"),
    (0x03B1A4, "direct", "20447f1e"),
    (0x03B218, "filtered", "2044f000"),
    (0x03B21C, "end", "28ef2eef"),
)
SENSOR_HOOKS = tuple(sorted(
    [(site, f"rbm_h03_{channel}_capture_hook", word) for site, channel, word in CAPTURE_HOOKS]
    + [(site, f"rbm_h03_atf_{name}", word) for site, name, word in ATF_HOOKS]
))
STOCK_SYMBOLS = {
    **{f"h03_sensor_after_{channel}": site + 4 for site, channel, _ in CAPTURE_HOOKS},
    "h03_atf_after_begin": 0x03B114,
    "h03_atf_after_adc": 0x04017C,
    "h03_atf_after_read": 0x03B13C,
    # Skip the remaining OEM conversion branches and run the patched epilogue.
    "h03_atf_resume_done": 0x03B21C,
    "h03_atf_after_end": 0x03B220,
}


def validate_stock(rom):
    for site, hook, stock_word in SENSOR_HOOKS:
        if rom[site:site + 4] != bytes.fromhex(stock_word):
            raise ValueError(f"H03 stock word at {site:#x} differs for {hook}")


def branch_patch(rom, site, target, stock_word, opcode):
    offset = target - site
    if rom[site:site + 4] != bytes.fromhex(stock_word):
        raise ValueError(f"Unexpected H03 stock word at {site:#x}")
    if site % 4 or target % 4 or not -(1 << 25) <= offset < (1 << 25):
        raise ValueError(f"M32R long branch at {site:#x} cannot reach {target:#x}")
    return opcode | ((offset // 4) & 0xFFFFFF)


def patch_plan(rom, hook_addresses):
    """Encode verified OEM-word replacements without writing an image."""
    plan = []
    for site, hook, stock_word in SENSOR_HOOKS:
        target = hook_addresses.get(hook)
        if target is None:
            raise ValueError(f"Missing placed H03 sensor hook: {hook}")
        word = branch_patch(rom, site, target, stock_word, 0xFF000000)
        plan.append({"site": site, "stock_word": stock_word, "branch_word": f"{word:08x}",
                     "hook": hook, "target": target})
    return plan
