import contextlib
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets/lfj8"))
import check_h03_sensor_config as sensor_config


BASE = "a" * 64
PROFILE = {
    "base_sha256": BASE,
    "evidence_id": "synthetic-test",
    "limits": {
        "s51_timeout_ticks": 800,
        "s83_timeout_ticks": 600,
        "atf_max_age_us": 900,
        "max_read_span_ticks": 7,
    },
    "observed_maxima": {
        "s51_period_ticks": 799,
        "s51_age_ticks": 800,
        "s83_period_ticks": 598,
        "s83_age_ticks": 599,
        "atf_age_us": 899,
        "read_span_ticks": 7,
    },
}
CLOCKS = {
    "max_error_ppm": 0,
    "intervals": [{"elapsed_us": 200, "tml0": [2**32 - 100, 100], "tml1": [12, 212]}],
}


class SensorConfigTests(unittest.TestCase):
    def test_profile_preserves_explicit_limits_including_equality(self):
        profile = sensor_config.calibration_evidence(PROFILE, BASE)
        self.assertEqual(profile["limits"], PROFILE["limits"])
        self.assertEqual(profile["observed_maxima"], PROFILE["observed_maxima"])

    def test_each_measurement_is_required_and_bounded(self):
        for field, (_, _, measurements) in sensor_config.CONFIG_FIELDS.items():
            for key in measurements:
                with self.subTest(key=key):
                    profile = deepcopy(PROFILE)
                    del profile["observed_maxima"][key]
                    with self.assertRaises(KeyError):
                        sensor_config.calibration_evidence(profile, BASE)
                    profile["observed_maxima"][key] = profile["limits"][field] + 1
                    with self.assertRaisesRegex(ValueError, "exceeds"):
                        sensor_config.calibration_evidence(profile, BASE)

    def test_rejects_wrong_base_missing_provenance_and_invalid_limits(self):
        for key, value in (("base_sha256", "b" * 64), ("evidence_id", " ")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                sensor_config.calibration_evidence({**PROFILE, key: value}, BASE)
        for field, value in (("s51_timeout_ticks", 0), ("s83_timeout_ticks", 2**31),
                             ("atf_max_age_us", True), ("max_read_span_ticks", 2**16)):
            profile = deepcopy(PROFILE)
            profile["limits"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                sensor_config.calibration_evidence(profile, BASE)

    def run_emit(self, clocks, profile):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            clocks_path = directory / "clocks.json"
            clocks_path.write_text(json.dumps(clocks), encoding="utf-8")
            profile_path = directory / "profile.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            output = directory / "report.json"
            cmd = ["probe", "--base", str(directory / "h03.bin"), "--clock-reference", str(clocks_path),
                   "--calibration-profile", str(profile_path), "--out", str(output), "--emit-config"]
            report = {"base": {"sha256": BASE}, "production_sensor_config": None, "flashable_image": None}
            stdout = io.StringIO()
            with patch.object(sys, "argv", cmd), patch.object(sensor_config, "stock_evidence", return_value=report):
                with contextlib.redirect_stdout(stdout):
                    result = sensor_config.main()
            return result, stdout.getvalue(), json.loads(output.read_text(encoding="utf-8"))

    def test_emits_target_c_and_binds_input_hashes(self):
        status, source, report = self.run_emit(CLOCKS, PROFILE)
        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "PASS_CONFIG_INPUTS")
        self.assertFalse(report["hardware_verified"])
        self.assertIsNone(report["flashable_image"])
        self.assertIn("const Lfj8H03SensorFeedConfig rbm_h03_sensor_config", source)
        for field, limit in PROFILE["limits"].items():
            width = 16 if field == "max_read_span_ticks" else 32
            self.assertIn(f".{field} = UINT{width}_C({limit})", source)
        for data in (CLOCKS, PROFILE):
            self.assertIn(sha256(json.dumps(data).encode()).hexdigest(), source)

    def test_rejects_clock_failure_without_emitting_code(self):
        for channel in ("tml0", "tml1"):
            clocks = deepcopy(CLOCKS)
            clocks["intervals"][0][channel] = [300, 300]
            with self.subTest(channel=channel):
                status, source, report = self.run_emit(clocks, PROFILE)
                self.assertEqual(status, 1)
                self.assertEqual(source, "")
                self.assertIsNone(report["production_sensor_config"])
                self.assertEqual(report["status"], "FAIL_RECORDED_CLOCKS")


if __name__ == "__main__":
    unittest.main()
