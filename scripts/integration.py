#!/usr/bin/env python3
"""Run all six native integration tests; skipped tests fail this gate."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


EXPECTED_TESTS = {
    "control_transport",
    "hook_lifecycle",
    "postgresql_read",
    "postgresql_dhcp",
    "mysql_read",
    "mysql_dhcp",
}
WORK_DIRECTORIES = (
    "runtime", "postgresql", "mysql", "postgresql-dhcp", "mysql-dhcp"
)


def verify_report(path):
    """Reject missing, duplicate, skipped, failed, or unexpected test results."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise RuntimeError(f"Cannot read CTest report {path}: {error}") from error
    cases = list(root.iter("testcase"))
    names = [case.get("name") for case in cases]
    if len(names) != len(EXPECTED_TESTS) or set(names) != EXPECTED_TESTS:
        raise RuntimeError(
            f"Expected exactly {sorted(EXPECTED_TESTS)}; report contains {names}"
        )
    for suite in root.iter("testsuite"):
        for attribute in ("skipped", "failures", "errors", "disabled"):
            if suite.get(attribute, "0") not in ("0", "0.0"):
                raise RuntimeError(
                    f"CTest suite reports {attribute}={suite.get(attribute)}"
                )
    for case in cases:
        if any(case.find(tag) is not None for tag in ("skipped", "failure", "error")):
            raise RuntimeError(f"CTest test did not pass: {case.get('name')}")
        if case.get("status", "run") not in ("run", "passed"):
            raise RuntimeError(f"CTest test did not run: {case.get('name')}")


def verify_cleanup(build_dir):
    """Integration harnesses must remove their temporary resource directories."""
    for name in WORK_DIRECTORIES:
        directory = build_dir / name
        if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
            raise RuntimeError(f"Integration resources remain in {directory}")


def required_program(*names):
    for name in names:
        executable = shutil.which(name)
        if executable:
            return executable
    raise RuntimeError(f"Missing required executable: {' or '.join(names)}")


def required_file(path, executable=False):
    if not path.is_file() or (executable and not os.access(path, os.X_OK)):
        raise RuntimeError(f"Missing required {'executable' if executable else 'file'}: {path}")
    return str(path)


def run(command, environment):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(command, env=environment, check=True)


