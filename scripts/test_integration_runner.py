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
        # unittest calls setUp before each test; these are per-test fixtures.
        self.directory: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()  # pyright: ignore[reportUninitializedInstanceVariable]
        self.addCleanup(self.directory.cleanup)
        self.report: Path = Path(self.directory.name) / "results.xml"  # pyright: ignore[reportUninitializedInstanceVariable]
        self.suite: ET.Element = ET.Element("testsuite", tests="6", failures="0", skipped="0")  # pyright: ignore[reportUninitializedInstanceVariable]
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
        name = self.suite[1].get("name")
        assert name is not None
        self.suite[0].set("name", name)
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


class DatabaseVersionTests(unittest.TestCase):
    def versions(self, postgres, mariadb):
        with patch("integration.subprocess.check_output", side_effect=[postgres, mariadb]):
            return integration.database_versions(Path("/pg/bin"), "/usr/sbin/mariadbd")

    def test_supported_vendor_versions(self):
        versions = self.versions(
            "postgres (PostgreSQL) 18.6 (Debian 18.6-1.pgdg12+2)",
            "/usr/sbin/mariadbd  Ver 12.3.3-MariaDB-deb12 for debian-linux-gnu",
        )
        self.assertEqual(versions["postgresql"]["version"], "18.6")
        self.assertEqual(versions["mariadb"]["version"], "12.3.3")

    def test_old_postgres_and_prereleases_rejected(self):
        for version in ("15.19", "19rc1", "18beta1", "18.6rc1"):
            with self.subTest(version=version), self.assertRaisesRegex(
                RuntimeError, "Expected PostgreSQL 18"
            ):
                self.versions(f"postgres (PostgreSQL) {version}", "")

    def test_old_rolling_and_oracle_mysql_rejected(self):
        for version in ("10.11.19-MariaDB", "13.0.2-MariaDB", "12.3.3"):
            with self.subTest(version=version), self.assertRaisesRegex(
                RuntimeError, "MariaDB 12.3 LTS"
            ):
                self.versions("postgres (PostgreSQL) 18.6", f"mysqld Ver {version}")


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
