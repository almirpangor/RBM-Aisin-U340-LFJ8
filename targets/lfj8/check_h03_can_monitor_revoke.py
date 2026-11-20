"""Verify the CAN recovery revoke with the real H03 output-inhibit code."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import check_h03_can_monitor_startup as startup
from check_h03_link import HERE, ROOT, TARGET, identify_h03
from check_h03_storage import check as check_storage


ALIASES = {
    "rbm_h03_application": "control/application",
    "rbm_h03_atf_state": "control/atf",
    "rbm_h03_selector_adc_state": "control/selector_adc",
    "rbm_h03_sensor_state": "control/sensors",
    "rbm_h03_tml0_1mhz_qualified": "control/clock_qualified",
    "rbm_h03_takeover_state": "control/takeover",
    "h03_can_owner": "communication/can_owner",
    "rbm_h03_main_result": "communication/main_result",
    "rbm_h03_fast_output": "communication/fast_output",
}
BINDINGS = r"""
#include "lfj8_h03_application.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_output_inhibit.h"

extern Lfj8H03Takeover rbm_h03_takeover_state;
extern Lfj8H03MainResult rbm_h03_main_result;
extern Lfj8H03FastOutput rbm_h03_fast_output;

enum { ACTIVE, NO_RAM, COLD, STALE_OPS, SERVICE, PROGRAMMING, FLASH_MODE, REPEATED };
uint32_t fixture_behavior;
static unsigned apply_count;

static int fixture_owns_ram(void *context)
{
    (void)context;
    return fixture_behavior != NO_RAM;
}

static void fixture_apply(void *context)
{
    (void)context;
    ++apply_count;
}

static const Lfj8H03TakeoverOps commissioned = {
    .io = &simulated_io, .inhibit = lfj8_h03_output_inhibit_locked, .apply = fixture_apply,
};
static const Lfj8H03TakeoverOps stale = {
    .io = &simulated_io, .inhibit = fixture_apply, .apply = fixture_apply,
};

const Lfj8H03ApplicationBinding rbm_h03_application_binding = {
    .takeover_ops = &commissioned, .takeover = &rbm_h03_takeover_state,
    .main = &rbm_h03_main_result, .ram_owned = fixture_owns_ram,
};

static const uint32_t command_bytes[] = {0x8063d5, 0x8063d7, 0x8063d8, 0x8063da, 0x8063db, 0x8063dd};
static const unsigned count_bytes = sizeof command_bytes / sizeof command_bytes[0];

void fixture_initialize_outputs(void)
{
    rbm_h03_application.running = 1u;
    h03_can_owner = (Lfj8H03CanOwner){.setup_generation = 42u, .admitted_generation = 42u,
                                     .grant = 1u, .initialized = true};
    rbm_h03_main_result.valid = 1u;
    rbm_h03_fast_output.valid = 1u;
    rbm_h03_takeover_state = (Lfj8H03Takeover){.ops = &commissioned, .generation = 7u,
                                            .have_generation = 1u, .pending = 1u};

    BYTE(0x800703) = 0xff;
    BYTE(0x80070a) = 0xff;
    BYTE(0x80074a) = 0xff;
    HALF(0x8048cc) = 0xaaaa;
    HALF(0x800344) = 0xaaaa;
    HALF(0x800346) = 0xaaaa;
    WORD(0x80508c) = 0x3f000000u;
    WORD(0x805094) = 0x3f000000u;
    for (unsigned i = 0; i < count_bytes; ++i) {
        BYTE(command_bytes[i]) = 1u;
    }
}

static int released_output_state(int inhibited)
{
    const uint8_t p3 = inhibited ? 0x1f : 0xff;
    const uint8_t p7 = inhibited ? 0xfe : 0xff;
    const uint16_t mode = inhibited ? 1u : 0xaaaau;
    const uint16_t period = inhibited ? 2998u : 0xaaaau;
    const uint16_t width = inhibited ? 0u : 0xaaaau;
    const uint32_t pressure = inhibited ? 0u : 0x3f000000u;
    if (BYTE(0x800703) != p3 || BYTE(0x80070a) != p7 || BYTE(0x80074a) != p7 ||
        HALF(0x8048cc) != mode || HALF(0x800344) != period || HALF(0x800346) != width ||
        WORD(0x80508c) != pressure || WORD(0x805094) != pressure) {
        return 0;
    }
    for (unsigned i = 0; i < count_bytes; ++i) {
        if (BYTE(command_bytes[i]) != !inhibited) {
            return 0;
        }
    }
    return 1;
}

