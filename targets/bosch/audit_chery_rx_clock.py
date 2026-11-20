"""Audit conservative 0x1AE capture timing on the Bosch ST10 model."""

import argparse
from collections import Counter
from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path

from build import CAN_ID, OBJECT, PHASE, build, digest
from verify import SPEED_PHYS, build_native_model, payload

T4_READER = 0x018BFC
T4, T4CON, T4IC, T4_HIGH = 0xFE44, 0xFF44, 0xFF64, 0xE176
CAN_CONTROL, CAN_STATUS = 0xEF00, 0xEF02
IF1_COMMAND, IF1_ARB2, IF1_MCTRL, IF1_DATA = 0xEF10, 0xEF1A, 0xEF1C, 0xEF1E
CAN_NEWDAT = 0xEF90
OBJECT_BIT = 1 << (OBJECT - 1)
TICK_MASK = 0xFFFFFFFF
TEST_LEASE = 40


class NativeClock:
    def __init__(self, s04, candidate, model):
        self.vm = build_native_model(candidate, model)
        from build_can_diag import offset

        off = offset(T4_READER)
        assert s04[off:off + 0x44] == candidate[off:off + 0x44]
        # PM0036: ATOMIC and NOP preserve all flags. The pinned decoder has no
        # IRQ scheduling. JMPR to the following instruction preserves flags.
        # MOV [R0],T4 is equivalent to MOV [R0],[R3], with fixture R3 = T4.
        for pc, original, equivalent in (
            (0x018C00, "d130", "0d00"),
            (0x018C0A, "cc00", "0d00"),
            (0x018C0C, "840044fe", "c8030d00"),
            (0x018C26, "840044fe", "c8030d00"),
        ):
            original = bytes.fromhex(original)
            assert bytes(self.vm.rom[pc + i] for i in range(len(original))) == original
            self.vm.rom.update(enumerate(bytes.fromhex(equivalent), pc))

    def read(self, high, low, second_low=None, *, overflow_during_read=False):
        vm = self.vm
        vm.reset()
        vm.r[3] = T4
        vm.r[4:6] = [0xDEAD, 0xBEEF]
        saved_regs = vm.r.copy()
        saved_sp = vm.sp
        saved_psw = 0x3C42
        pending_on_entry = second_low is not None and not overflow_during_read
        for address, value in (
            (T4, low), (T4_HIGH, high), (T4IC, 0x1C | (0x80 if pending_on_entry else 0)),
            (0xE116, 0x7FFF), (0xFF10, saved_psw),
        ):
            vm.write(address, value)
        reads = 0
        read = vm.read

        def read_with_overflow(address, size=2, extend=True):
            nonlocal reads
            if address == T4IC and overflow_during_read:
                assert reads == 1
                vm.write(T4IC, 0x9C)
            if address == T4:
                assert size == 2 and vm.psw_other >> 12 == 7
                reads += 1
                if reads == 2:
                    assert second_low is not None
                    return second_low
            return read(address, size, extend)

        vm.read = read_with_overflow
        try:
            vm.run(T4_READER, limit=32)
        finally:
            vm.read = read
        assert reads == (1 if second_low is None else 2)
        assert vm.r[:4] == saved_regs[:4] and vm.r[6:] == saved_regs[6:]
        assert vm.sp == saved_sp and vm.psw_other == saved_psw & 0xFFE0
        assert vm.read(T4_HIGH) == high
        assert vm.read(T4IC) == 0x1C | (0x80 if second_low is not None else 0)
        return (vm.r[5] << 16) | vm.r[4]

    def at(self, tick):
        return self.read(tick >> 16, tick & 0xFFFF)


def verify_clock(clock):
    cases = 0
    for high, low in product((0, 1, 0x7FFF, 0xFFFE, 0xFFFF), (0, 1, 0x7FFF, 0xFFFE, 0xFFFF)):
        assert clock.read(high, low) == (high << 16) | low
        cases += 1
        # Overrun before the first T4 read, or between that read and the check.
        expected = (((high + 1) << 16) | low) & TICK_MASK
        assert clock.read(high, low, low) == expected
        assert clock.read(high, 0xFFFF, low, overflow_during_read=True) == expected
        cases += 2
    return cases


@dataclass(frozen=True)
class Capture:
    earliest_tick: int
    observed_tick: int
    generation: int
    data: bytes


