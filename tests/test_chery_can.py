import unittest
from dataclasses import replace
from fractions import Fraction

from model.chery_can import (
    CapturedFrame,
    DecodeStatus,
    Direction,
    DirectionEvidence,
    FrameFormat,
    SignalReading,
    decode_chery_frame,
)


class CheryCanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.coolant_frame = CapturedFrame(
            arbitration_id=0x278,
            payload=bytes.fromhex("B1 01 02 03 04 05 06 07"),
            dlc=8,
            frame_format=FrameFormat.STANDARD_DATA,
            observed_direction=Direction.ECM_TO_TA2005,
        )

    def test_coolant_converts_only_byte_zero(self) -> None:
        decoded = decode_chery_frame(self.coolant_frame)
        self.assertIs(decoded.status, DecodeStatus.DECODED)
        self.assertIs(decoded.donor_direction, Direction.ECM_TO_TA2005)
        self.assertIs(decoded.direction_evidence, DirectionEvidence.DONOR_TX_AND_RX)
        self.assertEqual(decoded.reading, SignalReading("coolant_temperature", "°C", 0xB1, Fraction(339, 4)))
        zero_raw = replace(self.coolant_frame, payload=bytes(8))
        self.assertEqual(decode_chery_frame(zero_raw).reading.value, -48)

    def test_coolant_ff_is_invalid_but_preserves_raw(self) -> None:
        frame = replace(self.coolant_frame, payload=bytes.fromhex("FF 01 02 03 04 05 06 07"))
        decoded = decode_chery_frame(frame)
        self.assertIs(decoded.status, DecodeStatus.DECODED)
        self.assertEqual(decoded.reading, SignalReading("coolant_temperature", "°C", 0xFF, None))
        self.assertIs(decoded.frame, frame)

    def test_engine_speed_uses_big_endian_and_quarter_rpm(self) -> None:
        frame = replace(self.coolant_frame, arbitration_id=0x0FA, payload=bytes.fromhex("12 C1 00 00 00 00 00 00"))
        decoded = decode_chery_frame(frame)
        self.assertIs(decoded.status, DecodeStatus.DECODED)
        self.assertEqual(decoded.reading, SignalReading("engine_speed", "rpm", 0x12C1, Fraction(4801, 4)))

    def test_engine_speed_ffff_is_invalid_but_zero_is_valid(self) -> None:
        frame = replace(self.coolant_frame, arbitration_id=0x0FA, payload=bytes.fromhex("FF FF 00 00 00 00 00 00"))
        self.assertEqual(decode_chery_frame(frame).reading, SignalReading("engine_speed", "rpm", 0xFFFF, None))
        zero_raw = replace(frame, payload=bytes(8))
        self.assertEqual(decode_chery_frame(zero_raw).reading.value, 0)

    def test_decoding_requires_matching_observed_direction(self) -> None:
        cases = ((None, DecodeStatus.DIRECTION_UNKNOWN), (Direction.TA2005_TO_ECM, DecodeStatus.DIRECTION_MISMATCH))
        for direction, expected_status in cases:
            with self.subTest(direction=direction):
                decoded = decode_chery_frame(replace(self.coolant_frame, observed_direction=direction))
                self.assertIs(decoded.status, expected_status)
                self.assertIsNone(decoded.reading)

    def test_dlc_and_payload_must_both_be_eight(self) -> None:
        for dlc, size in ((7, 7), (8, 7), (7, 8), (8, 9)):
            with self.subTest(dlc=dlc, size=size):
                decoded = decode_chery_frame(replace(self.coolant_frame, dlc=dlc, payload=bytes(size)))
                self.assertIs(decoded.status, DecodeStatus.LENGTH_MISMATCH)
                self.assertIsNone(decoded.reading)

    def test_rejects_other_frame_formats_and_nonstandard_id_width(self) -> None:
        for frame_format in (FrameFormat.EXTENDED_DATA, FrameFormat.REMOTE, FrameFormat.FD, FrameFormat.UNKNOWN):
            with self.subTest(frame_format=frame_format):
                decoded = decode_chery_frame(replace(self.coolant_frame, frame_format=frame_format))
                self.assertIs(decoded.status, DecodeStatus.FORMAT_UNSUPPORTED)
        wide_id = replace(self.coolant_frame, arbitration_id=0x800)
        self.assertIs(decode_chery_frame(wide_id).status, DecodeStatus.FORMAT_UNSUPPORTED)

    def test_1ae_parses_raw_fields_in_the_matching_observed_direction(self) -> None:
        frame = replace(self.coolant_frame, arbitration_id=0x1AE,
                        payload=bytes.fromhex("0B 32 00 09 32 FF FF FF"),
                        observed_direction=Direction.TA2005_TO_ECM)
        decoded = decode_chery_frame(frame)
        self.assertIs(decoded.status, DecodeStatus.DECODED)
        self.assertIs(decoded.donor_direction, Direction.TA2005_TO_ECM)
        self.assertIs(decoded.direction_evidence, DirectionEvidence.DONOR_TX_AND_RX)
        self.assertEqual(decoded.reading, SignalReading("vehicle_speed", "km/h", 0xFFFF, None))
        self.assertTrue(decoded.fields_1ae.checksum_matches)
        self.assertTrue(decoded.fields_1ae.byte5_is_reserved)
        self.assertTrue(decoded.fields_1ae.bytes6_7_is_reserved)

        unknown_direction = decode_chery_frame(replace(frame, observed_direction=None))
        self.assertIs(unknown_direction.status, DecodeStatus.DIRECTION_UNKNOWN)
        self.assertIsNone(unknown_direction.fields_1ae)
        reverse_direction = decode_chery_frame(replace(frame, observed_direction=Direction.ECM_TO_TA2005))
        self.assertIs(reverse_direction.status, DecodeStatus.DIRECTION_MISMATCH)
        self.assertIsNone(reverse_direction.fields_1ae)

    def test_1ae_speed_uses_big_endian_and_one_hundredth_kmh(self) -> None:
        frame = replace(self.coolant_frame, arbitration_id=0x1AE,
                        payload=bytes.fromhex("0B 32 00 09 32 FF 19 8F"),
                        observed_direction=Direction.TA2005_TO_ECM)
        decoded = decode_chery_frame(frame)
        self.assertEqual(decoded.reading, SignalReading("vehicle_speed", "km/h", 6543, Fraction(6543, 100)))
        self.assertEqual(decoded.fields_1ae.bytes6_7, 6543)

    def test_1ae_receiver_wrap_and_reserved_word_preserve_raw(self) -> None:
        for raw, expected in ((0, 0), (51199, Fraction(51199, 100)), (51200, None),
                              (0xFFFE, None), (0xFFFF, None)):
            with self.subTest(raw=raw):
                frame = replace(self.coolant_frame, arbitration_id=0x1AE,
                                payload=bytes.fromhex("0B 32 00 09 32 00") + raw.to_bytes(2, "big"),
                                observed_direction=Direction.TA2005_TO_ECM)
                decoded = decode_chery_frame(frame)
                self.assertEqual(decoded.reading, SignalReading("vehicle_speed", "km/h", raw, expected))
                self.assertEqual(decoded.fields_1ae.bytes6_7_is_reserved, raw == 0xFFFF)

    def test_300_temperature_uses_byte_three_and_saturates_at_104_c(self) -> None:
        for raw, expected in ((0, -40), (40, 0), (100, 60), (143, 103), (144, 104),
                              (200, 104), (254, 104), (255, None)):
            with self.subTest(raw=raw):
                frame = replace(self.coolant_frame, arbitration_id=0x300,
                                payload=bytes((100, 101, 102, raw, 104, 105, 106, 107)),
                                observed_direction=Direction.TA2005_TO_ECM)
                decoded = decode_chery_frame(frame)
                self.assertIs(decoded.status, DecodeStatus.DECODED)
                self.assertIs(decoded.donor_direction, Direction.TA2005_TO_ECM)
                self.assertIs(decoded.direction_evidence, DirectionEvidence.DONOR_TX_AND_RX)
                self.assertEqual(decoded.reading, SignalReading("atf_temperature", "°C", raw, expected))
                self.assertIsNone(decoded.fields_1ae)
                self.assertIs(decoded.frame, frame)

    def test_300_requires_reported_ta2005_transmission(self) -> None:
        for direction, status in ((None, DecodeStatus.DIRECTION_UNKNOWN),
                                  (Direction.ECM_TO_TA2005, DecodeStatus.DIRECTION_MISMATCH)):
            with self.subTest(direction=direction):
                frame = replace(self.coolant_frame, arbitration_id=0x300, observed_direction=direction)
                decoded = decode_chery_frame(frame)
                self.assertIs(decoded.status, status)
                self.assertIsNone(decoded.reading)

    def test_unknown_id_stays_raw(self) -> None:
        frame = replace(self.coolant_frame, arbitration_id=0x123)
        decoded = decode_chery_frame(frame)
        self.assertIs(decoded.status, DecodeStatus.ID_UNKNOWN)
        self.assertIsNone(decoded.reading)
        self.assertIsNone(decoded.fields_1ae)
        self.assertIs(decoded.frame, frame)
