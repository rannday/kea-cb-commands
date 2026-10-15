"""Strict integration gate tests, independent of SQL or networking privileges."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import integration


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.report = Path(self.directory.name) / "results.xml"
        self.suite = ET.Element("testsuite", tests="6", failures="0", skipped="0")
        for name in sorted(integration.EXPECTED_TESTS):
            ET.SubElement(self.suite, "testcase", name=name, status="run")

    def verify(self):
        ET.ElementTree(self.suite).write(self.report)
        integration.verify_report(self.report)

    def test_all_six_pass(self):
        self.verify()

    def test_missing_test_fails(self):
        self.suite.remove(self.suite[0])
        with self.assertRaisesRegex(RuntimeError, "Expected exactly"):
            self.verify()

    def test_duplicate_test_fails(self):
        self.suite[0].set("name", self.suite[1].get("name"))
        with self.assertRaisesRegex(RuntimeError, "Expected exactly"):
            self.verify()

    def test_skipped_test_fails(self):
        ET.SubElement(self.suite[0], "skipped")
        with self.assertRaisesRegex(RuntimeError, "did not pass"):
            self.verify()

    def test_failed_test_fails(self):
        ET.SubElement(self.suite[0], "failure", message="SQL unavailable")
        with self.assertRaisesRegex(RuntimeError, "did not pass"):
            self.verify()

    def test_suite_error_fails(self):
        self.suite.set("errors", "1")
        with self.assertRaisesRegex(RuntimeError, "errors=1"):
            self.verify()

    def test_missing_report_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Cannot read CTest report"):
            integration.verify_report(self.report)

    def test_residual_resources_fail(self):
        build_dir = Path(self.directory.name)
        integration.verify_cleanup(build_dir)
        work_dir = build_dir / "mysql-dhcp"
        work_dir.mkdir()
        (work_dir / "leftover").write_text("residual resource", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "resources remain"):
            integration.verify_cleanup(build_dir)


class EnvironmentTests(unittest.TestCase):
    def test_system_dependency_search_and_assertions_preserved(self):
        prefix = Path("/test/kea")
        inherited = {
            "PKG_CONFIG_LIBDIR": "/unrelated/packages",
            "PKG_CONFIG_PATH": "/unrelated/kea",
            "PYTHONOPTIMIZE": "2",
            "PYTHONPATH": "/unrelated/python",
            "PYTHONHOME": "/unrelated/python",
            "LD_LIBRARY_PATH": "/unrelated/libraries",
            "PATH": "/usr/bin",
        }
        with patch.dict(os.environ, inherited, clear=True), patch(
            "integration.subprocess.check_output", return_value=str(prefix) + "\n"
        ) as query:
            environment = integration.kea_environment(prefix)
        self.assertEqual(environment["PKG_CONFIG_PATH"], "/test/kea/lib/pkgconfig")
        self.assertEqual(environment["LD_LIBRARY_PATH"], "/test/kea/lib")
        for name in ("PKG_CONFIG_LIBDIR", "PYTHONOPTIMIZE", "PYTHONPATH", "PYTHONHOME"):
            self.assertNotIn(name, environment)
        self.assertEqual(query.call_args.kwargs["env"], environment)

    def test_different_kea_install_fails(self):
        with patch("integration.subprocess.check_output", return_value="/another/kea\n"):
            with self.assertRaisesRegex(RuntimeError, "pkg-config selected Kea prefix"):
                integration.kea_environment(Path("/test/kea"))


if __name__ == "__main__":
    unittest.main()
