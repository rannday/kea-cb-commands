#!/usr/bin/env python3
"""Download, verify, build, and install the locked, unmodified Kea release."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shlex
import shutil
import subprocess
import sys
import tarfile
import urllib.request


def run(command, env):
    """Print each command before executing it, retaining useful failure output."""
    print("+ " + shlex.join(map(str, command)), flush=True)
    subprocess.run(command, env=env, check=True)


def extract_source(archive, destination, commit):
    """Extract files and internal relative symlinks beneath the expected root."""
    root = "kea-" + commit
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != root
                or not (member.isfile() or member.isdir() or member.issym())
            ):
                raise ValueError(f"Unsafe or unsupported archive member: {member.name}")
            if member.issym():
                link = PurePosixPath(member.linkname)
                resolved = PurePosixPath(posixpath.normpath(str(path.parent / link)))
                if link.is_absolute() or not resolved.parts or resolved.parts[0] != root:
                    raise ValueError(f"Unsafe symlink target: {member.name}")
        links = {PurePosixPath(member.name) for member in members if member.issym()}
        for member in members:
            if any(parent in links for parent in PurePosixPath(member.name).parents):
                raise ValueError(f"Archive member has a symlink parent: {member.name}")
        destination.mkdir()
        for member in members:
            relative = PurePosixPath(member.name).parts[1:]
            target = destination.joinpath(*relative)
            if member.issym():
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            incoming = source.extractfile(member)
            if incoming is None:
                raise ValueError(f"Archive member has no file content: {member.name}")
            with incoming, target.open("xb") as output:
                shutil.copyfileobj(incoming, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
        # Files are complete before links exist, so extraction never follows links.
        for member in members:
            if member.issym():
                target = destination.joinpath(*PurePosixPath(member.name).parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname)
        for link in links:
            target = destination.joinpath(*link.parts[1:])
            try:
                target.resolve(strict=True).relative_to(destination.resolve())
            except (OSError, RuntimeError, ValueError) as error:
                raise ValueError(f"Unsafe or unresolved symlink: {link}") from error


def toolchain_report(path, lock, env):
    """Record actual compiler and dependency versions, including optional probes."""
    commands = [
        [env["CC"], "--version"],
        [env["CXX"], "--version"],
        ["cmake", "--version"],
        ["meson", "--version"],
        ["ninja", "--version"],
        ["pkg-config", "--version"],
        ["pg_config", "--version"],
        ["mariadb_config", "--version"],
        ["mariadbd", "--version"],
        ["pkg-config", "--modversion", "libpq", "mysqlclient", "openssl"],
        [env["CXX"], "-dumpmachine"],
        ["ldd", "--version"],
        ["ld", "--version"],
    ]
    with path.open("w", encoding="utf-8") as report:
        report.write(json.dumps(lock, indent=2) + "\n")
        report.write(f"Python: {sys.version}\n")
        report.write("Environment: LC_ALL=C.UTF-8 TZ=UTC CCACHE_DISABLE=1\n")
        for command in commands:
            report.write("\n+ " + shlex.join(command) + "\n")
            try:
                result = subprocess.run(
                    command,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                report.write(result.stdout)
                report.write(f"exit status: {result.returncode}\n")
            except FileNotFoundError:
                report.write("not installed\n")


def build(work_dir, jobs):
    lock_path = Path(__file__).with_name("kea-source.json")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    work_dir = work_dir.absolute()
    if work_dir.is_symlink() or (work_dir.exists() and any(work_dir.iterdir())):
        raise ValueError("--work-dir must be nonexistent or an empty directory")
    env = os.environ.copy()
    env.update(LC_ALL="C.UTF-8", TZ="UTC", CCACHE_DISABLE="1")
    # Explicit compiler commands prevent Meson's automatic compiler-cache lookup.
    for variable, default in (("CC", "cc"), ("CXX", "c++")):
        compiler = env.get(variable, default)
        if len(shlex.split(compiler)) != 1 or Path(compiler).name in {
            "ccache",
            "sccache",
        }:
            raise ValueError(f"{variable} must name a compiler without a cache launcher")
        resolved = shutil.which(compiler)
        if not resolved:
            raise ValueError(f"Required compiler unavailable: {compiler}")
        env[variable] = resolved
    for tool in (
        "meson",
        "ninja",
        "pkg-config",
        "cmake",
        "pg_config",
        "mariadb_config",
    ):
        if not shutil.which(tool):
            raise ValueError(f"Required build tool unavailable: {tool}")
    work_dir.mkdir(parents=True, exist_ok=True)
    toolchain_report(work_dir / "toolchain.txt", lock, env)
    archive = work_dir / "kea.tar.gz"
    print(f"Downloading Kea {lock['version']} from {lock['url']}", flush=True)
    with (
        urllib.request.urlopen(lock["url"], timeout=60) as incoming,
        archive.open("xb") as output,
    ):
        shutil.copyfileobj(incoming, output)
    digest = hashlib.sha256()
    with archive.open("rb") as incoming:
        for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != lock["sha256"]:
        raise ValueError("Downloaded source SHA-256 does not match scripts/kea-source.json")
    print(f"Verified SHA-256: {digest.hexdigest()}", flush=True)
    source = work_dir / "source"
    build_dir = work_dir / "build"
    prefix = work_dir / "install"
    extract_source(archive, source, lock["commit"])
    run(
        [
            "meson",
            "setup",
            str(build_dir),
            str(source),
            f"--prefix={prefix}",
            "--libdir=lib",
            "--buildtype=release",
            "-Dcpp_std=c++14",
            "-Dcrypto=openssl",
            "-Dmysql=enabled",
            "-Dpostgresql=enabled",
            "-Dkrb5=disabled",
            "-Dnetconf=disabled",
            "-Dtests=disabled",
            "-Dfuzz=disabled",
        ],
        env,
    )
    # Meson's report includes Boost/log4cplus versions and resolved feature flags.
    shutil.copyfile(build_dir / "config.report", work_dir / "config.report")
    run(["meson", "compile", "-C", str(build_dir), "-j", str(jobs)], env)
    run(["meson", "install", "-C", str(build_dir)], env)
    print(f"Kea installation: {prefix}", flush=True)
    print(f"Toolchain report: {work_dir / 'toolchain.txt'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    arguments = parser.parse_args()
    if arguments.jobs < 1:
        parser.error("--jobs must be positive")
    try:
        build(arguments.work_dir, arguments.jobs)
    except (
        OSError,
        ValueError,
        tarfile.TarError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"Kea build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