class CaptureProbe:
    """A model observer sharing the emitted receiver's IF1 transactions."""

    def __init__(self, image, clock, symbols, delay):
        from audit_machine import Machine
        from build_can_diag import STATE, offset
        from test_can_diag import start

        idle, complete = offset(symbols["idle"]), offset(symbols["complete"])
        newdata_read = bytes.fromhex("f2f490ef")  # MOV R4, CAN_NEWDAT
        assert image[idle:complete].count(newdata_read) == 1
        self.poll_pc = symbols["idle"] + image[idle:complete].index(newdata_read)
        self.state = STATE
        self.reset_pc = symbols["reset"]
        self.received_pc = symbols["received"]
        self.clock = clock
        self.tick = 0
        self.generation = 0
        self.active = False
        self.earliest = None
        self.captures = []
        self.rejected = Counter()
        self.completed = []
        self.machine = Machine(image)
        self.machine.native_writes.add(SPEED_PHYS)
        start(self.machine)
        self.machine.transfer_delay = delay
        self.machine.poke(T4CON, 0x46)
        self.machine.instruction_hook = self.observe

    def revoke(self):
        self.earliest = None
        if self.active:
            self.active = False
            self.generation += 1

    def eligible(self):
        machine = self.machine
        return (machine.get(self.state) == 0 and machine.get(T4CON) == 0x46
                and not (machine.get(CAN_CONTROL) & 1 or machine.get(CAN_STATUS) & 0x80))

    def observe(self, machine, pc):
        if pc == self.reset_pc:
            self.revoke()
        elif pc == self.poll_pc and self.active:
            before_poll = self.clock.at(self.tick)
            if not (machine.get(CAN_NEWDAT) & OBJECT_BIT):
                self.earliest = before_poll
        elif pc == self.received_pc:
            assert machine.get(PHASE) == 1 and not machine.get(IF1_COMMAND) & 0x8000
            control = machine.get(IF1_MCTRL)
            self.completed.append(control)
            earliest, self.earliest = self.earliest, None
            if not self.active or not self.eligible():
                self.revoke()
                self.rejected["inactive"] += 1
            elif machine.get(IF1_ARB2) != 0x8000 | (CAN_ID << 2) or control & 0xC00F != 0x8008:
                self.revoke()
                self.rejected["invalid_if1"] += 1
            elif earliest is None:
                self.rejected["no_empty_poll"] += 1
            else:
                observed = self.clock.at(self.tick)
                age_bound = (observed - earliest) & TICK_MASK
                if age_bound >= TEST_LEASE:
                    self.rejected["too_old"] += 1
                else:
                    data = bytes(machine.mem[IF1_DATA:IF1_DATA + 8])
                    self.captures.append(Capture(earliest, observed, self.generation, data))

    def step(self, tick):
        self.tick = tick & TICK_MASK
        if self.eligible():
            self.active = True
        else:
            self.revoke()
        self.machine.run()

    def until(self, condition, first_tick, limit=40):
        for tick in range(first_tick, first_tick + limit):
            self.step(tick)
            if condition():
                return tick
        raise AssertionError("The expected receiver state was not reached")

    def arm(self, first_tick):
        return self.until(lambda: self.earliest is not None, first_tick)


