"""Run the emitted E4M3 receive timestamp path in the pinned ST10/C_CAN model."""

import argparse
from itertools import product
import json
from pathlib import Path

from build import AGE, CAN_ID, PHASE, STALE_CALLS, build
from rx_timestamp import (
    BOUND_HIGH, BOUND_LOW, BUSY_MASK, CAN_CONTROL, CAN_NEWDAT, CAN_STATUS, HAVE_BOUND,
    T4, T4CON, T4IC, T4_HIGH, WAITING,
)
from verify import SPEED_PHYS, payload


MASK = 0xFFFFFFFF
FRAME = payload(6000)
SPEED_Q7 = 6000 // 25 << 5


class Receiver:
    def __init__(self, image, symbols):
        from audit_machine import Machine
        from test_can_diag import start

        self.machine = Machine(image)
        self.machine.native_writes.add(SPEED_PHYS)
        self.symbols = symbols
        self.completed = 0
        self.checked = []
        self.reads = []
        start(self.machine)
        self.machine.poke(T4CON, 0x46)
        self.machine.instruction_hook = self.observe
        self.machine.read_hook = self.record_read

    def observe(self, machine, pc):
        if pc == self.symbols["received"]:
            self.completed += 1
        if pc == self.symbols["rx_bound_checked"]:
            current = machine.reg[4] | machine.reg[5] << 16
            bound = machine.get(BOUND_LOW) | machine.get(BOUND_HIGH) << 16
            self.checked.append((bound, current, bytes(machine.mem[0xEF1E:0xEF26])))

    def record_read(self, machine, address, _size):
        if address in (T4, CAN_NEWDAT):
            self.reads.append((machine.instruction_pc, address))

    def step(self, tick, *, pending_irq=False):
        self.machine.poke(T4, tick & 0xFFFF)
        self.machine.poke(T4_HIGH, (tick & MASK) >> 16)
        self.machine.poke(T4IC, 0x9C if pending_irq else 0x1C)
        self.machine.run()

    def until(self, condition, first_tick, *, limit=50):
        for tick in range(first_tick, first_tick + limit):
            self.step(tick)
            if condition():
                return tick
        raise AssertionError("Expected state was not reached")

    def arm(self, first_tick):
        return self.until(lambda: self.machine.get(PHASE) == HAVE_BOUND, first_tick)

    def inject(self, data=FRAME, **options):
        assert self.machine.inject(CAN_ID, data, **options)

    def complete(self, first_tick):
        expected = self.completed + 1
        return self.until(lambda: self.completed == expected, first_tick)


