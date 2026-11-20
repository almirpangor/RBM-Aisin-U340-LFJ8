"""Compare the H03 SLU command with the pinned Toyota reference on a PC."""

import argparse
from bisect import bisect_right
import ctypes as C
from hashlib import sha256
from io import BytesIO
from itertools import product
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
ANALOG_PROOF = "research/results/TOYOTA_OUTPUT_ANALOG_VERIFICATION.json"
CHAIN_PROOF = "research/results/C167_SECONDARY_SLU_CHAIN_PROBE.json"
PRESSURE_PROOF = "research/results/C167_SECONDARY_SLU_PRESSURE_PROBE.json"
PRESSURE_SOURCE = "research/probes/c167_secondary_slu_pressure.c"
PRESSURE_INPUTS = (PRESSURE_SOURCE, "research/probes/c167_secondary_slu_pressure.h",
                   "research/probes/c167_secondary_slu.h")
BASELINE_PROOF = "research/results/C167_SECONDARY_SLU_BASELINE_PROBE.json"
BASELINE_SOURCE = "research/probes/c167_secondary_slu_baseline.c"
BASELINE_INPUTS = (BASELINE_SOURCE, "research/probes/c167_secondary_slu_baseline.h",
                   "research/probes/c167_fast_oscillation.h")
BASELINE_DEPENDENCY = "research/probes/ta2005_compact_input_projection.h"
RESET_PROOF = "research/results/C167_SECONDARY_SLU_RESET_PROBE.json"
RESET_SOURCE = "research/probes/c167_secondary_slu_reset.c"
DIAGNOSTIC_PROOF = "research/results/C167_SECONDARY_SLU_DIAGNOSTICS_PROBE.json"
DIAGNOSTIC_SOURCE = "research/probes/c167_secondary_slu_diagnostics.c"
DIAGNOSTIC_HEADER = "research/probes/c167_secondary_slu_diagnostics.h"
ENTRY = 0x055C5E
GP = 12288
CTRL, PERIOD, CMP, ENABLE = 0xFFFFF602, 0xFFFFF614, 0xFFFFF616, 0xFFFFF41E


def git_bytes(path, name):
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    return subprocess.check_output(["git", "-C", str(path), "show", name], env=env)


class SluInput(C.Structure):
    _fields_ = [("pressure_7136", C.c_uint16), ("selector_4544", C.c_uint8),
                ("flags_4834", C.c_uint8), ("flags_4828", C.c_uint8), ("flags_4827", C.c_uint8),
                ("flags_4829", C.c_uint8), ("flags_4825", C.c_uint8), ("flags_4822", C.c_uint8),
                ("qualified", C.c_bool)]


class SluCommand(C.Structure):
    _fields_ = [("selected_7246", C.c_uint16), ("characteristic_7130", C.c_uint16),
                ("force", C.c_bool)]


class SecondaryInput(C.Structure):
    _fields_ = [("baseline_7026", C.c_uint16), ("override_7082", C.c_uint16),
                ("temperature_7184", C.c_uint16), ("offset_7028", C.c_int16), ("offset_7030", C.c_int16),
                ("flags_1636", C.c_uint8), ("mode_4505", C.c_uint8), ("selector_4544", C.c_uint8),
                ("flags_4834", C.c_uint8), ("flags_4828", C.c_uint8), ("flags_4827", C.c_uint8),
                ("flags_4829", C.c_uint8), ("flags_4825", C.c_uint8), ("flags_4822", C.c_uint8),
                ("qualified", C.c_bool)]


class SecondaryState(C.Structure):
    _fields_ = [("previous_mode_1637", C.c_uint8), ("timer_4735", C.c_uint8)]


class SecondaryResult(C.Structure):
    _fields_ = [("pressure_7136", C.c_uint16), ("command", SluCommand)]


class BaselineInput(C.Structure):
    _fields_ = [("speed_7200", C.c_uint16), ("speed_7204", C.c_uint16),
                ("base_7054", C.c_uint16), ("trim_7066", C.c_int16),
                ("gear", C.c_uint8), ("learning_4616", C.c_uint8 * 12)]


class BaselineState(C.Structure):
    _fields_ = [("baseline_7026", C.c_uint16), ("adjustment_7032", C.c_int16)]


class SluDiagnostics(C.Structure):
    _fields_ = [("flags_4829", C.c_uint8), ("low_age_4741", C.c_uint8), ("high_age_4740", C.c_uint8)]


