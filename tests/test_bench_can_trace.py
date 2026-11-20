import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.check_bench_can_trace import main


HEADER = "@ TEXT @ 3 @ 64 @ 0 @ 25261 @ 227442 @ 00:03:47.442 @"
ZERO_DATA = "00 00 00 00 00 00 00 00"


def row(stamp, can_id, *, stream="1", data=ZERO_DATA, flags="00000004", tail="00000000"):
    return "\t".join((stamp, stream, flags, can_id, str(len(data.split())), data, tail, "        ", ""))


def payload_1ae(counter, *, active=True, bad_checksum=False):
    # Bytes 1 and 4 are zero, so the stock control value is 0xFF.
    return f"{0x0E if bad_checksum else 0x0F:02X} 00 {(counter << 4) | active:02X} 0F 00 00 00 00"


class BenchCanTraceTests(unittest.TestCase):
    def run_trace(self, rows, *args, header=HEADER):
        raw = ("\r\n".join((header, "# $LocalTime=15:11:03.603", *rows)) + "\r\n").encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench.trc"
            path.write_bytes(raw)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = main([str(path), *args])
            report = json.loads(out.getvalue())
            self.assertEqual(report["trace_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertFalse(report["hardware_verified"])
        return code, report

    def test_minute_wrap_requires_opt_in(self):
        rows = [row("59,999500", "0FA"), row("0,000500", "0FA")]
        args = ("--stream", "1", "--interval", "0x0FA:1000:1000")
        code, report = self.run_trace(rows, *args)
        self.assertEqual(code, 1)
        self.assertEqual(report["streams"]["1"]["timestamp_discontinuities"], 1)
        self.assertEqual(report["streams"]["1"]["periodic"]["0FA"]["intervals"], 0)
        self.assertIn("timestamp_discontinuity", report["interval_checks"]["0FA"]["problems"])
        code, report = self.run_trace(rows, *args, "--minute-wrap")
        self.assertEqual(code, 0)
        self.assertEqual(report["verdict"], "PERIODIC_CHECKS_PASS")
        self.assertEqual(report["streams"]["1"]["minute_wraps"], 1)
        self.assertEqual(report["streams"]["1"]["periodic"]["0FA"]["min_interval_us"], 1000)

    def test_observation_keeps_streams_and_duplicate_timestamps(self):
        rows = [
            row("10,000000", "5E8"),
            row("01,000000", "278", stream="2"),
            row("10,000000", "278"),
            row("10,000000", "278"),
            row("01,010000", "278", stream="2"),
        ]
        code, report = self.run_trace(rows)
        self.assertEqual(code, 0)
        self.assertEqual(report["verdict"], "OBSERVED_OFFLINE_ONLY")
        self.assertEqual(report["interval_checks"], {})
        self.assertIsNone(report["checked_stream"])
        self.assertEqual(report["streams"]["1"]["counts"], {"278": 2, "5E8": 1})
        self.assertEqual(report["streams"]["1"]["periodic"]["278"]["min_interval_us"], 0)
        self.assertEqual(report["streams"]["2"]["periodic"]["278"]["min_interval_us"], 10000)

    def test_reports_only_requested_checks_and_requires_an_interval(self):
        rows = [row("0,000000", "278"), row("0,010000", "278"), row("0,021000", "278"),
                row("0,021000", "300"), row("0,031001", "278")]
        code, report = self.run_trace(
            rows, "--stream", "1", "--interval", "278:10000:11000",
            "--interval", "300:9000:11000", "--interval", "0FA:9000:11000",
        )
        self.assertEqual(code, 1)
        self.assertEqual(report["verdict"], "PERIODIC_CHECKS_FAIL")
        self.assertEqual(set(report["interval_checks"]), {"278", "300", "0FA"})
        self.assertTrue(report["interval_checks"]["278"]["pass"])
        self.assertEqual(report["interval_checks"]["300"]["problems"], ["no_intervals"])
        self.assertEqual(report["interval_checks"]["0FA"]["problems"], ["no_intervals"])
        code, report = self.run_trace(rows, "--stream", "1", "--interval", "278:10000:10999")
        self.assertEqual(code, 1)
        self.assertEqual(report["interval_checks"]["278"]["intervals_out_of_bounds"], 1)

    def test_1ae_checksum_wrap_disable_and_restart(self):
        rows = [
            row(f"0,{index * 10000:06d}", "1AE", data=payload_1ae(counter, active=active))
            for index, (counter, active) in enumerate(((7, True), (0, True), (0, False), (1, True)))
        ]
        args = ("--stream", "1", "--interval", "1AE:10000:10000")
        code, report = self.run_trace(rows, *args)
        self.assertEqual(code, 0)
        self.assertEqual(report["streams"]["1"]["periodic"]["1AE"]["counter_errors"], 0)
        rows.extend([
            row("0,040000", "1AE", data=payload_1ae(2, bad_checksum=True)),
            row("0,050000", "1AE", data=payload_1ae(5)),
            row("0,060000", "1AE", data=payload_1ae(7)),
            row("0,070000", "1AE", data=payload_1ae(1, active=False)),
        ])
        code, report = self.run_trace(rows, *args)
        self.assertEqual(code, 1)
        self.assertEqual(report["interval_checks"]["1AE"]["problems"], ["checksum_error", "counter_error"])
        self.assertEqual(report["streams"]["1"]["periodic"]["1AE"]["checksum_errors"], 1)
        self.assertEqual(report["streams"]["1"]["periodic"]["1AE"]["counter_errors"], 2)

    def test_excludes_other_flag_pairs_and_dlc(self):
        rows = [
            row("0,000000", "300"),
            row("0,003000", "300", flags="00000008"),
            row("0,006000", "300", tail="00000001"),
            row("0,010000", "300", data=""),
            row("0,020000", "300"),
            row("0,030000", "300"),
        ]
        code, report = self.run_trace(rows, "--stream", "1", "--interval", "300:10000:10000")
        self.assertEqual(code, 1)
        self.assertEqual(report["interval_checks"]["300"]["problems"], ["excluded_records"])
        stats = report["streams"]["1"]["periodic"]["300"]
        self.assertEqual((stats["accepted_frames"], stats["excluded_frames"], stats["intervals"]), (3, 3, 1))

    def test_rejects_invalid_trace_or_criteria(self):
        valid = row("0,000000", "0FA")
        cases = (
            ([valid], (), "@ TEXT @ 2 @", "CANHacker TEXT v3"),
            ([], (), HEADER, "нет записей CAN"),
            ([valid.replace("\t8\t", "\t7\t")], (), HEADER, "Строка 3"),
            ([row("60,000000", "0FA")], ("--minute-wrap",), HEADER, "меньше 60 секунд"),
            ([valid], ("--interval", "0FA:1:2"), HEADER, "укажите --stream"),
            ([valid], ("--stream", "2"), HEADER, "Поток 2 отсутствует"),
            ([valid], ("--interval", "5E8:1:2"), HEADER, "Допустимые ID"),
            ([valid], ("--interval", "0FA:2:1"), HEADER, "MIN_US <= MAX_US"),
            ([valid], ("--stream", "1", "--interval", "FA:1:2", "--interval", "0FA:1:2"),
             HEADER, "одна пара границ"),
        )
        for rows, args, header, error in cases:
            with self.subTest(args=args, error=error), contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as raised:
                    self.run_trace(rows, *args, header=header)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(error, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
