"""H03 application entry profile for the converted LFJ8/U340E bench pair."""

from lfj8_h03_application_placement import (
    REDIRECTS as APPLICATION_REDIRECTS,
    STOCK_SYMBOLS as APPLICATION_STOCK_SYMBOLS,
    Redirect,
    assembly,
    redirect_windows,
)

WAIT = Redirect(0x008150, "e4804ade", "rbm_h03_phase_wait_hook", 0xFF000000)
STRATEGY = Redirect(0x036F30, "fe00e3e9", "rbm_h03_strategy_hook", 0xFE000000)
APPLY = Redirect(0x07C10C, "feff29fd", "rbm_h03_commit_hook", 0xFE000000)
REDIRECTS = tuple(sorted((*APPLICATION_REDIRECTS, WAIT, STRATEGY, APPLY), key=lambda site: site.address))
REDIRECT_WINDOWS = redirect_windows(REDIRECTS)
ROOTS = tuple(site.root for site in REDIRECTS)
ASSEMBLY_SOURCES = (
    "h03_application_hooks.S", "h03_phase_startup_hook.S", "h03_phase_release_hook.S",
    "h03_phase_wait_hook.S", "h03_native_hooks.S",
)
ASSEMBLY_FLAGS = {"h03_native_hooks.S": ("-DRBM_H03_TARGET_ENTRY_ONLY=1",)}
# OEM reset gives R13 a fixed RAM base. Preserve it in the native C call chain.
NATIVE_STRATEGY_FLAGS = ("-ffixed-r13",)
NATIVE_CALLBACKS = (
    "rbm_h03_application_cold_gate", "rbm_h03_phase_startup_callback",
    "rbm_h03_phase_wait_callback", "rbm_h03_application_foreground_callback",
    "rbm_h03_phase_release_callback", "rbm_h03_strategy_callback", "rbm_h03_commit_callback",
)
STOCK_SYMBOLS = {
    **APPLICATION_STOCK_SYMBOLS,
    "h03_stock_phase_clear": 0x00815C,
    "h03_phase_wait_ticks": 0x8003E0,  # Running 32-bit TML0CT, not a frequency declaration.
}
INTERVAL_SYMBOL = "h03_phase_wait_interval_ticks"

# Edges retained around the hooks. The shared inner strategy and apply sites
# also intercept the OEM combined routine; its same-release apply is denied.
RETAINED_PACKETS = {
    0x003DB8: ("ed808000", "reset loads the OEM RAM base into r13"),
    0x003DC8: ("fe000112", "reset dispatcher calls marker check"),
    0x008084: ("ff00001f", "stock application dispatch; CAN monitor can interpose here"),
    0x008154: ("2094f000", "displaced wait loads OEM flag"),
    0x008158: ("b080fffe", "displaced back edge targets wait entry"),
    0x00815C: ("60002004", "clear OEM phase flag once"),
    0x0081E0: ("fe00f989", "scheduler calls stock phase 3"),
    0x0081F4: ("fe00f98e", "scheduler calls stock phase 2"),
    0x008318: ("7f8e29ef", "scheduler loops to shared wait"),
    0x036EB4: ("7e04f000", "combined entry calls stock preparation"),
    0x036EB8: ("7e13f000", "combined entry calls shared strategy path"),
    0x036EBC: ("7e20f000", "combined entry calls shared apply path"),
    0x036F34: ("fe00eb5c", "stock diagnostics after strategy"),
    0x036F50: ("fe01146c", "stock phase 2 calls apply wrapper"),
    0x046810: ("feffc1bd", "stock phase 3 calls shared strategy path"),
    0x046838: ("feffc1c1", "stock phase 2 calls shared apply path"),
    0x07C100: ("2e7f7e02", "stock phase 2 wrapper calls inner apply"),
    0x07C108: ("2e7ff000", "inner apply saves LR before the replaced call"),
    0x07C110: ("2eef1fce", "inner apply returns through original LR"),
}


def redirect_source(rom):
    for address, (word, _) in RETAINED_PACKETS.items():
        if rom[address:address + 4] != bytes.fromhex(word):
            raise ValueError(f"Unexpected H03 control-path word at {address:#08x}")
    return assembly(rom, REDIRECTS)


def qualified_stock_symbols(poll_interval_ticks, max_poll_interval_ticks):
    """Accept the integration profile's explicit poll limit in TML0CT ticks."""
    if (type(poll_interval_ticks) is not int or type(max_poll_interval_ticks) is not int or
            not 1 <= poll_interval_ticks <= min(max_poll_interval_ticks, 0xFFFFFF)):
        raise ValueError("H03 wait interval needs a positive, bounded TML0CT tick count")
    return {**STOCK_SYMBOLS, INTERVAL_SYMBOL: poll_interval_ticks}
