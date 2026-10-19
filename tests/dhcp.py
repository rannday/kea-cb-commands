"""Real relayed DHCPv4 packets on loopback in a disposable network namespace."""

# SPDX-License-Identifier: MPL-2.0
import csv
import ipaddress
import os
import secrets
import socket
import struct
import time
from pathlib import Path

from smoke import require_success
from options4 import PAYLOADS


COOKIE = b"\x63\x82\x53\x63"
RELAY = "127.0.0.2"
SERVER = ("127.0.0.1", 1067)
CLIENT_PORT = 1068
SUBNET_ID = 910


def _isolated():
    """Fail closed if the harness did not create its private test network."""
    host_namespace = os.environ.get("KEA_PACKET_HOST_NETNS")
    assert host_namespace and os.readlink("/proc/self/ns/net") != host_namespace, (
        "DHCP packet tests require a disposable network namespace")
    assert {name for _, name in socket.if_nameindex()} == {"lo"}, (
        "DHCP packet tests require a network containing only loopback")


def _packet(message, xid, hardware, requested=None, server=None):
    # BOOTP relay form makes Kea choose the subnet using giaddr. The harness
    # starts the unmodified server with -p 1067 -P 1068, including relay replies.
    header = struct.pack(
        "!BBBBIHH4s4s4s4s16s64s128s", 1, 1, 6, 1, xid, 0, 0,
        bytes(4), bytes(4), bytes(4), socket.inet_aton(RELAY),
        hardware.ljust(16, b"\0"), bytes(64), bytes(128))
    options = bytes((53, 1, message, 61, 7, 1)) + hardware
    if requested is not None:
        options += bytes((50, 4)) + socket.inet_aton(requested)
    if server is not None:
        options += bytes((54, 4)) + server
    options += bytes((55, 3, 1, 3, 6, 255))
    return (header + COOKIE + options).ljust(300, b"\0")


def _response(data, xid, hardware, expected, boot_file=None, lifetime=600):
    assert len(data) >= 240, "Truncated DHCP reply"
    assert data[0:3] == bytes((2, 1, 6)), "Invalid BOOTP reply"
    assert struct.unpack_from("!I", data, 4)[0] == xid, "Wrong transaction ID"
    assert data[28:34] == hardware, "Wrong client hardware address"
    assert data[24:28] == socket.inet_aton(RELAY), "Wrong relay address"
    assert data[236:240] == COOKIE, "Invalid DHCP magic cookie"
    if boot_file is not None:
        assert data[108:236].rstrip(b"\0") == boot_file.encode(), "Wrong BOOTP file"
    options = {}
    cursor = 240
    ended = False
    while cursor < len(data):
        code = data[cursor]
        cursor += 1
        if code == 255:
            ended = True
            break
        if code == 0:
            continue
        assert cursor < len(data), "Truncated DHCP option length"
        length = data[cursor]
        cursor += 1
        assert cursor + length <= len(data), "Truncated DHCP option value"
        options[code] = options.get(code, b"") + data[cursor:cursor + length]
        cursor += length
    assert ended, "Missing DHCP END option"
    assert options.get(53) == bytes((expected,)), "Unexpected DHCP message type"
    assert len(options.get(54, b"")) == 4, "Missing DHCP server identifier"
    assert options[54] == socket.inet_aton(SERVER[0]), "Wrong server identifier"
    assert len(options.get(51, b"")) == 4, "Missing DHCP lease lifetime"
    assert struct.unpack("!I", options[51])[0] == lifetime, "Wrong DHCP lease lifetime"
    return socket.inet_ntoa(data[16:20]), options


def _receive(receiver, xid, hardware, expected, timeout=3, boot_file=None, lifetime=600):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("No matching DHCP reply")
        receiver.settimeout(remaining)
        data, source = receiver.recvfrom(4096)
        # Ignore delayed replies for earlier clients without accepting them as
        # evidence that this transaction succeeded.
        if len(data) >= 8 and struct.unpack_from("!I", data, 4)[0] != xid:
            continue
        assert source == SERVER, "DHCP reply came from an unexpected endpoint"
        return _response(data, xid, hardware, expected, boot_file, lifetime)