def verify_can(image, clock, symbols):
    delay_cases = []
    valid = payload(6000)
    second = payload(6100)
    for delay, base in product((0, 1, 3), (100, 0xFFFF, 0xFFFFFFFF)):
        probe = CaptureProbe(image, clock, symbols, delay)
        armed = probe.arm(base)
        assert probe.machine.inject(CAN_ID, valid)
        probe.until(lambda: probe.completed, armed + 1)
        assert len(probe.captures) == 1
        sample = probe.captures[0]
        assert sample.data == valid and sample.generation == 0
        assert sample.earliest_tick == (armed & TICK_MASK)
        assert sample.observed_tick == probe.tick
        age_bound = (sample.observed_tick - sample.earliest_tick) & TICK_MASK
        assert delay < age_bound < TEST_LEASE
        delay_cases.append({"if1_delay_calls": delay, "from": sample.earliest_tick,
                            "to": sample.observed_tick, "age_upper_bound": age_bound})

    rejected = Counter()
    for case in ("old", "unarmed", "overwritten", "short", "if1_contention"):
        delay = 7 if case == "if1_contention" else 0
        probe = CaptureProbe(image, clock, symbols, delay)
        armed = 0 if case == "unarmed" else probe.arm(100)
        assert probe.machine.inject(CAN_ID, valid, dlc=7 if case == "short" else 8)
        if case == "overwritten":
            assert probe.machine.inject(CAN_ID, second)
        probe.until(lambda: probe.completed, armed + (TEST_LEASE - 1 if case == "old" else 1), limit=220)
        expected = {"old": "too_old", "unarmed": "no_empty_poll",
                    "overwritten": "invalid_if1", "short": "invalid_if1",
                    "if1_contention": "too_old"}[case]
        assert probe.rejected == {expected: 1} and not probe.captures
        if case in ("overwritten", "short"):
            assert probe.generation == 1
        if case == "overwritten":
            assert probe.completed[0] & 0x4000
        if case == "old":
            # This accepted speed is concrete evidence that post-IF1 time
            # alone cannot supply the missing receive age.
            assert probe.machine.get(SPEED_PHYS) == (6000 // 25) << 5
            assert probe.tick - armed == TEST_LEASE
        rejected.update(probe.rejected)

    # A second wire arrival after IF1 latched the first frame changes the
    # object, not the staged frame. Without another empty poll its age is unknown.
    probe = CaptureProbe(image, clock, symbols, 0)
    armed = probe.arm(100)
    assert probe.machine.inject(CAN_ID, valid)
    started = probe.until(lambda: probe.machine.get(PHASE) == 1, armed + 1)
    assert probe.machine.inject(CAN_ID, second)
    done = probe.until(lambda: probe.completed, started + 1)
    assert [capture.data for capture in probe.captures] == [valid]
    probe.until(lambda: len(probe.completed) == 2, done + 1)
    assert [capture.data for capture in probe.captures] == [valid]
    assert probe.rejected == {"no_empty_poll": 1}

    recovery_cases = []
    for fault in ("bus_off", "can_init", "clock_stopped"):
        probe = CaptureProbe(image, clock, symbols, 3)
        armed = probe.arm(100)
        assert probe.machine.inject(CAN_ID, valid)
        started = probe.until(lambda: probe.machine.get(PHASE) == 1, armed + 1)
        fault_register, value, restored = {
            "bus_off": (CAN_STATUS, 0x80, 0),
            "can_init": (CAN_CONTROL, 0x21, 0x61),
            "clock_stopped": (T4CON, 0x06, 0x46),
        }[fault]
        probe.machine.poke(fault_register, value)
        for tick in range(started + 1, started + 5):
            probe.step(tick)
        assert not probe.captures and probe.generation == 1 and not probe.active
        assert len(probe.completed) == (1 if fault == "clock_stopped" else 0)
        probe.machine.poke(fault_register, restored)
        # Keep reconfiguration at the same IF1 latency as the modeled cold
        # start. Delayed RX has already completed or been discarded above.
        probe.machine.transfer_delay = 0
        rearmed = probe.until(lambda: probe.earliest is not None, started + 5, limit=680)
        assert probe.machine.inject(CAN_ID, second)
        probe.until(lambda: probe.captures, rearmed + 1)
        assert len(probe.captures) == 1
        assert probe.captures[0].generation == 1 and probe.captures[0].data == second
        recovery_cases.append(fault)
    return {"newdat_poll": f"0x{probe.poll_pc:06X}", "capture_cases": delay_cases,
            "rejections": dict(rejected), "new_arrival_during_completion": "first_only",
            "recoveries": recovery_cases}


def audit(engine, s04, model):
    image, manifest, _, _ = build(engine, s04, model_fields=True, ordinary_model_field=True, compact=True)
    clock = NativeClock(s04, image, model)
    symbols = {name: int(address, 16) for name, address in manifest["speed_receiver_symbols"].items()}
    clock_cases = verify_clock(clock)
    can = verify_can(image, clock, symbols)
    return {
        "status": "PASS_OFFLINE_ONLY",
        "candidate_sha256": digest(image),
        "native_reader": f"0x{T4_READER:06X}",
        "if1_completion": f"0x{symbols['received']:06X}",
        "native_clock_cases": clock_cases,
        "test_lease_ticks": TEST_LEASE,
        **can,
        "hardware_tested": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("engine", "s04", "model"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.engine.resolve(), args.s04.read_bytes(), args.model)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