int __real_rbm_h03_can_monitor_cold_owner_init_locked(void);
void __real_rbm_h03_can_monitor_revoke_locked(void);

int __wrap_rbm_h03_can_monitor_cold_owner_init_locked(void)
{
    require_lock();
    if (release_count || !(HALF(CAN0 + 2) & 0x0100u) || !(HALF(CAN1 + 2) & 0x0100u)) {
        ++unsafe_writes;
    }
    const Lfj8H03CanOwner retained = h03_can_owner;
    const int ready = __real_rbm_h03_can_monitor_cold_owner_init_locked();
    if (ready && (!h03_can_owner.initialized || h03_can_owner.grant ||
                  h03_can_owner.setup_generation || h03_can_owner.admitted_generation)) {
        ++unsafe_writes;
    }
    if (!ready && (h03_can_owner.initialized != retained.initialized ||
                   h03_can_owner.grant != retained.grant ||
                   h03_can_owner.setup_generation != retained.setup_generation ||
                   h03_can_owner.admitted_generation != retained.admitted_generation)) {
        ++unsafe_writes;
    }
    return ready;
}

void __wrap_rbm_h03_can_monitor_revoke_locked(void)
{
    require_lock();
    ++revoke_count;
    const uint32_t generation = h03_can_owner.setup_generation;
    const uint32_t admitted = h03_can_owner.admitted_generation;
    const uint8_t grant = h03_can_owner.grant;
    __real_rbm_h03_can_monitor_revoke_locked();

    const int owned = fixture_behavior != NO_RAM;
    const int inhibited = fixture_behavior == ACTIVE || fixture_behavior == REPEATED;
    const int active = inhibited || !owned;
    const int granted = !owned && grant == 1u;
    uint32_t epoch = UINT32_MAX;
    if (h03_can_owner.grant != (owned ? 0u : grant) || h03_can_owner.setup_generation != generation ||
        h03_can_owner.admitted_generation != admitted ||
        lfj8_h03_can_owner_rx_epoch(&h03_can_owner, &epoch) != granted ||
        epoch != (granted ? generation : UINT32_MAX) ||
        rbm_h03_takeover_state.pending != !owned || rbm_h03_takeover_state.generation != 7u ||
        rbm_h03_application.running != active || rbm_h03_takeover_state.ops != (active ? &commissioned : 0) ||
        rbm_h03_main_result.valid != !owned || rbm_h03_fast_output.valid != !owned ||
        !released_output_state(inhibited)) {
        ++unsafe_writes;
    }
}

