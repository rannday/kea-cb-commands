"""Release archive reproducibility and compatibility guards; no runtime needed."""

from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import package_release


class PackageTests(unittest.TestCase):
    def test_reproducible_archive_and_exact_contents(self):
        files = {"release/lib/kea/hooks/hook.so": b"ELF fixture", "release/LICENSE": b"license"}
        with tempfile.TemporaryDirectory() as directory:
            first, second = (Path(directory) / name for name in ("one.gz", "two.gz"))
            package_release.archive(first, files)
            package_release.archive(second, dict(reversed(list(files.items()))))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first) as tar:
                self.assertEqual(tar.getnames(), sorted(files))
                for entry in tar.getmembers():
                    self.assertTrue(entry.isfile())
                    self.assertEqual((entry.uid, entry.gid, entry.mtime), (0, 0, 0))
                    self.assertEqual(tar.extractfile(entry).read(), files[entry.name])

    def test_compatibility_and_tag_guards(self):
        metadata = {"version": "0.1.0", "kea_version": "3.2.1-git", "build_type": "Release",
                    "cxx_standard": "14", "system": "Linux", "architecture": "x86_64"}
        with patch("package_release.platform.system", return_value="Linux"), patch(
            "package_release.platform.machine", return_value="x86_64"
        ):
            package_release.check_build(metadata, "v0.1.0")
            with self.assertRaisesRegex(RuntimeError, "tag must match"):
                package_release.check_build(metadata, "v0.2.0")
            for key, value in (("kea_version", "3.0.4"), ("build_type", "Debug"),
                               ("cxx_standard", "17"), ("architecture", "aarch64")):
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    package_release.check_build(dict(metadata, **{key: value}), "")


if __name__ == "__main__":
    unittest.main()
