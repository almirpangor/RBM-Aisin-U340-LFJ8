import unittest
from fractions import Fraction

from model.chery_1ae import PackerInputs
from model.chery_can import CapturedFrame, Direction, FrameFormat
from model.chery_transport import ReceiveSelection
from model.u340 import (
    Buttons, DriveMode, DriverControls, RelayCommands, ShiftRequest, SpeedCalibration, relay_commands,
)
from model.u340_scenario import DonorSpeedPanelScenario, pack_vss_sample


class U340ScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calibration = SpeedCalibration(1, 2, Fraction(3, 2))
        self.template = PackerInputs(
            byte1=0xFF, byte3_high=0, byte4=0xFF, raw_fa5f=0, raw_fad2=0xFFFF,
            raw_f8e1=0, counter_f8e4=0, flag_f842_5=False, flag_fd18_4=False,
            flag_fd10_7=False, flag_f83e_4=False, flag_e026_0=True,
        )

    def from_vss(self, frequency: Fraction) -> CapturedFrame:
        packed = pack_vss_sample(self.calibration, frequency, self.template)
        return CapturedFrame(arbitration_id=0x1AE, payload=packed.payload, dlc=8,
                             frame_format=FrameFormat.STANDARD_DATA,
                             observed_direction=Direction.TA2005_TO_ECM)

    def test_vss_chery_bosch_calculation_and_driver_inputs(self) -> None:
        controls = DriverControls(starting_mode=DriveMode.AUTO, debounce_ms=5)
        controls.sample(0, Buttons())
        self.assertEqual(relay_commands("R"), RelayCommands(True, True))
        self.assertEqual(relay_commands("L"), RelayCommands(False, True))
        self.assertEqual(relay_commands("D"), RelayCommands(False, False))
        controls.sample(1, Buttons(mode=True))
        self.assertIs(controls.sample(6, Buttons(mode=True)).mode, DriveMode.TIPTRONIC)
        controls.sample(7, Buttons(up=True, overdrive=True))
        request = controls.sample(12, Buttons(up=True, overdrive=True))
        self.assertIs(request.shift, ShiftRequest.UP)
        self.assertTrue(request.overdrive_button_pressed)
        self.assertIsNone(controls.sample(90, Buttons(up=True, overdrive=True)).shift)

        frame = self.from_vss(Fraction(100, 22) * Fraction(6263, 720))
        self.assertEqual(frame.payload[6:], bytes.fromhex("18 77"))
        panel = DonorSpeedPanelScenario(self.calibration)
        reception = panel.receive_tick(frame, exchange_enabled=True, busoff_diagnostic_b254=False)
        self.assertIs(reception.selection, ReceiveSelection.PAYLOAD)
        self.assertEqual(panel.speed_tick().speed_q7, 128)
        for _ in range(62):
            sample = panel.speed_tick()
        self.assertEqual(sample.speed_q7, 8000)
        self.assertEqual(sample.pid_0d, 62)
        self.assertEqual(sample.pulse_hz, Fraction(375, 4))

    def test_stale_speed_ramps_to_zero_and_resumes_after_new_poll(self) -> None:
        frame = self.from_vss(Fraction(100, 22) / 4)
        panel = DonorSpeedPanelScenario(self.calibration)
        panel.receive_tick(frame, exchange_enabled=True, busoff_diagnostic_b254=False)
        panel.speed_tick()
        self.assertEqual(panel.speed_tick().speed_q7, 224)
        for _ in range(32):
            status = panel.receive_tick(None, exchange_enabled=True, busoff_diagnostic_b254=False)
        self.assertIs(status.selection, ReceiveSelection.ENABLED_FALLBACK)
        self.assertEqual(panel.speed_tick().speed_q7, 96)
        self.assertEqual(panel.speed_tick().pulse_hz, 0)

        panel.receive_tick(frame, exchange_enabled=True, busoff_diagnostic_b254=False)
        status = panel.receive_tick(frame, exchange_enabled=True, busoff_diagnostic_b254=False)
        self.assertIs(status.selection, ReceiveSelection.PAYLOAD)
        self.assertEqual(panel.speed_tick().pulse_hz, Fraction(3, 2))

    def test_overflow_is_reserved_and_produces_no_numeric_speed(self) -> None:
        frame = self.from_vss(Fraction(100, 22) * 72)
        self.assertEqual(frame.payload[-2:], b"\xff\xff")
        panel = DonorSpeedPanelScenario(self.calibration)
        panel.receive_tick(frame, exchange_enabled=True, busoff_diagnostic_b254=False)
        self.assertEqual(panel.speed_tick().pulse_hz, 0)
