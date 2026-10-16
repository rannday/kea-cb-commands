"""Read and mutate disposable PostgreSQL configuration through native Kea APIs."""

# SPDX-License-Identifier: MPL-2.0
import argparse
import base64
import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from mutation import verify_mutations
from lifecycle import verify_lifecycle
from dhcp import _isolated, verify_dhcp, verify_packet_restart
from control import command
from smoke import require_success


def verify_complex(result, expected_ids, tag):
    """Compare typed native fields, ignoring serialization order/default fields."""
    assert result["server-tag"] == tag
    subnets = {subnet["id"]: subnet for subnet in result["subnet4"]}
    assert len(subnets) == len(result["subnet4"]), "Duplicate subnet IDs"
    assert set(subnets) == expected_ids
    subnet = subnets[42]
    assert ipaddress.ip_network(subnet["subnet"]) == ipaddress.ip_network("192.0.2.0/24")
    assert (subnet["valid-lifetime"], subnet["renew-timer"], subnet["rebind-timer"]) == (
        600, 200, 400)
    assert subnet["client-classes"] == ["known"]
    assert subnet["evaluate-additional-classes"] == ["audit"]
    assert subnet["user-context"] == {"fixture": "complex", "enabled": True}
    pools = {tuple(ipaddress.ip_address(part.strip()) for part in pool["pool"].split("-")):
             pool for pool in subnet["pools"]}
    assert len(pools) == len(subnet["pools"]) == 2
    first = (ipaddress.ip_address("192.0.2.10"), ipaddress.ip_address("192.0.2.20"))
    second = (ipaddress.ip_address("192.0.2.100"), ipaddress.ip_address("192.0.2.150"))
    assert set(pools) == {first, second}
    assert pools[first]["client-classes"] == ["pool-class"]
    options = {(option["space"], option["code"]): option for option in subnet["option-data"]}
    assert len(options) == len(subnet["option-data"]) == 2
    assert options[("dhcp4", 3)]["data"] == "192.0.2.1"
    assert [ipaddress.ip_address(value.strip())
            for value in options[("dhcp4", 6)]["data"].split(",")] == [
                ipaddress.ip_address("192.0.2.53"), ipaddress.ip_address("192.0.2.54")]
    assert options[("dhcp4", 6)]["always-send"] is True
    assert options[("dhcp4", 3)]["csv-format"] is True
    pool_options = pools[first]["option-data"]
    assert len(pool_options) == 1
    assert (pool_options[0]["code"], pool_options[0]["data"]) == (15, "pool.example")
    assert pools[second]["option-data"] == []
    other = subnets[45]
    assert (other["subnet"], other["valid-lifetime"], other["renew-timer"],
            other["rebind-timer"]) == ("192.0.3.0/24", 1200, 300, 900)
    assert len(other["pools"]) == 1


def execute(argv, **kwargs):
    """Never echo database/server output: upstream errors may contain secrets."""
    result = subprocess.run(
        [str(item) for item in argv], capture_output=True, timeout=30, **kwargs
    )
    if result.returncode:
        raise AssertionError(f"{Path(argv[0]).name} failed (exit {result.returncode})")
    return result.stdout


