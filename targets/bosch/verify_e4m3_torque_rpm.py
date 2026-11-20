"""Exercise the RB torque RPM gate and refresh deadline in the ordinary E4M3 candidate."""

import argparse
import json
from pathlib import Path

from build import build
from verify import SPEED_PHYS


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "verification/e4m3-can-9e1c/ordinary-model/manifest.json"
RPM_Q4 = 0xF7C4
LOW, HIGH = 4800, 26000
VALID_RPM = 8000
REDUCTION, DURATION = 32, 20  # RB test vector, in Q8 and units of 10 ms.
TORQUE_WORD = 20000
HOOK_REGISTERS = {"hook_air": 9, "hook_fast": 7, "hook_load": 9}
RB_LEASE_TICKS = 3906  # Pinned RB contract in T4 ticks.
RB_RELEASE_STEP_TICKS = 128  # One Q8 unit of release.


def ready_machine(image):
    from audit_machine import Machine, seed
    from test_torque import steps
    from torque_patch import MODE, READY

    machine = Machine(image)
    machine.native_writes.add(SPEED_PHYS)
    seed(machine, rpm4=VALID_RPM)
    machine.poke(0xFF44, 0x46)
    machine.test_time = 0
    steps(machine, 180)
    assert machine.get(READY) == 2 and machine.get(MODE) == 0
    return machine


def admission(image, rpm):
    from test_torque import send
    from torque_patch import MODE, REASON, TOKEN, command

    machine = ready_machine(image)
    machine.poke(RPM_Q4, rpm)
    send(machine, command(1, 1, REDUCTION, DURATION, 1))
    admitted = LOW <= rpm <= HIGH
    assert machine.get(MODE) == machine.get(TOKEN) == int(admitted), rpm
    reason = machine.get(REASON)
    assert reason == (0 if admitted else 6), (rpm, reason)
    return {"rpm_q4": rpm, "accepted": admitted, "reason": reason}


def native_torque(machine, hook):
    entry, displaced, name = hook
    register = HOOK_REGISTERS[name]
    machine.reg[register] = TORQUE_WORD
    machine.run(entry, stop=entry + len(bytes.fromhex(displaced)))
    return machine.reg[register]


def token_status(machine, token, start):
    from torque_patch import crc8

    status = []
    for frame in machine.frames[start:]:
        if frame["id"] == 0x5E9:
            data = bytes.fromhex(frame["data"])
            assert len(data) == 8 and crc8(data[:7]) == data[7]
            if int.from_bytes(data[4:6], "little") == token:
                status.append(data)
    return status


def lose_rpm(image, rpm, first_hook):
    from test_torque import send, steps
    from torque_patch import HOOKS, MODE, REASON, SEEN, TOKEN, command

    machine = ready_machine(image)
    frame_start = len(machine.frames)
    send(machine, command(1, 1, REDUCTION, DURATION, 1))
    assert machine.get(MODE) == 1
    steps(machine, 8)  # Allow the programmed ramp to finish within the first lease.
    reduced = TORQUE_WORD * (256 - REDUCTION) // 256
    assert all(native_torque(machine, hook) == reduced for hook in HOOKS)
    assert machine.get(SEEN) == 7
    steps(machine, 8)
    assert machine.get(MODE) == 1
    assert any(s[3] == REDUCTION and s[1] & 0x70 == 0x70 for s in token_status(machine, 1, frame_start))

    # The chosen branch sees the invalid RPM before another background call.
    machine.poke(RPM_Q4, rpm)
    after_loss = native_torque(machine, first_hook)
    assert after_loss == TORQUE_WORD
    assert machine.get(MODE) == 0 and machine.get(REASON) == 6 and machine.get(TOKEN) == 1
    assert all(native_torque(machine, hook) == TORQUE_WORD for hook in HOOKS if hook != first_hook)
    frame_start = len(machine.frames)
    steps(machine, 12)
    status = token_status(machine, 1, frame_start)
    assert status and all(s[3] == 0 for s in status), (rpm, first_hook, status)

    machine.poke(RPM_Q4, VALID_RPM)
    send(machine, command(2, 2, REDUCTION, DURATION, 1))
    assert machine.get(MODE) == 0 and machine.get(TOKEN) == 1
    assert all(native_torque(machine, hook) == TORQUE_WORD for hook in HOOKS)
    steps(machine, 400)
    send(machine, command(1, 3, REDUCTION, DURATION, 1))
    assert machine.get(MODE) == 0 and machine.get(REASON) == 4 and machine.get(TOKEN) == 1
    send(machine, command(1, 1, REDUCTION, DURATION, 2))
    assert machine.get(MODE) == 1 and machine.get(REASON) == 0 and machine.get(TOKEN) == 2
    steps(machine, 8)
    assert native_torque(machine, first_hook) == reduced
    return {"rpm_q4": rpm, "first_native_path": first_hook[2], "word_after_loss": after_loss,
            "zero_status_frames": len(status), "old_token_rejected_after_rpm_recovery": True,
            "next_token_accepted": True}


