"""Run local C++ checks using the configured hook compilation database."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    print("+", shlex.join(str(arg) for arg in command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=("format", "clangd", "tidy", "analyzer", "cppcheck", "all"))
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/integration")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    sources = sorted((ROOT / "src").glob("*.cc"))
    headers = sorted((ROOT / "src").glob("*.h"))
    # Editor feature probes are separate from the combined static-analysis gate.
    checks = {"format", "tidy", "analyzer", "cppcheck"} if args.check == "all" else {args.check}
    if "format" in checks:
        run(["clang-format", "--dry-run", "--Werror", *sources, *headers], cwd=ROOT)
    if checks == {"format"}:
        return

    database = build / "compile_commands.json"
    entries = json.loads(database.read_text())
    # Fail if the database is stale or describes anything beyond this module.
    by_source = {}
    for entry in entries:
        source = (Path(entry["directory"]) / entry["file"]).resolve()
        if source not in sources or source in by_source:
            raise ValueError(f"Unexpected or duplicate compilation entry: {source}")
        by_source[source] = entry
    if set(by_source) != set(sources):
        raise ValueError("Compilation database must cover every src/*.cc file; reconfigure CMake")

    if "clangd" in checks:
        for source in sources + headers:
            run(["clangd-22", f"--check={source}", f"--compile-commands-dir={build}"], cwd=ROOT)
    if "tidy" in checks:
        run(["clang-tidy", "-p", build, *sources], cwd=ROOT)
    if "analyzer" in checks:
        output = build / "analysis"
        output.mkdir(exist_ok=True)
        for source in sources:
            entry = by_source[source]
            command = entry.get("arguments") or shlex.split(entry["command"])
            # Reuse all defines, include paths and language/compiler flags.
            # Only compilation/output switches change for analysis; no rebuild.
            flags = []
            iterator = iter(command[1:])
            for flag in iterator:
                if flag == "-o":
                    next(iterator)
                elif flag != "-c":
                    flags.append(flag)
            run(["clang++", "--analyze", *flags, "-Xanalyzer", "-analyzer-werror",
                 "-Xanalyzer", "-analyzer-output=plist", "-o", output / f"{source.stem}.plist"],
                cwd=entry["directory"])
    if "cppcheck" in checks:
        run(["cppcheck", f"--project={database}", "--std=c++14",
             "--enable=warning,performance,portability", "--error-exitcode=1"], cwd=ROOT)
    print("PASS: requested C++ checks")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
