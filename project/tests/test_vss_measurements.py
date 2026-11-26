import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from tools.check_vss_measurements import evaluate


def fixture():
    profile = {
        "tick_hz": 1_000_000, "vss_timeout_ticks": 30_000,
        "wheel_um": 2_000_000, "wheel_num": 1, "wheel_den": 1,
        "max_error_centi_kmh": 0,
    }
    moving = {
        "case": "moving", "interval_ticks": 26_400, "age_ticks": 30_000,
        "stopped_confirmed": False, "reference_distance_um": 1_000_000,
        "reference_duration_us": 60_000, "payload_1ae": "0832133935001770",
    }
    standstill = dict(
        moving, case="standstill", interval_ticks=None, age_ticks=None,
        stopped_confirmed=True, reference_distance_um=0, payload_1ae="0832133935000000",
    )
    loss = dict(moving, case="signal_loss", age_ticks=30_001, payload_1ae="083213393500ffff")
    return {"profile": profile, "samples": [moving, standstill, loss]}


class VssMeasurementsTests(unittest.TestCase):
    def test_three_independent_cases(self):
        report = evaluate(fixture())
        self.assertEqual(report["status"], "PASS_OFFLINE_ONLY")
        self.assertIsNone(report["clock_reference"])
        self.assertEqual([row["expected_raw"] for row in report["samples"]], [6000, 0, 0xFFFF])
        self.assertEqual([row["reference_kmh"] for row in report["samples"]], ["60", "0", "60"])
        self.assertEqual([row["capture_valid"] for row in report["samples"]], [True, False, False])

    def test_zero_speed_cannot_pass_as_signal_loss(self):
        data = fixture()
        data["samples"][2]["payload_1ae"] = "0832133935000000"
        self.assertEqual(evaluate(data)["status"], "FAIL")
        data["samples"][2]["stopped_confirmed"] = True
        self.assertEqual(evaluate(data)["status"], "FAIL")

    def test_frame_checksum_and_length_checked(self):
        data = fixture()
        data["samples"][0]["payload_1ae"] = "0932133935001770"
        report = evaluate(data)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("checksum", report["samples"][0]["problems"][0])
        data["samples"][0]["payload_1ae"] = "1770"
        with self.assertRaisesRegex(ValueError, "sample 1.*payload_1ae"):
            evaluate(data)

    def test_missing_cases_cannot_pass(self):
        data = fixture()
        data["samples"].pop()
        report = evaluate(data)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["missing_cases"], ["signal_loss"])

    def test_fractional_error_uses_independent_reference(self):
        data = fixture()
        data["samples"][0]["reference_distance_um"] += 100
        report = evaluate(data)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["samples"][0]["error_kmh"], "3/500")
        data["profile"]["max_error_centi_kmh"] = 1
        self.assertEqual(evaluate(data)["status"], "PASS_OFFLINE_ONLY")

    def test_moving_capture_must_be_fresh_and_in_range(self):
        for change in ({"age_ticks": 30_001}, {"interval_ticks": 30_001}, {"interval_ticks": 1}):
            data = fixture()
            data["samples"][0].update(change, payload_1ae="083213393500ffff")
            with self.subTest(change=change):
                report = evaluate(data)
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(report["samples"][0]["expected_raw"], 0xFFFF)

    def test_malformed_profile_and_capture_rejected(self):
        for field, value in (("wheel_den", 0), ("tick_hz", True), ("wheel_num", 65536)):
            data = fixture()
            data["profile"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                evaluate(data)
        data = fixture()
        data["samples"][0]["age_ticks"] = None
        with self.assertRaisesRegex(ValueError, "sample 1.*age_ticks"):
            evaluate(data)

    def test_clock_check_recovers_rollover_and_accepts_exact_tolerance(self):
        data = fixture()
        data["clock_reference"] = {
            "max_error_ppm": 10,
            "intervals": [
                {"start_ticks": 0xFFFF0000, "end_ticks": 34464, "elapsed_us": 100000},
                {"start_ticks": 3000, "end_ticks": 103001, "elapsed_us": 100000},
            ],
        }
        report = evaluate(data)
        self.assertEqual(report["status"], "PASS_OFFLINE_ONLY")
        intervals = report["clock_reference"]["intervals"]
        self.assertEqual([row["measured_hz"] for row in intervals], ["1000000", "1000010"])
        self.assertEqual([row["error_ppm"] for row in intervals], ["0", "10"])

    def test_clock_check_rejects_wrong_and_stalled_clock(self):
        data = fixture()
        data["clock_reference"] = {
            "max_error_ppm": 100,
            "intervals": [
                {"start_ticks": 1000, "end_ticks": 51000, "elapsed_us": 100000},
                {"start_ticks": 10, "end_ticks": 10, "elapsed_us": 100000},
            ],
        }
        report = evaluate(data)
        self.assertEqual(report["status"], "FAIL")
        clock = report["clock_reference"]
        self.assertFalse(clock["passed"])
        self.assertEqual([row["measured_hz"] for row in clock["intervals"]], ["500000", "0"])
        self.assertTrue(all(not row["problems"] for row in report["samples"]))

    def test_clock_check_rejects_ambiguous_duration_and_empty_reference(self):
        data = fixture()
        data["clock_reference"] = {
            "max_error_ppm": 0,
            "intervals": [
                {"start_ticks": 0, "end_ticks": 1, "elapsed_us": 1 << 32},
            ],
        }
        with self.assertRaisesRegex(ValueError, "full TML0 revolution"):
            evaluate(data)
        data["clock_reference"]["intervals"] = []
        with self.assertRaisesRegex(ValueError, "nonempty array"):
            evaluate(data)
    def test_cli_exit_codes_and_json_report(self):
        data = fixture()
        failed = copy.deepcopy(data)
        failed["samples"][2]["payload_1ae"] = "0832133935000000"
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temp:
            measurements = Path(temp) / "trace.json"
            for sample, expected in ((data, 0), (failed, 1), ({}, 2)):
                with self.subTest(returncode=expected):
                    measurements.write_text(json.dumps(sample), encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, "-B", "-m", "tools.check_vss_measurements", str(measurements)],
                        cwd=root, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)
                    if expected != 2:
                        self.assertEqual(json.loads(result.stdout)["status"],
                                         "PASS_OFFLINE_ONLY" if expected == 0 else "FAIL")