def _lease(directory, address, hardware, lifetime=600):
    path = Path(directory).resolve() / "leases.csv"
    deadline = time.monotonic() + 3
    while True:
        try:
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            matching = [row for row in rows if row.get("address") == address]
            if matching:
                row = matching[-1]
                assert row["hwaddr"].lower() == hardware.hex(":"), "Wrong lease client"
                assert int(row["subnet_id"]) == SUBNET_ID, "Wrong lease subnet"
                assert int(row["valid_lifetime"]) == lifetime, "Wrong recorded lease lifetime"
                assert int(row["expire"]) > time.time(), "Recorded lease already expired"
                assert int(row.get("state", "0")) == 0, "Lease is not active"
                return path
        except FileNotFoundError:
            pass
        if time.monotonic() >= deadline:
            raise AssertionError("DHCPACK was not recorded in Kea's memfile lease database")
        time.sleep(0.05)


def _exchange(directory, first, last, expect_offer=True, boot_file=None,
              expected_options=None, absent_options=(), lifetime=600):
    _isolated()
    xid = secrets.randbits(32)
    hardware = b"\x02" + secrets.token_bytes(5)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind((RELAY, CLIENT_PORT))
        receiver.sendto(_packet(1, xid, hardware), SERVER)
        if not expect_offer:
            try:
                _receive(receiver, xid, hardware, 2, timeout=0.5)
            except socket.timeout:
                return None
            raise AssertionError("Kea offered a lease before activation or with no pools")
        address, offered = _receive(receiver, xid, hardware, 2, boot_file=boot_file,
                                    lifetime=lifetime)
        assert ipaddress.IPv4Address(first) <= ipaddress.IPv4Address(address) <= (
            ipaddress.IPv4Address(last)), "DHCPOFFER address is outside the SQL-managed pool"
        receiver.sendto(_packet(3, xid, hardware, address, offered[54]), SERVER)
        acknowledged, options = _receive(receiver, xid, hardware, 5, boot_file=boot_file,
                                        lifetime=lifetime)
        assert acknowledged == address, "DHCPACK differs from DHCPOFFER"
        assert options[54] == offered[54], "DHCP server changed during DORA"
        for message, payload in (("OFFER", offered), ("ACK", options)):
            for code, value in (expected_options or {}).items():
                assert payload.get(code) == value, (message, code, payload.get(code), value)
            for code in absent_options:
                assert code not in payload, (message, "Unexpected option", code)
    path = _lease(directory, address, hardware, lifetime)
    print(f"PASS: real DISCOVER/OFFER/REQUEST/ACK, lease {address}, subnet {SUBNET_ID}, "
          f"{lifetime}-second active lease recorded in memfile")
    return path


def _subnets(send, command):
    result = require_success(send(command))
    rows = result["Dhcp4"]["subnet4"] if command == "config-get" else result["subnet4"]
    return {row["id"]: row for row in rows}


def _pools(row):
    return [tuple(part.strip() for part in pool["pool"].split("-"))
            for pool in row["pools"]]


