"""Run the H03 C torque requester against the archived Bosch E4M3 ST10 code."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bosch"))
from build import build, digest
from verify import SPEED_PHYS


def dialogue(fixture, image, lose_status):
    from audit_machine import Machine, seed
    import test_torque as q
    import torque_patch as tq

    machine = Machine(image)
    machine.native_writes.add(SPEED_PHYS)
    seed(machine, rpm4=8000)
    machine.poke(0xFF44, 0x46)
    incoming = "-"
    applied_at = None
    commands, statuses = [], []
    with subprocess.Popen([str(fixture), "--bosch"], text=True, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as process:
        for now_us in range(0, 900_000, 2000):
            q.clock(machine, now_us * 5 // 64)
            allow_status = not lose_status or now_us <= 400_000 or now_us >= 650_000
            process.stdin.write(f"{now_us} {incoming if allow_status else '-'}\n")
            process.stdin.flush()
            tx_hex, phase, applied = process.stdout.readline().split()
            if int(applied) and applied_at is None:
                applied_at = now_us
            if tx_hex != "-":
                request = bytes.fromhex(tx_hex)
                assert tq.crc8(request[:7]) == request[7]
                assert machine.inject(0x5E8, request)
                commands.append((now_us, request))
            frame_count = len(machine.frames)
            machine.run()
            if machine.get(tq.MODE):
                for hook, reg in (("hook_air", 9), ("hook_fast", 7), ("hook_load", 9)):
                    machine.reg[reg] = 20_000
                    machine.run(q.LABELS[hook])
            incoming = "-"
            for frame in machine.frames[frame_count:]:
                if frame["id"] == 0x5E9:
                    incoming = frame["data"]
                    status = bytes.fromhex(incoming)
                    assert tq.crc8(status[:7]) == status[7]
                    if status[4:6] == b"\x01\x00":
                        statuses.append((now_us, status))
        process.stdin.close()
        assert process.wait(timeout=10) == 0

    assert commands[0] == (400_000, bytes.fromhex("a401012014010099"))
    assert sum(frame[1] == 1 for _, frame in commands) == 1
    assert all(frame[5:7] == b"\x01\x00" for _, frame in commands)
    assert statuses[-1][1][3] == 0 and machine.get(tq.MODE) == 0
    first_cancel = next(t for t, frame in commands if frame[1] == 0)
    refreshed = sum(frame[1] == 2 for _, frame in commands)
    cancel_sequences = {frame[2] for _, frame in commands if frame[1] == 0}
    released_at = next(t for t, status in statuses if t >= first_cancel and not status[3]
                       and status[2] in cancel_sequences and (status[1] & 15) in (0, 4))
    if lose_status:
        assert applied_at is None and int(phase) == 5 and not refreshed and first_cancel == 460_000
    else:
        assert applied_at is not None and int(phase) == 4 and refreshed and first_cancel == 520_000
        assert any(st[3] == 32 and st[1] & 0x70 == 0x70 for _, st in statuses)
    return {"can_commands": len(commands), "status_frames_for_token": len(statuses),
            "start_us": commands[0][0], "full_reduction_confirmed_us": applied_at,
            "first_cancel_us": first_cancel, "engine_status_confirmed_zero_us": released_at,
            "refresh_commands": refreshed, "terminal_state": "failed" if lose_status else "complete"}


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions for this verification")
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--repo", required=True, type=Path, help="Repository R4 checkout")
    cli.add_argument("--image", required=True, type=Path, help="Archived compact Bosch offline image")
    cli.add_argument("--fixture", required=True, type=Path, help="Compiled host test_lfj8_h03_torque executable")
    args = cli.parse_args()
    engine = (args.repo / "development/E4M3/engine").resolve()
    base = (engine / "firmware/GW4G15_REV8_CAN_TORQUE_E4_BENCH.bin").read_bytes()
    image = args.image.read_bytes()
    rebuilt, _, _, _ = build(engine, base, model_fields=True, compact=True)
    if rebuilt != image:
        raise ValueError("The Bosch image does not match the compact rebuild")
    print(json.dumps({"status": "PASS_OFFLINE_ONLY", "bosch_sha256": digest(image),
                      "source": "Toyota torque stage GP-4833.4, GP-4520, GP-9660",
                      "fixture_profile_q8": 32, "fixture_profile_duration_ms": 200,
                      "normal": dialogue(args.fixture.resolve(), image, lose_status=False),
                      "lost_status": dialogue(args.fixture.resolve(), image, lose_status=True),
                      "current_pair_hardware_tested": False}, indent=2))


if __name__ == "__main__":
    main()