void fixture_revoke_once(void)
{
    switch (fixture_behavior) {
    case COLD: rbm_h03_application.running = 0u; break;
    case STALE_OPS: rbm_h03_takeover_state.ops = &stale; break;
    case SERVICE: BYTE(0x804887) = 4u; break;
    case PROGRAMMING: BYTE(0x80801c) = 1u; break;
    case FLASH_MODE: BYTE(0x8007e2) = 1u; break;
    default: break;
    }

    const uint32_t saved = simulated_io.enter(0);
    __wrap_rbm_h03_can_monitor_revoke_locked();
    if (fixture_behavior == REPEATED) {
        __wrap_rbm_h03_can_monitor_revoke_locked();
    }
    simulated_io.leave(0, saved);
    if (fixture_behavior != NO_RAM &&
        (lfj8_h03_takeover_apply(&rbm_h03_takeover_state, 7u) || apply_count ||
         !released_output_state(fixture_behavior == ACTIVE || fixture_behavior == REPEATED))) {
        ++unsafe_writes;
    }
}
"""


def aliases_for(base, compiler, storage_report):
    expected = json.loads(storage_report.read_text(encoding="utf-8"))
    actual = check_storage(base, compiler)
    for field in ("base", "artifact_kind", "blocks", "fields", "input_sha256"):
        if expected[field] != actual[field]:
            raise ValueError(f"The H03 RAM report differs from a fresh M32R inventory: {field}")
    addresses = {}
    for symbol, qualified in ALIASES.items():
        group = qualified.split("/", 1)[0]
        field = actual["fields"][qualified]
        block = actual["blocks"][group]
        address = block["address"] + field["offset"]
        if address % field["alignment"] or not block["address"] <= address < address + field["bytes"] <= block["end_exclusive"]:
            raise ValueError(f"The RAM address of {symbol} violates its typed block")
        if any(start < address + field["bytes"] and address < end for start, end in addresses.values()):
            raise ValueError(f"Overlapping native symbol {symbol}")
        addresses[symbol] = (address, address + field["bytes"])
    text = "\n".join(f".global {symbol}\n.set {symbol}, {start:#x}"
                     for symbol, (start, _) in addresses.items()) + "\n"
    return addresses, text


def probe_binding(base, compiler, aliases, addresses):
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identify_h03(base)["sha256"]:
        raise ValueError("H03 changed before the binding probe")
    if not all(int.from_bytes(rom[address:address + 4], "big") == value
               for address, value in startup.native_words().items()):
        raise ValueError("A native word changed before the binding probe")
    asm = startup.FIXTURE.replace("    ld24 fp,#0x808000\nfixture_ready:",
                                  "    ld24 fp,#0x808000\n    bl.l fixture_initialize_outputs\nfixture_ready:")
    if asm == startup.FIXTURE or not startup.BACKEND.endswith(startup.OWNER_STUBS):
        raise ValueError("The parent simulator entry has changed")
    stub = startup.BACKEND.removesuffix(startup.OWNER_STUBS) + BINDINGS

    with TemporaryDirectory(prefix="rbm-h03-can-revoke-probe-") as directory:
        work = Path(directory)
        for name, data in (("h03-before.dat", rom[:startup.CANDIDATE_START]),
                           ("h03-after.dat", rom[startup.CANDIDATE_END:])):
            (work / name).write_bytes(data)
        for name, text in (("fixture.S", asm), ("fixture.c", stub), ("parked.S", startup.PARKED_SETUP),
                           ("aliases.S", aliases),
                           ("fixture.ld", startup.LAYOUT + startup.LINK_SYMBOLS + "stock_recovery_body = 0x00B850;\n")):
            (work / name).write_text(text, encoding="ascii")

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        includes = (HERE, ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                    ROOT / "diagnostics")
        sources = (
            "lfj8_h03_can_monitor_revoke.c", "lfj8_h03_can_monitor_startup.c", "lfj8_h03_monitor_quiesce.c",
            "h03_can_monitor_startup_hooks.S", "lfj8_h03_mmio.c", "lfj8_h03_takeover.c",
            "lfj8_h03_can_owner.c", "lfj8_h03_output_inhibit.c",
        )
        run(compiler, *TARGET, "-Os", "-g", "-std=c11", "-ffreestanding", "-fno-builtin",
            "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wsign-conversion",
            "-ffunction-sections", "-fdata-sections", "-nostdlib",
            "-DRBM_H03_MONITOR_STARTUP_SIMULATOR",
            *(option for folder in includes for option in ("-I", folder)),
            "-Wl,--gc-sections,-T,fixture.ld,--wrap=rbm_h03_can_monitor_revoke_locked",
            "-Wl,--wrap=rbm_h03_can_monitor_cold_owner_init_locked",
            "-Wl,--undefined=fixture_recovery,--undefined=fixture_fault,--undefined=fixture_revoke_once",
            *(f"-Wl,--undefined={name}" for _, _, name, _ in startup.PATCHES),
            "fixture.S", "fixture.c", "parked.S", "aliases.S", *(HERE / name for name in sources),
            "-lc", "-lgcc", "-o", "fixture.elf")
        nm = compiler.with_name(f"m32r-elf-nm{compiler.suffix}")
        symbols = {row[2].decode(): (int(row[0], 16), row[1]) for row in
                   (line.split() for line in run(nm, "-g", "--defined-only", "fixture.elf").splitlines())
                   if len(row) == 3}
        for name, (start, _) in addresses.items():
            if symbols[name] != (start, b"A"):
                raise ValueError(f"{name} allocated new storage or changed address")
        native = startup.observations(run, work, compiler, can_owner=addresses["h03_can_owner"][0])
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        results = []
        for mode, name in enumerate(("active", "denied_ram", "cold", "stale_takeover_ops",
                                     "service_mode", "programming_gate", "virtual_flash", "repeat")):
            flags = (("unsigned int", symbols["fixture_behavior"][0], mode),)
            observed, = startup.read_probe(run, work, debugger, "&fixture_revoke_once", flags,
                                           ((symbols["fixture_done"][0],),), 0)
            if observed[1:4] != (0, 0, 2 if name == "repeat" else 1):
                raise ValueError(f"Unexpected output/lease state for {name}: {observed}")
            results.append({"case": name, "software_grant_withdrawn": name != "denied_ram",
                            "inhibit_mmio_verified": name in ("active", "repeat")})
        owner_address = addresses["h03_can_owner"][0]
        denied_ram = ("unsigned int", symbols["fixture_behavior"][0], 1)
        generation = f"*(unsigned int*){owner_address:#x}"
        grant = f"*(unsigned char*){owner_address + 4:#x}"
        memory = (*startup.seed(), *startup.patch_words(run, compiler))
        # Bypass unrelated application startup with a fixture-only BRA.L.
        app_bridge = ("unsigned int", 0x008100, 0xFF000000 | ((0x00B7CC - 0x008100) // 4))
        cold, initial_permit = startup.read_probe(
            run, work, debugger, "0x003DC8", (*memory, app_bridge),
            ((0x008100, 0x0047D8), (0x00B7FC,)), 0, (generation, grant),
        )
        if (cold[0], cold[1:4], cold[-2:]) != (0x008100, (2, 0, 0), (0, 0)):
            raise ValueError(f"Cold entry did not initialize the CAN owner before releasing RX: {cold}")
        if initial_permit[1:4] != (4, 0, 1) or initial_permit[-2:] != (1, 0):
            raise ValueError(f"First stock permit did not publish generation one with TX revoked: {initial_permit}")
        denied, = startup.read_probe(
            run, work, debugger, "0x003DC8", (*memory, denied_ram),
            ((0x008100, 0x0047D8),), 0, (generation, grant),
        )
        if (denied[0], denied[1:4], denied[-2:]) != (0x0047D8, (0, 0, 0), (42, 1)) or not (
            denied[4] & 0x11 and denied[5] & 0x11
        ):
            raise ValueError(f"Cold permit without RAM ownership released CAN or wrote retained state: {denied}")
        preserved, = startup.read_probe(
            run, work, debugger, "0x00B7CC",
            (*memory, denied_ram),
            ((0x00B7FC,),), 0, (generation,),
        )
        if preserved[1:4] != (2, 0, 1) or preserved[-1] != 42:
            raise ValueError(f"Successful stock permit without RAM ownership published target state: {preserved}")
    return {"direct_cases": results, "native_entry_cases": native,
            "cold_owner_initialized_while_both_can_parked": True,
            "first_native_setup_generation": 1,
            "cold_ram_denial_keeps_rx_parked": True,
            "native_permit_preserves_unowned_generation": True,
            "used_actual_inhibit_implementation": True, "physical_output_verified": False}


def aggregate_placement(args, aliases):
    sys.path.insert(0, str(ROOT))
    from tools import check_h03_image_layout as layout

    old_modules = layout.BINDING_MODULES
    local = ROOT / "local"
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="rbm-can-revoke-placement-", dir=local) as directory:
        alias_path = Path(directory) / "h03-typed-aliases.S"
        alias_path.write_text(aliases, encoding="ascii")
        layout.BINDING_MODULES += ("lfj8_h03_can_monitor_revoke.c",
                                   Path(os.path.relpath(alias_path, HERE)).as_posix())
        try:
            result = startup.aggregate_placement(args)
        finally:
            layout.BINDING_MODULES = old_modules
    result["baseline_with_revoke_and_aliases_only"] = result.pop("main_baseline")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "storage-report", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("controller", "bridge"):
        parser.add_argument("--" + name, type=Path, help="also recheck the aggregate application placement")
    args = parser.parse_args()
    if bool(args.controller) != bool(args.bridge):
        parser.error("aggregate placement requires both --controller and --bridge")
    inputs = (args.base, args.storage_report, *(path for path in (args.controller, args.bridge) if path))
    if args.out.suffix.lower() != ".json" or any(args.out.resolve() == path.resolve() for path in inputs):
        parser.error("--out must be a separate JSON report")
    try:
        compiler = args.gcc.resolve()
        addresses, assembly = aliases_for(args.base, compiler, args.storage_report)
        report = {"base": identify_h03(args.base),
                  "aliases": {name: [f"0x{start:06X}", f"0x{end:06X}"] for name, (start, end) in addresses.items()},
                  "aliases_allocate_new_ram": False, "hardware_ram_ownership_verified": False,
                  "fixture": probe_binding(args.base, compiler, assembly, addresses), "flashable_image": None}
        if args.controller:
            report["aggregate_placement"] = aggregate_placement(args, assembly)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error).encode()).decode(errors="replace")
        parser.exit(1, detail + "\n")
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