def _verify_shared_network_inheritance(send, config, directory, snapshot, sql, expected):
    """Diagnostic SQL fixtures qualify native activation, not hook membership writes."""
    network = "m27-packet"
    result = require_success(send("cb-shared-network4-set", {
        "server-tag": "test-server", "shared-network": {"name": network}}))
    assert result["activation-requested"] is False
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    if backend == "postgresql":
        prefix = ("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
                  "'all', 'M27 packet inheritance fixture', false); ")
        persistent = "true"
    else:
        prefix = ("START TRANSACTION; CALL createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
                  "'all', 'M27 packet inheritance fixture', 0); ")
        persistent = "1"

    def diagnostic(statements):
        sql(prefix + statements + "; COMMIT")

    def packet(options):
        _exchange(directory, "127.0.0.10", "127.0.0.29",
                  boot_file="m25-packet.efi", expected_options=options)

    def runtime():
        configuration = require_success(send("config-get"))["Dhcp4"]
        networks = {row["name"]: row for row in configuration.get("shared-networks", [])}
        row = networks[network]
        members = {subnet["id"]: subnet for subnet in row["subnet4"]}
        assert SUBNET_ID in members
        assert _pools(members[SUBNET_ID]) == [("127.0.0.10", "127.0.0.29")]
        return row, members[SUBNET_ID]

    def domain(row):
        return {option["code"]: option for option in row.get("option-data", [])}[15]["data"]

    before = require_success(send("config-get"))
    diagnostic(
        f"UPDATE dhcp4_subnet SET shared_network_name='{network}', "
        f"modification_ts=CURRENT_TIMESTAMP WHERE subnet_id={SUBNET_ID}; "
        "INSERT INTO dhcp4_options(code, formatted_value, space, persistent, "
        "scope_id, shared_network_name, client_classes) VALUES "
        f"(15, 'm27-network.example', 'dhcp4', {persistent}, 4, '{network}', '[]')")
    assert require_success(send("config-get")) == before
    packet(expected)
    persisted = require_success(send("cb-shared-network4-get", {
        "server-tag": "test-server", "name": network}))["shared-networks"][0]
    assert SUBNET_ID in {row["id"] for row in persisted["subnet4"]}
    before_refusal = snapshot()
    refused = send("cb-subnet4-set", {"server-tag": "test-server", "subnet4": {
        "id": SUBNET_ID, "subnet": "127.0.0.0/24", "valid-lifetime": 600}})
    assert refused["result"] == 1, refused
    assert snapshot() == before_refusal, "Refused member mutation changed SQL/audit state"

    require_success(send("config-reload"))
    row, member = runtime()
    assert domain(row) == "m27-network.example"
    assert all(option["code"] != 15 for option in member.get("option-data", []))
    network_options = dict(expected)
    network_options[15] = b"m27-network.example"
    packet(network_options)

    diagnostic(
        "INSERT INTO dhcp4_options(code, formatted_value, space, persistent, "
        "scope_id, dhcp4_subnet_id, client_classes) VALUES "
        f"(15, 'm27-subnet.example', 'dhcp4', {persistent}, 1, {SUBNET_ID}, '[]')")
    require_success(send("config-reload"))
    row, member = runtime()
    assert domain(row) == "m27-network.example"
    assert domain(member) == "m27-subnet.example"
    subnet_options = dict(expected)
    subnet_options[15] = b"m27-subnet.example"
    packet(subnet_options)

    diagnostic(
        "INSERT INTO dhcp4_options(code, formatted_value, space, persistent, scope_id, "
        "pool_id, client_classes) SELECT 15, 'm27-pool.example', 'dhcp4', "
        f"{persistent}, 5, id, '[]' FROM dhcp4_pool WHERE subnet_id={SUBNET_ID}")
    require_success(send("config-reload"))
    _, member = runtime()
    assert domain(member["pools"][0]) == "m27-pool.example"
    pool_options = dict(expected)
    pool_options[15] = b"m27-pool.example"
    packet(pool_options)

    # Return the original minimal standalone subnet to later pool/delete tests.
    diagnostic(
        "DELETE FROM dhcp4_options WHERE code=15 AND space='dhcp4' AND "
        f"((scope_id=4 AND shared_network_name='{network}') OR "
        f"(scope_id=1 AND dhcp4_subnet_id={SUBNET_ID}) OR "
        f"(scope_id=5 AND pool_id IN (SELECT id FROM dhcp4_pool "
        f"WHERE subnet_id={SUBNET_ID}))); "
        "UPDATE dhcp4_subnet SET shared_network_name=NULL, "
        f"modification_ts=CURRENT_TIMESTAMP WHERE subnet_id={SUBNET_ID}")
    require_success(send("config-reload"))
    assert _pools(_subnets(send, "config-get")[SUBNET_ID]) == [
        ("127.0.0.10", "127.0.0.29")]
    packet(expected)
    print("PASS: diagnostic shared-network membership requires explicit activation; "
          "nested runtime membership and global < network < subnet < pool domain-option "
          "precedence verified in actual OFFER/ACK; router/DNS/custom and BOOTP preserved")


