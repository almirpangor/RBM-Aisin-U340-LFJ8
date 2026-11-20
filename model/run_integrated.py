"""Compile and run the portable C controller and LFJ8 bridge through the offline model."""

import argparse
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from .chery_can import CapturedFrame, DecodeStatus, Direction, FrameFormat, decode_chery_frame
from .chery_transport import ReceiveSelection
from .u340 import SpeedCalibration
from .u340_scenario import DonorSpeedPanelScenario


ROOT = Path(__file__).resolve().parent.parent


def run_c_scenario(compiler: str, engine_vectors: tuple[str, ...] = ()) -> dict:
    resolved = shutil.which(compiler)
    if resolved is None:
        raise ValueError(f"Compiler not found: {compiler}")
    driver = [resolved, "cc"] if Path(resolved).stem.casefold() == "zig" else [resolved]
    controller = ROOT / "controller"
    toyota = controller / "vendor" / "toyota"
    lfj8 = ROOT / "targets" / "lfj8"
    panel = ROOT / "targets" / "panel"
    manifest = json.loads((toyota / "manifest.json").read_text(encoding="utf-8"))
    sources = [str(toyota / entry["path"]) for entry in manifest["files"] if entry["path"].endswith(".c")]
    with TemporaryDirectory(prefix="u340-host-scenario-") as temp:
        exe = Path(temp) / ("u340_integration.exe" if sys.platform == "win32" else "u340_integration")
        command = [
            *driver, "-std=c11", "-O2", "-UNDEBUG", "-Wall", "-Wextra", "-Werror",
            "-I", str(controller / "include"), "-I", str(toyota / "include"),
            "-I", str(lfj8), "-I", str(panel),
            str(controller / "src" / "rbm_u340e.c"), *sources, str(lfj8 / "lfj8_bridge.c"),
            str(lfj8 / "ta2005_chery_inputs.c"), str(lfj8 / "lfj8_selector_adc.c"),
            str(lfj8 / "lfj8_range_control.c"),
            str(lfj8 / "test_lfj8_selector_adc.c"),
            str(panel / "panel_pulse.c"), str(ROOT / "tests" / "u340_integration_host.c"),
            "-o", str(exe),
        ]
        subprocess.run(command, check=True)
        return json.loads(subprocess.check_output([str(exe), *engine_vectors], text=True))


def frame_from_c(frame_id: int, payload_hex: str) -> CapturedFrame:
    return CapturedFrame(arbitration_id=frame_id, payload=bytes.fromhex(payload_hex), dlc=8,
                         frame_format=FrameFormat.STANDARD_DATA,
                         observed_direction=Direction.TA2005_TO_ECM)


def run_bosch_candidate(engine: Path, s04: Path, image: Path, frame: str) -> dict:
    command = [
        sys.executable, "-B", str(ROOT / "targets" / "bosch" / "verify.py"),
        "--engine", str(engine), "--s04", str(s04), "--image", str(image), "--frame", frame,
    ]
    return json.loads(subprocess.check_output(command, text=True))


