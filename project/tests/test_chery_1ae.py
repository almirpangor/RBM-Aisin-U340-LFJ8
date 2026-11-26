import unittest
from dataclasses import replace
from fractions import Fraction

from model.chery_1ae import PackerInputs, encode_1ae_vehicle_speed, pack_1ae_payload, parse_1ae_payload
from model.chery_can import CapturedFrame, Direction, FrameFormat, decode_chery_frame
from model.u340 import SpeedCalibration


class Chery1AETests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = PackerInputs(
            byte1=50,
            byte3_high=0xA,
            byte4=50,
            raw_fa5f=126,
            raw_fad2=0x1234,
            raw_f8e1=0xFE,
            counter_f8e4=6,
            flag_f842_5=True,
            flag_fd18_4=True,
            flag_fd10_7=True,
            flag_f83e_4=True,
            flag_e026_0=False,
        )

    def test_native_packer_layout_and_field_boundaries(self) -> None:
        packed = pack_1ae_payload(self.inputs)
        self.assertEqual(packed.payload, bytes.fromhex("1B 32 FB A9 32 FC 12 34"))
        self.assertEqual(packed.next_counter_f8e4, 7)
        fields = parse_1ae_payload(packed.payload)
        self.assertEqual(fields.byte0_bits7_5, 0)
        self.assertTrue(fields.flag_f842_5)
        self.assertEqual((fields.checksum_high, fields.checksum_low), (9, 11))
        self.assertTrue(fields.checksum_matches)
        self.assertEqual(fields.byte1, 50)
        self.assertTrue(fields.flag_fd18_4)
        self.assertTrue(fields.flag_fd10_7)
        self.assertEqual(fields.f8e1_low_two_bits, 2)
        self.assertEqual(fields.counter_low_three_bits, 7)
        self.assertTrue(fields.flag_f83e_4)
        self.assertEqual(fields.byte3_high, 0xA)
        self.assertEqual(fields.byte4, 50)
        self.assertEqual(fields.byte5, 0xFC)
        self.assertEqual(fields.bytes6_7, 0x1234)

    def test_control_field_wrap_and_corruption(self) -> None:
        packed = pack_1ae_payload(replace(self.inputs, byte1=200, byte4=150))
        fields = parse_1ae_payload(packed.payload)
        self.assertEqual(fields.checksum, 0xA1)
        edited = bytearray(packed.payload)
        edited[4] = 151
        fields = parse_1ae_payload(bytes(edited))
        self.assertEqual(fields.checksum, 0xA1)
        self.assertEqual(fields.expected_checksum, 0xA0)
        self.assertFalse(fields.checksum_matches)

    def test_control_field_does_not_cover_flags_counter_and_remaining_bytes(self) -> None:
        edited = bytearray(pack_1ae_payload(self.inputs).payload)
        for index, difference in ((0, 0xF0), (2, 0xFF), (3, 0xF0), (5, 0xFF), (6, 0xFF), (7, 0xFF)):
            edited[index] ^= difference
        fields = parse_1ae_payload(bytes(edited))
        self.assertEqual(fields.byte0_bits7_5, 7)
        self.assertTrue(fields.checksum_matches)

    def test_counter_advances_wraps_and_resets(self) -> None:
        for before, active, register, on_wire in ((6, True, 7, 7), (7, True, 8, 0),
                                                  (255, True, 0, 0), (42, False, 0, 0)):
            with self.subTest(counter=before, active=active):
                packed = pack_1ae_payload(replace(self.inputs, counter_f8e4=before, flag_fd18_4=active))
                self.assertEqual(packed.next_counter_f8e4, register)
                self.assertEqual(parse_1ae_payload(packed.payload).counter_low_three_bits, on_wire)

    def test_modular_counter_delta_is_separate_from_checksum(self) -> None:
        frame = pack_1ae_payload(replace(self.inputs, counter_f8e4=7))
        fields = parse_1ae_payload(frame.payload)
        self.assertEqual(fields.counter_delta(7), 1)
        self.assertEqual(fields.counter_delta(6), 2)
        self.assertEqual(fields.counter_delta(5), 3)
        self.assertEqual(fields.counter_delta(0), 0)
        with self.assertRaises(ValueError):
            fields.counter_delta(8)

    def test_reserved_codes_and_byte5_saturation(self) -> None:
        maximum = pack_1ae_payload(replace(self.inputs, raw_fa5f=255))
        fields = parse_1ae_payload(maximum.payload)
        self.assertEqual(fields.byte5, 0xFE)
        self.assertFalse(fields.byte5_is_reserved)

        reserved = pack_1ae_payload(replace(self.inputs, byte1=0xFF, byte4=0xFF,
                                            flag_e026_0=True, raw_fad2=0xFFFF))
        fields = parse_1ae_payload(reserved.payload)
        self.assertTrue(fields.byte1_is_reserved)
        self.assertTrue(fields.byte4_is_reserved)
        self.assertTrue(fields.byte5_is_reserved)
        self.assertTrue(fields.bytes6_7_is_reserved)
        self.assertTrue(fields.checksum_matches)

    def test_rejects_non_byte_fields_and_invalid_payload_length(self) -> None:
        for patch in ({"byte1": -1}, {"raw_fa5f": 256}, {"byte3_high": 16},
                      {"raw_fad2": 65536}, {"flag_f842_5": 2}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                replace(self.inputs, **patch)
        for size in (7, 9):
            with self.subTest(size=size), self.assertRaises(ValueError):
                parse_1ae_payload(bytes(size))

    def test_vss_to_1ae_speed_and_ecm_scale(self) -> None:
        calibration = SpeedCalibration(
            wheel_rev_per_differential_rev=1, wheel_circumference_m=2, panel_hz_per_kmh=1,
        )
        speed = calibration.estimate(Fraction(1250, 33)).vehicle_kmh
        packed = pack_1ae_payload(replace(self.inputs, raw_fad2=encode_1ae_vehicle_speed(speed)))
        self.assertEqual(packed.payload[6:], bytes.fromhex("17 70"))
        reading = decode_chery_frame(CapturedFrame(
            arbitration_id=0x1AE, payload=packed.payload, dlc=8,
            frame_format=FrameFormat.STANDARD_DATA, observed_direction=Direction.TA2005_TO_ECM,
        )).reading
        self.assertEqual(reading.value, 60)

    def test_vehicle_speed_quantization_and_reserved_word(self) -> None:
        self.assertEqual(encode_1ae_vehicle_speed(Fraction("60.019")), 6001)
        self.assertEqual(encode_1ae_vehicle_speed(Fraction("511.999")), 51199)
        self.assertEqual(encode_1ae_vehicle_speed(None), 0xFFFF)
        for speed in (-1, 512, True):
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                encode_1ae_vehicle_speed(speed)
