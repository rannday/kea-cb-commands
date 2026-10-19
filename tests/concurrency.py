"""Opt-in, bounded multi-process checks inside the existing private SQL fixtures."""

# SPDX-License-Identifier: MPL-2.0
import copy
import io
import json
import selectors
import signal
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier

from control import command
from lifecycle import delete_request
from mutation import request
from smoke import require_success


def until(predicate, message, seconds=3):
    """Poll an observable condition; timing never decides the race winner."""
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, message
        time.sleep(0.02)


class Peer:
    """A separate daemon, PID/lock/data directory, config and HTTP endpoint."""

    def __init__(self, args, root, config, environment, authorization):
        root.mkdir()
        self.root = root
        self.server = args.server
        self.config = copy.deepcopy(config)
        self.environment = environment.copy()
        self.environment.update({name: str(root) for name in (
            "KEA_PIDFILE_DIR", "KEA_LOCKFILE_DIR", "KEA_DHCP_DATA_DIR")})
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.port = reservation.getsockname()[1]
        self.config["Dhcp4"]["control-sockets"][0]["socket-port"] = self.port
        self.authorization = authorization
        self.process: subprocess.Popen[bytes] | None = None
        self.log = (root / "kea.log").open("w", encoding="utf-8")

    def start(self):
        path = self.root / "kea.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        path.chmod(0o600)
        self.process = subprocess.Popen(
            [str(self.server), "-c", str(path)], cwd=self.root,
            env=self.environment, stdout=self.log, stderr=subprocess.STDOUT)

        def ready():
            assert self.process is not None
            assert self.process.poll() is None, "Peer exited; inspect retained Kea log"
            try:
                response = self.send("list-commands")
                return response["result"] == 0
            except (OSError, ValueError):
                return False

        until(ready, "Peer control endpoint did not become ready", seconds=15)
        commands = require_success(self.send("list-commands"))
        assert {"cb-subnet4-list", "cb-subnet4-get", "cb-subnet4-set",
                "cb-subnet4-del"} <= set(commands)

    def send(self, name, arguments=None):
        return command(self.port, name, arguments, authorization=self.authorization)

    def stop(self, abrupt=False):
        if self.process is not None and self.process.poll() is None:
            if abrupt:
                self.process.kill()
            else:
                require_success(self.send("shutdown"))
            self.process.wait(timeout=10)
            if not abrupt:
                assert self.process.returncode == 0

    def close(self):
        try:
            self.stop(abrupt=True)
        finally:
            self.log.close()


