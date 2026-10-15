"""Check the trusted, locally built hook's ELF exports and resolved dependencies."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


def output(*args, env=None):
    return subprocess.check_output(args, env=env, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--kea-prefix", required=True, type=Path)
    parser.add_argument("--forbid-path", action="append", default=[])
    args = parser.parse_args()
    library = args.library.resolve(strict=True)
    prefix = args.kea_prefix.resolve(strict=True)
    if library.name != "libdhcp_db_commands.so":
        raise RuntimeError("unexpected hook filename")
    exports = {line.split()[-1] for line in output(
        "nm", "-D", "--defined-only", str(library)).splitlines() if line.split()}
    required = {"load", "unload", "version", "multi_threading_compatible"}
    if not required <= exports:
        raise RuntimeError(f"missing exports: {required - exports}")
    dynamic = output("readelf", "-d", str(library))
    if "(RPATH)" in dynamic or "(RUNPATH)" in dynamic:
        raise RuntimeError("hook embeds a runtime search path")
    env = dict(os.environ, LD_LIBRARY_PATH=str(prefix / "lib"))
    dependencies = output("ldd", str(library), env=env)
    if "not found" in dependencies:
        raise RuntimeError(dependencies)
    kea_libraries = re.findall(r"\b(libkea-[\w.-]+) => (\S+)", dependencies)
    if not kea_libraries:
        raise RuntimeError("no shared Kea dependencies found")
    for name, path in kea_libraries:
        if not Path(path).resolve().is_relative_to(prefix / "lib"):
            raise RuntimeError(f"{name} resolves outside the matching Kea prefix: {path}")
    data = library.read_bytes()
    for path in args.forbid_path:
        if str(Path(path).resolve()).encode() in data:
            raise RuntimeError("hook embeds a forbidden development path")
    if b"-----BEGIN PRIVATE KEY-----" in data:
        raise RuntimeError("unexpected private key marker")
    print("PASS: required exports, shared Kea resolution, no RPATH or forbidden paths")
    print(dependencies)
    print(output("readelf", "--version-info", str(library)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
