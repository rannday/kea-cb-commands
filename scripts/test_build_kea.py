"""Security regression checks for the locked source archive extraction."""

import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from build_kea import extract_source


class SourceExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.archive = self.base / "source.tar.gz"
        self.destination = self.base / "source"
        self.root = "kea-test-commit"

    def write_archive(self, entries):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, kind, value in entries:
                member = tarfile.TarInfo(name)
                if kind == "file":
                    member.size = len(value)
                    member.mode = 0o755
                    archive.addfile(member, io.BytesIO(value))
                else:
                    member.type = kind
                    member.linkname = value
                    archive.addfile(member)

    def extract(self):
        extract_source(self.archive, self.destination, "test-commit")

    def test_internal_symlink_and_executable_preserved(self):
        self.write_archive(
            [
                (self.root + "/doc/images/logo", "file", b"image"),
                (self.root + "/doc/static/logo", tarfile.SYMTYPE, "../images/logo"),
            ]
        )
        self.extract()
        target = self.destination / "doc/static/logo"
        self.assertTrue(target.is_symlink())
        self.assertEqual(target.read_bytes(), b"image")
        self.assertTrue(target.stat().st_mode & 0o111)

    def test_unsafe_member_paths_rejected_before_extraction(self):
        for name in ("/absolute", self.root + "/../escape", "other-root/file"):
            with self.subTest(name=name):
                self.write_archive([(name, "file", b"bad")])
                with self.assertRaises(ValueError):
                    self.extract()
                self.assertFalse(self.destination.exists())

    def test_absolute_and_escaping_symlinks_rejected(self):
        for target in ("/tmp/outside", "../../outside"):
            with self.subTest(target=target):
                self.write_archive([(self.root + "/link", tarfile.SYMTYPE, target)])
                with self.assertRaises(ValueError):
                    self.extract()
                self.assertFalse(self.destination.exists())

    def test_member_beneath_symlink_rejected(self):
        self.write_archive(
            [
                (self.root + "/link", tarfile.SYMTYPE, "directory"),
                (self.root + "/link/file", "file", b"bad"),
            ]
        )
        with self.assertRaisesRegex(ValueError, "symlink parent"):
            self.extract()
        self.assertFalse(self.destination.exists())

    def test_hardlink_rejected(self):
        self.write_archive([(self.root + "/link", tarfile.LNKTYPE, self.root + "/file")])
        with self.assertRaises(ValueError):
            self.extract()

    def test_symlink_cycle_rejected(self):
        self.write_archive(
            [
                (self.root + "/first", tarfile.SYMTYPE, "second"),
                (self.root + "/second", tarfile.SYMTYPE, "first"),
            ]
        )
        with self.assertRaisesRegex(ValueError, "unresolved symlink"):
            self.extract()

    def test_symlink_chain_cannot_escape_after_normalization(self):
        self.write_archive(
            [
                (self.root + "/deep/alias", tarfile.SYMTYPE, ".."),
                (self.root + "/link", tarfile.SYMTYPE, "deep/alias/../../outside"),
            ]
        )
        with self.assertRaisesRegex(ValueError, "unresolved symlink"):
            self.extract()


if __name__ == "__main__":
    unittest.main()
