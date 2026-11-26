"""Execute and compare exact ST10 bytes for the qualified RB ordinary profile."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

from build import build, checksum_records, digest
from verify_e4m3_torque_rpm import (
    DURATION, HIGH, LOW, REDUCTION, TORQUE_WORD, native_torque, ready_machine, token_status,
)

ORDINARY_SHA = "bd0afefa40dfd1ea82e647ea5af7e64e2f652c27ccc5c3b91a986224fd77ec79"


def qualify(machine, synchronized=True, rejected=False):
    # Other set bits demonstrate that only the native qualified/invalid bits matter.
    machine.poke(0xFD18, 0x8005 | (0x40 if synchronized else 0))
    machine.poke(0xFD1A, 0x8005 | (0x4000 if rejected else 0))


def start_cases(image):
    import test_torque as q
    from torque_patch import MODE, REASON, TOKEN, command

    rows = []
    for delay in (0, 1, 3):
        for rpm in (LOW - 1, LOW, HIGH, HIGH + 1):
            for synced, invalid in ((False, False), (False, True), (True, False), (True, True)):
                machine = ready_machine(image)
                machine.transfer_delay = delay
                machine.poke(0xF7C4, rpm)
                qualify(machine, synced, invalid)
                q.send(machine, command(1, 1, REDUCTION, DURATION, 1))
                accepted = LOW <= rpm <= HIGH and synced and not invalid
                assert machine.get(MODE) == machine.get(TOKEN) == int(accepted)
                assert machine.get(REASON) == (0 if accepted else 6)
                rows.append({"delay": delay, "rpm_q4": rpm, "synchronized": synced,
                             "invalid": invalid, "accepted": accepted})
    return rows


def active_machine(image):
    import test_torque as q

    machine = ready_machine(image)
    qualify(machine)
    q.arm(machine)
    q.steps(machine, 8)
    return machine


def lose_qualification(image, failure, hook):
    import test_torque as q
    from torque_patch import HOOKS, MODE, REASON, SEQ, TOKEN, command

    machine = active_machine(image)
    reduced = TORQUE_WORD * (256 - REDUCTION) // 256
    assert all(native_torque(machine, path) == reduced for path in HOOKS)
    mark = len(machine.frames)
    q.steps(machine, 10)
    assert any(s[3] == REDUCTION and s[1] & 0x70 == 0x70 for s in token_status(machine, 1, mark))

    qualify(machine, synchronized=failure != "synchronization_lost", rejected=failure == "native_invalid")
    mark = len(machine.frames)
    assert native_torque(machine, hook) == TORQUE_WORD  # Before another CAN task invocation.
    assert machine.get(MODE) == 0 and machine.get(REASON) == 6 and machine.get(TOKEN) == 1
    assert all(native_torque(machine, path) == TORQUE_WORD for path in HOOKS)
    q.steps(machine, 12)
    status = token_status(machine, 1, mark)
    assert status and all(s[3] == 0 for s in status)

    qualify(machine)
    q.send(machine, command(2, 2, REDUCTION, DURATION, 1))
    assert machine.get(MODE) == 0 and machine.get(SEQ) == 1
    q.steps(machine, 400)
    q.arm(machine, token=2)
    return {"failure": failure, "first_hook": hook[2], "zero_status_frames": len(status),
            "previous_refresh_cannot_revive": True, "next_token_accepted": True,
            "max_model_stack_bytes": machine.max_stack}


def refresh_and_cancel(image):
    import test_torque as q
    from torque_patch import HOOKS, MODE, REASON, RX_HI, RX_LO, SEQ, command

    machine = active_machine(image)
    q.send(machine, command(2, 2, REDUCTION, DURATION, 1))
    assert machine.get(MODE) == 1 and machine.get(SEQ) == 2
    receipt = (machine.get(RX_HI), machine.get(RX_LO))
    qualify(machine, rejected=True)
    q.send(machine, command(2, 3, REDUCTION, DURATION, 1))
    assert machine.get(SEQ) == 2 and machine.get(REASON) == 6
    assert (machine.get(RX_HI), machine.get(RX_LO)) == receipt

    for qualified in (True, False):
        machine = active_machine(image)
        mark = len(machine.frames)
        qualify(machine, synchronized=qualified)
        assert machine.inject(0x5E8, command(0, 2, 0, 0, 1))
        for _ in range(8):
            q.steps(machine)
            if machine.get(SEQ) == 2:
                break
        assert machine.get(SEQ) == 2 and machine.get(REASON) == 8
        q.steps(machine, 40)
        assert all(native_torque(machine, hook) == TORQUE_WORD for hook in HOOKS)
        assert machine.get(MODE) == 0
        assert any(s[2] == 2 and s[3] == 0 for s in token_status(machine, 1, mark))
    return {"qualified_refresh": True, "unqualified_refresh_leaves_receipt_unchanged": True,
            "cancel_with_and_without_rpm_permit": True}


def native_startup(image):
    from test_e4m2 import NativeAddressProbe

    rows = []
    for caller, call_pc in ((0x1BC4A, 0x1BC52), (0x1BAA4, 0x1BAAC)):
        for cp in (0xF800, 0xFC00):
            probe = NativeAddressProbe(image, cp)
            probe.set(0, int.from_bytes(image[0x2B4:0x2B6], "little"))
            probe.run(caller, call_pc)
            probe.run(0x18034, 0x18062)
            top = probe.r(0)
            assert top == 0xE7BE
            probe.run(0x18220, 0x1822C)
            assert not any(0xE7C0 <= row[2] < 0xE800 for row in probe.trace if row[1] == "stack_write")
            rows.append({"caller": hex(caller), "register_bank": hex(cp), "r0_top": hex(top)})
    return rows


def paired_dialogues(fixture, image):
    import audit_machine

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lfj8"))
    from verify_h03_torque import dialogue

    seed = audit_machine.seed

    def seed_qualified_rpm(machine, **values):
        seed(machine, **values)
        qualify(machine)

    # The original host scenario models valid numerical RPM only. Seed the
    # now-required native status in the same machine fixture before ECU calls.
    with patch.object(audit_machine, "seed", seed_qualified_rpm):
        return {
            "normal": dialogue(fixture, image, lose_status=False),
            "lost_status": dialogue(fixture, image, lose_status=True),
            "late_status": dialogue(fixture, image, lose_status=True, deliver_at_deadline=True),
        }


def verify(engine, s04, image, *, rx_timestamp=False):
    ordinary, _, _, _ = build(engine, s04, model_fields=True, ordinary_model_field=True,
                                  compact=True, rx_timestamp=rx_timestamp)
    if not rx_timestamp:
        assert digest(ordinary) == ORDINARY_SHA
    exact, manifest, _, _ = build(engine, s04, model_fields=True, ordinary_model_field=True,
                                   compact=True, rb_native_permit=True, rx_timestamp=rx_timestamp)
    assert exact == image
    import build_can_diag as diag
    from torque_patch import HOOKS

    checks = checksum_records(diag, image)
    assert all(record["valid"] for record in checks)
    counts = {}
    allowed = set()
    for name in ("rb_native_permit_hook", "rb_native_permit"):
        region = manifest["regions"][name]
        start = int(region["offset"], 16)
        offsets = range(start, start + region["length"])
        counts[name] = sum(ordinary[p] != image[p] for p in offsets)
        allowed.update(offsets)
    checksum_fields = {p for r in checks for p in range(r["file_offset"] + 8, r["file_offset"] + 16)}
    delta = {p for p, (a, b) in enumerate(zip(ordinary, image, strict=True)) if a != b}
    assert delta <= allowed | checksum_fields
    assert all(counts.values())
    for entry, displaced, _ in HOOKS:
        start = diag.offset(entry)
        stop = start + len(bytes.fromhex(displaced))
        assert image[start:stop] == s04[start:stop]

    revocations = [lose_qualification(image, failure, hook)
                   for failure in ("synchronization_lost", "native_invalid") for hook in HOOKS]
    report = {
        "status": "PASS_OFFLINE_ONLY",
        "base_sha256": digest(s04), "ordinary_sha256": digest(ordinary), "qualified_sha256": digest(image),
        "regions_from_s04": manifest["regions"], "changed_bytes_from_s04": manifest["changed_bytes"],
        "changed_bytes_from_ordinary": len(delta),
        "changed_bytes_per_new_region": counts,
        "changed_checksum_bytes_from_ordinary": len(delta & checksum_fields),
        "checksum_records": len(checks),
        "startup_stack_paths": native_startup(image),
        "unchanged_s04_arbitration_entry_points": {name: hex(cpu) for cpu, _, name in HOOKS},
        "start_admission": start_cases(image),
        "native_revocation": revocations,
        "refresh_cancel": refresh_and_cancel(image),
        "software": manifest["rb_native_permit"],
        "hardware_tested": False,
    }
    if rx_timestamp:
        from verify_rx_timestamp import verify_image

        report["chery_t4_receive"] = verify_image(image, manifest)
    return report


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions")
    cli = argparse.ArgumentParser(description=__doc__)
    for arg in ("engine", "s04", "image"):
        cli.add_argument("--" + arg, type=Path, required=True)
    cli.add_argument("--with-rx-timestamp", action="store_true",
                     help="Verify native T4 RX chronology in the same BIN")
    cli.add_argument("--h03-fixture", type=Path, help="Host executable lfj8_h03_torque_test")
    args = cli.parse_args()
    image = args.image.read_bytes()
    report = verify(args.engine.resolve(), args.s04.read_bytes(), image,
                    rx_timestamp=args.with_rx_timestamp)
    if args.h03_fixture:
        report["paired_host_dialogues"] = paired_dialogues(args.h03_fixture.resolve(), image)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