def _verify_rich_subnet(send, directory, snapshot, sql):
    """Native rich writes affect packets only after explicit activation."""
    arguments = {"server-tag": "test-server", "subnet4": {
        "id": SUBNET_ID, "subnet": "127.0.0.0/24", "valid-lifetime": 1200,
        "renew-timer": 200, "rebind-timer": 400,
        "next-server": "192.0.2.28", "server-hostname": "m28-packet",
        "boot-file-name": "m28-packet.efi", "client-classes": ["ALL"],
        "pools": [{"pool": "127.0.0.64/28", "client-classes": ["ALL"]}]}}
    previous = _subnets(send, "config-get")[SUBNET_ID]
    result = require_success(send("cb-subnet4-set", arguments))
    assert result["activation-requested"] is False
    assert _subnets(send, "config-get")[SUBNET_ID] == previous
    # Leave capacity for fresh clients in the later option/inheritance cases.
    # Every exchange verifies a new lease with its full configured lifetime.
    _exchange(directory, "127.0.0.10", "127.0.0.29", expected_options=PAYLOADS)
    require_success(send("config-reload"))
    runtime = _subnets(send, "config-get")[SUBNET_ID]
    assert runtime["valid-lifetime"] == 1200
    assert runtime["renew-timer"] == 200 and runtime["rebind-timer"] == 400
    assert runtime["next-server"] == "192.0.2.28"
    assert runtime["server-hostname"] == "m28-packet"
    packet_options = dict(PAYLOADS)
    packet_options.update({58: struct.pack("!I", 200), 59: struct.pack("!I", 400)})
    _exchange(directory, "127.0.0.64", "127.0.0.79", lifetime=1200,
              boot_file="m28-packet.efi", expected_options=packet_options)
    # Omitted rich fields/pools survive a lifetime-only native update.
    update = {"server-tag": "test-server", "subnet4": {
        "id": SUBNET_ID, "subnet": "127.0.0.0/24", "valid-lifetime": 1200,
        "client-classes": ["KNOWN"]}}
    require_success(send("cb-subnet4-set", update))
    _exchange(directory, "127.0.0.64", "127.0.0.79", lifetime=1200,
              boot_file="m28-packet.efi", expected_options=packet_options)
    require_success(send("config-reload"))
    _exchange(directory, None, None, expect_offer=False)
    update["subnet4"]["client-classes"] = []
    require_success(send("cb-subnet4-set", update))
    require_success(send("config-reload"))
    _exchange(directory, "127.0.0.64", "127.0.0.79", lifetime=1200,
              boot_file="m28-packet.efi", expected_options=packet_options)
    before = snapshot()
    replacement = dict(update, subnet4=dict(update["subnet4"], pools=[]))
    assert send("cb-subnet4-set", replacement)["result"] == 1
    assert snapshot() == before, "Refused rich pool removal changed SQL/audit"
    # Diagnostic-only reset removes the pool class protected against replacement.
    backend = require_success(send("config-get"))["Dhcp4"]["config-control"][
        "config-databases"][0]["type"]
    audit = ("SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
             "'M28 packet fixture reset', false); " if backend == "postgresql" else
             "CALL createAuditRevisionDHCP4(NOW(), 'all', 'M28 packet fixture reset', 0); ")
    sql("START TRANSACTION; " + audit +
        f"UPDATE dhcp4_pool SET client_classes=NULL WHERE subnet_id={SUBNET_ID}; COMMIT")
    reset = dict(update, subnet4=dict(update["subnet4"], **{
        "valid-lifetime": 600, "renew-timer": 0, "rebind-timer": 0,
        "next-server": "0.0.0.0", "server-hostname": "", "boot-file-name": "",
        "pools": [{"start": "127.0.0.10", "end": "127.0.0.29"}]}))
    require_success(send("cb-subnet4-set", reset))
    require_success(send("config-reload"))
    _exchange(directory, "127.0.0.10", "127.0.0.29", boot_file="",
              expected_options=PAYLOADS)
    # Explicit empty boot fields are real overrides, not inheritance. Restore
    # SQL NULLs diagnostically so the later global-boot regression can inherit.
    sql("START TRANSACTION; " + audit +
        "UPDATE dhcp4_subnet SET boot_file_name=NULL, server_hostname=NULL, "
        f"next_server=NULL WHERE subnet_id={SUBNET_ID}; COMMIT")
    require_success(send("config-reload"))
    print("PASS: rich subnet/prefix pool persists separately from activation; actual "
          "OFFER/ACK lifetime/T1/T2/boot-file and class gating; safe omission and "
          "SQL/audit-preserving rich pool replacement refusal")


