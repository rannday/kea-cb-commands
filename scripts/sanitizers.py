"""GCC sanitizer support for the existing strict integration runner."""

from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tempfile


def prepare(build_dir, server, compiler):
    """Preload runtimes into Kea only, never the Python or database processes."""
    setarch = shutil.which("setarch")
    if not setarch:
        raise RuntimeError("Sanitizer startup requires setarch (util-linux)")
    cache = build_dir / "CMakeCache.txt"
    if cache.exists() and "KEA_DB_COMMANDS_SANITIZERS:BOOL=ON" not in cache.read_text():
        raise RuntimeError("Sanitizers require a fresh or existing sanitizer build directory")
    build_dir.mkdir(parents=True, exist_ok=True)
    logs_root = build_dir / "sanitizer-logs"
    logs_root.mkdir(exist_ok=True)
    logs = Path(tempfile.mkdtemp(prefix="run-", dir=logs_root))
    runtimes = []
    for name in ("libasan.so", "libubsan.so"):
        runtime = Path(subprocess.check_output(
            [compiler, f"-print-file-name={name}"], text=True
        ).strip())
        if not runtime.is_absolute() or not runtime.is_file():
            raise RuntimeError(f"Missing GCC runtime: {name}")
        runtimes.append(str(runtime.resolve()))
    wrapper = build_dir / "kea-dhcp4-sanitized"
    values = {
        "LD_PRELOAD": ":".join(runtimes),
        "ASAN_OPTIONS": f"detect_leaks=1:halt_on_error=1:verbosity=1:log_path={logs}/asan",
        "UBSAN_OPTIONS": f"halt_on_error=1:print_stacktrace=1:log_path={logs}/ubsan",
    }
    wrapper.write_text(
        "#!/bin/sh\nset -eu\n"
        + f"printf '%s\\n' \"$$\" >> {shlex.quote(str(logs / 'launches'))}\n"
        # GCC 12 ASan intermittently crashes before Init done with this PIE Kea
        # under WSL ASLR. Change only this test process's personality, then load
        # runtimes into Kea; setarch itself must not inherit LD_PRELOAD.
        + f"exec {shlex.quote(setarch)} {shlex.quote(platform.machine())} -R env "
        + " ".join(shlex.quote(f"{key}={value}") for key, value in values.items())
        + f" {shlex.quote(str(server))} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    (logs / "runtime.txt").write_text(
        subprocess.check_output([compiler, "--version"], text=True)
        + f"Kea: {server}\nHook: {build_dir / 'libdhcp_db_commands.so'}\n"
        + "ASLR: disabled for the test Kea process only (setarch -R)\n"
        + "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    print(f"Sanitizer diagnostics: {logs}", flush=True)
    return wrapper, logs


def verify_instrumentation(library):
    symbols = subprocess.check_output(["nm", "-D", str(library)], text=True)
    for marker in ("__asan_init", "__ubsan_handle_"):
        if marker not in symbols:
            raise RuntimeError(f"Missing sanitizer instrumentation {marker}: {library}")
    dependencies = subprocess.check_output(["readelf", "-d", str(library)], text=True)
    for runtime in ("libasan.so", "libubsan.so"):
        if runtime not in dependencies:
            raise RuntimeError(f"Missing sanitizer dependency {runtime}: {library}")
    print(f"PASS: ASan and UBSan instrumentation present in {library}", flush=True)


def verify_detectors(compiler, logs, environment):
    """Compile throwaway faults from stdin; require real reports and failure exits."""
    probes = logs / "probes"
    probes.mkdir()
    faults = {
        "asan": ("int main() { volatile int* p = new int[1]; delete[] p; return *p; }",
                 "heap-use-after-free"),
        "ubsan": ("#include <climits>\nint main() { volatile int n = INT_MAX; return n + 1; }",
                  "signed integer overflow"),
    }
    for name, (source, marker) in faults.items():
        executable = probes / name
        try:
            subprocess.run(
                [compiler, "-x", "c++", "-", "-o", str(executable), "-std=c++14",
                 "-O1", "-g", "-fno-omit-frame-pointer", "-fno-sanitize-recover=all",
                 f"-fsanitize={'address' if name == 'asan' else 'undefined'}", "-no-pie"],
                input=source, text=True, env=environment, check=True,
            )
            probe_environment = environment.copy()
            probe_environment.update(
                ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
                UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
            )
            result = subprocess.run(
                [str(executable)], env=probe_environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20, check=False,
            )
            (probes / f"{name}.txt").write_text(result.stdout, encoding="utf-8")
            if result.returncode == 0 or marker not in result.stdout:
                raise RuntimeError(f"{name.upper()} fault detector failed; inspect {probes}")
            print(f"PASS: intentional {name.upper()} probe detected {marker}", flush=True)
        finally:
            executable.unlink(missing_ok=True)


def verify_logs(logs):
    """Reject reports even if a fixture inadvertently ignored a child exit status."""
    reports = sorted((*logs.glob("asan.*"), *logs.glob("ubsan.*")))
    if not reports:
        raise RuntimeError(f"No sanitizer initialization logs: {logs}")
    for report in reports:
        content = report.read_text(encoding="utf-8", errors="replace")
        if re.search(r"ERROR:|SUMMARY:|DEADLYSIGNAL|runtime error:|LeakSanitizer", content):
            raise RuntimeError(f"Sanitizer finding; inspect {report}")
    launches = (logs / "launches").read_text().splitlines()
    if not launches:
        raise RuntimeError("No sanitized Kea invocations recorded")
    for pid in launches:
        report = logs / f"asan.{pid}"
        if not report.exists() or "AddressSanitizer Init done" not in report.read_text():
            raise RuntimeError(f"ASan did not initialize for Kea PID {pid}; inspect {logs}")
    print(f"PASS: ASan initialized for {len(launches)} Kea invocations; no sanitizer findings",
          flush=True)