@contextmanager
def row_gate(argv, environment):
    """Test-only row lock: pause a native transaction before association removal.

    The admin session belongs only to the disposable SQL fixture. No lock is
    added to the hook, and this is not a deployment coordination mechanism.
    """
    with subprocess.Popen([str(part) for part in argv], env=environment,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as process:
        try:
            assert process.stdin is not None
            assert isinstance(process.stdout, io.BufferedReader)
            process.stdin.write(
                b"START TRANSACTION; SELECT subnet_id FROM dhcp4_subnet_server "
                b"WHERE subnet_id=1500 FOR UPDATE; SELECT 'gate-ready';\n")
            process.stdin.flush()
            # Read bytes to avoid buffered readline hiding a subsequent marker.
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                output = b""
                deadline = time.monotonic() + 3
                while b"gate-ready" not in output:
                    assert selector.select(max(0, deadline - time.monotonic())), \
                        "SQL row gate did not become ready"
                    data = process.stdout.read1(4096)
                    assert data, "SQL row gate exited"
                    output += data
                assert b"1500" in output, "SQL gate did not lock the fixture association"
            yield
        finally:
            if process.poll() is None:
                try:
                    process.communicate(b"ROLLBACK;\n", timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=3)
            assert process.returncode == 0, "SQL row gate failed"


def verify_multiprocess(args, directory, config, environment, authorization,
                        send, sql, snapshot, admin_argv, admin_environment,
                        deny_association, restore_privileges):
    """Record real races, rollback boundaries, stale writes and upstream failures."""
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    pg = backend == "postgresql"
    user = config["Dhcp4"]["config-control"]["config-databases"][0]["user"]
    # Account names originate exclusively in these fixtures, never user input.
    assert user.replace("_", "").isalnum()
    mt = config["Dhcp4"]["multi-threading"]["enable-multi-threading"]
    report_dir = args.work_dir.parent / "concurrency-results" / f"{backend}-mt-{int(mt)}"
    report_dir.mkdir(parents=True, exist_ok=True)
    records = []
    peers = []
    executor = ThreadPoolExecutor(max_workers=3)

    def record(case, responses, final):
        entry = {"case": case, "responses": responses, "final": final}
        records.append(entry)
        print("CONCURRENCY " + json.dumps(entry, sort_keys=True), flush=True)

    def get(client=send, subnet_id=1500, tag="test-server"):
        response = client("cb-subnet4-get", {"id": subnet_id, "server-tag": tag})
        assert response["result"] in (0, 3), response
        rows = response["arguments"]["subnet4"]
        assert len(rows) == (1 if response["result"] == 0 else 0)
        return rows[0] if rows else None

    def require_subnet(client=send, subnet_id=1500, tag="test-server"):
        row = get(client, subnet_id, tag)
        assert row is not None, f"Expected subnet {subnet_id} for {tag}"
        return row

    def listed(client):
        rows = require_success(client("cb-subnet4-list"))["subnet4"]
        assert len({row["id"] for row in rows}) == len(rows)
        assert len({row["subnet"] for row in rows}) == len(rows)
        return rows

    def set_request(lifetime=600, pools=None, subnet_id=1500, tag="test-server"):
        return request(subnet_id, f"198.25.{subnet_id - 1500}.0/24", lifetime,
                       tag=tag, pools=pools)

    def put(arguments, client=send):
        return client("cb-subnet4-set", arguments)

    def remove(subnet_id=1500, client=send, tag="test-server"):
        return client("cb-subnet4-del", delete_request(id=subnet_id, **{"server-tag": tag}))

    def race(first, second):
        barrier = Barrier(2, timeout=3)

        def invoke(operation):
            barrier.wait()
            return operation()

        futures = [executor.submit(invoke, operation) for operation in (first, second)]
        results = [future.result(timeout=8) for future in futures]
        assert all(result["result"] in (0, 1, 3) for result in results), results
        return results

    def wait_writers(count=1, competing=()):
        query = (f"SELECT count(*) FROM pg_stat_activity WHERE datname='kea_test' "
                 f"AND usename='{user}' AND wait_event_type='Lock'" if pg else
                 f"SELECT count(*) FROM information_schema.PROCESSLIST "
                 f"WHERE USER='{user}' AND COMMAND!='Sleep'")
        until(lambda: int(sql(query).strip()) >= count or
              any(future.done() for future in competing), "Native SQL writer did not block")

    def active(client):
        return require_success(client("config-get"))["Dhcp4"]["subnet4"]

    try:
        record("database-isolation", [], sql("SHOW transaction_isolation" if pg else
                                             "SELECT @@tx_isolation").strip().decode())
        for name in ("writer-b", "observer"):
            peer = Peer(args, directory / name, config, environment, authorization)
            peers.append(peer)
            peer.start()
        writer, observer = peers
        other, read = writer.send, observer.send
        assert len({peer.process.pid for peer in peers}) == 2
        # Three repetitions bound race costs. Outcomes may depend on scheduling;
        # the row-gated stale-update case below provides deterministic evidence.
        pool_a = [{"start": "198.25.0.10", "end": "198.25.0.20"}]
        pool_b = [{"start": "198.25.0.30", "end": "198.25.0.40"}]
        for iteration in range(3):
            for subnet_id in (1500, 1501):
                assert remove(subnet_id)["result"] in (0, 3)
            outcomes = race(lambda: put(set_request(610)),
                            lambda: put(set_request(620), other))
            final = get()
            assert final and final["valid-lifetime"] in (610, 620)
            record(f"same-id-create-{iteration}", outcomes, final)
            require_success(remove())
            conflicting = set_request(620, subnet_id=1501)
            conflicting["subnet4"]["subnet"] = "198.25.0.0/24"
            outcomes = race(lambda: put(set_request(610)), lambda: put(conflicting, other))
            rows = [row for row in listed(read) if row["id"] in (1500, 1501)]
            assert len(rows) == 1 and rows[0]["subnet"] == "198.25.0.0/24", rows
            record(f"prefix-create-{iteration}", outcomes, rows)
            for subnet_id in (1500, 1501):
                assert remove(subnet_id)["result"] in (0, 3)
            for subnet_id in (1500, 1501):
                require_success(put(set_request(subnet_id=subnet_id)))
            outcomes = race(lambda: put(set_request(710)),
                            lambda: put(set_request(720, subnet_id=1501), other))
            assert [require_subnet(subnet_id=i)["valid-lifetime"] for i in (1500, 1501)] == [710, 720]
            record(f"different-id-update-{iteration}", outcomes,
                   [get(subnet_id=i) for i in (1500, 1501)])
            outcomes = race(lambda: put(set_request(810)),
                            lambda: put(set_request(820), other))
            assert require_subnet()["valid-lifetime"] in (810, 820)
            record(f"same-id-update-{iteration}", outcomes, get())
            outcomes = race(lambda: put(set_request(910, pool_a)),
                            lambda: put(set_request(920, pool_b), other))
            final = require_subnet()
            expected_pool = "198.25.0.10-198.25.0.20" if final["valid-lifetime"] == 910 \
                else "198.25.0.30-198.25.0.40"
            record(f"pool-replace-{iteration}", outcomes, final)
            assert final["valid-lifetime"] in (910, 920)
            actual_pools = [p["pool"].replace(" ", "") for p in final["pools"]]
            assert actual_pools and set(actual_pools) <= {
                "198.25.0.10-198.25.0.20", "198.25.0.30-198.25.0.40"}, final
            if actual_pools != [expected_pool]:
                record(f"native-pool-interleaving-{iteration}", outcomes, final)
            outcomes = race(lambda: remove(), lambda: put(set_request(930, []), other))
            final = get()
            assert final is None or (final["valid-lifetime"] == 930 and final["pools"] == [])
            record(f"delete-update-{iteration}", outcomes, final)
            require_success(put(set_request()))
            outcomes = race(lambda: remove(), lambda: remove(client=other))
            assert get() is None
            record(f"delete-delete-{iteration}", outcomes, None)
            # Explicitly retry after reconciliation, not blindly after an error.
            require_success(put(set_request(600, pool_a)))
            outcomes = race(lambda: send("cb-subnet4-get", {"id": 1500}),
                            lambda: other("cb-subnet4-list"))
            assert all(result["result"] == 0 for result in outcomes)
            assert get(read) == get()

        for iteration in range(2):
            require_success(put(set_request(600, pool_a)))
            baseline = require_subnet(read)
            with row_gate(admin_argv, admin_environment):
                first = executor.submit(put, set_request(1000, pool_b))
                try:
                    wait_writers()
                except AssertionError:
                    record("gate-writer-diagnostic", [first.result(timeout=8)], None)
                    raise
                # This preflight copies the old committed pools; its write waits.
                second = executor.submit(put, set_request(1100), other)
                wait_writers(2, (first, second))
                assert get(read) == baseline
                assert next(row for row in listed(read) if row["id"] == 1500) == baseline
            outcomes = [future.result(timeout=8) for future in (first, second)]
            final = require_subnet(read)
            record(f"gated-omitted-pools-{iteration}", outcomes, final)
            assert any(response["result"] == 0 for response in outcomes), outcomes
            assert all(response["result"] in (0, 1) for response in outcomes), outcomes
            assert final["valid-lifetime"] in (1000, 1100), final
            if all(response["result"] == 0 for response in outcomes):
                assert final["valid-lifetime"] == 1100 and final["pools"] == baseline["pools"]
                record(f"stale-omitted-pools-{iteration}", outcomes, final)
            else:
                assert not pg, outcomes
                record("native-deadlock-counter", [],
                       sql("SHOW GLOBAL STATUS LIKE 'Innodb_deadlocks'").decode().strip())

        # Privilege failure occurs after native row/pool writes; readers must see
        # the old committed object, then identical table/audit contents on rollback.
        before = snapshot()
        baseline = get(read)
        deny_association()
        try:
            with row_gate(admin_argv, admin_environment):
                future = executor.submit(put, set_request(1200, []), other)
                wait_writers()
                assert get(read) == baseline
            response = future.result(timeout=8)
            assert response["result"] == 1, response
            assert snapshot() == before and get(read) == baseline
            record("transaction-rollback", [response], baseline)
        finally:
            restore_privileges()

        # Kill a daemon while its native transaction is provably blocked. This
        # is a confirmed pre-commit rollback, not an uncertain commit simulation.
        before = snapshot()
        with row_gate(admin_argv, admin_environment):
            future = executor.submit(put, set_request(1300, []), other)
            wait_writers()
            writer.stop(abrupt=True)
            try:
                future.result(timeout=8)
                raise AssertionError("Killed writer unexpectedly returned a response")
            except (OSError, ValueError):
                pass
            assert get(read) == baseline
        assert snapshot() == before
        writer.start()
        require_success(put(set_request(1400), other))
        record("killed-writer-restart", [], get(read))

        # Terminate active peer connections only, leaving the primary alive.
        # Kea 3.2.1 can abort in its native transaction destructor on rollback
        # through an unusable connection. Record this upstream blocker explicitly.
        baseline = get()
        before = snapshot()
        with row_gate(admin_argv, admin_environment):
            futures = [executor.submit(put, set_request(1500, []), client)
                       for client in (other, read)]
            wait_writers(2, futures)
            if pg:
                sql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname='kea_test' AND usename='{user}' "
                    "AND state='active' AND wait_event_type='Lock'")
            else:
                connections = sql("SELECT ID FROM information_schema.PROCESSLIST "
                                  f"WHERE USER='{user}' AND COMMAND!='Sleep'").splitlines()
                assert connections
                for connection in connections:
                    sql(f"KILL CONNECTION {int(connection)}")
        outcomes = []
        for future in futures:
            try:
                response = future.result(timeout=8)
                assert response["result"] == 1, response
                outcomes.append(response)
            except (OSError, ValueError) as error:
                outcomes.append({"transport-error": type(error).__name__})
        assert snapshot() == before and get() == baseline
        exits = []
        for peer, outcome in zip(peers, outcomes):
            if "transport-error" in outcome:
                peer.process.wait(timeout=5)
                assert peer.process.returncode == -signal.SIGABRT
                peer.log.flush()
                log = (peer.root / "kea.log").read_text(encoding="utf-8")
                assert "terminate called" in log and "DbConnectionUnusable" in log
                exits.append(peer.process.returncode)
                peer.start()
            else:
                until(lambda: peer.send("cb-subnet4-list")["result"] == 0,
                      "Native reconnect failed", seconds=15)
                exits.append(None)
        record("sql-interruption-upstream-abort", outcomes,
               {"exit-codes": exits, "rollback-confirmed": True,
                "recovery": "restart aborted peers; reconcile before retry"})
        assert get(read) == baseline
        require_success(put(set_request(1600), other))
        record("sql-interruption-recovery", [], get(read))

        # Bound lock contention at the database, and prove the failed native
        # transaction (including audit rows) rolls back before a reconciled retry.
        setting = (f"ALTER ROLE {user} SET lock_timeout='750ms'" if pg else
                   "SET GLOBAL innodb_lock_wait_timeout=1")
        restore_setting = (f"ALTER ROLE {user} RESET lock_timeout" if pg else
                           "SET GLOBAL innodb_lock_wait_timeout=50")
        if not pg:
            previous_timeout = int(sql("SELECT @@GLOBAL.innodb_lock_wait_timeout"))
            restore_setting = f"SET GLOBAL innodb_lock_wait_timeout={previous_timeout}"
        writer.stop()
        sql(setting)
        try:
            writer.start()
            baseline = get(read)
            before = snapshot()
            with row_gate(admin_argv, admin_environment):
                future = executor.submit(put, set_request(1700, []), other)
                wait_writers()
                assert get(read) == baseline
                response = future.result(timeout=3)
                assert response["result"] == 1, response
            assert snapshot() == before and get(read) == baseline
            record("lock-timeout-rollback", [response], baseline)
        finally:
            sql(restore_setting)
            writer.stop()
            writer.start()
        require_success(put(set_request(1600), other))

        # Drop the HTTP caller after the database confirms the request is in
        # flight. The caller has no result, but the native transaction commits.
        # This models response loss, not a lost SQL COMMIT acknowledgement.
        payload = json.dumps({"command": "cb-subnet4-set",
                              "arguments": set_request(1650)}).encode("ascii")
        with row_gate(admin_argv, admin_environment):
            with socket.create_connection(("127.0.0.1", writer.port), timeout=3) as caller:
                header = ("POST / HTTP/1.1\r\nHost: localhost\r\n"
                          f"Authorization: {authorization}\r\n"
                          "Content-Type: application/json\r\n"
                          f"Content-Length: {len(payload)}\r\n\r\n")
                caller.sendall(header.encode("ascii") + payload)
                wait_writers()
        until(lambda: require_subnet(read)["valid-lifetime"] == 1650,
              "Response-loss request did not commit")
        record("uncertain-http-outcome-reconciled", [], get(read))
        require_success(put(set_request(1600), other))

        for iteration in range(3):
            outcomes = race(lambda: put(set_request(600, subnet_id=1504)),
                            lambda: put(set_request(700, subnet_id=1504,
                                                     tag="other-server"), other))
            visible = {tag: get(read, 1504, tag) for tag in ("test-server", "other-server")}
            assert sum(row is not None for row in visible.values()) == 1, visible
            record(f"cross-tag-same-id-{iteration}", outcomes, visible)
            owner = next(tag for tag, row in visible.items() if row is not None)
            require_success(remove(1504, tag=owner))
        outcomes = race(lambda: put(set_request(600, subnet_id=1505, tag="all")),
                        lambda: put(set_request(700, subnet_id=1506,
                                                 tag="other-server"), other))
        assert all(response["result"] == 0 for response in outcomes)
        assert get(read, 1505) == get(read, 1505, "other-server")
        assert get(read, 1506) is None
        record("universal-and-one", outcomes, get(read, 1505, "all"))
        require_success(remove(1505, tag="all"))
        require_success(remove(1506, tag="other-server"))

        # Explicit tags are selectors, not authorization. ONE includes universal
        # rows; UNASSIGNED has no public command selector. ANY is internal only.
        outcomes = race(lambda: put(set_request(600, subnet_id=1502)),
                        lambda: put(set_request(600, subnet_id=1503, tag="other-server"), other))
        assert all(response["result"] == 0 for response in outcomes)
        assert get(read, 1503) is None and get(read, 1503, "other-server") is not None
        outcomes = race(lambda: put(set_request(700, subnet_id=1503)),
                        lambda: remove(1502, other, "other-server"))
        assert all(response["result"] == 1 for response in outcomes)
        assert get(read, 42, "other-server") is not None  # universal ALL row
        assert get(read, 46) is None  # UNASSIGNED row
        assert put(request(46, "198.26.0.0/24"))["result"] == 1
        # Audited test-only multiple-association fixture.
        audit = ("SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', 'race fixture', false); "
                 if pg else "CALL createAuditRevisionDHCP4(NOW(), 'all', 'race fixture', 0); ")
        sql("START TRANSACTION; " + audit +
            "INSERT INTO dhcp4_subnet_server (subnet_id, server_id, modification_ts) "
            "SELECT 1502, id, CURRENT_TIMESTAMP FROM dhcp4_server "
            "WHERE tag='other-server'; COMMIT")
        outcomes = race(lambda: put(set_request(700, subnet_id=1502)),
                        lambda: remove(1502, other, "other-server"))
        assert all(response["result"] == 1 for response in outcomes)
        record("server-selectors", outcomes, get(read, 1502))
        sql("START TRANSACTION; " + audit +
            "DELETE FROM dhcp4_subnet_server WHERE subnet_id=1502 AND server_id IN "
            "(SELECT id FROM dhcp4_server WHERE tag='other-server'); COMMIT")

        # Stored writes do not synchronize any active process. Pull one daemon;
        # another remains unchanged until its own explicit reload.
        original_active = [active(client) for client in (send, other, read)]
        require_success(put(set_request(1800), other))
        assert [active(client) for client in (send, other, read)] == original_active
        require_success(send("config-backend-pull"))
        assert next(row for row in active(send) if row["id"] == 1500)["valid-lifetime"] == 1800
        assert active(read) == original_active[2]
        require_success(read("config-reload"))
        assert next(row for row in active(read) if row["id"] == 1500)["valid-lifetime"] == 1800
        record("explicit-per-process-activation", [], {"writer": 1800, "observer": 1800})
        for subnet_id in (1500, 1501, 1502, 1503):
            require_success(remove(subnet_id, tag="other-server" if subnet_id == 1503
                                   else "test-server"))
        require_success(send("config-backend-pull"))
        for peer in peers:
            peer.stop()
        print(f"PASS: multi-process {backend}, MT={mt}; concurrent writes remain unsupported")
    finally:
        # Stop daemons before joining command threads, including failure paths.
        for peer in peers:
            peer.close()
        executor.shutdown(wait=True, cancel_futures=True)
        (report_dir / "outcomes.json").write_text(
            json.dumps(records, indent=2) + "\n", encoding="utf-8")
        for peer in peers:
            log = (peer.root / "kea.log").read_text(encoding="utf-8")
            (report_dir / f"{peer.root.name}.log").write_text(
                log.replace(authorization, "[redacted]"), encoding="utf-8")