def verify_image(image, manifest):
    symbols = {name: int(address, 16) for name, address in manifest["speed_receiver_symbols"].items()}
    cases = []
    for delay, base in product((0, 1, 3), (100, 0xFFFF, 0xFFFFFFFF)):
        rx = Receiver(image, symbols)
        armed = rx.arm(base)
        m = rx.machine
        poll = rx.reads.index((symbols["rx_poll"], CAN_NEWDAT))
        assert rx.reads[poll - 1][1] == T4  # Physical T4 read before the object observation.
        m.transfer_delay = delay
        rx.inject()
        done = rx.complete(armed + 1)
        assert rx.checked == [(armed & MASK, done & MASK, FRAME)]
        assert done - armed > delay
        assert m.get(SPEED_PHYS) == SPEED_Q7 and m.get(AGE) == STALE_CALLS
        assert m.get(PHASE) == 0
        cases.append({"if1_delay": delay, "lower": armed & MASK,
                      "completion": done & MASK, "age_upper_bound": done - armed})

    rejected = []
    for name in ("unarmed", "dlc", "msglst", "checksum", "clock_stopped",
                 "overflow_pending", "torn_high_word", "half_range", "backward",
                 "late_bus_off", "late_init"):
        rx = Receiver(image, symbols)
        m = rx.machine
        armed = 100 if name == "unarmed" else rx.arm(100)
        m.poke(SPEED_PHYS, SPEED_Q7)  # Make revocation observable even without a preceding frame.
        m.poke(AGE, STALE_CALLS)
        rx.inject(payload(6000, corrupt=name == "checksum"), dlc=7 if name == "dlc" else 8)
        if name == "msglst":
            rx.inject()
        started = rx.until(lambda: m.get(PHASE) & WAITING, armed + 1)
        m.poke(T4CON, 0x06 if name == "clock_stopped" else 0x46)
        if name == "torn_high_word":
            def change_high(machine, address, size):
                rx.record_read(machine, address, size)
                if address == T4:
                    machine.poke(T4_HIGH, 1)
            m.read_hook = change_high
        elif name in ("late_bus_off", "late_init"):
            def lose_can(machine, pc):
                rx.observe(machine, pc)
                if pc == symbols["received"]:
                    register, mask = (CAN_STATUS, 0x80) if name == "late_bus_off" else (CAN_CONTROL, 1)
                    machine.poke(register, mask)
            m.instruction_hook = lose_can
        tick = {"half_range": armed + 0x80000000, "backward": armed - 1}.get(name, started + 1)
        rx.step(tick, pending_irq=name == "overflow_pending")
        assert rx.completed == 1 and not rx.checked, name
        assert m.get(SPEED_PHYS) == 0 and m.get(AGE) == 0 and m.get(PHASE) == 0, name
        rejected.append(name)

    rx = Receiver(image, symbols)
    armed = rx.arm(100)
    rx.inject()
    started = rx.until(lambda: rx.machine.get(PHASE) & WAITING, armed + 1)
    rx.inject(payload(6100))
    first = rx.complete(started + 1)
    assert len(rx.checked) == 1 and rx.checked[0][2] == FRAME
    rx.complete(first + 1)
    assert len(rx.checked) == 1 and rx.machine.get(SPEED_PHYS) == 0

    rx = Receiver(image, symbols)
    armed = rx.arm(100)
    rx.inject()
    done = rx.complete(armed + 1)
    for tick in range(done + 1, done + STALE_CALLS):
        rx.step(tick)
        assert rx.machine.get(SPEED_PHYS) == SPEED_Q7
    rx.step(done + STALE_CALLS)
    assert rx.machine.get(SPEED_PHYS) == 0 and rx.machine.get(AGE) == 0

    rx = Receiver(image, symbols)
    armed = rx.arm(100)
    m = rx.machine
    rx.step(armed + 1, pending_irq=True)
    assert m.get(PHASE) == 0
    rx.inject()
    rx.complete(armed + 2)
    assert not rx.checked and m.get(SPEED_PHYS) == 0
    rearmed = rx.arm(armed + 20)
    rx.inject()
    rx.complete(rearmed + 1)
    assert len(rx.checked) == 1 and rx.checked[0][0] == rearmed

    recovery = []
    for name in ("bus_off", "can_init", "busy_timeout"):
        rx = Receiver(image, symbols)
        m = rx.machine
        armed = rx.arm(100)
        m.transfer_delay = 60 if name == "busy_timeout" else 3
        rx.inject()
        started = rx.until(lambda: m.get(PHASE) & WAITING, armed + 1)
        if name == "busy_timeout":
            rx.until(lambda: m.get(CAN_CONTROL) & 1, started + 1, limit=55)
            assert m.get(PHASE) & BUSY_MASK == 50
        else:
            register, value = (CAN_STATUS, 0x80) if name == "bus_off" else (CAN_CONTROL, 0x21)
            m.poke(register, value)
        reset = rx.until(lambda: m.get(PHASE) == 0, started + (51 if name == "busy_timeout" else 1))
        assert m.get(BOUND_LOW) == m.get(BOUND_HIGH) == m.get(SPEED_PHYS) == 0
        assert not rx.checked
        m.poke(CAN_STATUS, 0)
        m.transfer_delay = 0
        rearmed = rx.until(lambda: m.get(PHASE) == HAVE_BOUND, reset + 1, limit=680)
        rx.inject()
        rx.complete(rearmed + 1)
        assert len(rx.checked) == 1 and rx.checked[0][0] == rearmed, name
        recovery.append(name)

    return {"sha256": manifest["sha256"], "checksum_records": manifest["checksum_records"],
            "receiver_bytes": manifest["regions"]["speed_receiver"]["length"], "captures": cases,
            "rejections": rejected, "back_to_back_requires_new_empty_poll": True,
            "speed_expiry_service_calls": STALE_CALLS, "idle_clock_recovery_requires_new_empty_poll": True,
            "recovery": recovery}


def main():
    if not __debug__:
        raise RuntimeError("This verifier requires assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--s04", required=True, type=Path)
    parser.add_argument("--image", type=Path, help="Also compare a generated timestamp BIN byte for byte")
    args = parser.parse_args()
    base = args.s04.read_bytes()
    report = {}
    supplied = args.image.read_bytes() if args.image else None
    matching_profile = None
    for compact in (False, True):
        image, manifest, _, _ = build(args.engine.resolve(), base, model_fields=True,
                                      ordinary_model_field=True, compact=compact, rx_timestamp=True)
        profile = "compact" if compact else "wide"
        if supplied == image:
            matching_profile = profile
        report[profile] = verify_image(image, manifest)
    if supplied is not None and matching_profile is None:
        parser.error("The supplied file differs from both rebuilt timestamp profiles")
    print(json.dumps({"status": "PASS_OFFLINE_ONLY", "hardware_tested": False,
                      "matched_input_profile": matching_profile, **report}, indent=2))


if __name__ == "__main__":
    main()