def compare_stage_boundaries(reference, h03):
    context = (C.c_uint8 * 11)()
    reset_reference = reference.probe_secondary_slu_reset
    reset_reference.argtypes = [type(context)]
    reset_reference.restype = C.c_int
    reset = h03.lfj8_h03_slu_reset_secondary
    reset.argtypes = [C.POINTER(SecondaryInput)]
    reset.restype = None

    reset_cases = 0
    for flags, offset in product(range(256), (-32768, -1, 0, 1, 32767)):
        context[0] = flags
        context[5:7] = offset.to_bytes(2, "little", signed=True)
        assert reset_reference(context) == 1
        actual = SecondaryInput(flags_1636=flags, offset_7028=offset, offset_7030=-2000,
                                mode_4505=2, override_7082=0xa1b2, qualified=True)
        expected = SecondaryInput.from_buffer_copy(actual)
        expected.flags_1636 = context[0]
        expected.offset_7028 = int.from_bytes(context[5:7], "little", signed=True)
        reset(C.byref(actual))
        assert bytes(actual) == bytes(expected), (flags, offset)
        reset_cases += 1

    core = (C.c_uint8 * 843)()
    slu = (C.c_uint8 * 20)()
    diagnose_reference = reference.probe_secondary_slu_diagnostics
    diagnose_reference.argtypes = [type(core), type(slu)]
    diagnose_reference.restype = C.c_int
    diagnose = h03.lfj8_h03_slu_update_diagnostics
    diagnose.argtypes = [C.POINTER(SluDiagnostics), C.c_uint16]
    diagnose.restype = None

    diagnostic_cases = 0
    commands = (0, 2559, 2560, 2561, 25600, 65535)
    for flags, selected, low, high in product(range(256), commands, (0, 3, 4, 5, 255), (0, 11, 12, 13, 255)):
        core[241] = flags
        core[321:323] = low, high
        slu[4:6] = selected.to_bytes(2, "little")
        assert diagnose_reference(core, slu) == 1
        actual = SluDiagnostics(flags, low, high)
        diagnose(C.byref(actual), selected)
        assert tuple(bytes(actual)) == (core[241], core[321], core[322]), (flags, selected, low, high)
        diagnostic_cases += 1
    return {"05DA44_reset_cases": reset_cases, "05B6DE_diagnostic_cases": diagnostic_cases}


def compare_baseline_flow(compare_case, combined):
    inputs = SecondaryInput(baseline_7026=65535, selector_4544=0xa5, qualified=True)
    sample = BaselineInput(base_7054=10000, gear=1)
    sample.learning_4616[:] = (0, 255, 10, 220, 50, 255, 3, 224, 80, 241, 1, 188)
    control_cases = 0
    for mode, gear, speed, nt, hold in product((0, 1, 2, 3, 255), (0, 1, 255), (0, 128), (0, 1), (0, 8)):
        inputs.mode_4505, sample.gear = mode, gear
        inputs.flags_4828, inputs.flags_4827, inputs.flags_4825 = speed, nt, hold
        sample.speed_7200, sample.speed_7204 = 6000, 31000
        compare_case(inputs, SecondaryState(1, 200), sample, BaselineState(17777, -1234))
        control_cases += 1

    inputs.mode_4505 = 3
    inputs.flags_4825 = 0
    sample.gear = 1
    curve_cases = 0
    for use_nt, breaks in ((False, (21, 31, 41, 51, 61, 71, 81)), (True, (128, 241, 243, 245, 247))):
        inputs.flags_4828, inputs.flags_4827 = 128, int(use_nt)
        points = {0, 1, 32767, 32768, 65535}
        points.update(x * 128 + delta for x, delta in product(breaks, (-2, -1, 0, 1, 2)))
        points.update((a + b) * 64 for a, b in zip(breaks, breaks[1:]))
        for speed, base, trim in product(sorted(points), (0, 2559, 2560, 10000, 20480, 65535),
                                         (-32768, -2000, 0, 2000, 32767)):
            sample.speed_7200 = sample.speed_7204 = speed
            sample.base_7054, sample.trim_7066 = base, trim
            compare_case(inputs, SecondaryState(3, 0), sample, BaselineState())
            curve_cases += 1

    state, baseline = SecondaryState(1, 199), BaselineState(12345, -3210)
    sample.base_7054, sample.trim_7066 = 10000, 0
    inputs.mode_4505, inputs.flags_4827 = 2, 0
    for gear, hold, speed in ((1, 0, 6000), (1, 8, 6400), (0, 8, 6400), (1, 8, 6400), (1, 0, 6400)):
        sample.gear, inputs.flags_4825, sample.speed_7200 = gear, hold, speed
        compare_case(inputs, state, sample, baseline)

    arguments = [C.byref(arg) for arg in (inputs, sample, baseline, state)]
    saved = bytes(state), bytes(baseline)
    for missing in range(5):
        result = SecondaryResult(1, SluCommand(2, 3, True))
        args = [*arguments, C.byref(result)]
        args[missing] = None
        assert not combined(*args)
        if missing != 4:
            assert (result.pressure_7136, result.command.selected_7246,
                    result.command.characteristic_7130, result.command.force) == (0, 0, 0, False)
        assert (bytes(state), bytes(baseline)) == saved
    inputs.qualified = False
    result = SecondaryResult(1, SluCommand(2, 3, True))
    assert not combined(*arguments, C.byref(result))
    assert (result.pressure_7136, result.command.selected_7246,
            result.command.characteristic_7130, result.command.force) == (0, 0, 0, False)
    assert (bytes(state), bytes(baseline)) == saved
    return {"control_cases": control_cases, "curve_cases": curve_cases, "sequence_steps": 5, "invalid_cases": 6}


