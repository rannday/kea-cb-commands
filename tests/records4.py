"""Shared native DHCPv4 server/global assertions for disposable SQL fixtures."""

# SPDX-License-Identifier: MPL-2.0
from mutation import configure_admission
from smoke import ADMISSION_ERROR, require_success

SERVER = "cb-server4-"
GLOBAL = "cb-global-parameter4-"
TAG = "m25-server"


def verify_records(send, snapshot, sql, config, save):
    """Exercise native persistence independently from explicit runtime activation."""
    def checked(name, arguments=None, result=0):
        before = snapshot()
        response = send(name, arguments)
        assert response["result"] == result, response
        assert snapshot() == before, (name, "Read/rejected operation changed SQL")
        return response.get("arguments")

    def server(tag=TAG):
        rows = require_success(send(SERVER + "get", {"server-tag": tag}))["servers"]
        assert len(rows) == 1, rows
        return rows[0]

    def parameter(name, tag=TAG):
        result = require_success(send(GLOBAL + "get", {"server-tag": tag, "name": name}))
        assert result["count"] == 1, result
        return result["parameters"][0]

    def set_parameter(name, value, tag=TAG):
        result = require_success(send(GLOBAL + "set", {
            "server-tag": tag, "name": name, "value": value}))
        assert result["activation-requested"] is False, result
        row = result["parameters"][0]
        assert row["name"] == name and row["value"] == value, row
        assert type(row["value"]) is type(value), row
        assert row["server-tags"] == [tag], row
        return row

    original_servers = require_success(send(SERVER + "list"))["servers"]
    checked(SERVER + "get", {"server-tag": TAG}, 3)
    missing = checked(SERVER + "del", {"server-tag": TAG}, 3)
    assert missing == {"count": 0, "servers": [], "activation-requested": False}

    for description in ("created", "updated", "updated"):
        result = require_success(send(SERVER + "set", {
            "server-tag": TAG, "description": description}))
        assert result["count"] == 1 and result["activation-requested"] is False
        assert server()["description"] == description
        assert server()["server-tag"] == TAG
    listed = checked(SERVER + "list")["servers"]
    assert [row["server-tag"] for row in listed] == sorted(
        row["server-tag"] for row in listed)
    assert [row for row in listed if row["server-tag"] != TAG] == original_servers

    for tag in ("", "all", "any", "M25-SERVER", " m25-server ", "x" * 257, None, 25, []):
        checked(SERVER + "set", {"server-tag": tag, "description": "invalid"}, 1)
        checked(SERVER + "get", {"server-tag": tag}, 1)
    for description in (None, False, 1, [], {}, "x" * 65537, "bad\0description"):
        checked(SERVER + "set", {"server-tag": TAG, "description": description}, 1)
    for arguments in (None, {}, [], {"server-tag": TAG},
                      {"server-tag": TAG, "description": "", "unexpected": True}):
        checked(SERVER + "set", arguments, 1)

    # A fresh selector has no globals; creating a server does not copy common data.
    empty = checked(GLOBAL + "list", {"server-tag": TAG}, 3)
    assert empty["parameters"] == [] and empty["count"] == 0, empty
    checked(GLOBAL + "get", {"server-tag": TAG, "name": "authoritative"}, 3)
    checked(GLOBAL + "del", {"server-tag": TAG, "name": "authoritative"}, 3)
    for name, value in (("authoritative", False), ("renew-timer", 120),
                        ("t1-percent", 0.4), ("boot-file-name", "m25-scalar")):
        set_parameter(name, value)
        row = parameter(name)
        assert row["value"] == value and type(row["value"]) is type(value), row
        assert row["server-tags"] == [TAG], row
    assert parameter("authoritative")["value"] is False
    associated = checked(GLOBAL + "list", {"server-tag": TAG})["parameters"]
    require_success(send(SERVER + "set", {"server-tag": TAG, "description": "updated"}))
    assert checked(GLOBAL + "list", {"server-tag": TAG})["parameters"] == associated
    before_parameters = checked(GLOBAL + "list", {"server-tag": TAG})["parameters"]
    assert [row["name"] for row in before_parameters] == sorted(
        row["name"] for row in before_parameters)
    checked(GLOBAL + "set", {"server-tag": TAG, "name": "renew-timer", "value": 180}, 1)
    assert parameter("renew-timer")["value"] == 120
    after_parameters = checked(GLOBAL + "list", {"server-tag": TAG})["parameters"]
    assert [row for row in after_parameters if row["name"] != "renew-timer"] == [
        row for row in before_parameters if row["name"] != "renew-timer"]

    for name, value in (
        ("", 1), ("not-a-kea-global", 1), ("dhcp-ddns.enable-updates", True),
        ("dhcp-ddns", {"enable-updates": True}), ("host-reservation-identifiers", []),
        ("authoritative", 1), ("authoritative", None), ("renew-timer", True),
        ("renew-timer", -1), ("renew-timer", 4294967296),
        ("valid-lifetime", 0), ("renew-timer", "120"),
        ("t1-percent", 1), ("t1-percent", 0.0), ("t2-percent", 1.0),
        ("boot-file-name", []), ("boot-file-name", "x" * 128),
        ("boot-file-name", "bad\0file"), ("next-server", "::1"),
    ):
        checked(GLOBAL + "set", {"server-tag": TAG, "name": name, "value": value}, 1)
    for tag in ("any", "", "M25-SERVER", None, [], "m25-missing"):
        checked(GLOBAL + "get", {"server-tag": tag, "name": "authoritative"}, 1)
    for arguments in (None, {}, [], {"server-tag": TAG},
                      {"server-tag": TAG, "name": False, "value": 1},
                      {"server-tag": TAG, "name": "authoritative", "value": True,
                       "unexpected": True}):
        checked(GLOBAL + "set", arguments, 1)

    # Separate native rows override common values, but existing-row mutations
    # are refused because filtered native views cannot prove full associations.
    set_parameter("boot-file-name", "m25-common", "all")
    assert parameter("boot-file-name")["value"] == "m25-scalar"
    assert parameter("boot-file-name", "all")["value"] == "m25-common"
    for tag in (TAG, "test-server", "all"):
        checked(GLOBAL + "set", {
            "server-tag": tag, "name": "boot-file-name", "value": "refused"}, 1)
        checked(GLOBAL + "del", {"server-tag": tag, "name": "boot-file-name"}, 1)

    # Diagnostic SQL is confined to disposable fixtures: make a shared native
    # row that ONE(tag) readback misrepresents as a single association.
    sql("INSERT INTO dhcp4_global_parameter_server "
        "(parameter_id, server_id, modification_ts) "
        "SELECT g.id, s.id, CURRENT_TIMESTAMP FROM dhcp4_global_parameter g "
        "JOIN dhcp4_global_parameter_server gs ON g.id=gs.parameter_id "
        "JOIN dhcp4_server owner ON gs.server_id=owner.id "
        "JOIN dhcp4_server s ON s.tag='test-server' "
        "WHERE owner.tag='m25-server' AND g.name='authoritative'")
    assert parameter("authoritative")["server-tags"] == [TAG]
    assert parameter("authoritative", "test-server")["server-tags"] == ["test-server"]
    for tag in (TAG, "test-server"):
        checked(GLOBAL + "set", {
            "server-tag": tag, "name": "authoritative", "value": True}, 1)
        checked(GLOBAL + "del", {"server-tag": tag, "name": "authoritative"}, 1)

    # A mixed common/named association is likewise hidden behind the all tag.
    sql("INSERT INTO dhcp4_global_parameter_server "
        "(parameter_id, server_id, modification_ts) "
        "SELECT g.id, s.id, CURRENT_TIMESTAMP FROM dhcp4_global_parameter g "
        "JOIN dhcp4_global_parameter_server gs ON g.id=gs.parameter_id "
        "JOIN dhcp4_server owner ON gs.server_id=owner.id "
        "JOIN dhcp4_server s ON s.tag='test-server' "
        "WHERE owner.tag='all' AND g.name='boot-file-name'")
    assert parameter("boot-file-name", "test-server")["server-tags"] == ["all"]
    for tag in ("all", "test-server"):
        checked(GLOBAL + "set", {
            "server-tag": tag, "name": "boot-file-name", "value": "refused"}, 1)
        checked(GLOBAL + "del", {"server-tag": tag, "name": "boot-file-name"}, 1)

    # Existing-record deletion is deliberately excluded: native deletion also
    # purges orphan globals/options/definitions. Neither association may change.
    before = snapshot()
    response = send(SERVER + "del", {"server-tag": TAG})
    assert response == {"result": 1, "text": (
        "Server deletion is unsupported: native orphan cleanup cannot be verified safe.")}
    assert snapshot() == before
    checked(SERVER + "del", {"server-tag": TAG}, 1)
    assert parameter("authoritative")["server-tags"] == [TAG]
    assert parameter("boot-file-name", "all")["server-tags"] == ["all"]

    # Read-only admission applies before malformed arguments or backend work.
    configure_admission(send, config, save, {"allow-mutations": False})
    before = snapshot()
    for command, arguments in (
        (SERVER + "set", {"server-tag": TAG, "description": "denied"}),
        (SERVER + "del", {"server-tag": TAG}),
        (GLOBAL + "set", {"server-tag": TAG, "name": "authoritative", "value": True}),
        (GLOBAL + "del", {"server-tag": TAG, "name": "authoritative"}),
    ):
        assert send(command, arguments) == ADMISSION_ERROR
        assert send(command, []) == ADMISSION_ERROR
    checked(SERVER + "get", {"server-tag": TAG})
    checked(GLOBAL + "get", {"server-tag": TAG, "name": "authoritative"})
    assert snapshot() == before
    configure_admission(send, config, save, {"allow-mutations": True})

    # config-get is an independent runtime observation, never SQL readback.
    active = require_success(send("config-get"))["Dhcp4"]
    assert active["boot-file-name"] == "m25-common", active.get("boot-file-name")
    old_next_server = active["next-server"]
    set_parameter("next-server", "127.0.0.2", "test-server")
    assert require_success(send("config-get"))["Dhcp4"]["next-server"] == old_next_server
    require_success(send("config-reload"))
    assert require_success(send("config-get"))["Dhcp4"]["next-server"] == "127.0.0.2"

    # Restore disposable test data through diagnostic SQL, not a claimed hook
    # delete. Retain only the typed restart sentinel and its two associations.
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    audit = (
        "BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
        "'M25 fixture cleanup', false); "
        if backend == "postgresql" else
        "START TRANSACTION; CALL createAuditRevisionDHCP4(NOW(), 'all', "
        "'M25 fixture cleanup', 0); "
    )
    sql(audit + "DELETE FROM dhcp4_global_parameter WHERE name <> 'authoritative'; COMMIT")
    require_success(send("config-reload"))
    assert require_success(send("config-get"))["Dhcp4"]["boot-file-name"] == ""
    # A harmless shared boolean and its server record remain for restart.
    assert int(sql("SELECT COUNT(*) FROM dhcp4_server WHERE tag='m25-server'")) == 1
    assert int(sql("SELECT COUNT(*) FROM dhcp4_global_parameter g "
                   "JOIN dhcp4_global_parameter_server gs ON g.id=gs.parameter_id "
                   "JOIN dhcp4_server s ON gs.server_id=s.id "
                   "WHERE s.tag='m25-server' AND g.name='authoritative'")) == 1
    print("PASS: M25 native server create/update/list/get, safe delete refusal, "
          "scalar JSON types, selectors/fallback, shared-association mutation refusal, "
          "validation, admission and independently observed explicit activation")


def verify_records_restart(send, packets=False):
    """Read native sentinels after the fixture cleanly replaces its Kea process."""
    rows = require_success(send(SERVER + "get", {"server-tag": TAG}))["servers"]
    assert len(rows) == 1 and rows[0]["description"] == "updated", rows
    result = require_success(send(GLOBAL + "get", {
        "server-tag": TAG, "name": "authoritative"}))
    assert result["parameters"] == [
        {"name": "authoritative", "value": False, "server-tags": [TAG]}], result
    expected_file = "m25-packet.efi" if packets else ""
    assert require_success(send("config-get"))["Dhcp4"]["boot-file-name"] == expected_file
    print("PASS: M25 server and typed associated global persist across process restart")
