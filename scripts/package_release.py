"""Package a strictly tested CMake installation; bundle no dependency libraries."""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import tempfile

from integration import verify_cleanup, verify_report


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = Path("lib/kea/hooks/libdhcp_db_commands.so")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive(path, files):
    """Fixed ordering, ownership, modes and timestamps, including the gzip header."""
    with path.open("wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9
    ) as compressed, tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith(".so") else 0o644
            tar.addfile(info, io.BytesIO(data))


def check_build(metadata, tag):
    if not re.fullmatch(r"0\.\d+\.\d+", metadata["version"]):
        raise RuntimeError("Expected a pre-1.0 numeric project version")
    if tag and tag != "v" + metadata["version"]:
        raise RuntimeError("Release tag must match the CMake project version exactly")
    if metadata["kea_version"] not in ("3.2.1", "3.2.1-git"):
        raise RuntimeError("Release packaging requires Kea 3.2.1")
    if metadata["build_type"] != "Release" or metadata["cxx_standard"] != "14":
        raise RuntimeError("Release packaging requires a Release C++14 build")
    if metadata["system"] != "Linux" or metadata["architecture"] != "x86_64":
        raise RuntimeError("Initial release packaging supports Linux x86_64 builds only")
    if platform.system() != "Linux" or platform.machine() != metadata["architecture"]:
        raise RuntimeError("Package on the native build platform")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=Path("build/integration"))
    parser.add_argument("--kea-prefix", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("build/release"))
    parser.add_argument("--tag", default="", help="If provided, must match the project version")
    args = parser.parse_args()
    build = args.build_dir.resolve(strict=True)
    metadata = json.loads((build / "release-build.json").read_text())
    check_build(metadata, args.tag)
    verify_report(build / "ctest-results.xml")
    verify_cleanup(build)
    library = build / "libdhcp_db_commands.so"
    if (build / "ctest-results.xml").stat().st_mtime < library.stat().st_mtime:
        raise RuntimeError("Integration results predate the built library; rerun the strict gate")
    operating_system = platform.freedesktop_os_release()
    target = "-".join((operating_system["ID"], operating_system["VERSION_ID"]))
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", target):
        raise RuntimeError("Unexpected operating-system identifier")
    name = f"kea-cb-commands-{metadata['version']}-linux-{target}-x86_64-kea-3.2.1"
    prefix = args.kea_prefix.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="release-stage-", dir=build) as directory:
        stage = Path(directory)
        subprocess.run(["cmake", "--install", str(build), "--prefix", str(stage)], check=True)
        installed = stage / LIBRARY
        if installed.is_symlink() or not installed.is_file():
            raise RuntimeError("Expected the installed hook as a regular file under lib/kea/hooks")
        subprocess.run([
            sys.executable, "-B", str(ROOT / "scripts/verify_artifact.py"),
            "--library", str(installed), "--kea-prefix", str(prefix),
            "--forbid-path", str(ROOT),
        ], check=True)
        data = installed.read_bytes()
    dynamic = subprocess.check_output(["readelf", "-d", str(library)], text=True)
    versions = subprocess.check_output(["readelf", "--version-info", str(library)], text=True)
    metadata.update({
        "platform": target,
        "libc": " ".join(platform.libc_ver()),
        "kea_hooks_abi": 30201,
        "kea_source": json.loads((ROOT / "scripts/kea-source.json").read_text()),
        "source": f"https://github.com/rannday/kea-cb-commands/tree/v{metadata['version']}",
        "needed_libraries": sorted(re.findall(r"\(NEEDED\).*\[(.*?)\]", dynamic)),
        "required_symbol_versions": sorted(set(re.findall(
            r"\b(?:GLIBCXX|GLIBC|CXXABI)_[\d.]+", versions))),
        "library_sha256": digest(data),
    })
    files = {
        str(LIBRARY): data,
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
        "INSTALL.md": (ROOT / "docs/release-install.md").read_bytes(),
        "RELEASE-NOTES.md": (ROOT / "docs/release-notes.md").read_bytes(),
        "manifest.json": (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode(),
    }
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (name + ".tar.gz")
    archive(path, {f"{name}/{key}": value for key, value in files.items()})
    checksum = path.with_name(path.name + ".sha256")
    checksum.write_text(f"{digest(path.read_bytes())}  {path.name}\n", encoding="utf-8")
    print(f"PASS: {path}\nSHA-256: {checksum}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