def verify_dhcp(send, config, save, directory, snapshot, sql=None):
    """Persist with our hook; explicitly activate; prove packet and lease effects.

    The caller owns the Kea process, disposable SQL backend, namespace, and all
    cleanup. Optional SQL creates disposable diagnostic membership/option fixtures;
    production commands never perform membership or scoped-option SQL writes.
    """
    _isolated()
    lease_path = Path(directory).resolve() / "leases.csv"
    config["Dhcp4"]["interfaces-config"] = {
        "interfaces": ["lo/127.0.0.1"], "dhcp-socket-type": "udp"}
    config["Dhcp4"]["lease-database"] = {
        "type": "memfile", "persist": True, "name": str(lease_path), "lfc-interval": 0}
    config["Dhcp4"]["server-tag"] = "test-server"
    save()
    require_success(send("config-reload"))
    assert SUBNET_ID not in _subnets(send, "config-get")

    def persist(first, last):
        pools = [] if first is None else [{"start": first, "end": last}]
        arguments = {"server-tag": "test-server", "subnet4": {
            "id": SUBNET_ID, "subnet": "127.0.0.0/24", "valid-lifetime": 600,
            "pools": pools}}
        result = require_success(send("cb-subnet4-set", arguments))
        assert result["persisted"] is True and result["activation-requested"] is False
        expected = [] if first is None else [(first, last)]
        assert _pools(_subnets(send, "cb-subnet4-list")[SUBNET_ID]) == expected

    persist("127.0.0.10", "127.0.0.29")
    assert SUBNET_ID not in _subnets(send, "config-get")
    _exchange(directory, None, None, expect_offer=False)

    # Force native activation to fail before committing a runtime configuration.
    # A failed reload can remove the live backend pool. Check SQL separately
    # from the runtime and restore backend connectivity with a corrected reload.
    before_failure = snapshot()
    good_interfaces = config["Dhcp4"]["interfaces-config"]
    config["Dhcp4"]["interfaces-config"] = {
        "interfaces": ["kea_missing_if"], "dhcp-socket-type": "udp", "re-detect": False}
    save()
    try:
        failure = send("config-reload")
        assert failure["result"] != 0, "Invalid interface did not fail native activation"
    finally:
        config["Dhcp4"]["interfaces-config"] = good_interfaces
        save()
    assert snapshot() == before_failure, "Failed activation changed persisted SQL"
    backend = send("cb-subnet4-list")
    if backend["result"] == 0:
        assert _pools({row["id"]: row for row in backend["arguments"]["subnet4"]}[
            SUBNET_ID]) == [("127.0.0.10", "127.0.0.29")]
    else:
        assert backend["result"] == 1
        print("PASS: failed reload removes live backend access; persisted SQL remains intact")
    assert SUBNET_ID not in _subnets(send, "config-get")
    print("PASS: SQL persistence survives failed native activation; runtime remains unchanged")
    require_success(send("config-reload"))
    assert _pools(_subnets(send, "cb-subnet4-list")[SUBNET_ID]) == [
        ("127.0.0.10", "127.0.0.29")]
    assert _pools(_subnets(send, "config-get")[SUBNET_ID]) == [
        ("127.0.0.10", "127.0.0.29")]
    _exchange(directory, "127.0.0.10", "127.0.0.29", expected_options=PAYLOADS,
              absent_options=(246,))
    if sql is not None:
        _verify_rich_subnet(send, directory, snapshot, sql)
    # Persist another custom option while packets still reflect the old runtime.
    require_success(send("cb-option-def4-set", {"server-tag": "test-server", "option-def": {
        "name": "m26-packet", "code": 246, "space": "dhcp4", "type": "string"}}))
    require_success(send("cb-option4-global-set", {"server-tag": "test-server", "option": {
        "code": 246, "space": "dhcp4", "data": "after-activation", "always-send": True}}))
    _exchange(directory, "127.0.0.10", "127.0.0.29", expected_options=PAYLOADS,
              absent_options=(246,))
    require_success(send("config-reload"))
    expected = dict(PAYLOADS)
    expected[246] = b"after-activation"
    _exchange(directory, "127.0.0.10", "127.0.0.29", expected_options=expected)
    print("PASS: router/DNS/domain/custom OFFER and ACK bytes; new custom option "
          "absent until explicit activation")

    # A native global affects the BOOTP file only after explicit activation.
    initial_file = require_success(send("config-get"))["Dhcp4"].get("boot-file-name", "")
    require_success(send("cb-global-parameter4-set", {
        "server-tag": "test-server", "name": "boot-file-name", "value": "m25-packet.efi"}))
    assert require_success(send("config-get"))["Dhcp4"].get("boot-file-name", "") == initial_file
    _exchange(directory, "127.0.0.10", "127.0.0.29", boot_file=initial_file)
    require_success(send("config-reload"))
    assert require_success(send("config-get"))["Dhcp4"]["boot-file-name"] == "m25-packet.efi"
    _exchange(directory, "127.0.0.10", "127.0.0.29", boot_file="m25-packet.efi")
    refused = send("cb-global-parameter4-del", {
        "server-tag": "test-server", "name": "boot-file-name"})
    assert refused["result"] == 1, refused
    _exchange(directory, "127.0.0.10", "127.0.0.29", boot_file="m25-packet.efi")
    print("PASS: persisted global boot-file-name changes actual OFFER/ACK only after activation; "
          "unsafe deletion is refused")

    if sql is not None:
        _verify_shared_network_inheritance(send, config, directory, snapshot, sql, expected)

    # Pool replacement changes backend visibility first, then runtime on pull.
    time.sleep(1.1)
    persist("127.0.0.30", "127.0.0.40")
    assert _pools(_subnets(send, "config-get")[SUBNET_ID]) == [
        ("127.0.0.10", "127.0.0.29")]
    require_success(send("config-backend-pull"))
    assert _pools(_subnets(send, "config-get")[SUBNET_ID]) == [
        ("127.0.0.30", "127.0.0.40")]
    require_success(send("config-reload"))
    _exchange(directory, "127.0.0.30", "127.0.0.40")

    time.sleep(1.1)
    persist(None, None)
    require_success(send("config-backend-pull"))
    assert _pools(_subnets(send, "config-get")[SUBNET_ID]) == []
    _exchange(directory, None, None, expect_offer=False)
    print("PASS: an explicitly activated empty pool collection produces no DHCPOFFER")
    time.sleep(1.1)
    persist("127.0.0.30", "127.0.0.40")
    require_success(send("config-backend-pull"))
    return lease_path


