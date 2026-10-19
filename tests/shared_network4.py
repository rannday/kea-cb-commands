"""Native shared-network assertions for disposable PostgreSQL/MariaDB fixtures."""

# SPDX-License-Identifier: MPL-2.0
from typing import Any

from mutation import configure_admission
from smoke import ADMISSION_ERROR, require_success

PREFIX = "cb-shared-network4-"
TAG = "test-server"
NAME = "m27-specific"
COMMON = "m27-common"
REFUSAL = (
    "Existing shared-network mutations are unsupported: complete associations "
    "and dependencies cannot be verified."
)


def verify_shared_networks(send, snapshot, sql, config, save):
    """Read/refusal snapshots include native audit records and all SQL objects."""
    del sql  # Rich membership/hidden-association fixtures belong to the caller.

    def request(operation, obj=None, tag: Any = TAG):
        arguments: dict[str, Any] = {"server-tag": tag}
        if operation == "set":
            arguments["shared-network"] = obj
        elif operation != "list":
            arguments["name"] = obj
        return send(PREFIX + operation, arguments)

    def checked(operation, obj=None, tag: Any = TAG, result=0):
        before = snapshot()
        response = request(operation, obj, tag)
        assert response["result"] == result, response
        assert snapshot() == before, (operation, obj, "SQL/audit changed")
        return response

    def rows(response, tag=TAG):
        result = require_success(response)
        assert result["associations-complete"] is False, result
        assert result["membership-selector"] == "ANY", result
        assert result["server-tag"] == tag, result
        assert result["count"] == len(result["shared-networks"]), result
        return result["shared-networks"]

    checked("list", result=3)
    for operation in ("get", "del"):
        checked(operation, NAME, result=3)
    active_before = require_success(send("config-get"))["Dhcp4"].get("shared-networks", [])
    for tag, obj in (
        (TAG, {"name": NAME, "valid-lifetime": 900, "renew-timer": 300, "rebind-timer": 600}),
        ("all", {"name": COMMON}),
    ):
        response = request("set", obj, tag)
        assert require_success(response)["activation-requested"] is False, response
        created = rows(response, tag)
        assert len(created) == 1, created
        assert created[0]["name"] == obj["name"], created
        assert created[0]["server-tags"] == [tag], created
        assert created[0]["subnet4"] == [], created
        for field, value in obj.items():
            assert created[0][field] == value, created
        observed = rows(checked("get", obj["name"], tag), tag)
        assert observed == created, (observed, created)
        assert any(row["name"] == obj["name"] for row in rows(checked("list", tag=tag), tag))
        for operation, value in (("set", obj), ("del", obj["name"])):
            refusal = checked(operation, value, tag, result=1)
            assert refusal == {"result": 1, "text": REFUSAL}, refusal

    # Name is globally unique, so an invisible selected view cannot authorize upsert.
    checked("get", NAME, "m25-server", result=3)
    for operation, value in (("set", {"name": NAME}), ("del", NAME)):
        refusal = checked(operation, value, "m25-server", result=1)
        assert refusal == {"result": 1, "text": REFUSAL}, refusal
    assert require_success(send("config-get"))["Dhcp4"].get("shared-networks", []) == active_before

    invalid_objects = [
        None, [], False, {}, {"name": 1}, {"name": ""}, {"name": " "},
        {"name": " leading"}, {"name": "trailing "}, {"name": "x" * 129},
        {"name": "nul\x00name"},
        {"name": "invalid", "valid-lifetime": 0},
        {"name": "invalid", "valid-lifetime": 2147483648},
        {"name": "invalid", "valid-lifetime": 4294967295},
        {"name": "invalid", "valid-lifetime": True},
        {"name": "invalid", "renew-timer": "300"},
        {"name": "invalid", "rebind-timer": -1},
        {"name": "invalid", "renew-timer": 600, "rebind-timer": 300},
        {"name": "invalid", "valid-lifetime": 600, "renew-timer": 600},
        {"name": "invalid", "valid-lifetime": 600, "rebind-timer": 601},
        {"name": "invalid", "subnet4": []},
        {"name": "invalid", "option-data": []},
        {"name": "invalid", "unexpected": True},
    ]
    for obj in invalid_objects:
        checked("set", obj, result=1)
    for name in (None, False, 1, "", " name", "name ", "x" * 129, "nul\x00name"):
        for operation in ("get", "del"):
            checked(operation, name, result=1)
    for tag in (None, False, 1, "", "UPPER", " all", "any", "missing-m27-server"):
        checked("set", {"name": "invalid"}, tag, result=1)
    for operation in ("list", "get", "set", "del"):
        for arguments in (None, [], False, {}, {"server-tag": TAG, "unexpected": True}):
            before = snapshot()
            response = send(PREFIX + operation, arguments)
            assert response["result"] == 1, response
            assert snapshot() == before, (operation, arguments, "SQL/audit changed")

    configure_admission(send, config, save, {"allow-mutations": False})
    for operation in ("set", "del"):
        before = snapshot()
        assert request(operation, []) == ADMISSION_ERROR
        assert snapshot() == before
    rows(checked("get", NAME))
    configure_admission(send, config, save, {"allow-mutations": True})
    require_success(send("config-reload"))
    active = require_success(send("config-get"))["Dhcp4"].get("shared-networks", [])
    assert any(row["name"] == NAME for row in active), active
    print("PASS: M27 native shared-network reads/create, common/specific selectors, "
          "global-name preflight, exact SQL/audit-preserving refusal, admission "
          "and independent explicit activation")