def receive_tick(machine):
    from torque_patch import RX_HI, RX_LO

    return (machine.get(RX_HI) << 16) | machine.get(RX_LO)


def pulse_with_refresh(image, start_tick):
    from test_torque import send, steps
    from torque_patch import MODE, REASON, SEQ, TOKEN, command

    machine = ready_machine(image)
    machine.test_time = start_tick
    send(machine, command(1, 1, REDUCTION, DURATION, 1))
    started = receive_tick(machine)
    assert machine.get(MODE) == machine.get(TOKEN) == 1
    steps(machine, 8)
    send(machine, command(2, 2, REDUCTION, DURATION, 1))
    refreshed = receive_tick(machine)
    assert machine.get(MODE) == 1 and machine.get(SEQ) == 2 and machine.get(REASON) == 0
    assert 0 < refreshed - started < RB_LEASE_TICKS
    return machine, refreshed


def lose_refresh(image, start_tick, first_hook):
    from test_torque import clock, steps
    from torque_patch import HOOKS, MODE, ORIGINAL_DURATION, START_HI, START_LO

    machine, refreshed = pulse_with_refresh(image, start_tick)
    started = (machine.get(START_HI) << 16) | machine.get(START_LO)
    deadline = refreshed + RB_LEASE_TICKS
    release_time = REDUCTION * RB_RELEASE_STEP_TICKS
    assert deadline + release_time - started < machine.get(ORIGINAL_DURATION)
    observations = []
    points = ((-1, REDUCTION), (0, REDUCTION), (RB_RELEASE_STEP_TICKS, REDUCTION - 1),
              (release_time - 1, 1), (release_time, 0))
    for since_deadline, reduction in points:
        # Advance the clock without running CAN foreground. Each native
        # entry point must handle the timeout even when foreground is absent.
        clock(machine, deadline + since_deadline)
        expected_word = TORQUE_WORD * (256 - reduction) // 256
        assert native_torque(machine, first_hook) == expected_word, (first_hook, since_deadline)
        assert machine.get(MODE) == int(reduction != 0)
        observations.append({"ticks_from_deadline": since_deadline, "request_word": expected_word})

    assert all(native_torque(machine, hook) == TORQUE_WORD for hook in HOOKS)
    frame_start = len(machine.frames)
    machine.test_time = deadline + release_time
    steps(machine, 24)
    status = token_status(machine, 1, frame_start)
    assert status and all(s[2] == 2 and s[3] == 0 for s in status)
    return {"first_native_path": first_hook[2], "refresh_t4": refreshed,
            "deadline_t4": deadline & 0xFFFFFFFF, "observations": observations,
            "zero_status_frames": len(status)}


def refresh_at_deadline(image, offset):
    from test_torque import steps
    from torque_patch import MODE, REASON, SEQ, command

    machine, refreshed = pulse_with_refresh(image, 40000)
    at = refreshed + RB_LEASE_TICKS + offset
    assert machine.inject(0x5E8, command(2, 3, REDUCTION, DURATION, 1))
    machine.test_time = at
    # Hold T4 constant across the modeled C_CAN IF1 transfer so RX completion
    # is exercised on the specified side of the expiry boundary.
    steps(machine, 8, delta=0)
    accepted = offset < 0
    assert machine.get(MODE) == 1
    assert machine.get(SEQ) == (3 if accepted else 2)
    assert machine.get(REASON) == (0 if accepted else 5)
    assert receive_tick(machine) == (at if accepted else refreshed)
    return {"ticks_from_deadline": offset, "accepted": accepted, "reason": machine.get(REASON)}


def verify(engine, s04):
    image, manifest, _, _ = build(engine, s04, model_fields=True, compact=True, ordinary_model_field=True)
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["sha256"] != recorded["sha256"] or manifest["checksum_records"] != recorded["checksum_records"]:
        raise ValueError("Rebuild differs from the audited ordinary E4M3 candidate")
    from torque_patch import HOOKS

    return {"status": "PASS_OFFLINE_ONLY", "base_sha256": manifest["base_sha256"],
            "bosch_sha256": manifest["sha256"], "checksum_records": manifest["checksum_records"],
            "model_bus": "RB 0x5E8/0x5E9", "fixture_reduction_q8": REDUCTION, "fixture_duration_ms": DURATION * 10,
            "admission": [admission(image, rpm) for rpm in (LOW - 1, LOW, HIGH, HIGH + 1)],
            "loss_and_recovery": [lose_rpm(image, rpm, hook) for rpm in (LOW - 1, HIGH + 1) for hook in HOOKS],
            "refresh_lease_t4_ticks": RB_LEASE_TICKS,
            "refresh_cutoff": [refresh_at_deadline(image, offset)
                               for offset in (-1, 0, RB_RELEASE_STEP_TICKS)],
            "loss_of_refresh": [lose_refresh(image, started, hook)
                                for started in (40000, 0x10000 - 6100, 0x100000000 - 6100)
                                for hook in HOOKS],
            "current_pair_hardware_tested": False}


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions for this verification")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--s04", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.engine.resolve(), args.s04.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
