"""Opt-in isolated native MySQL/MariaDB configuration backend integration."""

# SPDX-License-Identifier: MPL-2.0
import argparse
import base64
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from mutation import configure_admission, request, verify_mutations
from lifecycle import verify_lifecycle
from records4 import verify_records, verify_records_restart
from options4 import verify_options, verify_options_restart
from scoped_options4 import verify_scoped_options, verify_scoped_options_restart
from shared_network4 import (
    prepare_shared_network_restart, verify_shared_network_membership,
    verify_shared_networks, verify_shared_networks_restart,
)
from concurrency import verify_multiprocess
from dhcp import _isolated, verify_dhcp, verify_packet_restart
from control import command
from postgresql import verify_complex
from smoke import require_success


def execute(argv, *, input: bytes | None = None, env: Mapping[str, str] | None = None,
            cwd: Path | None = None) -> bytes:
    """Keep database output private; error text can include credentials."""
    with subprocess.Popen(
        [str(item) for item in argv], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, env=env, cwd=cwd
    ) as process:
        try:
            output, error = process.communicate(input=input, timeout=30)
        except subprocess.TimeoutExpired:
            # An installer can spawn a bootstrap server; kill its whole group.
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise AssertionError(f"{Path(argv[0]).name} timed out") from None
        if process.returncode:
            code = re.search(rb"ERROR (\d+) \(([0-9A-Z]+)\)", error)
            detail = f"; SQL error {code[1].decode()} state {code[2].decode()}" if code else ""
            raise AssertionError(f"{Path(argv[0]).name} failed (exit {process.returncode}{detail})")
        return output


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_case(args, directory, multithreading):
    # Short Unix socket, private data directory, and no TCP database listener.
    with tempfile.TemporaryDirectory(prefix="kea-mysql-") as socket_directory:
        database_socket = Path(socket_directory) / "mysql.sock"
        data = directory / "data"
        environment = os.environ.copy()
        for name in list(environment):
            if name.startswith(("MYSQL", "MARIADB")):
                del environment[name]
        environment.update(
            MYSQL_HOME=str(directory),
            MYSQL_TEST_LOGIN_FILE=str(directory / "absent-login-file"),
            MYSQL_UNIX_PORT=str(database_socket),
        )
        connection = ["--no-defaults", "--protocol=socket",
                      f"--socket={database_socket}", "--user=root"]

        def sql(statement=None, file=None, database="kea_test", user=None):
            if file is not None:
                content = file.read_bytes()
            else:
                if statement is None:
                    raise ValueError("SQL statement or file required")
                content = statement.encode("utf-8")
            return execute([args.mysql_bin, *connection, *([f"--user={user}"] if user else []),
                            "--batch", "--skip-column-names",
                            database], input=content, env=environment)

        def snapshot(database="kea_test"):
            # Capture all table contents without volatile dump headers or metadata.
            tables = sql("SHOW TABLES", database=database).decode("ascii").splitlines()
            statements = ";".join(
                f"SELECT '__kea_table_{table}'; SELECT * FROM `{table}`" for table in tables)
            result = {}
            current = None
            for line in sql(statements, database=database).splitlines():
                if line.startswith(b"__kea_table_"):
                    current = line.removeprefix(b"__kea_table_").decode("ascii")
                    assert current in tables
                    result[current] = []
                else:
                    assert current is not None
                    result[current].append(line)
            assert set(result) == set(tables)
            return {table: sorted(rows) for table, rows in result.items()}

        database_process = None
        kea_process = None
        try:
            execute([args.mysql_install_db, "--no-defaults", f"--datadir={data}",
                     "--auth-root-authentication-method=normal", "--skip-test-db"],
                    env=environment, cwd=directory)
            with (directory / "mysql.log").open("w", encoding="utf-8") as database_log:
                def start_database():
                    process = subprocess.Popen(
                        [str(args.mysql_server), "--no-defaults", f"--datadir={data}",
                         f"--socket={database_socket}", f"--pid-file={directory / 'mysql.pid'}",
                         "--skip-networking"],
                        env=environment, cwd=directory, stdout=database_log,
                        stderr=subprocess.STDOUT,
                    )
                    deadline = time.monotonic() + 15
                    try:
                        while True:
                            if process.poll() is not None:
                                raise AssertionError("Private MySQL server exited during startup")
                            try:
                                sql("SELECT 1", database="mysql")
                                return process
                            except AssertionError:
                                if time.monotonic() >= deadline:
                                    raise AssertionError("Private MySQL startup timed out") from None
                                time.sleep(0.1)
                    except BaseException:
                        stop(process)
                        raise

                database_process = start_database()
                sql("CREATE DATABASE kea_test", database="mysql")
                sql(file=args.schema)
                reader = "kea_reader_" + secrets.token_hex(8)
                # Native Kea prepares write statements even for read commands.
                # Restrict grants to this disposable schema; never grant DDL.
                privileges = ("SELECT" if args.select_only else
                              "SELECT, INSERT, UPDATE, DELETE")
                sql(f"CREATE USER '{reader}'@'localhost'; "
                    f"GRANT {privileges} ON kea_test.* TO '{reader}'@'localhost'")
                grants = sql(f"SHOW GRANTS FOR '{reader}'@'localhost'")
                assert b"SELECT" in grants and b"ALL PRIVILEGES" not in grants
                assert b"CREATE" not in grants and b"ALTER" not in grants and b"DROP" not in grants
                assert (b"INSERT" in grants) == (not args.select_only)
                schema_version = sql("SELECT CONCAT(version, '.', minor) FROM schema_version")

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

                config: dict[str, Any] = {"Dhcp4": {
                    "interfaces-config": {"interfaces": []},
                    "lease-database": {"type": "memfile", "persist": False},
                    "valid-lifetime": 600,
                    "subnet4": [],
                    "multi-threading": {"enable-multi-threading": multithreading},
                    "config-control": {"config-fetch-wait-time": 0, "config-databases": [{
                        "type": "mysql", "host": "localhost", "name": "kea_test",
                        "user": reader, "on-fail": "serve-retry-continue",
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
                hook_directory = directory / "hooks"
                hook_directory.mkdir()
                for library in (args.mysql_hook, args.hook):
                    target = hook_directory / library.name
                    shutil.copy2(library, target)
                    config["Dhcp4"]["hooks-libraries"].append({"library": str(target)})
                config_path = directory / "kea.json"

                def save():
                    config_path.write_text(json.dumps(config), encoding="utf-8")
                    config_path.chmod(0o600)

                environment.update(KEA_PIDFILE_DIR=str(directory),
                                   KEA_LOCKFILE_DIR=str(directory),
                                   KEA_DHCP_DATA_DIR=str(directory),
                                   KEA_HOOKS_PATH=str(hook_directory))
                if args.packet:
                    environment["KEA_LFC_EXECUTABLE"] = str(args.lfc.resolve())
                if args.designated_writer or args.reconciliation:
                    from designated_writer import verify_designated_writer

                    sql("CREATE USER 'kea_writer'@'localhost'; "
                        "GRANT SELECT,INSERT,UPDATE,DELETE,EXECUTE ON kea_test.* "
                        "TO 'kea_writer'@'localhost'")
                    if args.reconciliation:
                        from recovery import verify_recovery

                        verify_recovery(args, directory, config, environment,
                                        authorization, snapshot, sql)
                    else:
                        verify_designated_writer(args, directory, config, environment,
                                                 authorization, snapshot)
                    return
                if not args.select_only:
                    # Record which native prepared statements require each grant.
                    # Inspect output privately; never echo account names or SQL.
                    for count in range(1, 6):
                        ladder = ("SELECT", "INSERT", "UPDATE", "DELETE", "EXECUTE")[:count]
                        probe = "kea_probe_" + secrets.token_hex(8)
                        sql(f"CREATE USER '{probe}'@'localhost'; GRANT {', '.join(ladder)} "
                            f"ON kea_test.* TO '{probe}'@'localhost'")
                        config["Dhcp4"]["config-control"]["config-databases"][0]["user"] = probe
                        save()
                        before = snapshot()
                        result = subprocess.run(
                            [str(args.server), "-T", str(config_path)],
                            env=environment, cwd=directory, capture_output=True, timeout=30,
                        )
                        output = (result.stdout + result.stderr).lower()
                        if result.returncode:
                            denied = next((name for name in ("insert", "update", "delete", "execute")
                                           if (name + " command denied").encode() in output), None)
                            assert denied, "Privilege probe failed without classified permission denial"
                            assert denied.upper() not in ladder
                            print(f"PASS: native initialization grants={','.join(ladder)} "
                                  f"rejected: {denied.upper()} permission required")
                        else:
                            print(f"PASS: native initialization grants={','.join(ladder)} accepted")
                        assert snapshot() == before, "Initialization probe changed database contents"
                        if count == 5:
                            assert result.returncode == 0, "Functional native grants did not initialize"
                    config["Dhcp4"]["config-control"]["config-databases"][0]["user"] = reader
                save()
                with (directory / "kea.log").open("w", encoding="utf-8") as log:
                    execute([args.server, "-T", config_path], env=environment, cwd=directory)
                    kea_process = subprocess.Popen(
                        [str(args.server), "-d", "-c", str(config_path),
                         *(["-p", "1067", "-P", "1068"] if args.packet else [])],
                        env=environment, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                    )
                    deadline = time.monotonic() + 15
                    while True:
                        if kea_process.poll() is not None:
                            raise AssertionError("Kea exited during MySQL startup")
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
                        assert require_success(send("cb-subnet4-list", arguments)) == {
                            "subnet4": [], "server-tag": "all",
                        }
                    assert snapshot() == before, "Empty read changed database contents"
                    sql("START TRANSACTION; "
                        "CALL createAuditRevisionDHCP4(NOW(), 'all', 'test fixture', 0); "
                        "INSERT INTO dhcp4_subnet "
                        "(subnet_id, subnet_prefix, valid_lifetime, renew_timer, "
                        "rebind_timer, modification_ts) "
                        "VALUES (42, '192.0.2.0/24', 600, 200, 400, NOW()); "
                        "INSERT INTO dhcp4_subnet_server VALUES (42, 1, NOW()); COMMIT")
                    before = snapshot()
                    result = require_success(send("cb-subnet4-list"))
                    assert result["server-tag"] == "all" and len(result["subnet4"]) == 1
                    subnet = result["subnet4"][0]
                    assert {key: subnet[key] for key in (
                        "id", "subnet", "valid-lifetime", "renew-timer", "rebind-timer"
                    )} == {"id": 42, "subnet": "192.0.2.0/24", "valid-lifetime": 600,
                          "renew-timer": 200, "rebind-timer": 400}
                    assert snapshot() == before, "Known-subnet read changed database contents"
                    sql("START TRANSACTION; "
                        "CALL createAuditRevisionDHCP4(NOW(), 'all', 'complex fixture', 0); "
                        "INSERT INTO dhcp4_server(tag, modification_ts) "
                        "VALUES ('test-server', NOW()), ('other-server', NOW()); "
                        "INSERT INTO dhcp4_subnet(subnet_id, subnet_prefix, valid_lifetime, "
                        "renew_timer, rebind_timer, modification_ts) VALUES "
                        "(43, '198.51.100.0/24', 600, 200, 400, NOW()), "
                        "(44, '203.0.113.0/24', 600, 200, 400, NOW()), "
                        "(45, '192.0.3.0/24', 1200, 300, 900, NOW()), "
                        "(46, '192.0.4.0/24', 600, 200, 400, NOW()); "
                        "INSERT INTO dhcp4_subnet_server "
                        "SELECT 43, id, NOW() FROM dhcp4_server WHERE tag='test-server'; "
                        "INSERT INTO dhcp4_subnet_server "
                        "SELECT 44, id, NOW() FROM dhcp4_server WHERE tag='other-server'; "
                        "INSERT INTO dhcp4_subnet_server "
                        "SELECT 45, id, NOW() FROM dhcp4_server WHERE tag='all'; "
                        "UPDATE dhcp4_subnet SET client_classes='[\"known\"]', "
                        "evaluate_additional_classes='[\"audit\"]', "
                        "user_context='{\"fixture\": \"complex\", \"enabled\": true}' "
                        "WHERE subnet_id=42; "
                        "INSERT INTO dhcp4_pool(start_address,end_address,subnet_id,"
                        "client_classes,modification_ts) VALUES "
                        "(INET_ATON('192.0.2.10'),INET_ATON('192.0.2.20'),42,'[\"pool-class\"]',NOW()),"
                        "(INET_ATON('192.0.2.100'),INET_ATON('192.0.2.150'),42,'[]',NOW()),"
                        "(INET_ATON('192.0.3.10'),INET_ATON('192.0.3.30'),45,'[]',NOW()); "
                        "INSERT INTO dhcp4_options(code,formatted_value,space,persistent,"
                        "dhcp4_subnet_id,scope_id,client_classes,modification_ts) VALUES "
                        "(3,'192.0.2.1','dhcp4',0,42,1,'[]',NOW()),"
                        "(6,'192.0.2.53, 192.0.2.54','dhcp4',1,42,1,'[]',NOW()); "
                        "INSERT INTO dhcp4_options(code,formatted_value,space,persistent,"
                        "scope_id,pool_id,client_classes,modification_ts) "
                        "SELECT 15,'pool.example','dhcp4',0,5,id,'[]',NOW() FROM dhcp4_pool "
                        "WHERE start_address=INET_ATON('192.0.2.10'); COMMIT")
                    before = snapshot()
                    result = require_success(send("cb-subnet4-list"))
                    verify_complex(result, {42, 45}, "all")
                    for arguments in ({"unexpected": True}, [], "invalid", 0, False,
                                      {"backend-index": 0}, {"server-tag": "other-server"}):
                        assert send("cb-subnet4-list", arguments)["result"] == 1
                    assert require_success(send("config-get"))["Dhcp4"]["subnet4"] == []
                    config["Dhcp4"]["server-tag"] = "test-server"
                    save()
                    require_success(send("config-reload"))
                    result = require_success(send("cb-subnet4-list"))
                    assert result["server-tag"] == "test-server"
                    verify_complex(result, {42, 43, 45}, "test-server")
                    assert snapshot() == before, "Read commands changed database contents"
                    config["Dhcp4"]["server-tag"] = "missing-server"
                    save()
                    require_success(send("config-reload"))
                    verify_complex(require_success(send("cb-subnet4-list")), {42, 45}, "missing-server")
                    sql("START TRANSACTION; CALL createAuditRevisionDHCP4(NOW(), 'all', 'detach', 0); "
                        "DELETE FROM dhcp4_subnet_server WHERE server_id=1; COMMIT")
                    before = snapshot()
                    assert require_success(send("cb-subnet4-list")) == {
                        "subnet4": [], "server-tag": "missing-server"}
                    assert snapshot() == before
                    sql("START TRANSACTION; CALL createAuditRevisionDHCP4(NOW(), 'all', 'restore', 0); "
                        "INSERT INTO dhcp4_subnet_server VALUES (42,1,NOW()),(45,1,NOW()); COMMIT")
                    before = snapshot()

                    configure_admission(send, config, save, {"allow-mutations": True})
                    # Two official-schema databases, including overlapping subnet IDs.
                    sql("CREATE DATABASE kea_other", database="mysql")
                    sql(file=args.schema, database="kea_other")
                    sql(f"GRANT SELECT,INSERT,UPDATE,DELETE ON kea_other.* TO '{reader}'@'localhost'")
                    databases = config["Dhcp4"]["config-control"]["config-databases"]
                    databases.append(dict(databases[0], name="kea_other"))
                    save()
                    require_success(send("config-reload"))
                    ambiguous = {"result": 1, "text": "cb-subnet4-list requires exactly one configured "
                                 "backend; multiple backends cannot be listed without ambiguity."}
                    assert send("cb-subnet4-set", {"server-tag": "all", "subnet4": {
                        "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600}})["result"] == 1
                    other_before = snapshot("kea_other")
                    assert send("cb-subnet4-list") == ambiguous
                    for name, arguments in (("cb-subnet4-get", {"id": 42}),
                                            ("cb-subnet4-del", {"id": 42, "server-tag": "all",
                                                                "preserve-leases": True})):
                        response = send(name, arguments)
                        assert response["result"] == 1 and "exactly one" in response["text"]
                    assert snapshot("kea_other") == other_before
                    sql("START TRANSACTION; CALL createAuditRevisionDHCP4(NOW(), 'all', 'overlap', 0); "
                        "INSERT INTO dhcp4_subnet(subnet_id,subnet_prefix,valid_lifetime,modification_ts) "
                        "VALUES(42,'10.0.0.0/24',600,NOW()); "
                        "INSERT INTO dhcp4_subnet_server VALUES(42,1,NOW()); COMMIT", database="kea_other")
                    other_before = snapshot("kea_other")
                    assert send("cb-subnet4-list") == ambiguous
                    for name, arguments in (("cb-subnet4-get", {"id": 42}),
                                            ("cb-subnet4-del", {"id": 42, "server-tag": "all",
                                                                "preserve-leases": True})):
                        assert send(name, arguments)["result"] == 1
                    assert snapshot("kea_other") == other_before
                    assert snapshot() == before
                    databases.pop()
                    save()
                    require_success(send("config-reload"))
                    verify_complex(require_success(send("cb-subnet4-list")), {42, 45}, "missing-server")

                    if not args.skip_outages:
                        unavailable = {
                            "result": 1, "text": "Configuration backend read failed or unavailable."}
                        active_before_outage = require_success(send("config-get"))
                        stop(database_process)
                        assert database_process.returncode == 0, "MySQL shutdown failed"
                        assert send("config-backend-pull")["result"] != 0
                        assert send("cb-subnet4-get", {"id": 42}) == unavailable
                        assert send("cb-subnet4-del", {
                            "id": 42, "server-tag": "all", "preserve-leases": True}) == {
                                "result": 1, "text": (
                                    "Configuration backend deletion failed or unavailable; "
                                    "reconcile backend state before retrying.")}
                        assert send("cb-subnet4-set", {"server-tag": "all", "subnet4": {
                            "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600}}) == {
                                "result": 1, "text": (
                                    "Configuration backend write failed or unavailable; "
                                    "reconcile backend state before retrying.")}
                        assert require_success(send("db-commands-diagnostic"))[
                            "database-connectivity-tested"] is False
                        # Reconnect removes the broken backend; later pulls can
                        # report success without applying any configuration.
                        require_success(send("config-backend-pull"))
                        assert require_success(send("config-get")) == active_before_outage
                        assert send("cb-subnet4-list") == unavailable
                        deadline = time.monotonic() + 2
                        while time.monotonic() < deadline:
                            assert send("cb-subnet4-list") == unavailable
                            time.sleep(0.1)
                        database_process = start_database()
                        deadline = time.monotonic() + 15
                        while True:
                            response = send("cb-subnet4-list")
                            if response["result"] == 0:
                                verify_complex(response["arguments"], {42, 45}, "missing-server")
                                break
                            assert response == unavailable
                            assert time.monotonic() < deadline, "Native MySQL recovery timed out"
                            time.sleep(0.1)
                        assert snapshot() == before

                        # After exhaustion serve-retry-continue stays alive without a backend.
                        databases[0]["max-reconnect-tries"] = 2
                        save()
                        require_success(send("config-reload"))
                        stop(database_process)
                        assert database_process.returncode == 0
                        assert send("cb-subnet4-list") == unavailable
                        deadline = time.monotonic() + 8
                        while b"MYSQL_CB_RECONNECT_FAILED4" not in (directory / "kea.log").read_bytes():
                            assert kea_process.poll() is None, "serve-retry-continue unexpectedly exited"
                            assert send("cb-subnet4-list") == unavailable
                            assert time.monotonic() < deadline, "Native retry exhaustion was not logged"
                            time.sleep(0.1)
                        database_process = start_database()
                        deadline = time.monotonic() + 2
                        while time.monotonic() < deadline:
                            assert send("cb-subnet4-list") == unavailable
                            time.sleep(0.1)
                        require_success(send("config-reload"))
                        verify_complex(require_success(send("cb-subnet4-list")),
                                       {42, 45}, "missing-server")
                        assert snapshot() == before
                    else:
                        print("EXCLUDED: deliberate SQL outage/retry exhaustion (--skip-outages)")
                    # The read account can initialize but cannot call the native
                    # audit procedure. Verify failure before granting EXECUTE.
                    before_write = snapshot()
                    denied = send("cb-subnet4-set", request())
                    assert denied["result"] == 1 and "arguments" not in denied, denied
                    assert denied["text"].startswith("Configuration backend write failed")
                    assert snapshot() == before_write
                    sql(f"GRANT EXECUTE ON kea_test.* TO '{reader}'@'localhost'")
                    tables = [row.decode() for row in sql("SHOW TABLES").splitlines()]
                    for table in tables:
                        sql(f"GRANT INSERT ON kea_test.`{table}` TO '{reader}'@'localhost'")
                    sql(f"REVOKE INSERT ON kea_test.* FROM '{reader}'@'localhost'")

                    def deny_association():
                        # Table privilege changes apply to existing connections;
                        # schema privilege changes require reconnecting first.
                        sql("REVOKE INSERT ON kea_test.dhcp4_subnet_server "
                            f"FROM '{reader}'@'localhost'")

                    def restore_privileges():
                        sql("GRANT INSERT ON kea_test.dhcp4_subnet_server "
                            f"TO '{reader}'@'localhost'")

                    verify_mutations(send, snapshot, sql, config, save,
                                     deny_association, restore_privileges)
                    verify_lifecycle(send, snapshot, sql, config, save)
                    verify_records(send, snapshot, sql, config, save)
                    verify_options(send, snapshot, sql, config, save)
                    verify_shared_networks(send, snapshot, sql, config, save)
                    verify_shared_network_membership(send, snapshot, sql, config, save)
                    verify_scoped_options(send, snapshot, sql, config, save)
                    if args.multiprocess:
                        verify_multiprocess(
                            args, directory, config, environment, authorization, send, sql,
                            snapshot,
                            [args.mysql_bin, *connection, "--batch", "--unbuffered",
                             "--skip-column-names", "kea_test"], environment,
                            deny_association, restore_privileges)
                    if args.packet:
                        verify_dhcp(send, config, save, directory, snapshot, sql)
                    prepare_shared_network_restart(send, sql, config)
                    require_success(send("shutdown"))
                    assert kea_process.wait(timeout=10) == 0
                    kea_process = subprocess.Popen(
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
                            assert kea_process.poll() is None and time.monotonic() < deadline
                            time.sleep(0.1)
                    verify_records_restart(send, args.packet)
                    verify_options_restart(send)
                    verify_scoped_options_restart(send)
                    verify_shared_networks_restart(send, sql, config)
                    if args.packet:
                        verify_packet_restart(send, directory)
                    require_success(send("shutdown"))
                    assert kea_process.wait(timeout=10) == 0
                    print("PASS: persisted subnet loaded after actual Kea process restart")
                print(f"PASS: MySQL schema {schema_version.decode().strip()}, "
                      f"MT={multithreading}: empty, complex native reads, pools/options/classes, tags, "
                      f"invalid arguments, select-only={args.select_only}, "
                      "nonmutating reads, native mutations and rollback, ambiguous backends, "
                      f"outage/retry-exhaustion coverage={not args.skip_outages}, shutdown")
        finally:
            stop(kea_process)
            stop(database_process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("server", "hook", "mysql-hook", "schema", "mysql-bin",
                 "mysql-install-db", "mysql-server", "work-dir"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument(
        "--select-only", action="store_true",
        help="probe native SELECT-only startup; preparation failures remain test failures",
    )
    parser.add_argument("--skip-outages", action="store_true",
                        help="exclude deliberate SQL stop/recovery scenarios")
    parser.add_argument("--multiprocess", action="store_true",
                        help="run bounded independent-process concurrency checks")
    parser.add_argument("--packet", action="store_true",
                        help="run DORA inside the packet namespace runner")
    parser.add_argument("--lfc", type=Path, help="matching Kea lease-file cleanup executable")
    parser.add_argument("--designated-writer", action="store_true",
                        help="qualify isolated three-role deployment without SQL faults")
    parser.add_argument("--reconciliation", action="store_true",
                        help="qualify read-only recovery evidence and fail-closed holds")
    args = parser.parse_args()
    if args.designated_writer and args.reconciliation:
        parser.error("choose one deployment qualification mode")
    if ((args.designated_writer or args.reconciliation) and
            (not args.packet or args.multiprocess or args.select_only)):
        parser.error("deployment qualification requires --packet and excludes other probe modes")
    if args.packet:
        _isolated()
        if args.lfc is None or not args.lfc.is_file() or not os.access(args.lfc, os.X_OK):
            print("SKIP: packet tests require --lfc with a matching kea-lfc executable")
            return 77
    files = ("server", "hook", "mysql_hook", "schema", "mysql_bin",
             "mysql_install_db", "mysql_server")
    missing = [f"{name}={getattr(args, name)}" for name in files
               if not getattr(args, name).is_file()]
    for name in ("server", "mysql_bin", "mysql_install_db", "mysql_server"):
        path = getattr(args, name)
        if path.is_file() and not os.access(path, os.X_OK):
            missing.append(f"{name}={path} (not executable)")
    if missing or os.geteuid() == 0:
        print("SKIP: requires non-root user, matching Kea 3.2.1 server/MySQL hook/schema, "
              "MySQL client, MariaDB installer and server; missing: " + ", ".join(missing))
        return 77
    for name in files:
        setattr(args, name, getattr(args, name).resolve())
    if not execute([args.server, "-v"]).decode().strip().startswith("3.2.1"):
        raise AssertionError("MySQL integration requires Kea 3.2.1")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    for multithreading in (False, True):
        with tempfile.TemporaryDirectory(dir=args.work_dir.resolve()) as temporary:
            run_case(args, Path(temporary), multithreading)
    print("PASS: isolated servers stopped and temporary data removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
