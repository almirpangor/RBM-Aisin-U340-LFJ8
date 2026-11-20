import unittest
from fractions import Fraction

from model.u340 import (
    VSS_PULSES_PER_DIFFERENTIAL_REV,
    Buttons,
    DriveMode,
    DriverControls,
    RelayCommands,
    ShiftRequest,
    SpeedCalibration,
    SpeedEstimate,
    relay_commands,
)


class RelayTests(unittest.TestCase):
    def test_selector_positions(self) -> None:
        expected = {
            "P": RelayCommands(False, False),
            "R": RelayCommands(True, True),
            "N": RelayCommands(False, False),
            "D": RelayCommands(False, False),
            "2": RelayCommands(False, False),
            "L": RelayCommands(False, True),
            "UNKNOWN": RelayCommands(False, False),
        }
        for selector, commands in expected.items():
            with self.subTest(selector=selector):
                self.assertEqual(relay_commands(selector), commands)


class SpeedTests(unittest.TestCase):
    def test_vss_ratio_is_exact(self) -> None:
        self.assertEqual(VSS_PULSES_PER_DIFFERENTIAL_REV, Fraction(100, 22))
        calibration = SpeedCalibration(2, Fraction(5, 2), Fraction(3, 2))
        self.assertEqual(calibration.estimate(Fraction(100, 22)), SpeedEstimate(18, 27))
        self.assertEqual(calibration.estimate(0), SpeedEstimate(0, 0))

    def test_panel_coefficient_changes_panel_frequency_only(self) -> None:
        circumference = Fraction("2.115")
        base = SpeedCalibration(1, circumference, Fraction("1.1")).estimate(10)
        corrected = SpeedCalibration(1, circumference, Fraction("2.2")).estimate(10)
        self.assertEqual(base.vehicle_kmh, corrected.vehicle_kmh)
        self.assertEqual(corrected.panel_hz, base.panel_hz * 2)

    def test_rejects_missing_or_nonphysical_input(self) -> None:
        with self.assertRaises(ValueError):
            SpeedCalibration(1, 0, 1)
        with self.assertRaises(ValueError):
            SpeedCalibration(1, Fraction("2.3"), -1)
        with self.assertRaises(ValueError):
            SpeedCalibration(1, 2, 1).estimate(-1)


class ControlsTests(unittest.TestCase):
    def test_one_transition_per_press_with_bounce_and_hold(self) -> None:
        controls = DriverControls(starting_mode=DriveMode.AUTO, debounce_ms=10)
        self.assertEqual(controls.sample(0, Buttons()).mode, DriveMode.AUTO)
        self.assertEqual(controls.sample(1, Buttons(mode=True)).mode, DriveMode.AUTO)
        self.assertEqual(controls.sample(2, Buttons()).mode, DriveMode.AUTO)
        self.assertEqual(controls.sample(3, Buttons(mode=True)).mode, DriveMode.AUTO)
        self.assertEqual(controls.sample(12, Buttons(mode=True)).mode, DriveMode.AUTO)
        self.assertEqual(controls.sample(13, Buttons(mode=True)).mode, DriveMode.TIPTRONIC)
        self.assertEqual(controls.sample(300, Buttons(mode=True)).mode, DriveMode.TIPTRONIC)
        self.assertEqual(controls.sample(310, Buttons()).mode, DriveMode.TIPTRONIC)
        self.assertEqual(controls.sample(320, Buttons()).mode, DriveMode.TIPTRONIC)
        self.assertEqual(controls.sample(321, Buttons(mode=True)).mode, DriveMode.TIPTRONIC)
        self.assertEqual(controls.sample(331, Buttons(mode=True)).mode, DriveMode.AUTO)

    def test_up_down_in_tiptronic_and_only_on_a_press(self) -> None:
        controls = DriverControls(starting_mode=DriveMode.TIPTRONIC, debounce_ms=0)
        controls.sample(0, Buttons())
        self.assertEqual(controls.sample(1, Buttons(up=True)).shift, ShiftRequest.UP)
        self.assertIsNone(controls.sample(2, Buttons(up=True)).shift)
        self.assertEqual(controls.sample(3, Buttons(down=True)).shift, ShiftRequest.DOWN)
        self.assertIsNone(controls.sample(4, Buttons(down=True)).shift)
        controls.sample(5, Buttons(mode=True))
        self.assertIsNone(controls.sample(6, Buttons(up=True)).shift)

    def test_overdrive_press_is_reported_once(self) -> None:
        controls = DriverControls(starting_mode=DriveMode.AUTO, debounce_ms=2)
        controls.sample(0, Buttons())
        self.assertFalse(controls.sample(1, Buttons(overdrive=True)).overdrive_button_pressed)
        self.assertTrue(controls.sample(3, Buttons(overdrive=True)).overdrive_button_pressed)
        self.assertFalse(controls.sample(40, Buttons(overdrive=True)).overdrive_button_pressed)

    def test_first_sample_defines_button_baseline(self) -> None:
        controls = DriverControls(starting_mode=DriveMode.TIPTRONIC, debounce_ms=0)
        self.assertEqual(controls.sample(0, Buttons(mode=True)).mode, DriveMode.TIPTRONIC)
        self.assertEqual(controls.sample(1, Buttons(mode=True)).mode, DriveMode.TIPTRONIC)
        controls.sample(2, Buttons())
        self.assertEqual(controls.sample(3, Buttons(mode=True)).mode, DriveMode.AUTO)

    def test_simultaneous_shift_inputs_are_marked_ambiguous(self) -> None:
        controls = DriverControls(starting_mode=DriveMode.TIPTRONIC, debounce_ms=0)
        controls.sample(0, Buttons())
        conflicting = controls.sample(1, Buttons(up=True, down=True))
        self.assertTrue(conflicting.simultaneous_shift_inputs)
        self.assertIsNone(conflicting.shift)
        controls.sample(2, Buttons())
        conflicting = controls.sample(3, Buttons(mode=True, up=True))
        self.assertTrue(conflicting.simultaneous_shift_inputs)
        self.assertIsNone(conflicting.shift)
        self.assertEqual(conflicting.mode, DriveMode.AUTO)

    def test_time_cannot_run_backwards(self) -> None:
        controls = DriverControls(starting_mode=DriveMode.AUTO, debounce_ms=0)
        controls.sample(10, Buttons())
        with self.assertRaises(ValueError):
            controls.sample(9, Buttons())


if __name__ == "__main__":
    unittest.main()
