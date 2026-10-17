"""External installation acceptance using the published hook, never a local build."""

import base64
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time

from control import command
from dhcp import CLIENT_PORT, RELAY, SERVER, _lease, _packet, _receive
from smoke import require_success, run_case

PREFIX = Path("/opt/kea/install")
HOOK = PREFIX / "lib/kea/hooks/libdhcp_db_commands.so"
SERVER_BIN = PREFIX / "sbin/kea-dhcp4"
EVIDENCE = Path("/evidence")
PASSWORD = "docker-only-not-a-secret"  # Public disposable fixture, never a real credential.
TAG = "all"
AUTH = "Basic " + base64.b64encode(b"docker-test:docker-test").decode()


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=60, **kwargs)


def initialize(backend, database):
    """Create only this run's disposable schema using Kea's native installer."""
    if backend == "pgsql":
        env = dict(os.environ, PGPASSWORD=PASSWORD)
        client = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-h", "postgres",
                  "-U", "kea_test", "-d", "postgres"]
        run([*client, "-c", f"DROP DATABASE IF EXISTS {database}"] , env=env)
        run([*client, "-c", f"CREATE DATABASE {database}"] , env=env)
        version = run([*client, "-At", "-c", "SHOW server_version"], env=env,
                      capture_output=True, text=True).stdout.strip()
        assert version.startswith("18.") and version.split()[0][3:].isdigit(), version
        user, host = "kea_test", "postgres"
    else:
        env = dict(os.environ, MYSQL_PWD=PASSWORD)
        client = ["mariadb", "--no-defaults", "-h", "mariadb", "-u", "root"]
        run(client, input=(f"DROP DATABASE IF EXISTS {database}; CREATE DATABASE {database};"
                           "CREATE USER IF NOT EXISTS 'kea_test'@'%' IDENTIFIED BY "
                           f"'{PASSWORD}'; GRANT ALL ON {database}.* TO 'kea_test'@'%';"
                           ).encode(), env=env)
        version = run([*client, "-N", "-B", "-e", "SELECT VERSION()"], env=env,
                      capture_output=True, text=True).stdout.strip()
        assert version.startswith("12.3.") and "-MariaDB" in version, version
        user, host = "kea_test", "mariadb"
    with (EVIDENCE / "database-versions.jsonl").open("a") as output:
        output.write(json.dumps({"backend": backend, "database": database,
                                 "server-version": version}) + "\n")
    print(f"{backend} server: {version}", flush=True)
    # kea-admin uses its matching installed schema and SQL clients.
    run([str(PREFIX / "sbin/kea-admin"), "db-init", backend,
         "-h", host, "-u", user, "-p", PASSWORD, "-n", database])
    return {"type": "postgresql" if backend == "pgsql" else "mysql",
            "host": host, "user": user, "password": PASSWORD, "name": database}


def dora(directory, first, last):
    """Use only container loopback; reuse the existing wire and lease validators."""
    assert SERVER == ("127.0.0.1", 1067) and RELAY == "127.0.0.2"
    assert Path("/.dockerenv").exists(), "Packet harness must run inside Docker"
    xid, hardware = secrets.randbits(32), b"\x02" + secrets.token_bytes(5)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind((RELAY, CLIENT_PORT))
        receiver.sendto(_packet(1, xid, hardware), SERVER)
        if first is None:
            try:
                _receive(receiver, xid, hardware, 2, timeout=0.5)
            except socket.timeout:
                return
            raise AssertionError("Unexpected offer before activation or after deletion")
        address, offered = _receive(receiver, xid, hardware, 2)
        assert ipaddress.IPv4Address(first) <= ipaddress.IPv4Address(address) <= (
            ipaddress.IPv4Address(last))
        receiver.sendto(_packet(3, xid, hardware, address, offered[54]), SERVER)
        acknowledged, options = _receive(receiver, xid, hardware, 5)
        assert acknowledged == address and options[54] == offered[54]
    _lease(directory, address, hardware)
    print(f"PASS: DORA and active 600-second lease {address}", flush=True)