def verify_packet_restart(send, directory):
    """Called only after the harness has stopped and restarted the same Kea."""
    assert _pools(_subnets(send, "config-get")[SUBNET_ID]) == [
        ("127.0.0.30", "127.0.0.40")]
    expected = dict(PAYLOADS)
    expected[246] = b"after-activation"
    path = _exchange(directory, "127.0.0.30", "127.0.0.40", boot_file="m25-packet.efi",
                     expected_options=expected)
    print("PASS: restarted Kea loads SQL pool/global values and records a fresh DHCP lease")
    before = path.read_bytes()
    time.sleep(1.1)
    response = require_success(send("cb-subnet4-del", {
        "id": SUBNET_ID, "server-tag": "test-server", "preserve-leases": True}))
    assert response["leases-deleted"] is False
    assert path.read_bytes() == before, "Configuration deletion modified lease storage"
    assert send("cb-subnet4-get", {"id": SUBNET_ID})["result"] == 3
    assert SUBNET_ID not in _subnets(send, "cb-subnet4-list")
    assert SUBNET_ID in _subnets(send, "config-get")
    # The still-active runtime subnet can allocate despite SQL deletion.
    _exchange(directory, "127.0.0.30", "127.0.0.40")
    before = path.read_bytes()
    require_success(send("config-backend-pull"))
    assert SUBNET_ID not in _subnets(send, "config-get")
    _exchange(directory, None, None, expect_offer=False)
    assert path.read_bytes() == before, "Native deletion activation removed/changed leases"
    require_success(send("config-reload"))
    assert SUBNET_ID not in _subnets(send, "config-get")
    _exchange(directory, None, None, expect_offer=False)
    assert path.read_bytes() == before
    print("PASS: SQL deletion retains leases and active DORA; explicit pull/reload "
          "removes runtime subnet, no subsequent DHCPOFFER, existing leases unchanged")
    return path