def verify_shared_network_membership(send, snapshot, sql, config, save):
    """Diagnostic fixtures characterize membership; production commands never move it."""
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]

    def diagnostic(statements):
        if backend == "postgresql":
            prefix = ("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
                      "'all', 'M27 membership fixture', false); ")
        else:
            prefix = ("START TRANSACTION; CALL createAuditRevisionDHCP4("
                      "CURRENT_TIMESTAMP, 'all', 'M27 membership fixture', 0); ")
        sql(prefix + statements + "; COMMIT")

    def get(name="m27-members", tag=TAG):
        before = snapshot()
        result = require_success(send(PREFIX + "get", {"server-tag": tag, "name": name}))
        assert snapshot() == before, "Membership read changed SQL/audit"
        assert result["membership-selector"] == "ANY", result
        assert result["associations-complete"] is False, result
        assert result["count"] == 1, result
        return result["shared-networks"][0]

    def refuse(name="m27-members"):
        for operation in ("set", "del"):
            arguments: dict[str, Any] = {"server-tag": TAG}
            arguments["shared-network" if operation == "set" else "name"] = (
                {"name": name} if operation == "set" else name)
            before = snapshot()
            assert send(PREFIX + operation, arguments) == {"result": 1, "text": REFUSAL}
            assert snapshot() == before, "Refused mutation changed membership/SQL/audit"

    for name in ("m27-members", "m27-other"):
        require_success(send(PREFIX + "set", {
            "server-tag": TAG, "shared-network": {"name": name}}))
    for subnet_id, prefix in ((970, "198.19.70.0/24"), (971, "198.19.71.0/24")):
        require_success(send("cb-subnet4-set", {"server-tag": TAG, "subnet4": {
            "id": subnet_id, "subnet": prefix, "valid-lifetime": 600}}))
    assert get()["subnet4"] == []
    # Native SQL schema uses shared_network_name for both member and option scope.
    diagnostic("UPDATE dhcp4_subnet SET shared_network_name='m27-members', "
               "modification_ts=CURRENT_TIMESTAMP WHERE subnet_id IN (970,971)")
    row = get()
    assert [member["id"] for member in row["subnet4"]] == [970, 971], row
    assert all(member["server-tags"] == [TAG] for member in row["subnet4"]), row
    refuse()
    before = snapshot()
    response = send("cb-subnet4-set", {"server-tag": TAG, "subnet4": {
        "id": 970, "subnet": "198.19.70.0/24", "valid-lifetime": 600}})
    assert response["result"] == 1, response
    assert snapshot() == before, "Existing subnet restriction changed SQL/audit"

    diagnostic(
        "INSERT INTO dhcp4_shared_network_server "
        "(shared_network_id,server_id,modification_ts) "
        "SELECT n.id,s.id,CURRENT_TIMESTAMP FROM dhcp4_shared_network n "
        "JOIN dhcp4_server s ON s.tag='m25-server' WHERE n.name='m27-members'; "
        "DELETE FROM dhcp4_subnet_server WHERE subnet_id=971; "
        "INSERT INTO dhcp4_subnet_server (subnet_id,server_id,modification_ts) "
        "SELECT 971,id,CURRENT_TIMESTAMP FROM dhcp4_server WHERE tag='m25-server'")
    row = get()
    assert set(row["server-tags"]) == {TAG, "m25-server"}, row
    assert [member["id"] for member in row["subnet4"]] == [970, 971], row
    assert row["subnet4"][1]["server-tags"] == ["m25-server"], row
    other_view = get(tag="m25-server")
    assert other_view["subnet4"] == row["subnet4"], (other_view, row)
    common = get(COMMON, TAG)
    assert common["name"] == COMMON and common["subnet4"] == [], common

    boolean = "true" if backend == "postgresql" else "1"
    diagnostic(
        "INSERT INTO dhcp4_options "
        "(code,formatted_value,space,persistent,scope_id,shared_network_name,client_classes,modification_ts) "
        "VALUES(15,'m27-network.example','dhcp4'," + boolean +
        ",4,'m27-members','[]',CURRENT_TIMESTAMP)")
    row = get()
    assert any(option["code"] == 15 and option["data"] == "m27-network.example"
               for option in row["option-data"]), row
    refuse()

    diagnostic("UPDATE dhcp4_subnet SET shared_network_name='m27-other', "
               "modification_ts=CURRENT_TIMESTAMP WHERE subnet_id=971")
    assert [member["id"] for member in get()["subnet4"]] == [970]
    assert [member["id"] for member in get("m27-other")["subnet4"]] == [971]
    assert get(COMMON, "all")["subnet4"] == []
    diagnostic("UPDATE dhcp4_subnet SET shared_network_name=NULL, "
               "modification_ts=CURRENT_TIMESTAMP WHERE subnet_id IN (970,971); "
               "DELETE FROM dhcp4_subnet_server WHERE subnet_id=971; "
               "INSERT INTO dhcp4_subnet_server (subnet_id,server_id,modification_ts) "
               "SELECT 971,id,CURRENT_TIMESTAMP FROM dhcp4_server WHERE tag='test-server'")
    assert get()["subnet4"] == [] and get("m27-other")["subnet4"] == []
    refuse()
    save()
    require_success(send("config-reload"))
    active = require_success(send("config-get"))["Dhcp4"]
    networks = {network["name"]: network for network in active.get("shared-networks", [])}
    assert networks["m27-members"].get("subnet4", []) == [], networks
    assert any(option["code"] == 15 and option["data"] == "m27-network.example"
               for option in networks["m27-members"]["option-data"]), networks
    print("PASS: M27 diagnostic SQL membership add/move/remove, ANY membership "
          "across selectors, multi-association network, network option readback, "
          "existing-subnet restriction and SQL/audit-preserving mutation refusals")