def compare_secondary(library, projection, reference_command):
    # The frozen R3 probe uses canonical GP bytes and C167 state views.
    core = (C.c_uint8 * 843)()
    context = (C.c_uint8 * 11)()
    slu = (C.c_uint8 * 20)()
    pressure = library.probe_secondary_slu_pressure
    pressure.argtypes = [type(core), type(context), type(slu)]
    pressure.restype = C.c_int
    secondary = projection.lfj8_h03_slu_secondary
    secondary.argtypes = [C.POINTER(SecondaryInput), C.POINTER(SecondaryState), C.POINTER(SecondaryResult)]
    secondary.restype = C.c_bool

    reference_baseline = library.probe_secondary_slu_baseline
    baseline_bytes = (C.c_uint8 * 18)()
    osc = (C.c_uint8 * 39)()
    reference_baseline.argtypes = [type(core), type(context), type(baseline_bytes), type(osc)]
    reference_baseline.restype = C.c_int
    combined = projection.lfj8_h03_slu_secondary_from_baseline
    combined.argtypes = [C.POINTER(SecondaryInput), C.POINTER(BaselineInput), C.POINTER(BaselineState),
                         C.POINTER(SecondaryState), C.POINTER(SecondaryResult)]
    combined.restype = C.c_bool

    def compare_case(inputs, state, sample=None, baseline=None):
        core[124:126] = inputs.temperature_7184.to_bytes(2, "little")
        core[241:244] = (inputs.flags_4829, inputs.flags_4828, inputs.flags_4827)
        core[327] = state.timer_4735
        context[:3] = inputs.flags_1636, state.previous_mode_1637, inputs.mode_4505
        context[3:] = b"".join((word & 0xffff).to_bytes(2, "little") for word in
                               (inputs.baseline_7026, inputs.offset_7028, inputs.offset_7030,
                                inputs.override_7082))
        if sample is not None:
            core[108:110] = sample.speed_7204.to_bytes(2, "little")
            core[112:114] = sample.speed_7200.to_bytes(2, "little")
            core[220] = sample.gear
            context[3:5] = baseline.baseline_7026.to_bytes(2, "little")
            osc[30] = inputs.flags_4825
            baseline_bytes[:6] = (
                sample.trim_7066.to_bytes(2, "little", signed=True)
                + sample.base_7054.to_bytes(2, "little")
                + baseline.adjustment_7032.to_bytes(2, "little", signed=True)
            )
            baseline_bytes[6:] = sample.learning_4616[:]
            assert reference_baseline(core, context, baseline_bytes, osc) == 1
            expected_baseline = int.from_bytes(context[3:5], "little")
            expected_adjustment = int.from_bytes(baseline_bytes[4:6], "little", signed=True)
        assert pressure(core, context, slu) == 1
        expected_pressure = int.from_bytes(slu[2:4], "little")
        expected_command = reference_command(inputs, expected_pressure)

        result = SecondaryResult()
        if sample is None:
            assert secondary(C.byref(inputs), C.byref(state), C.byref(result))
        else:
            assert combined(C.byref(inputs), C.byref(sample), C.byref(baseline), C.byref(state), C.byref(result))
            assert (baseline.baseline_7026, baseline.adjustment_7032) == (expected_baseline, expected_adjustment)
        assert result.pressure_7136 == expected_pressure
        assert (state.previous_mode_1637, state.timer_4735) == (context[1], core[327])
        assert (result.command.selected_7246, result.command.characteristic_7130, result.command.force) == expected_command
        return result

    inputs = SecondaryInput(baseline_7026=10000, override_7082=65535, offset_7028=-2000,
                            offset_7030=2000, selector_4544=0xa5, qualified=True)
    conditions = product((0, 1, 2, 3, 255), (0, 1, 2, 255), (0, 8, 16, 24),
                         (0, 128), (0, 1), (0, 2), (0, 2560, 2561, 5120, 5121, 65535),
                         (0, 1, 2, 255))
    condition_cases = 0
    for mode, previous, override, enabled, alternate, bank, temperature, timer in conditions:
        inputs.mode_4505, inputs.flags_4829 = mode, override
        inputs.flags_4828, inputs.flags_4827 = enabled, alternate
        inputs.flags_1636, inputs.temperature_7184 = bank, temperature
        inputs.flags_4822 = 0x80 if timer & 1 else 0
        inputs.flags_4825 = 8 if previous == 2 else 0
        compare_case(inputs, SecondaryState(previous, timer))
        condition_cases += 1

    inputs = SecondaryInput(mode_4505=3, selector_4544=0xa5, flags_4828=0x80, qualified=True)
    bounds = (0, 2559, 2560, 2561, 20479, 20480, 20481, 65535)
    offsets = (-32768, -1, 0, 1, 32767)
    arithmetic_cases = 0
    for baseline, offset_a, offset_b, bank in product(bounds, offsets, offsets, (0, 2)):
        inputs.baseline_7026 = baseline
        inputs.offset_7028, inputs.offset_7030, inputs.flags_1636 = offset_a, offset_b, bank
        compare_case(inputs, SecondaryState(3, 0))
        arithmetic_cases += 1

    inputs = SecondaryInput(baseline_7026=10000, mode_4505=1, selector_4544=0xa5,
                            flags_4828=0x80, qualified=True)
    state = SecondaryState(0, 7)
    assert compare_case(inputs, state).pressure_7136 == 10000
    inputs.mode_4505 = 2
    assert compare_case(inputs, state).pressure_7136 == 23040 and state.timer_4735 == 0
    state.timer_4735 = 1
    assert compare_case(inputs, state).pressure_7136 == 23040 and state.timer_4735 == 1
    state.timer_4735 = 2
    assert compare_case(inputs, state).pressure_7136 == 10000 and state.timer_4735 == 2

    inputs.mode_4505 = 1
    for sample, retained in ((None, C.byref(state)), (C.byref(SecondaryInput()), C.byref(state)),
                             (C.byref(inputs), None)):
        result = SecondaryResult(1, SluCommand(2, 3, True))
        assert not secondary(sample, retained, C.byref(result))
        assert (result.pressure_7136, result.command.selected_7246,
                result.command.characteristic_7130, result.command.force) == (0, 0, 0, False)
    assert not secondary(C.byref(inputs), C.byref(state), None)
    assert (state.previous_mode_1637, state.timer_4735) == (2, 2)
    return {"condition_cases": condition_cases, "arithmetic_cases": arithmetic_cases,
            "transition_steps": 4, "invalid_cases": 4,
            "from_baseline": compare_baseline_flow(compare_case, combined)}