def run_case(args, directory, multithreading):
    # Short, private socket path; no TCP listener and no existing cluster touched.
    with tempfile.TemporaryDirectory(prefix="kea-pg-") as socket_directory:
        data = directory / "data"
        pg = args.pg_bin
        pg_started = False
        process = None
        pg_environment = os.environ.copy()
        # Do not inherit production connection, password, service or options.
        for name in list(pg_environment):
            if name.startswith("PG"):
                del pg_environment[name]
        pg_environment["PGPASSFILE"] = str(directory / "absent-pgpass")
        connection = ["-h", socket_directory, "-p", "5432", "-U", "postgres"]

        def sql(statement=None, file=None, database="kea_test"):
            argv = [pg / "psql", "-X", "-v", "ON_ERROR_STOP=1", *connection,
                    "-d", database]
            argv += ["-f", str(file)] if file else ["-At", "-c", statement]
            return execute(argv, env=pg_environment)

        def snapshot():
            dump = execute(
                [pg / "pg_dump", *connection, "-d", "kea_test", "--data-only"],
                env=pg_environment,
            )
            # New PostgreSQL clients randomize psql's dump restriction token.
            return b"\n".join(
                line for line in dump.splitlines()
                if not line.startswith((b"\\restrict ", b"\\unrestrict "))
            )

        try:
            execute([pg / "initdb", "-D", data, "-U", "postgres", "--no-locale",
                     "-E", "UTF8", "--auth-local=trust", "--auth-host=reject"],
                    env=pg_environment)
            # Startup may fail after creating a running postmaster. Cleanup must
            # inspect this private cluster even when pg_ctl never reports success.
            pg_started = True
            execute([pg / "pg_ctl", "-D", data, "-l", directory / "postgres.log",
                     "-o", f"-k {socket_directory} -h '' -p 5432", "-t", "15",
                     "-w", "start"], env=pg_environment)
            sql("CREATE DATABASE kea_test", database="postgres")
            # Official schema documents direct psql initialization in its header.
            sql(file=args.schema)
            sql("CREATE ROLE kea_reader LOGIN; "
                "GRANT CONNECT ON DATABASE kea_test TO kea_reader; "
                "GRANT USAGE ON SCHEMA public TO kea_reader; "
                "GRANT SELECT ON ALL TABLES IN SCHEMA public TO kea_reader; "
                "ALTER ROLE kea_reader SET default_transaction_read_only=on")
            schema_version = sql("SELECT version || '.' || minor FROM schema_version")

            password = secrets.token_urlsafe(24)
            credentials = directory / "http-credentials"
            credentials.write_text(f"test:{password}", encoding="ascii")
            credentials.chmod(0o600)
            authorization = "Basic " + base64.b64encode(
                f"test:{password}".encode("ascii")
            ).decode("ascii")
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]

            def send(name, arguments=None):
                return command(port, name, arguments, authorization=authorization)

            config = {"Dhcp4": {
                "interfaces-config": {"interfaces": []},
                "lease-database": {"type": "memfile", "persist": False},
                "valid-lifetime": 600,
                "subnet4": [],
                "multi-threading": {"enable-multi-threading": multithreading},
                "config-control": {"config-fetch-wait-time": 0, "config-databases": [{
                    "type": "postgresql", "host": socket_directory, "port": 5432,
                    "name": "kea_test", "user": "kea_reader",
                    "on-fail": "serve-retry-continue",
                    "max-reconnect-tries": 30, "reconnect-wait-time": 1000,
                }]},
                "hooks-libraries": [],
                "control-sockets": [{
                    "socket-type": "http", "socket-address": "127.0.0.1",
                    "socket-port": port,
                    "authentication": {"type": "basic", "realm": "read-test",
                                       "clients": [{"password-file": str(credentials)}]},
                }],
                "loggers": [{"name": "kea-dhcp4", "severity": "WARN",
                             "output-options": [{"output": "stdout"}]}],
            }}
            # Kea enforces one hook directory. Stage both matching libraries.
            hook_directory = directory / "hooks"
            hook_directory.mkdir()
            for library in (args.pgsql_hook, args.hook):
                target = hook_directory / library.name
                shutil.copy2(library, target)
                config["Dhcp4"]["hooks-libraries"].append({"library": str(target)})
            config_path = directory / "kea.json"

            def save():
                config_path.write_text(json.dumps(config), encoding="utf-8")
                config_path.chmod(0o600)

            save()
            environment = pg_environment.copy()
            environment.update(KEA_PIDFILE_DIR=str(directory),
                               KEA_LOCKFILE_DIR=str(directory),
                               KEA_DHCP_DATA_DIR=str(directory),
                               KEA_HOOKS_PATH=str(hook_directory))
            if args.packet:
                environment["KEA_LFC_EXECUTABLE"] = str(args.lfc.resolve())
            with (directory / "kea.log").open("w", encoding="utf-8") as log:
                execute([args.server, "-T", config_path], env=environment, cwd=directory)
                process = subprocess.Popen(
                    [str(args.server), "-d", "-c", str(config_path),
                     *(["-p", "1067", "-P", "1068"] if args.packet else [])], env=environment,
                    cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                )
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        raise AssertionError("Kea exited during PostgreSQL startup")
                    try:
                        names = require_success(send("list-commands"))
                        break
                    except (OSError, ValueError):
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.1)
                assert "cb-subnet4-list" in names
                before = snapshot()
                for arguments in (None, {}):
                    result = require_success(send("cb-subnet4-list", arguments))
                    assert result == {"subnet4": [], "server-tag": "all"}
                assert before == snapshot(), "Empty read changed database contents"

                sql(file=Path(__file__).with_name("subnet4_fixture.sql"))
                before = snapshot()
                result = require_success(send("cb-subnet4-list"))
                verify_complex(result, {42, 45}, "all")
                # The runtime configuration remains empty: this was a fresh SQL read.
                assert require_success(send("config-get"))["Dhcp4"]["subnet4"] == []
                for arguments in ({"unexpected": True}, [], "invalid", 0, False,
                                  {"backend-index": 0}, {"server-tag": "other-server"}):
                    assert send("cb-subnet4-list", arguments)["result"] == 1
                require_success(send("db-commands-diagnostic"))
                config["Dhcp4"]["server-tag"] = "test-server"
                save()
                require_success(send("config-reload"))
                tagged = require_success(send("cb-subnet4-list"))
                verify_complex(tagged, {42, 43, 45}, "test-server")
                assert before == snapshot(), "Read commands changed database contents"

                # A missing server tag still receives universal objects, not
                # objects for other tags or unassigned rows.
                config["Dhcp4"]["server-tag"] = "missing-server"
                save()
                require_success(send("config-reload"))
                verify_complex(require_success(send("cb-subnet4-list")),
                               {42, 45}, "missing-server")

                # A populated database can have no matching rows. Removing the
                # universal associations leaves only other tags/unassigned rows.
                sql("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                    "'empty selection fixture', false); "
                    "DELETE FROM dhcp4_subnet_server WHERE server_id=1; COMMIT")
                before_empty = snapshot()
                assert require_success(send("cb-subnet4-list")) == {
                    "subnet4": [], "server-tag": "missing-server"}
                assert before_empty == snapshot()
                sql("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                    "'restore selection fixture', false); "
                    "INSERT INTO dhcp4_subnet_server(subnet_id, server_id) "
                    "VALUES (42, 1), (45, 1); COMMIT")

                # No native name/index selector exists to distinguish these
                # two databases on one host. Even disjoint data must fail closed.
                sql("CREATE DATABASE kea_second", database="postgres")
                sql(file=args.schema, database="kea_second")
                sql("GRANT CONNECT ON DATABASE kea_second TO kea_reader; "
                    "GRANT USAGE ON SCHEMA public TO kea_reader; "
                    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO kea_reader",
                    database="kea_second")
                original = config["Dhcp4"]["config-control"]["config-databases"][0]
                databases = config["Dhcp4"]["config-control"]["config-databases"]
                databases.append(dict(original, name="kea_second"))
                save()
                require_success(send("config-reload"))
                assert send("cb-subnet4-set", {"server-tag": "all", "subnet4": {
                    "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600}})["result"] == 1
                ambiguous = send("cb-subnet4-list")
                assert ambiguous["result"] == 1 and "multiple backends" in ambiguous["text"]
                for name, arguments in (("cb-subnet4-get", {"id": 42}),
                                        ("cb-subnet4-del", {"id": 42, "server-tag": "all",
                                                            "preserve-leases": True})):
                    response = send(name, arguments)
                    assert response["result"] == 1 and "exactly one" in response["text"]
                sql("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                    "'overlap fixture', false); "
                    "INSERT INTO dhcp4_subnet(subnet_id, subnet_prefix, valid_lifetime) "
                    "VALUES (42, '10.0.0.0/24', 600); "
                    "INSERT INTO dhcp4_subnet_server(subnet_id, server_id) VALUES (42, 1); "
                    "COMMIT", database="kea_second")
                assert send("cb-subnet4-list") == ambiguous
                for name, arguments in (("cb-subnet4-get", {"id": 42}),
                                        ("cb-subnet4-del", {"id": 42, "server-tag": "all",
                                                            "preserve-leases": True})):
                    assert send(name, arguments)["result"] == 1
                databases.pop()
                save()
                require_success(send("config-reload"))
                verify_complex(require_success(send("cb-subnet4-list")),
                               {42, 45}, "missing-server")

                # A duplicate ID in one database is rejected by the official
                # schema. No invented merge/last-writer semantics in the hook.
                sql("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                    "'duplicate fixture', false); "
                    "DO $$ BEGIN BEGIN "
                    "INSERT INTO dhcp4_subnet(subnet_id, subnet_prefix) "
                    "VALUES (42, '10.1.0.0/24'); "
                    "EXCEPTION WHEN unique_violation THEN RETURN; END; "
                    "RAISE EXCEPTION 'Official schema accepted a duplicate ID'; "
                    "END $$; COMMIT")

                # Native flat serialization omits the shared network's name
                # and inherited configuration. Refuse the entire result.
                sql("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                    "'shared fixture', false); "
                    "INSERT INTO dhcp4_shared_network(name, valid_lifetime) VALUES ('shared', 900); "
                    "UPDATE dhcp4_subnet SET shared_network_name='shared' WHERE subnet_id=42; "
                    "COMMIT")
                shared_before = snapshot()
                shared = send("cb-subnet4-list")
                assert shared["result"] == 1 and "Shared-network" in shared["text"]
                assert "arguments" not in shared
                assert shared_before == snapshot()
                sql("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                    "'restore fixture', false); "
                    "UPDATE dhcp4_subnet SET shared_network_name=NULL WHERE subnet_id=42; COMMIT")

                active_before_outage = require_success(send("config-get"))
                execute([pg / "pg_ctl", "-D", data, "-m", "fast", "-w", "stop"],
                        env=pg_environment)
                pg_started = False
                assert send("config-backend-pull")["result"] != 0
                assert send("cb-subnet4-set", {"server-tag": "all", "subnet4": {
                    "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600}})["result"] == 1
                # Native reconnect removes the broken backend: a subsequent
                # pull can succeed as a no-op. Check runtime, not status alone.
                require_success(send("config-backend-pull"))
                assert require_success(send("config-get")) == active_before_outage
                response = send("cb-subnet4-list")
                assert response == {
                    "result": 1,
                    "text": "Configuration backend read failed or unavailable.",
                }, "Backend failure response changed or exposed details"
                assert send("cb-subnet4-get", {"id": 42}) == response
                failed_delete = send("cb-subnet4-del", {
                    "id": 42, "server-tag": "all", "preserve-leases": True})
                assert failed_delete == {"result": 1, "text": (
                    "Configuration backend deletion failed or unavailable; "
                    "reconcile backend state before retrying.")}
                # Allow native retry callbacks to remove the unusable backend;
                # reads must remain errors rather than successful empty lists.
                unavailable_until = time.monotonic() + 2
                while time.monotonic() < unavailable_until:
                    assert send("cb-subnet4-list") == response
                    time.sleep(0.2)
                # Restart only the private cluster. Kea's own posted recovery
                # callback replaces the connection; no config reload or hook retry.
                pg_started = True
                execute([pg / "pg_ctl", "-D", data, "-l", directory / "postgres.log",
                         "-o", f"-k {socket_directory} -h '' -p 5432", "-t", "15",
                         "-w", "start"], env=pg_environment)
                deadline = time.monotonic() + 15
                while True:
                    recovered = send("cb-subnet4-list")
                    if recovered["result"] == 0:
                        verify_complex(require_success(recovered), {42, 45}, "missing-server")
                        break
                    assert recovered == response
                    assert time.monotonic() < deadline, "Native PostgreSQL recovery timed out"
                    time.sleep(0.2)
                before = snapshot()
                verify_complex(require_success(send("cb-subnet4-list")),
                               {42, 45}, "missing-server")
                assert before == snapshot(), "Recovered read changed database contents"
                # Separate native mutation phase: preserve the SELECT-only read proof.
                sql("CREATE ROLE kea_writer LOGIN; "
                    "GRANT CONNECT ON DATABASE kea_test TO kea_writer; "
                    "GRANT USAGE ON SCHEMA public TO kea_writer; "
                    "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO kea_writer; "
                    "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO kea_writer")
                config["Dhcp4"]["config-control"]["config-databases"][0]["user"] = "kea_writer"

                def rows_snapshot():
                    # PostgreSQL sequences are nontransactional; compare table
                    # contents, not consumed audit IDs from rolled-back writes.
                    return b"\n".join(line for line in snapshot().splitlines()
                                      if not line.startswith(b"SELECT pg_catalog.setval("))

                verify_mutations(
                    send, rows_snapshot, sql, config, save,
                    lambda: sql("REVOKE INSERT ON dhcp4_subnet_server FROM kea_writer"),
                    lambda: sql("GRANT INSERT ON dhcp4_subnet_server TO kea_writer"))
                verify_lifecycle(send, rows_snapshot, sql, config, save)
                if args.packet:
                    verify_dhcp(send, config, save, directory, rows_snapshot)
                require_success(send("shutdown"))
                assert process.wait(timeout=10) == 0
                process = subprocess.Popen(
                    [str(args.server), "-d", "-c", str(config_path),
                     *(["-p", "1067", "-P", "1068"] if args.packet else [])], env=environment,
                    cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                )
                deadline = time.monotonic() + 15
                while True:
                    try:
                        active = require_success(send("config-get"))["Dhcp4"]["subnet4"]
                        assert {row["id"]: row["subnet"] for row in active}[900] == "198.18.4.0/24"
                        assert not {920, 921} & {row["id"] for row in active}
                        pools = {row["id"]: row["pools"] for row in active}
                        assert pools[900][0]["pool"].replace(" ", "") == "198.18.4.10-198.18.4.20"
                        break
                    except (OSError, ValueError):
                        assert process.poll() is None and time.monotonic() < deadline
                        time.sleep(0.1)
                if args.packet:
                    verify_packet_restart(send, directory)
                require_success(send("shutdown"))
                assert process.wait(timeout=10) == 0
                print("PASS: persisted subnet loaded after actual Kea process restart")
            print(f"PASS: PostgreSQL schema {schema_version.decode().strip()}, "
                  f"MT={multithreading}: complex fields, tags, ambiguity, shared-network "
                  "rejection, nonmutating reads, native mutations and rollback, "
                  "native recovery, shutdown")
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if pg_started:
                status = subprocess.run(
                    [str(pg / "pg_ctl"), "-D", str(data), "status"],
                    capture_output=True, env=pg_environment, timeout=5,
                )
                if status.returncode == 0:
                    execute([pg / "pg_ctl", "-D", data, "-m", "immediate",
                             "-t", "15", "-w", "stop"], env=pg_environment)
                elif status.returncode != 3:
                    raise AssertionError("Could not verify private PostgreSQL shutdown")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("server", "hook", "pgsql-hook", "schema", "pg-bin", "work-dir"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--packet", action="store_true",
                        help="run DORA inside the packet namespace runner")
    parser.add_argument("--lfc", type=Path, help="matching Kea lease-file cleanup executable")
    args = parser.parse_args()
    if args.packet:
        _isolated()
    dependencies = [args.server, args.hook, args.pgsql_hook, args.schema]
    if args.packet:
        if args.lfc is None:
            print("SKIP: packet tests require --lfc with a matching kea-lfc executable")
            return 77
        dependencies.append(args.lfc)
    for binary in ("initdb", "pg_ctl", "psql", "pg_dump"):
        dependencies.append(args.pg_bin / binary)
    missing = [str(path) for path in dependencies if not path.is_file()]
    if missing or os.geteuid() == 0:
        print("SKIP: requires non-root user, matching Kea server/PG hook/schema and "
              "PostgreSQL binaries; missing: " + ", ".join(missing))
        return 77
    for name in ("server", "hook", "pgsql_hook", "schema", "pg_bin"):
        setattr(args, name, getattr(args, name).resolve())
    version = execute([args.server, "-v"]).decode().strip()
    if not version.startswith("3.2.1"):
        raise AssertionError("PostgreSQL milestone requires Kea 3.2.1")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    for multithreading in (False, True):
        with tempfile.TemporaryDirectory(dir=args.work_dir.resolve()) as temporary:
            run_case(args, Path(temporary), multithreading)
    print("PASS: isolated clusters stopped and temporary data removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