def run(compiler: str, bosch: tuple[Path, Path, Path] | None = None,
        bosch_tx: tuple[Path, Path] | None = None) -> dict:
    engine_vectors = ()
    if bosch_tx is not None:
        tx_image, verification = bosch_tx
        tx_report = json.loads(verification.read_text(encoding="utf-8"))
        tx_sha = sha256(tx_image.read_bytes()).hexdigest()
        if tx_report["status"] != "PASS_OFFLINE_ONLY" or tx_sha != tx_report["sha256"]:
            raise ValueError("The Bosch TX report does not match the supplied candidate")
        by_id = {int(item["can_id"], 16): bytes.fromhex(item["payload_hex"])
                 for item in tx_report["wire_vectors"]}
        if set(by_id) != {0x0FA, 0x278} or any(len(frame) != 8 for frame in by_id.values()):
            raise ValueError("The Bosch TX report must contain both eight-byte engine frames")
        engine_vectors = (by_id[0x0FA].hex(), by_id[0x278].hex())
    host = run_c_scenario(compiler, engine_vectors)
    speed_frame = frame_from_c(0x1AE, host["0x1AE"])
    speed = decode_chery_frame(speed_frame)
    if speed.status is not DecodeStatus.DECODED or speed.reading is None or speed.fields_1ae is None:
        raise RuntimeError("C 0x1AE could not be decoded")
    if not speed.fields_1ae.checksum_matches or speed.reading.value != Fraction(72, 5):
        raise RuntimeError("C 0x1AE differs from the expected 14.40 km/h and checksum")
    atf = decode_chery_frame(frame_from_c(0x300, host["0x300"]))
    if atf.status is not DecodeStatus.DECODED or atf.reading is None or atf.reading.value != 84:
        raise RuntimeError("C 0x300 differs from the expected 84 °C")

    scenario = DonorSpeedPanelScenario(SpeedCalibration(1, 2, Fraction(5, 3)))
    reception = scenario.receive_tick(speed_frame, exchange_enabled=True, busoff_diagnostic_b254=False)
    if reception.selection is not ReceiveSelection.PAYLOAD:
        raise RuntimeError("The S02 receiver model did not select the new frame")
    for _ in range(15):
        panel = scenario.speed_tick()
    if (panel.speed_q7, panel.pid_0d, panel.pulse_hz) != (1824, 14, Fraction(95, 4)):
        raise RuntimeError("The offline speed/panel chain deviates from the expected result")
    if host["panel_input_speed_q7"] != panel.speed_q7:
        raise RuntimeError("The C panel scenario did not use the S02 reference speed")
    report = {
        "status": "PASS_OFFLINE_ONLY",
        "host_controller_and_lfj8": host,
        "speed_kmh_wire": str(speed.reading.value),
        "atf_c": str(atf.reading.value),
        "s02_model_speed_q7": panel.speed_q7,
        "s02_model_pid_0d": panel.pid_0d,
        "panel_pulse_hz_calculated": str(panel.pulse_hz),
        "panel_nominal_pulses_per_km": 6000,
        "equipment_tested": False,
    }
    if bosch is not None:
        probe = run_bosch_candidate(*bosch, host["0x1AE"])
        if probe["frame"] != speed_frame.payload.hex() or not probe["accepted_speed"]:
            raise RuntimeError("The Bosch ST10 model did not accept the frame produced by the LFJ8 C bridge")
        if probe["speed_q7"] != panel.speed_q7:
            raise RuntimeError("The Bosch ST10 speed and the S02 reference scale disagree")
        report["bosch_candidate_frame_probe"] = probe
    if bosch_tx is not None:
        report["bosch_tx_to_tcm"] = {
            "sha256": tx_sha,
            "0x0FA": engine_vectors[0],
            "0x278": engine_vectors[1],
            "rpm": host["tc_rx_rpm_q3"] // 8,
            "coolant_celsius": host["tc_rx_coolant_plus_50"] - 50,
        }
        if bosch is not None:
            report["same_bosch_image_both_directions"] = probe["sha256"] == tx_sha
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="zig", help="Zig, GCC or Clang compiler executable")
    parser.add_argument("--bosch-engine", type=Path, help="Path to the pinned engine tooling tree")
    parser.add_argument("--bosch-s04", type=Path, help="Path to the unmodified S04 binary")
    parser.add_argument("--bosch-image", type=Path, help="Path to the emitted Bosch candidate to probe")
    parser.add_argument("--bosch-tx-image", type=Path, help="Path to the Bosch RPM/ECT candidate")
    parser.add_argument("--bosch-tx-report", type=Path, help="Machine-executed Bosch RPM/ECT vectors")
    args = parser.parse_args()
    inputs = (args.bosch_engine, args.bosch_s04, args.bosch_image)
    if any(inputs) and not all(inputs):
        parser.error("Provide all three Bosch paths for the ST10 model probe")
    tx_inputs = (args.bosch_tx_image, args.bosch_tx_report)
    if any(tx_inputs) and not all(tx_inputs):
        parser.error("Provide both the Bosch TX image and its verification report")
    print(json.dumps(run(args.cc, inputs if all(inputs) else None,
                         tx_inputs if all(tx_inputs) else None), indent=2))


if __name__ == "__main__":
    main()