def compare(library, projection, rom):
    run = library.toyota_output_analog_reference
    enter = C.CFUNCTYPE(C.c_uint32, C.c_void_p)
    leave = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32)
    read = C.CFUNCTYPE(C.c_uint16, C.c_void_p, C.c_uint32, C.c_uint)
    write = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32, C.c_uint, C.c_uint16)

    class Critical(C.Structure):
        _fields_ = [("enter", enter), ("leave", leave), ("user", C.c_void_p)]

    class Services(C.Structure):
        _fields_ = [("critical", Critical), ("read", read), ("write", write), ("user", C.c_void_p)]

    run.argtypes = [C.POINTER(Services), C.POINTER(C.c_uint8), C.c_uint32]
    run.restype = C.c_int
    project = projection.lfj8_h03_slu_command
    project.argtypes = [C.POINTER(SluInput), C.POINTER(SluCommand)]
    project.restype = C.c_bool
    memory = (C.c_uint8 * 16384)()
    events = []
    ports = {}
    depth = 0

    @enter
    def enter_critical(_):
        nonlocal depth
        previous = depth
        depth += 1
        return previous

    @leave
    def leave_critical(_, token):
        nonlocal depth
        depth = token if depth == token + 1 else -100

    @read
    def read_port(_, address, width):
        value = ports.get(address, 0)
        events.append(("read", address, width, depth, value))
        return value

    @write
    def write_port(_, address, width, value):
        events.append(("write", address, width, depth, value))
        ports[address] = value

    services = Services(Critical(enter_critical, leave_critical, None), read_port, write_port, None)

    def put_word(offset, value):
        memory[GP + offset] = value & 0xFF
        memory[GP + offset + 1] = (value >> 8) & 0xFF

    def get_word(offset):
        return memory[GP + offset] | memory[GP + offset + 1] << 8

    count = rom[0xFD4]
    xs = [x * 256 for x in rom[0xFD5:0xFD5 + count]]
    ys = [y * 256 for y in rom[0xFD5 + count:0xFD5 + 2 * count]]
    assert count == 10 and xs == sorted(xs)

    def curve(raw):
        index = bisect_right(xs, raw) - 1
        if index < 0:
            return ys[0]
        if index == count - 1:
            return ys[-1]
        span = xs[index + 1] - xs[index]
        return (ys[index] * (xs[index + 1] - raw) + ys[index + 1] * (raw - xs[index])) // span

    def check_transaction(*allowed):
        assert depth == 0 and all(level == 1 for _, _, _, level, _ in events)
        widths = {CTRL: 1, PERIOD: 2, CMP: 2, ENABLE: 1}
        assert all(address in allowed and width == widths[address]
                   for _, address, width, _, _ in events)
        return [address for direction, address, _, _, _ in events if direction == "write"]

    def check_projection():
        inputs = SluInput(get_word(-7136), *(memory[GP + gp] for gp in
                          (-4544, -4834, -4828, -4827, -4829, -4825, -4822)), True)
        projected = SluCommand()
        assert project(C.byref(inputs), C.byref(projected))
        assert projected.selected_7246 == get_word(-7246)
        assert projected.characteristic_7130 == get_word(-7130)
        assert projected.force == bool(memory[GP + 1156] & 2)

    memory[GP - 4544] = 165
    memory[GP - 4828] = 128
    memory[GP - 5286] = 1
    for raw in range(65536):
        put_word(-7136, 25600 - raw)
        initial_control = 0x85 if raw & 1 else 0x05
        ports[CTRL] = initial_control
        events.clear()
        assert run(C.byref(services), memory, ENTRY) == 1
        selected = curve(raw)
        assert get_word(-7246) == raw and get_word(-7130) == selected
        assert get_word(-9062) == get_word(-1560) == selected
        assert get_word(-1562) == ports[CMP] == 400 + (9 * selected) // 64
        assert ports[PERIOD] == 4000 and ports[CTRL] == 0x85
        expected_writes = [CTRL, CMP, PERIOD, CTRL] if raw & 1 else [CMP, PERIOD, CTRL]
        assert check_transaction(CTRL, PERIOD, CMP) == expected_writes
        check_projection()

    # Force the command and restore each of the two driver modes.
    memory[GP - 4822] = 128
    memory[GP - 5284] = 1
    ports[ENABLE] = 0xB4
    events.clear()
    assert run(C.byref(services), memory, ENTRY) == 1
    assert memory[GP - 5286] == 3 and memory[GP + 1156] & 2
    assert get_word(-9066) == curve(65535) and ports[ENABLE] == 0x34
    assert check_transaction(CTRL, PERIOD, CMP, ENABLE) == [CTRL, CMP, PERIOD, CTRL, ENABLE]

    memory[GP - 4822] = 0
    events.clear()
    assert run(C.byref(services), memory, ENTRY) == 1
    assert memory[GP - 5286] == 2 and not memory[GP + 1156] & 2
    assert get_word(-9066) == 0 and ports[ENABLE] == 0xB4
    assert check_transaction(ENABLE) == [ENABLE]

    memory[GP + 1156] |= 2
    memory[GP - 5286] = 3
    memory[GP - 5284] = 0
    # The stored signed command goes through truncation toward zero after
    # the arithmetic shift. Use -8 so its effect is visible at the compare.
    put_word(-9062, -8)
    events.clear()
    assert run(C.byref(services), memory, ENTRY) == 1
    assert memory[GP - 5286] == 1 and not memory[GP + 1156] & 2
    assert check_transaction(CTRL, PERIOD, CMP) == [CTRL, CMP, PERIOD, CTRL] * 2
    assert [value for direction, address, _, _, value in events if direction == "write" and address == CMP] == [399, 4000]
    assert run(None, memory, ENTRY) == 0

    selected_bits = ((-4544, 0xa5), (-4834, 0x40), (-4834, 0x08),
                     (-4828, 0x80), (-4827, 0x01), (-4829, 0x08), (-4829, 0x10),
                     (-4825, 0x08), (-4822, 0x80))
    pressure_edges = (0, 25599, 25600, 25601, 65535)
    for pattern in range(1 << len(selected_bits)):
        for gp, _ in selected_bits:
            memory[GP + gp] = 0
        for bit, (gp, mask) in enumerate(selected_bits):
            if pattern & (1 << bit):
                memory[GP + gp] |= mask
        for pressure in pressure_edges:
            put_word(-7136, pressure)
            events.clear()
            assert run(C.byref(services), memory, ENTRY) == 1
            check_projection()

    for missing in (None, C.byref(SluInput())):
        response = SluCommand(1, 2, True)
        assert not project(missing, C.byref(response))
        assert (response.selected_7246, response.characteristic_7130, response.force) == (0, 0, False)
    assert not project(C.byref(SluInput(qualified=True)), None)

    def reference_command(inputs, pressure):
        put_word(-7136, pressure)
        for offset in (-4544, -4834, -4828, -4827, -4829, -4825, -4822):
            field = "selector_4544" if offset == -4544 else f"flags_{-offset}"
            memory[GP + offset] = getattr(inputs, field)
        events.clear()
        assert run(C.byref(services), memory, ENTRY) == 1
        return get_word(-7246), get_word(-7130), bool(memory[GP + 1156] & 2)

    return {
        "normal_u16_commands": 65536, "force_resume_cases": 3, "donor_period_register": 4000,
        "h03_projection_pressure_words": 65536,
        "h03_projection_branch_cases": (1 << len(selected_bits)) * len(pressure_edges),
        "h03_projection_invalid_cases": 3,
        "h03_secondary_chain": compare_secondary(library, projection, reference_command),
    }


