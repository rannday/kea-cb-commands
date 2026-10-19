"""Sanitizer reports must fail the gate even when CTest reports success."""

from pathlib import Path
import tempfile
import unittest

import sanitizers


class SanitizerLogTests(unittest.TestCase):
    def setUp(self):
        # unittest calls setUp before each test; these are per-test fixtures.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.logs: Path = Path(directory.name)  # pyright: ignore[reportUninitializedInstanceVariable]
        (self.logs / "launches").write_text("123\n")
        self.report: Path = self.logs / "asan.123"  # pyright: ignore[reportUninitializedInstanceVariable]
        self.report.write_text("AddressSanitizer Init done\n")

    def test_initialized_runtime_passes(self):
        sanitizers.verify_logs(self.logs)

    def test_missing_runtime_log_fails(self):
        self.report.unlink()
        with self.assertRaisesRegex(RuntimeError, "No sanitizer initialization"):
            sanitizers.verify_logs(self.logs)

    def test_incomplete_initialization_fails(self):
        self.report.write_text("ASan runtime starting\n")
        with self.assertRaisesRegex(RuntimeError, "did not initialize"):
            sanitizers.verify_logs(self.logs)

    def test_reported_faults_fail(self):
        for message in ("ERROR: AddressSanitizer", "SUMMARY: AddressSanitizer",
                        "AddressSanitizer:DEADLYSIGNAL", "LeakSanitizer detected leaks"):
            with self.subTest(message=message):
                self.report.write_text("AddressSanitizer Init done\n" + message)
                with self.assertRaisesRegex(RuntimeError, "Sanitizer finding"):
                    sanitizers.verify_logs(self.logs)

    def test_ubsan_report_fails(self):
        (self.logs / "ubsan.123").write_text("runtime error: signed integer overflow\n")
        with self.assertRaisesRegex(RuntimeError, "Sanitizer finding"):
            sanitizers.verify_logs(self.logs)

    def test_intentional_probe_reports_are_separate(self):
        probes = self.logs / "probes"
        probes.mkdir()
        (probes / "asan.txt").write_text("ERROR: AddressSanitizer\n")
        sanitizers.verify_logs(self.logs)


if __name__ == "__main__":
    unittest.main()