def case(backend, multithreading):
    directory = EVIDENCE / f"{backend}-mt-{str(multithreading).lower()}"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir()
    connection = initialize(backend, f"docker_{backend}_{int(multithreading)}")
    credentials = directory / "test-credentials"
    credentials.write_text("docker-test:docker-test", encoding="ascii")
    config = {"Dhcp4": {
        "interfaces-config": {"interfaces": ["lo/127.0.0.1"], "dhcp-socket-type": "udp"},
        "lease-database": {"type": "memfile", "persist": True,
                           "name": str(directory / "leases.csv"), "lfc-interval": 0},
        "valid-lifetime": 600, "subnet4": [], "server-tag": TAG,
        "multi-threading": {"enable-multi-threading": multithreading,
                            "thread-pool-size": 2, "packet-queue-size": 64},
        "hooks-libraries": [
            {"library": str(PREFIX / f"lib/kea/hooks/libdhcp_{backend}.so")},
            {"library": str(HOOK)}],
        "config-control": {"config-fetch-wait-time": 0, "config-databases": [connection]},
        "control-sockets": [{"socket-type": "http", "socket-address": "127.0.0.1",
                             "socket-port": 18000,
                             "authentication": {"type": "basic", "clients": [
                                 {"password-file": str(credentials)}]}}],
        "loggers": [{"name": "kea-dhcp4", "severity": "DEBUG", "debuglevel": 99,
                     "output-options": [{"output": "stdout"}]}],
    }}
    config_path = directory / "kea.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    env = dict(os.environ, KEA_PIDFILE_DIR=str(directory), KEA_LOCKFILE_DIR=str(directory),
               KEA_DHCP_DATA_DIR=str(directory), KEA_HOOKS_PATH=str(HOOK.parent))
    process = None
    log = (directory / "kea.log").open("w")

    def send(name, arguments=None):
        response = command(18000, name, arguments, authorization=AUTH)
        # Record command-level evidence without config-get (which includes credentials).
        if name != "config-get":
            with (directory / "commands.jsonl").open("a") as stream:
                stream.write(json.dumps({"command": name, "arguments": arguments,
                                         "response": response}) + "\n")
        return response

    def start():
        run([str(SERVER_BIN), "-T", str(config_path)], env=env, stdout=log,
            stderr=subprocess.STDOUT)
        child = subprocess.Popen([str(SERVER_BIN), "-d", "-c", str(config_path),
                                  "-p", "1067", "-P", "1068"],
                                 env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while True:
                assert child.poll() is None, "Kea exited: inspect kea.log"
                try:
                    names = require_success(send("list-commands"))
                    assert all(name in names for name in (
                        "cb-subnet4-list", "cb-subnet4-get", "cb-subnet4-set", "cb-subnet4-del"))
                    return child
                except (OSError, ValueError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
        except BaseException:
            child.terminate()
            child.wait(timeout=10)
            raise

    def subnets(name="cb-subnet4-list"):
        value = require_success(send(name))
        return value["Dhcp4"]["subnet4"] if name == "config-get" else value["subnet4"]

    def persist(pools):
        subnet = {"id": 910, "subnet": "127.0.0.0/24", "valid-lifetime": 600}
        if pools is not None:
            subnet["pools"] = pools
        value = require_success(send("cb-subnet4-set", {"server-tag": TAG, "subnet4": subnet}))
        assert value["persisted"] is True and value["activation-requested"] is False

    try:
        process = start()
        assert subnets() == []
        assert require_success(send("db-commands-diagnostic"))["kea-hooks-version"] == 30201
        assert send("cb-subnet4-get", {"id": 910})["result"] == 3
        for name in ("cb-subnet4-list", "cb-subnet4-get", "cb-subnet4-set", "cb-subnet4-del"):
            assert send(name, {"unexpected": True})["result"] == 1
        persist([{"start": "127.0.0.10", "end": "127.0.0.20"}])
        assert subnets()[0]["id"] == 910
        require_success(send("cb-subnet4-get", {"subnet": "127.0.0.0/24", "server-tag": TAG}))
        assert subnets("config-get") == []
        dora(directory, None, None)
        require_success(send("config-reload"))
        dora(directory, "127.0.0.10", "127.0.0.20")
        before = subnets()
        persist(None)
        assert subnets() == before, "Omitted pools were not preserved"
        assert send("cb-subnet4-set", {"server-tag": TAG, "subnet4": {
            "id": 911, "subnet": "127.0.0.0/24", "valid-lifetime": 600}})["result"] == 1
        assert subnets() == before, "Failed conflict changed persisted configuration"
        persist([{"start": "127.0.0.30", "end": "127.0.0.40"}])
        assert "127.0.0.30" in subnets()[0]["pools"][0]["pool"]
        require_success(send("shutdown"))
        assert process.wait(timeout=10) == 0
        process = start()
        assert "127.0.0.30" in subnets("config-get")[0]["pools"][0]["pool"]
        dora(directory, "127.0.0.30", "127.0.0.40")
        persist([])
        assert subnets()[0]["pools"] == []
        require_success(send("config-reload"))
        dora(directory, None, None)
        before_leases = (directory / "leases.csv").read_bytes()
        result = require_success(send("cb-subnet4-del", {
            "id": 910, "server-tag": TAG, "preserve-leases": True}))
        assert result["leases-deleted"] is False
        assert send("cb-subnet4-get", {"id": 910})["result"] == 3
        assert subnets() == [] and subnets("config-get")[0]["id"] == 910
        require_success(send("config-reload"))
        assert subnets("config-get") == []
        dora(directory, None, None)
        assert (directory / "leases.csv").read_bytes() == before_leases
        require_success(send("shutdown"))
        assert process.wait(timeout=10) == 0
        print(f"PASS: {backend}, multithreading={multithreading}: registration, CRUD, pools, "
              "conflict recovery, restart persistence, explicit activation, DORA, retained leases",
              flush=True)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        log.close()
        # Keep useful logs/leases but no credential-bearing generated configuration.
        config_path.unlink(missing_ok=True)
        credentials.unlink(missing_ok=True)


def main():
    assert Path("/etc/os-release").read_text().find('VERSION_ID="24.04"') >= 0
    assert os.uname().machine == "x86_64"
    version = subprocess.check_output([str(SERVER_BIN), "-v"], text=True).strip()
    assert version in ("3.2.1", "3.2.1-git"), version
    print(f"Ubuntu 24.04 x86_64; Kea {version}", flush=True)
    with (EVIDENCE / "dependencies.txt").open("w") as output:
        for library in (HOOK, HOOK.parent / "libdhcp_pgsql.so", HOOK.parent / "libdhcp_mysql.so"):
            deps = subprocess.check_output(["ldd", str(library)], text=True)
            assert "not found" not in deps, deps
            output.write(str(library) + "\n" + deps)
    symbols = subprocess.check_output(["nm", "-D", "--defined-only", str(HOOK)], text=True)
    exports = {line.split()[-1] for line in symbols.splitlines()}
    assert {"version", "load", "unload", "multi_threading_compatible"} <= exports
    (EVIDENCE / "exports.txt").write_text(symbols)
    for source in (Path("/opt/release/provenance.json"), Path("/opt/release/manifest.json"),
                   Path("/opt/kea/runtime-packages.txt"), Path("/opt/kea/toolchain.txt"),
                   Path("/opt/kea/config.report")):
        shutil.copyfile(source, EVIDENCE / source.name)
    for multithreading in (False, True):
        lifecycle = EVIDENCE / f"lifecycle-{int(multithreading)}"
        lifecycle.mkdir(exist_ok=True)
        try:
            # The pinned published v0.1.0 predates mutation admission.
            run_case(SERVER_BIN, HOOK, lifecycle, multithreading, mutation_admission=False)
        finally:
            for name in ("kea.json", "test-credentials"):
                (lifecycle / name).unlink(missing_ok=True)
    (EVIDENCE / "database-versions.jsonl").unlink(missing_ok=True)
    for backend in ("pgsql", "mysql"):
        for multithreading in (False, True):
            case(backend, multithreading)
    print("PASS: published release Docker validation (four SQL/threading cases)", flush=True)


if __name__ == "__main__":
    main()
