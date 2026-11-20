"""H03 AN1 monitor call-site metadata for a placed M32R hook."""

CALL_SITE = 0x0725B0
STOCK_CALL = bytes.fromhex("fe000b7d")
MONITOR = 0x0753A4
HOOK_SYMBOL = "rbm_h03_atf_fault_hook"
MONITOR_SYMBOL = "h03_oem_atf_circuit_monitor"


def call_replacement(rom, hook_address):
    """Return the single replacement word, leaving validation of placement to the caller."""
    if rom[CALL_SITE:CALL_SITE + 4] != STOCK_CALL:
        raise ValueError("Unexpected H03 ATF monitor call word")
    displacement = hook_address - CALL_SITE
    if displacement % 4 or not -(1 << 25) <= displacement < 1 << 25:
        raise ValueError("H03 ATF hook is outside the aligned BL displacement")
    return (0xFE000000 | (displacement // 4 & 0xFFFFFF)).to_bytes(4, "big")
