import unittest
from dataclasses import replace

from model.chery_1ae import Raw1AEFields, parse_1ae_payload
from model.chery_transport import Donor1AERequestQualifier, DonorReceiveChannel, ReceiveSelection


def raw_fields(counter: int, bad_checksum: bool = False) -> Raw1AEFields:
    return parse_1ae_payload(bytes((0x0A if bad_checksum else 0x0B, 50, counter << 4, 0x09, 50, 0, 0, 0)))


class CheryTransportTests(unittest.TestCase):
    def test_poll_spacing_and_loss_thresholds(self) -> None:
        for frame_id, calls_per_poll, misses_to_loss in ((0x1AE, 2, 16), (0x300, 6, 6)):
            with self.subTest(arbitration_id=frame_id):
                receiver = DonorReceiveChannel(frame_id)
                final_call = (misses_to_loss - 1) * calls_per_poll
                for call in range(final_call + 1):
                    poll = receiver.step(exchange_enabled=True, matching_new_data=False,
                                         busoff_diagnostic_b254=False)
                    self.assertEqual(poll.polled, call % calls_per_poll == 0)
                    self.assertEqual(poll.loss_flag, call == final_call)
                self.assertEqual(poll.unsuccessful_polls, misses_to_loss - 1)
                self.assertIs(poll.selection, ReceiveSelection.ENABLED_FALLBACK)

        boot_1ae = DonorReceiveChannel(0x1AE, initial_skip=1)
        for call in range(1, 33):
            poll = boot_1ae.step(exchange_enabled=True, matching_new_data=False, busoff_diagnostic_b254=False)
            self.assertEqual(poll.polled, call % 2 == 0)
            self.assertEqual(poll.loss_flag, call == 32)

    def test_busoff_diagnostic_selects_fallback_even_on_new_data(self) -> None:
        receiver = DonorReceiveChannel(0x1AE)
        for _ in range(31):
            monitor = receiver.step(exchange_enabled=True, matching_new_data=False,
                                    busoff_diagnostic_b254=False)
        self.assertTrue(monitor.loss_flag)
        skipped = receiver.step(exchange_enabled=True, matching_new_data=False, busoff_diagnostic_b254=True)
        self.assertIs(skipped.selection, ReceiveSelection.KEEP)
        recovered = receiver.step(exchange_enabled=True, matching_new_data=True, busoff_diagnostic_b254=True)
        self.assertEqual(recovered.unsuccessful_polls, 0)
        self.assertFalse(recovered.loss_flag)
        self.assertIs(recovered.selection, ReceiveSelection.ENABLED_FALLBACK)
        receiver.step(exchange_enabled=True, matching_new_data=False, busoff_diagnostic_b254=False)
        accepted = receiver.step(exchange_enabled=True, matching_new_data=True, busoff_diagnostic_b254=False)
        self.assertIs(accepted.selection, ReceiveSelection.PAYLOAD)

    def test_disabled_variant_selects_its_default_without_polling(self) -> None:
        receiver = DonorReceiveChannel(0x1AE)
        receiver.step(exchange_enabled=True, matching_new_data=False, busoff_diagnostic_b254=False)
        disabled = receiver.step(exchange_enabled=False, matching_new_data=True, busoff_diagnostic_b254=False)
        self.assertIs(disabled.selection, ReceiveSelection.DISABLED_DEFAULT)
        self.assertFalse(disabled.polled)
        preserved_skip = receiver.step(exchange_enabled=True, matching_new_data=True, busoff_diagnostic_b254=False)
        self.assertIs(preserved_skip.selection, ReceiveSelection.KEEP)
        self.assertFalse(preserved_skip.polled)

    def test_checksum_fault_and_combined_recovery_delays_differ(self) -> None:
        receiver = Donor1AERequestQualifier()
        for call in range(1, 5):
            bad = receiver.step(raw_fields(0, bad_checksum=True), sequence_enabled=False, external_invalid_flag=False)
            self.assertTrue(bad.checksum_error)
            self.assertEqual(bad.checksum_fault, call >= 3)
            self.assertEqual(bad.combined_latch, call >= 4)
        for call in range(1, 5):
            good = receiver.step(raw_fields(0), sequence_enabled=False, external_invalid_flag=False)
            self.assertFalse(good.checksum_error)
            self.assertEqual(good.checksum_fault, call < 4)
            self.assertEqual(good.combined_latch, call < 4)
            self.assertEqual(good.byte1_fallback, call < 4)

    def test_counter_and_fallback_for_reserved_fields(self) -> None:
        receiver = Donor1AERequestQualifier()
        for counter in (2, 4, 6, 0, 1):
            accepted = receiver.step(raw_fields(counter), sequence_enabled=True, external_invalid_flag=False)
            self.assertFalse(accepted.sequence_error)
        for call in range(1, 4):
            repeated = receiver.step(raw_fields(1), sequence_enabled=True, external_invalid_flag=False)
            self.assertTrue(repeated.sequence_error)
            self.assertEqual(repeated.sequence_fault, call == 3)
        good = receiver.step(raw_fields(2), sequence_enabled=True, external_invalid_flag=True)
        self.assertFalse(good.sequence_fault)
        self.assertTrue(good.byte1_fallback)
        self.assertTrue(good.byte4_fallback)

        one_reserved = replace(raw_fields(3), byte1=0xFF, checksum_high=0xC, checksum_low=0xE)
        result = receiver.step(one_reserved, sequence_enabled=True, external_invalid_flag=False)
        self.assertFalse(result.checksum_error)
        self.assertTrue(result.byte1_fallback)
        self.assertFalse(result.byte4_fallback)