def kea_environment(prefix):
    """Prefer this Kea install while retaining system dependency metadata."""
    environment = os.environ.copy()
    for name in ("PYTHONOPTIMIZE", "PYTHONPATH", "PYTHONHOME", "PKG_CONFIG_LIBDIR"):
        environment.pop(name, None)
    environment.update({
        "PKG_CONFIG_PATH": str(prefix / "lib/pkgconfig"),
        "LD_LIBRARY_PATH": str(prefix / "lib"),
        "PATH": f"{prefix / 'bin'}:{prefix / 'sbin'}:{environment.get('PATH', '')}",
    })
    selected = subprocess.check_output(
        ["pkg-config", "--variable=prefix", "kea"], env=environment, text=True
    ).strip()
    if not selected or Path(selected).resolve() != prefix:
        raise RuntimeError(f"pkg-config selected Kea prefix {selected!r}; expected {prefix}")
    return environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kea-prefix", required=True, type=Path)
    parser.add_argument("--build-dir", default=Path("build/integration"), type=Path)
    parser.add_argument("--jobs", default=2, type=int)
    parser.add_argument("--sanitizers", action="store_true",
                        help="GCC ASan+UBSan hook build; requires a separate --build-dir")
    parser.add_argument("--multiprocess", action="store_true",
                        help="extend SQL tests with independent Kea processes")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if os.geteuid() == 0:
        raise RuntimeError("Run as an unprivileged user; PostgreSQL refuses root")
    for executable in ("cmake", "ctest", "pkg-config", "ip", "unshare"):
        required_program(executable)
    prefix = args.kea_prefix.resolve()
    build_dir = args.build_dir.resolve()
    source_dir = Path(__file__).resolve().parents[1]
    paths = {
        "KEA_DHCP4_EXECUTABLE": required_file(prefix / "sbin/kea-dhcp4", True),
        "KEA_LFC_EXECUTABLE": required_file(prefix / "sbin/kea-lfc", True),
        "KEA_POSTGRESQL_HOOK": required_file(prefix / "lib/kea/hooks/libdhcp_pgsql.so"),
        "KEA_MYSQL_HOOK": required_file(prefix / "lib/kea/hooks/libdhcp_mysql.so"),
        "KEA_POSTGRESQL_SCHEMA": required_file(
            prefix / "share/kea/scripts/pgsql/dhcpdb_create.pgsql"
        ),
        "KEA_MYSQL_SCHEMA": required_file(
            prefix / "share/kea/scripts/mysql/dhcpdb_create.mysql"
        ),
    }
    required_file(prefix / "lib/pkgconfig/kea.pc")
    pg_config = required_program("pg_config")
    pg_bin = Path(subprocess.check_output([pg_config, "--bindir"], text=True).strip())
    for binary in ("initdb", "pg_ctl", "psql", "pg_dump", "postgres"):
        required_file(pg_bin / binary, True)
    paths.update({
        "KEA_POSTGRESQL_BIN_DIR": str(pg_bin),
        "KEA_MYSQL_CLIENT": required_program("mariadb", "mysql"),
        "KEA_MYSQL_SERVER": required_program("mariadbd", "mysqld"),
        "KEA_MYSQL_INSTALL_DB": required_program("mariadb-install-db", "mysql_install_db"),
    })
    environment = kea_environment(prefix)
    sanitizer_logs = None
    if args.sanitizers:
        import sanitizers

        if build_dir == (source_dir / "build/integration").resolve():
            raise RuntimeError("Use a dedicated --build-dir (for example build/sanitizers)")
        compiler = required_program("g++")
        server, sanitizer_logs = sanitizers.prepare(
            build_dir, Path(paths["KEA_DHCP4_EXECUTABLE"]), compiler
        )
        paths["KEA_DHCP4_EXECUTABLE"] = str(server)
    command = [
        "cmake", "-S", str(source_dir), "-B", str(build_dir),
        # Refresh all Kea discovery and link checks when reusing a build directory.
        "-U", "*KEA*",
        f"-DCMAKE_BUILD_TYPE={'RelWithDebInfo' if args.sanitizers else 'Release'}",
        "-DBUILD_TESTING=ON", "-DCMAKE_INSTALL_LIBDIR=lib",
        "-DKEA_DB_COMMANDS_WARNINGS_AS_ERRORS=ON",
        f"-DKEA_DB_COMMANDS_MULTIPROCESS_TESTS={'ON' if args.multiprocess else 'OFF'}",
        f"-DKEA_DB_COMMANDS_SANITIZERS={'ON' if args.sanitizers else 'OFF'}",
    ]
    if args.sanitizers:
        command.append(f"-DCMAKE_CXX_COMPILER={compiler}")
    for option in ("RUNTIME", "POSTGRESQL", "MYSQL", "DHCP"):
        command.append(f"-DKEA_DB_COMMANDS_{option}_TESTS=ON")
    command.extend(f"-D{name}={value}" for name, value in paths.items())
    run(command, environment)
    run(["cmake", "--build", str(build_dir), "--parallel", str(args.jobs)], environment)
    if args.sanitizers:
        sanitizers.verify_instrumentation(build_dir / "libdhcp_db_commands.so")
        sanitizers.verify_detectors(compiler, sanitizer_logs, environment)
    report = build_dir / "ctest-results.xml"
    report.unlink(missing_ok=True)
    command = [
        "ctest", "--test-dir", str(build_dir), "--parallel", "1",
        "--output-on-failure", "--output-junit", str(report),
    ]
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, env=environment, check=False)
    errors = []
    for check, target in ((verify_report, report), (verify_cleanup, build_dir)):
        try:
            check(target)
        except RuntimeError as error:
            errors.append(str(error))
    if args.sanitizers:
        try:
            sanitizers.verify_logs(sanitizer_logs)
        except RuntimeError as error:
            errors.append(str(error))
    if result.returncode:
        errors.append(f"CTest exited with status {result.returncode}")
    if errors:
        raise RuntimeError("; ".join(errors))
    print("PASS: all six integration tests ran successfully; temporary resources removed")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