def check_m32r_secondary(stage, compiler, vendor):
    compiler = compiler.resolve()
    triple = subprocess.check_output([str(compiler), "-dumpmachine"], text=True).strip()
    if triple != "m32r-elf":
        raise ValueError("The SLU CPU probe requires a bare-metal M32R compiler")
    target = ["-m32r", "-mmodel=medium", "-msdata=none", "-Wa,-EB"]
    startup = subprocess.check_output([str(compiler), *target, "-print-file-name=crt0.o"],
                                      text=True).strip()
    h03 = ROOT / "targets/lfj8"
    fixture = "test_lfj8_h03_slu_secondary.c"
    sources = (h03 / fixture, h03 / "lfj8_h03_slu.c", h03 / "lfj8_h03_slu.h",
               vendor / "src/factory_core.c", vendor / "src/donor_calibration.h",
               vendor / "include/factory_core.h")
    for source in sources:
        shutil.copyfile(source, stage / source.name)
    image = "slu-secondary.elf"
    subprocess.run([str(compiler), *target, "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror",
                    "-ffreestanding", "-fno-builtin", "-nostartfiles", startup, fixture,
                    "lfj8_h03_slu.c", "factory_core.c", "-Wl,-e,_start,--start-group",
                    "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", image],
                   cwd=stage, check=True)
    simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
    output = subprocess.check_output([str(simulator), image], cwd=stage, text=True, timeout=60).strip()
    if "M32R SECONDARY SLU" not in output:
        raise ValueError("Missing M32R SLU probe result")
    return output


