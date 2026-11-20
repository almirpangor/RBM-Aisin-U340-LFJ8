"""Replay the recorded E4G4 requests on the exact Bosch RX/TX candidate in ST10."""

import argparse
from collections import deque
import gzip
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build import build, digest
from verify import SPEED_PHYS


R4 = "dc6b4f08a24e648d3d0dab986c1765abb6fd294a"
ENGINE_PATH = "development/E4M3/engine"
TRACE = "development/E4R4/evidence/E4M3_G4_BENCH_TEST2_20261014/input_trace.trc.gz"
TRACE_SHA = "aa0580a56bcad633406595a7ad98e7d7043d6d6dd762121d3922fe28c1e0353f"


def recorded_requests(repo, crc8):
    data = gzip.decompress(subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repo), "show", f"{R4}:{TRACE}"],
    ))
    if digest(data) != TRACE_SHA:
        raise ValueError("Different bench trace")
    commands = deque()
    responses = []
    previous = minute_us = checked = 0
    for line in data.decode("latin1").split("\r"):
        fields = line.split("\t")
        if len(fields) < 6:
            continue
        seconds, micros = fields[0].split(",")
        tick = int(seconds) * 1_000_000 + int(micros)
        if tick < previous:
            minute_us += 60_000_000
        previous = tick
        if fields[3] not in ("5E8", "5E9"):
            continue
        payload = bytes.fromhex(fields[5])
        assert len(payload) == int(fields[4]) == 8 and crc8(payload[:7]) == payload[7]
        checked += 1
        if fields[3] == "5E8":
            commands.append((minute_us + tick, payload))
        else:
            responses.append((minute_us + tick, payload))
    assert checked == 3256 and commands
    timings = []
    for start, request in commands:
        if request[1] != 1:
            continue
        replies = [(t, s) for t, s in responses if t >= start and s[4:6] == request[5:7]]
        ack = next(t for t, s in replies if s[2] == request[2] and s[3] > 0)
        full = next(t for t, s in replies if s[3] == request[3] and s[1] & 0x70 == 0x70)
        zero = next(t for t, s in replies if t > full and s[3] == 0)
        assert all(s[6] != 6 and (t < zero or s[3] == 0) for t, s in replies)
        timings.append([(t - start) // 1000 for t in (ack, full, zero)])
    assert timings == [[8, 28, 268], [8, 28, 269]]
    return commands, checked, timings


def replay(repo, image):
    # Run the trace and ST10 tools from the same immutable R4 input.
    with TemporaryDirectory(prefix="rbm-e4m3-replay-") as directory:
        workspace = Path(directory).resolve()
        archive = workspace / "engine.zip"
        subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), "archive",
             "--format=zip", "-o", str(archive), R4, ENGINE_PATH],
            check=True,
        )
        with ZipFile(archive) as bundle:
            bundle.extractall(workspace)
        return replay_with_engine(repo, workspace / ENGINE_PATH, image)


def replay_with_engine(repo, engine, image):
    base = (engine / "firmware/GW4G15_REV8_CAN_TORQUE_E4_BENCH.bin").read_bytes()
    rebuilt, manifest, _, _ = build(engine, base, with_engine_signals_tx=True)
    if rebuilt != image:
        rebuilt, manifest, _, _ = build(engine, base, model_fields=True, compact=True)
    if rebuilt != image:
        for ordinary_compact in (True, False):
            rebuilt, manifest, _, _ = build(engine, base, model_fields=True, compact=ordinary_compact,
                                            ordinary_model_field=True)
            if rebuilt == image:
                break
    if rebuilt != image:
        raise ValueError("Image differs from the exact RX/TX build")
    from audit_machine import Machine, seed
    import test_torque as q
    import torque_patch as tq

    commands, checked, timings = recorded_requests(repo, tq.crc8)
    count = len(commands)
    first, last = commands[0][0], commands[-1][0]
    m = Machine(image)
    m.native_writes.add(SPEED_PHYS)
    seed(m, rpm4=8000)
    m.poke(0xFF44, 0x46)
    # Fixed simulated engine inputs; execute one background call every 2 ms.
    # Feed the recorded bytes on the first service tick at or after their time.
    seen = {1: [], 2: []}
    for elapsed in range(-400_000, last - first + 1_000_000, 2000):
        q.clock(m, (elapsed + 400_000) * 5 // 64)
        while commands and commands[0][0] <= first + elapsed:
            _, payload = commands.popleft()
            assert m.inject(0x5E8, payload)
        frame_index = len(m.frames)
        m.run()
        if m.get(tq.MODE):
            for hook, reg in (("hook_air", 9), ("hook_fast", 7), ("hook_load", 9)):
                m.reg[reg] = 20000
                m.run(q.LABELS[hook])
        for frame in m.frames[frame_index:]:
            if frame["id"] != 0x5E9:
                continue
            status = bytes.fromhex(frame["data"])
            assert tq.crc8(status[:7]) == status[7]
            token = int.from_bytes(status[4:6], "little")
            if token in seen:
                seen[token].append(status)
    assert not commands and m.get(tq.MODE) == 0
    for statuses in seen.values():
        assert any(s[3] == 32 and s[1] & 0x70 == 0x70 for s in statuses)
        assert statuses[-1][3] == 0 and all(s[6] != 6 for s in statuses)
    return {"r4_commit": R4, "trace_sha256": TRACE_SHA, "bosch_sha256": manifest["sha256"],
            "bench_frames_crc_checked": checked, "recorded_commands_replayed": count,
            "bench_ack_full_zero_ms": timings,
            "tokens_reaching_q8_32_mask_7_then_zero": list(seen),
            "model_bus": "RB 0x5E8/0x5E9", "current_pair_hardware_tested": False}


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Enable assertions for this verification")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.repo, args.image.read_bytes()), indent=2))
