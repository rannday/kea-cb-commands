"""Offline formatting, Python lint, documentation links and whitespace gates."""

import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [ROOT / name for name in (
        "README.md", "CMakeLists.txt", ".clang-format", "pyproject.toml", ".gitignore"
    )]
    for directory in ("src", "tests", "scripts", "docs", ".github"):
        files.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and p.suffix in {".cc", ".h", ".py", ".md", ".yml", ".json", ".txt"}
                     and "__pycache__" not in p.parts)
    errors = []
    for path in sorted(files):
        data = path.read_text()
        if not data.endswith("\n"):
            errors.append(f"{path.relative_to(ROOT)}: missing final newline")
        for number, line in enumerate(data.splitlines(), 1):
            if line.rstrip() != line:
                errors.append(f"{path.relative_to(ROOT)}:{number}: trailing whitespace")
        if path.suffix == ".json":
            json.loads(data)
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^\s)]+)\)", data):
                if ":" in target or target.startswith("#"):
                    continue
                target = target.split("#", 1)[0]
                if not (path.parent / target).exists():
                    errors.append(f"{path.relative_to(ROOT)}: missing link target {target}")
    if errors:
        raise RuntimeError("\n".join(errors))
    cpp_files = sorted(str(p.relative_to(ROOT)) for p in files if p.suffix in {".cc", ".h"})
    subprocess.run(["clang-format", "--dry-run", "--Werror", *cpp_files],
                   cwd=ROOT, check=True)
    subprocess.run(["ruff", "check", "tests", "scripts"], cwd=ROOT, check=True)
    print(f"PASS: formatting, lint, whitespace and local document links ({len(files)} files)")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