def verify(r1, r3, compiler, m32r=None):
    source_index = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    s01 = next(source for source in source_index["firmware"] if source["id"] == "S01")
    r1_commit = source_index["repositories"]["R1"]["commit"]
    r3_commit = source_index["repositories"]["R3"]["commit"]
    rom = git_bytes(r1, f"{r1_commit}:{s01['path']}")
    assert len(rom) == s01["bytes"] and sha256(rom).hexdigest() == s01["sha256"]
    analog_bytes = git_bytes(r3, f"{r3_commit}:{ANALOG_PROOF}")
    chain_bytes = git_bytes(r3, f"{r3_commit}:{CHAIN_PROOF}")
    pressure_bytes = git_bytes(r3, f"{r3_commit}:{PRESSURE_PROOF}")
    baseline_bytes = git_bytes(r3, f"{r3_commit}:{BASELINE_PROOF}")
    reset_bytes = git_bytes(r3, f"{r3_commit}:{RESET_PROOF}")
    diagnostic_bytes = git_bytes(r3, f"{r3_commit}:{DIAGNOSTIC_PROOF}")
    analog, chain, pressure = json.loads(analog_bytes), json.loads(chain_bytes), json.loads(pressure_bytes)
    baseline = json.loads(baseline_bytes)
    reset, diagnostic = json.loads(reset_bytes), json.loads(diagnostic_bytes)
    assert analog["donor_sha256"] == s01["sha256"] and analog["status"] == "passed"
    assert chain["comparisons"] == 3072 and chain["physical_slu_output_bound"] is False
    assert pressure["entry"] == "05DCE8" and pressure["next_entry"] == "055C5E"
    assert baseline["original_entries"] == ["05DC5E", "05DCE8"] and baseline["next_entry"] == "055C5E"
    assert reset["original_entry"] == "05DA44" and reset["next_entry"] == "05DC5E"
    assert diagnostic["original_entry"] == "05B6DE" and diagnostic["next_entry"] == "060A62"

    analog_source = "toyota_isolation/output_analog.c"
    core_source = "u340e_logic/factory/src/factory_core.c"
    with TemporaryDirectory(prefix="rbm-toyota-slu-") as directory:
        staged = Path(directory)
        headers = "u340e_logic/factory/include"
        archive = subprocess.check_output(["git", "-C", str(r3), "archive", "--format=zip", r3_commit, headers])
        with ZipFile(BytesIO(archive)) as pinned_headers:
            pinned_headers.extractall(staged)
        sources = dict(analog["input_sha256"])
        sources.update({filename: pressure["input_sha256"][filename] for filename in PRESSURE_INPUTS})
        sources.update({filename: baseline["input_sha256"][filename] for filename in BASELINE_INPUTS})
        sources[RESET_SOURCE] = reset["input_sha256"][RESET_SOURCE]
        sources.update({filename: diagnostic["input_sha256"][filename]
                        for filename in (DIAGNOSTIC_SOURCE, DIAGNOSTIC_HEADER)})
        for filename, expected in sources.items():
            source = git_bytes(r3, f"{r3_commit}:{filename}")
            if sha256(source).hexdigest() != expected:
                # Three factory files were hashed upstream with the checkout's CRLF.
                source = source.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            assert sha256(source).hexdigest() == expected, filename
            target = staged / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source)
        (staged / BASELINE_DEPENDENCY).write_bytes(git_bytes(r3, f"{r3_commit}:{BASELINE_DEPENDENCY}"))
        suffix = ".dll" if os.name == "nt" else ".so"
        shared = staged / ("slu" + suffix)
        h03_shared = staged / ("h03_slu" + suffix)
        driver = [str(compiler)] + (["cc"] if compiler.stem.lower() == "zig" else [])
        shared_flags = [*driver, "-shared", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]
        abi_check = staged / "pressure_abi.c"
        abi_check.write_text(
            '#include "research/probes/c167_secondary_slu_pressure.h"\n'
            '#include "research/probes/c167_secondary_slu_baseline.h"\n'
            '#include <stddef.h>\n'
            '_Static_assert(sizeof(FactoryTcuState) == 843, "R3 GP state ABI");\n'
            '_Static_assert(sizeof(ToyotaSluPressureState) == 11, "R3 pressure context ABI");\n'
            '_Static_assert(sizeof(ToyotaSecondarySlu) == 20, "R3 SLU state ABI");\n'
            '_Static_assert(offsetof(ToyotaSecondarySlu, selected_7246) == 4, "R3 selected word ABI");\n'
            '_Static_assert(offsetof(ToyotaSluPressureState, offset_7028) == 5, "R3 reset word ABI");\n'
            '_Static_assert(sizeof(ToyotaSluBaselineState) == 18, "R3 baseline state ABI");\n'
            '_Static_assert(sizeof(ToyotaFastOscillation) == 39, "R3 oscillator state ABI");\n'
            '_Static_assert(offsetof(ToyotaFastOscillation, flags_4825) == 30, "R3 oscillator flag ABI");\n',
            encoding="ascii",
        )
        # The C167 oracle's uint16_t expression promotes to signed int on
        # the host. It is always between 0 and 65535, so the comparison
        # remains exact. Keep the pinned source and allow that warning here.
        subprocess.run([*shared_flags, "-Wno-error=sign-compare", "-I", str(staged / headers),
                        str(staged / analog_source),
                        str(staged / core_source), str(staged / PRESSURE_SOURCE), str(staged / BASELINE_SOURCE),
                        str(staged / RESET_SOURCE), str(staged / DIAGNOSTIC_SOURCE),
                        str(abi_check),
                        "-o", str(shared)], check=True)
        vendor = ROOT / "controller/vendor/toyota"
        subprocess.run([*shared_flags, "-I", str(vendor / "include"),
                        str(ROOT / "targets/lfj8/lfj8_h03_slu.c"),
                        str(vendor / "src/factory_core.c"), "-o", str(h03_shared)], check=True)
        library = C.CDLL(str(shared))
        projection = C.CDLL(str(h03_shared))
        try:
            coverage = compare(library, projection, rom)
            coverage["stage_boundaries"] = compare_stage_boundaries(library, projection)
        finally:
            if os.name == "nt":
                from _ctypes import FreeLibrary

                FreeLibrary(projection._handle)
                FreeLibrary(library._handle)

        m32r_output = check_m32r_secondary(staged, m32r, vendor) if m32r else None

    report = {
        "status": "PASS_DONOR_SLU_AND_H03_SECONDARY_HOST_ONLY",
        "s01_sha256": s01["sha256"],
        "r3_commit": r3_commit,
        "entry": f"{ENTRY:06X}",
        "local_host_checks": coverage,
        "upstream_055c5e_oracle_cases": next(x["cases"] for x in analog["operations"] if x["entry"] == "055C5E"),
        "upstream_05dce8_oracle_cases": pressure["comparisons"],
        "upstream_05dc5e_05dce8_oracle_cases": baseline["comparisons"],
        "upstream_05da44_oracle_cases": reset["evidence"]["comparisons"],
        "upstream_05b6de_oracle_cases": diagnostic["evidence"]["comparisons"],
        "upstream_secondary_slu_chain_cases": chain["comparisons"],
        "upstream_secondary_slu_chain_call_boundaries": chain["compared_call_boundaries"],
        "upstream_proof_sha256": {ANALOG_PROOF: sha256(analog_bytes).hexdigest(),
                                  CHAIN_PROOF: sha256(chain_bytes).hexdigest(),
                                  PRESSURE_PROOF: sha256(pressure_bytes).hexdigest(),
                                  BASELINE_PROOF: sha256(baseline_bytes).hexdigest(),
                                  RESET_PROOF: sha256(reset_bytes).hexdigest(),
                                  DIAGNOSTIC_PROOF: sha256(diagnostic_bytes).hexdigest()},
        "h03_scheduler_or_snapshot_bound": False,
        "h03_physical_channel_current_or_failure_bound": False,
        "ready_for_flash": False,
    }
    if m32r_output:
        report["m32r_secondary_check"] = m32r_output
    return report


def main():
    if not __debug__:
        raise RuntimeError("Assertions must be enabled for the donor SLU test")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1", type=Path, default=ROOT / ".sources/R1")
    parser.add_argument("--r3", type=Path, default=ROOT / ".sources/R2")
    parser.add_argument("--cc", type=Path, required=True)
    parser.add_argument("--m32r-cc", type=Path, help="also execute the isolated SECONDARY CPU probe")
    args = parser.parse_args()
    print(json.dumps(verify(args.r1, args.r3, args.cc, args.m32r_cc), indent=2))


if __name__ == "__main__":
    main()