def _restart_membership(sql, config, network):
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    if backend == "postgresql":
        prefix = ("BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
                  "'all', 'M27 restart fixture', false); ")
    else:
        prefix = ("START TRANSACTION; CALL createAuditRevisionDHCP4("
                  "CURRENT_TIMESTAMP, 'all', 'M27 restart fixture', 0); ")
    value = "'m27-other'" if network else "NULL"
    sql(prefix + "UPDATE dhcp4_subnet SET shared_network_name=" + value +
        ", modification_ts=CURRENT_TIMESTAMP WHERE subnet_id=970; COMMIT")


def prepare_shared_network_restart(send, sql, config):
    """Leave persisted membership pending the fixture's clean process restart."""
    before = require_success(send("config-get"))
    _restart_membership(sql, config, True)
    row = require_success(send(PREFIX + "get", {
        "server-tag": TAG, "name": "m27-other"}))["shared-networks"][0]
    assert [member["id"] for member in row["subnet4"]] == [970], row
    assert require_success(send("config-get")) == before


def verify_shared_networks_restart(send, sql, config):
    """A fresh process independently reads persisted native network properties."""
    for tag, name in ((TAG, NAME), ("all", COMMON)):
        result = require_success(send(PREFIX + "get", {"server-tag": tag, "name": name}))
        assert result["associations-complete"] is False
        assert result["membership-selector"] == "ANY"
        row = result["shared-networks"][0]
        assert row["name"] == name and row["subnet4"] == [], row
        assert row["server-tags"] == [tag], row
    active = require_success(send("config-get"))["Dhcp4"].get("shared-networks", [])
    assert any(row["name"] == NAME for row in active), active
    network = next(row for row in active if row["name"] == "m27-other")
    assert [member["id"] for member in network["subnet4"]] == [970], network
    persisted = require_success(send(PREFIX + "get", {
        "server-tag": TAG, "name": "m27-other"}))["shared-networks"][0]
    assert [member["id"] for member in persisted["subnet4"]] == [970], persisted
    _restart_membership(sql, config, False)
    require_success(send("config-reload"))
    restored = require_success(send("config-get"))["Dhcp4"]
    assert 970 in {row["id"] for row in restored["subnet4"]}, restored
    print("PASS: M27 shared-network properties, membership and independently observed "
          "active state survive process restart; diagnostic detach explicitly activated")
