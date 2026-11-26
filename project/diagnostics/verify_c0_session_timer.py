"""Replay the S03 C0 session clock and its reset on the pinned C167 executor."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from verify_model_monitor import native_vm


SESSION_RELOAD = 0xAB3B
SESSION_REMAINING = 0xF9F1
SESSION_MODE = 0xF963
SESSION_PERMISSION = 0xF9A9
SESSION_FLAGS = 0xFD1E
EXPIRY_PENDING = 0x0100
STARTUP = 0x073AFA
OPEN = 0x073966
DISPATCH = 0x0739A2
TASK12_TIMER = 0x073B54
FOREGROUND = 0x07102E


def run(vm, start, stop=None):
    vm.r[0], vm.sp = 0xE600, 0xFD80
    vm.run(start, stop=stop)
    if stop is None and (vm.r[0], vm.sp) != (0xE600, 0xFD80):
        raise ValueError(f"S03 routine did not restore its call frame at {start:#08x}")


def snapshot(vm):
    return [vm.read(SESSION_REMAINING, 1), vm.read(SESSION_MODE, 1),
            vm.read(SESSION_PERMISSION, 1), bool(vm.read(SESSION_FLAGS) & EXPIRY_PENDING)]


def cold_start(vm):
    vm.reset()
    for addr in (0xFD0A, 0xFD18, 0xFD1A, SESSION_FLAGS, 0xFD20, 0xF8EF, 0xE698, 0xF841, 0xF831):
        vm.write(addr, 0)
    run(vm, STARTUP)
    if snapshot(vm) != [0, 0x9F, 0x11, False]:
        raise ValueError("Unexpected C0 cold session")


def dispatch(vm, request):
    # The transport has already copied a coherent single-frame PDU to E653.
    for offset, value in enumerate(bytes(request).ljust(8, b"\0")):
        vm.write(0xE653 + offset, value, 1)
    vm.write(0xE650, len(request), 1)
    run(vm, DISPATCH)
    return bytes(vm.read(0xE653 + offset, 1) for offset in range(vm.read(0xE650, 1)))


def verify_timer(vm):
    cold_start(vm)
    run(vm, TASK12_TIMER)
    if snapshot(vm) != [0, 0x9F, 0x11, False]:
        raise ValueError("A cold session unexpectedly armed the timer")
    vm.r[12] = 0x90
    run(vm, OPEN)
    if vm.read(SESSION_RELOAD, 1) != 9 or snapshot(vm) != [9, 0x90, 0x01, False]:
        raise ValueError("Unexpected S03 timer reload on the C0 receive route")

    reloads = []
    for request, expected, permission in (
        ((0x17, 0xFF, 0), (0x7F, 0x17, 0x80), 0x01),
        ((0x10, 0x86), (0x50, 0x86), 0x08),
        ((0x17,), (0x7F, 0x17, 0x12), 0x08),
        ((0x99,), (0x7F, 0x99, 0x11), 0x08),
    ):
        run(vm, TASK12_TIMER)
        if vm.read(SESSION_REMAINING, 1) != 8:
            raise ValueError("Expected an elapsed task 12 event before dispatch")
        reply = dispatch(vm, request)
        if reply != bytes(expected) or snapshot(vm) != [9, 0x90, permission, False]:
            raise ValueError(f"S03 did not reload after {bytes(request).hex()}")
        reloads.append({"request": bytes(request).hex(), "reply": reply.hex(), "count": 9})

    steps = []
    for step in range(1, 10):
        run(vm, TASK12_TIMER)
        state = snapshot(vm)
        if state != [9 - step, 0x90, 0x08, step == 9]:
            raise ValueError(f"Unexpected session state after {step} task 12 events: {state}")
        steps.append(state)
        if step < 9:
            run(vm, FOREGROUND)
            if snapshot(vm) != state:
                raise ValueError("The foreground reset the C0 session before expiry")

    # Prime a pending receive and transport fields just before expiry is consumed.
    vm.write(0xF831, 4, 1)
    vm.write(0xE642, 3)
    vm.write(0xE63D, 2, 1)
    vm.write(0xE0AC, 0x10, 1)
    run(vm, FOREGROUND)
    ended = snapshot(vm)
    remaining_transport = (vm.read(0xF831, 1), vm.read(0xE642), vm.read(0xE63D, 1))
    if ended != [0, 0x9F, 0x11, False] or remaining_transport != (0, 0, 0):
        raise ValueError("The next C0 foreground did not consume the expiry and clear the transport")
    if vm.read(0xE0AC, 1) != 0x10:
        raise ValueError("Session expiry changed the diagnostic history marker")
    return {"reloads": reloads, "task12_event_observations": steps, "foreground_after_expiry": ended,
            "cleared": ["F831.2", "E642", "E63D"], "history_marker_preserved": True}


def verify_task_clock(vm):
    roots = [
        (0x05209C, 0x07009E, 0x0700A2),
        (0x05254A, 0x0774BA, 0x0774BE),
    ]
    for table, root, site in roots:
        pointer = int.from_bytes(bytes(vm.rom[table + offset] for offset in range(4)), "little")
        call = bytes(vm.rom[site + offset] for offset in range(4))
        if pointer != root or call != bytes.fromhex("da07543b"):
            raise ValueError(f"S03 task 12 dispatch differs at {table:#08x}")

    phases = []
    for previous in range(256):
        vm.reset()
        vm.write(0xF828, previous, 1)
        run(vm, 0x077EE6, 0x077F06)
        mask = vm.read(0x60AC + 2 * vm.r[9])
        if mask & 0x0008:
            phases.append(vm.read(0xF828, 1))
    if phases != [0x40, 0xC0]:
        raise ValueError(f"Unexpected task 12 publication phases: {phases}")
    return {"task_number": 12, "selector_cases": 256, "task12_ready_mask": "0x0008",
            "publication_phases": phases, "nominal_t6_periods_between_posts": 128}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1", required=True, type=Path, help="Git checkout containing the pinned S03 image")
    parser.add_argument("--r3", required=True, type=Path, help="Git checkout containing the pinned executor")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json":
        parser.error("--out must be a JSON report")
    try:
        vm, source_sha = native_vm(args.r1, args.r3)
        report = {"s03_sha256": source_sha, "timer": verify_timer(vm), "clock": verify_task_clock(vm),
                  "hardware_executed": False, "physical_t6_period_measured": False}
        raw = (json.dumps(report, indent=2) + "\n").encode("utf-8")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(raw)
        print(f"PASS S03 C0 session timer and task clock ({sha256(raw).hexdigest()})")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
