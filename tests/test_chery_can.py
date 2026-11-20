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

    def test_candidate_frames_and_unknown_id_stay_raw(self) -> None:
        for arbitration_id in (0x1AE, 0x300):
            with self.subTest(arbitration_id=arbitration_id):
                frame = replace(self.coolant_frame, arbitration_id=arbitration_id, observed_direction=Direction.TA2005_TO_ECM)
                decoded = decode_chery_frame(frame)
                self.assertIs(decoded.status, DecodeStatus.PAYLOAD_NOT_DECODED)
                self.assertIs(decoded.direction_evidence, DirectionEvidence.DONOR_RX_TX_CANDIDATE)
                self.assertIs(decoded.donor_direction, Direction.TA2005_TO_ECM)
                self.assertIsNone(decoded.reading)
                self.assertIs(decoded.frame, frame)
        unknown = replace(self.coolant_frame, arbitration_id=0x123)
        self.assertIs(decode_chery_frame(unknown).status, DecodeStatus.ID_UNKNOWN)
