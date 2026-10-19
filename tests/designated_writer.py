"""Three-role, fail-closed designated-writer qualification on disposable SQL."""

# SPDX-License-Identifier: MPL-2.0
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import subprocess
import time
from typing import Any

from control import command
from dhcp import CLIENT_PORT, RELAY, _isolated, _lease, _packet, _response
from mutation import request
from smoke import ADMISSION_ERROR, require_success


class Role:
    """One supervised daemon. No restart policy; configuration stays private."""

    def __init__(self, args, directory, base, environment, authorization, name, writer, port,
                 database_user=None):
        self.root = directory / name
        self.root.mkdir()
        self.name = name
        self.writer = writer
        self.packet_port = port
        self.authorization = authorization
        self.config = copy.deepcopy(base)
        body = self.config["Dhcp4"]
        body["server-tag"] = name
        body["interfaces-config"] = (
            {"interfaces": []} if writer else
            {"interfaces": ["lo/127.0.0.1"], "dhcp-socket-type": "udp"})
        body["lease-database"] = {
            "type": "memfile", "persist": not writer,
            "name": str(self.root / "leases.csv"), "lfc-interval": 0}
        for hook in body["hooks-libraries"]:
            if hook["library"].endswith("/libdhcp_db_commands.so"):
                hook["parameters"] = {"allow-mutations": writer}
        database = body["config-control"]["config-databases"][0]
        if database["type"] == "postgresql" and not writer:
            database["user"] = "kea_reader"
        elif database["type"] == "mysql" and writer:
            database["user"] = "kea_writer"
        if database_user is not None:
            database["user"] = database_user
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.control_port = reservation.getsockname()[1]
        body["control-sockets"][0]["socket-port"] = self.control_port
        self.path = self.root / "kea.json"
        self.save()
        env = environment.copy()
        env.update(KEA_PIDFILE_DIR=str(self.root), KEA_LOCKFILE_DIR=str(self.root),
                   KEA_DHCP_DATA_DIR=str(self.root))
        self.log = (self.root / "kea.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(args.server), "-c", str(self.path), "-p", str(port), "-P", str(CLIENT_PORT)],
            cwd=self.root, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while True:
                assert self.process.poll() is None, f"{name} exited during startup"
                try:
                    require_success(self.send("list-commands"))
                    break
                except (OSError, ValueError):
                    assert time.monotonic() < deadline, f"{name} control startup timeout"
                    time.sleep(0.05)
            assert require_success(self.send("db-commands-diagnostic"))["allow-mutations"] is writer
            active = require_success(self.send("config-get"))["Dhcp4"]
            assert active["config-control"]["config-fetch-wait-time"] == 0
            assert len(active["config-control"]["config-databases"]) == 1
        except BaseException:
            self.close()
            raise

    def save(self):
        self.path.write_text(json.dumps(self.config), encoding="utf-8")
        self.path.chmod(0o600)

    def send(self, name, arguments=None):
        return command(self.control_port, name, arguments, authorization=self.authorization)

    def active(self):
        return {row["id"]: row for row in
                require_success(self.send("config-get"))["Dhcp4"]["subnet4"]}

    def stop(self):
        require_success(self.send("shutdown"))
        assert self.process.wait(timeout=15) == 0, "Native shutdown failed"
        self.log.close()

    def close(self):
        try:
            if self.process.poll() is None:
                self.stop()
        finally:
            if self.process.poll() is None:
                # Cleanup after an assertion, never a fencing/promotion result.
                self.process.terminate()
                self.process.wait(timeout=15)
            self.log.close()

    def packetless(self):
        assert self.writer
        active = require_success(self.send("config-get"))["Dhcp4"]
        assert active["interfaces-config"]["interfaces"] == []
        inodes = set()
        for descriptor in Path(f"/proc/{self.process.pid}/fd").iterdir():
            try:
                target = descriptor.readlink().as_posix()
            except FileNotFoundError:
                continue
            if target.startswith("socket:["):
                inodes.add(target[8:-1])
        for table in ("udp", "udp6", "raw", "raw6", "packet"):
            rows = Path(f"/proc/{self.process.pid}/net/{table}").read_text().splitlines()
            for row in rows[1:]:
                fields = row.split()
                inode = fields[8] if table == "packet" else fields[9]
                assert inode not in inodes, f"Writer owns a packet socket in {table}"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", self.packet_port))


def desired(first=10):
    return request(910, "127.0.0.0/24", tag="all", pools=[
        {"start": f"127.0.0.{first}", "end": f"127.0.0.{first + 10}"}])


def managed(row):
    return row["id"], row["subnet"], row["valid-lifetime"], sorted(
        pool["pool"].replace(" ", "") for pool in row["pools"])


def exchange(role, first):
    """Relayed unicast DORA, endpoint identity and persisted lease."""
    xid = secrets.randbits(32)
    hardware = b"\x02" + secrets.token_bytes(5)
    endpoint = ("127.0.0.1", role.packet_port)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind((RELAY, CLIENT_PORT))
        receiver.settimeout(3)

        def receive(expected):
            data, source = receiver.recvfrom(4096)
            assert source == endpoint, "Unexpected DHCP responder"
            return _response(data, xid, hardware, expected)

        receiver.sendto(_packet(1, xid, hardware), endpoint)
        address, options = receive(2)
        assert ipaddress.IPv4Address(f"127.0.0.{first}") <= ipaddress.IPv4Address(address) <= (
            ipaddress.IPv4Address(f"127.0.0.{first + 10}"))
        receiver.sendto(_packet(3, xid, hardware, address, options[54]), endpoint)
        acknowledged, _ = receive(5)
        assert acknowledged == address
    _lease(role.root, address, hardware)
    return {"consumer": role.name, "address": address, "subnet-id": 910, "lifetime": 600}


class Workflow:
    """Fail-closed local supervisor gate; privileged direct access is out of scope."""

    def __init__(self, snapshot, consumers, events):
        self.snapshot = snapshot
        self.consumers = consumers
        self.events = events
        self.held = False
        self.pending = False
        self.writer: Role | None = None
        self.fenced: int | None = None
        self.reconciled = None

    def mutate(self, name, arguments):
        assert not self.held and not self.pending, "Workflow write hold"
        assert self.writer is not None and self.writer.process.poll() is None
        self.pending = True
        self.held = True
        result = require_success(self.writer.send(name, arguments))
        self.held = False
        return result

    def activate(self, role, expected, command_name="config-backend-pull"):
        try:
            require_success(role.send(command_name))
            active = role.active()
            assert 910 in active, "Activation omitted desired subnet"
            assert managed(active[910]) == expected, "Activation did not apply desired state"
            self.events.append({"event": "active-state-verified", "consumer": role.name,
                                "managed-subnet": expected})
        except (AssertionError, OSError, ValueError):
            self.held = True
            self.events.append({"event": "activation-failed-write-hold", "consumer": role.name})
            raise

    def converge(self, expected, operator=False):
        if self.held:
            assert operator, "Operator verification required to release hold"
        for role in self.consumers:
            assert managed(role.active()[910]) == expected, "Fleet has not converged"
        # A second, independent SQL snapshot must match the acknowledged state.
        assert self.snapshot() == self.reconciled, "SQL changed during activation"
        self.pending = False
        self.held = False
        self.events.append({"event": "operator-resume" if operator else "converged"})

    def promote(self, start):
        assert self.held, "Promotion requires a write hold"
        assert self.writer is not None, "Missing previous writer"
        assert self.writer.process.poll() == 0, "Old writer is not fenced"
        assert self.fenced == self.writer.process.pid, "Missing verified fencing"
        assert not self.pending, "Outstanding write or activation outcome"
        assert self.reconciled is not None and self.snapshot() == self.reconciled, (
            "Missing or changed SQL reconciliation")
        replacement = start()
        self.writer = replacement
        self.held = False
        self.pending = False
        self.fenced = None
        self.events.append({"event": "promoted", "pid": replacement.process.pid})
        return replacement


def verify_designated_writer(args, directory, config, environment, authorization, snapshot):
    """Never interrupt SQL, inject a transaction failure, or retry a mutation."""
    _isolated()
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    mt = config["Dhcp4"]["multi-threading"]["enable-multi-threading"]
    output = args.work_dir.resolve().parent / "designated-writer-results"
    output.mkdir(exist_ok=True)
    report: dict[str, Any] = {"backend": backend, "packet-mt": mt, "status": "FAIL", "events": []}
    events = report["events"]
    roles = []

    def start(name, writer, port):
        role = Role(args, directory, config, environment, authorization, name, writer, port)
        roles.append(role)
        events.append({"event": "started", "role": name, "pid": role.process.pid,
                       "admission": writer, "control-port": role.control_port,
                       "dhcp-port": None if writer else port,
                       "server-tag": name, "automatic-fetch": False,
                       "interfaces": role.config["Dhcp4"]["interfaces-config"]["interfaces"]})
        return role

    def digest():
        return hashlib.sha256(repr(snapshot()).encode()).hexdigest()

    try:
        writer = start("admin-old", True, 1267)
        a = start("consumer-a", False, 1067)
        b = start("consumer-b", False, 1167)
        assert len({role.process.pid for role in roles}) == 3
        writer.packetless()
        workflow = Workflow(snapshot, [a, b], events)
        workflow.writer = writer
        for role in roles:
            assert not role.active()
            assert require_success(role.send("cb-subnet4-list"))["subnet4"] == []
        # Set/delete acceptance on an unused standalone object.
        scratch = request(911, "198.18.0.0/24", tag="all")
        before = snapshot()
        workflow.mutate("cb-subnet4-set", scratch)
        assert snapshot() != before
        assert writer.send("cb-subnet4-get", {"id": 911, "server-tag": "all"})["result"] == 0
        workflow.pending = False  # Never activated scratch; readback is the complete outcome.
        workflow.mutate("cb-subnet4-del",
                        {"id": 911, "server-tag": "all", "preserve-leases": True})
        assert writer.send("cb-subnet4-get", {"id": 911, "server-tag": "all"})["result"] == 3
        workflow.pending = False
        workflow.mutate("cb-subnet4-set", desired())
        stored = require_success(writer.send(
            "cb-subnet4-get", {"id": 910, "server-tag": "all"}))["subnet4"][0]
        expected = managed(stored)
        assert expected == (910, "127.0.0.0/24", 600, ["127.0.0.10-127.0.0.20"])
        workflow.reconciled = snapshot()
        assert not a.active() and not b.active()
        events.append({"event": "persisted-not-activated", "sql-sha256": digest()})
        for consumer in (a, b):
            before = snapshot()
            active = consumer.active()
            for tag in ("all", "admin-old", consumer.name):
                assert consumer.send("cb-subnet4-set", desired() | {"server-tag": tag}) == (
                    ADMISSION_ERROR)
                assert consumer.send("cb-subnet4-del", {
                    "id": 910, "server-tag": tag, "preserve-leases": True}) == ADMISSION_ERROR
            assert snapshot() == before and consumer.active() == active
            assert require_success(consumer.send("cb-subnet4-list"))["subnet4"]
            assert managed(require_success(consumer.send("cb-subnet4-get", {
                "id": 910, "server-tag": consumer.name}))["subnet4"][0]) == expected
        events.append({"event": "consumer-denials-preserve-sql-and-active-state",
                       "tags": ["all", "admin-old", "consumer-role"]})
        workflow.activate(a, expected)
        assert managed(a.active()[910]) == expected and not b.active()
        events.append({"event": "canary-active-peer-unchanged"})
        workflow.activate(b, expected)
        workflow.converge(expected)
        report["dora"] = [exchange(a, 10), exchange(b, 10)]

        # Failed fencing: promotion must not even call the candidate factory.
        workflow.held = True

        def forbidden_start():
            raise RuntimeError("Promotion reached candidate before fencing")

        try:
            workflow.promote(forbidden_start)
        except AssertionError as error:
            assert str(error) == "Old writer is not fenced"
        else:
            raise AssertionError("Live old writer permitted promotion")
        assert writer.process.poll() is None
        assert snapshot() == workflow.reconciled
        events.append({"event": "failed-fence-blocks-promotion", "candidate-started": False})
        # Every write was acknowledged and reconciled. Native shutdown drains
        # this serial workflow; no session kill, transaction disruption or retry.
        writer.stop()
        assert not Path(f"/proc/{writer.process.pid}").exists()
        try:
            writer.send("cb-subnet4-set", desired(30))
        except (OSError, ValueError):
            pass
        else:
            raise AssertionError("Former writer still accepts commands")
        assert snapshot() == workflow.reconciled
        workflow.fenced = writer.process.pid
        events.append({"event": "fenced", "pid": writer.process.pid, "exit": 0,
                       "endpoint-closed": True, "sql-sha256": digest()})
        report["dora"].extend([exchange(a, 10), exchange(b, 10)])
        events.append({"event": "consumers-serve-with-writer-stopped"})
        # Fail closed also when SQL reconciliation has not been recorded.
        workflow.reconciled = None
        try:
            workflow.promote(forbidden_start)
        except AssertionError as error:
            assert str(error) == "Missing or changed SQL reconciliation"
        else:
            raise AssertionError("Promotion bypassed reconciliation")
        events.append({"event": "missing-reconciliation-blocks-promotion",
                       "candidate-started": False})
        assert managed(require_success(a.send("cb-subnet4-get", {
            "id": 910, "server-tag": "all"}))["subnet4"][0]) == expected
        workflow.reconciled = snapshot()
        events.append({"event": "sql-reconciled-before-promotion", "sql-sha256": digest()})
        replacement = workflow.promote(lambda: start("admin-new", True, 1267))
        assert replacement.process.pid != writer.process.pid
        replacement.packetless()
        assert sum(role.writer and role.process.poll() is None for role in roles) == 1
        workflow.mutate("cb-subnet4-set", desired(30))
        expected = managed(require_success(replacement.send("cb-subnet4-get", {
            "id": 910, "server-tag": "all"}))["subnet4"][0])
        workflow.reconciled = snapshot()
        assert expected == (910, "127.0.0.0/24", 600, ["127.0.0.30-127.0.0.40"])
        old_b = b.active()
        assert managed(a.active()[910]) != expected and managed(old_b[910]) != expected
        workflow.activate(a, expected)
        assert managed(a.active()[910]) == expected and b.active() == old_b
        # Local parser rejection before SQL fetch. Kea preserves B's runtime.
        b.config["Dhcp4"]["valid-lifetime"] = "invalid"
        b.save()
        try:
            workflow.activate(b, expected, "config-reload")
        except AssertionError:
            pass
        else:
            raise AssertionError("Invalid consumer configuration was activated")
        assert workflow.held and b.active() == old_b and snapshot() == workflow.reconciled
        try:
            workflow.converge(expected, operator=True)
        except AssertionError:
            pass
        else:
            raise AssertionError("Partial activation reported convergence")
        before = snapshot()
        try:
            workflow.mutate("cb-subnet4-set", desired(50))
        except AssertionError as error:
            assert str(error) == "Workflow write hold"
        else:
            raise AssertionError("Activation failure allowed another mutation")
        assert snapshot() == before
        events.append({"event": "partial-activation-failure", "consumer": b.name,
                       "subsequent-mutation-blocked": True})
        b.config["Dhcp4"]["valid-lifetime"] = 600
        b.save()
        workflow.activate(b, expected, "config-reload")
        report["dora"].extend([exchange(a, 30), exchange(b, 30)])
        workflow.converge(expected, operator=True)
        replacement.packetless()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind((RELAY, CLIENT_PORT))
            probe.settimeout(0.3)
            probe.sendto(_packet(1, secrets.randbits(32), bytes((2,)) + secrets.token_bytes(5)),
                         ("127.0.0.1", replacement.packet_port))
            try:
                probe.recvfrom(4096)
            except socket.timeout:
                pass
            else:
                raise AssertionError("Administrative writer answered DHCP")
        events.append({"event": "writer-packetless", "socket-tables-checked": [
            "udp", "udp6", "raw", "raw6", "packet"], "probe": "no-reply"})
        report["status"] = "PASS"
        print(f"PASS: designated writer {backend} MT={mt}; process fencing/replacement, "
              "SQL reconciliation, staged activation, failure holds, six DORA/leases")
    finally:
        cleanup = True
        for role in reversed(roles):
            try:
                role.close()
            except (OSError, AssertionError, subprocess.TimeoutExpired):
                cleanup = False
        report["kea-cleanup"] = cleanup and all(role.process.poll() == 0 for role in roles)
        if not report["kea-cleanup"]:
            report["status"] = "FAIL"
        (output / f"{backend}-mt-{int(mt)}.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
        assert report["kea-cleanup"], "Deployment Kea cleanup failed"
