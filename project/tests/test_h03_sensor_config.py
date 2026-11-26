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
    "intervals": [{
        "elapsed_us": 200,
        "tml0": [2**32 - 2, 198],
        "tml1": [12, 212],
        "tml0_after": [0, 205],
    }],
}


def json_bytes(data):
    return json.dumps(data).encode("utf-8")


CLOCK_HASH = sha256(json_bytes(CLOCKS)).hexdigest()
PROFILE["clock_reference_sha256"] = CLOCK_HASH


class SensorConfigTests(unittest.TestCase):
    def test_profile_preserves_explicit_limits_including_equality(self):
        profile = sensor_config.calibration_evidence(PROFILE, BASE, CLOCK_HASH)
        self.assertEqual(profile["limits"], PROFILE["limits"])
        self.assertEqual(profile["observed_maxima"], PROFILE["observed_maxima"])

    def test_each_measurement_is_required_and_bounded(self):
        for field, (_, _, measurements) in sensor_config.CONFIG_FIELDS.items():
            for key in measurements:
                with self.subTest(key=key):
                    profile = deepcopy(PROFILE)
                    del profile["observed_maxima"][key]
                    with self.assertRaises(KeyError):
                        sensor_config.calibration_evidence(profile, BASE, CLOCK_HASH)
                    profile["observed_maxima"][key] = profile["limits"][field] + 1
                    with self.assertRaisesRegex(ValueError, "exceeds"):
                        sensor_config.calibration_evidence(profile, BASE, CLOCK_HASH)

    def test_rejects_wrong_base_missing_provenance_and_invalid_limits(self):
        for key, value in (("base_sha256", "b" * 64), ("clock_reference_sha256", "0" * 64),
                           ("evidence_id", " ")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                sensor_config.calibration_evidence({**PROFILE, key: value}, BASE, CLOCK_HASH)
        for field, value in (("s51_timeout_ticks", 0), ("s83_timeout_ticks", 2**31),
                             ("atf_max_age_us", True), ("max_read_span_ticks", 2**16)):
            profile = deepcopy(PROFILE)
            profile["limits"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                sensor_config.calibration_evidence(profile, BASE, CLOCK_HASH)

    def run_emit(self, clocks, profile=PROFILE, *, bind_clock=True):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            clocks_path = directory / "clocks.json"
            clocks_path.write_bytes(json_bytes(clocks))
            if bind_clock:
                profile = {**profile, "clock_reference_sha256": sha256(clocks_path.read_bytes()).hexdigest()}
            profile_path = directory / "profile.json"
            profile_path.write_bytes(json_bytes(profile))
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
        self.assertIn("int rbm_h03_target_clock_ready(void *context)", source)
        self.assertIn("return lfj8_h03_sensor_clock_registers_match();", source)
        for field, limit in PROFILE["limits"].items():
            width = 16 if field == "max_read_span_ticks" else 32
            self.assertIn(f".{field} = UINT{width}_C({limit})", source)
        self.assertIn(CLOCK_HASH, source)
        self.assertIn(sha256(json_bytes(PROFILE)).hexdigest(), source)
        self.assertEqual(report["paired_alignment"]["intervals"], [{
            "start_span_ticks": 2, "end_span_ticks": 7, "elapsed_difference_ticks": 0, "passed": True,
        }])

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


    def test_pair_uses_asymmetric_read_brackets_even_within_ppm_limit(self):
        for difference, allowed in ((-3, False), (-2, True), (7, True), (8, False)):
            with self.subTest(difference=difference):
                clocks = deepcopy(CLOCKS)
                clocks["max_error_ppm"] = 40000
                clocks["intervals"][0]["tml1"][1] += difference
                status, source, report = self.run_emit(clocks)
                self.assertTrue(report["clock_reference"]["passed"])
                self.assertEqual(report["paired_alignment"]["passed"], allowed)
                self.assertEqual(report["paired_alignment"]["intervals"][0]["elapsed_difference_ticks"], difference)
                self.assertEqual(bool(source), allowed)
                self.assertEqual(status, int(not allowed))

    def test_bracket_must_be_bounded_by_recorded_maximum(self):
        clocks = deepcopy(CLOCKS)
        clocks["intervals"][0]["tml0_after"][1] += 1
        profile = deepcopy(PROFILE)
        profile["limits"]["max_read_span_ticks"] = 8
        status, source, report = self.run_emit(clocks, profile)
        self.assertEqual(status, 1)
        self.assertEqual(source, "")
        self.assertFalse(report["paired_alignment"]["passed"])
        self.assertIsNone(report["production_sensor_config"])

    def test_profile_rejects_a_different_clock_reference(self):
        clocks = deepcopy(CLOCKS)
        clocks["intervals"][0]["tml1"] = [13, 213]
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            self.run_emit(clocks, bind_clock=False)
        self.assertEqual(error.exception.code, 2)
        self.assertIn("supplied clock reference by SHA-256", stderr.getvalue())

    def test_missing_read_brackets_allow_audit_only(self):
        clocks = deepcopy(CLOCKS)
        del clocks["intervals"][0]["tml0_after"]
        self.assertTrue(sensor_config.paired_clock_evidence(clocks)["passed"])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            self.run_emit(clocks)
        self.assertEqual(error.exception.code, 2)
        self.assertIn("must include tml0_after", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
