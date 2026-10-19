"""Scoped options through real callouts in disposable native SQL backends."""

# SPDX-License-Identifier: MPL-2.0
import copy

from mutation import configure_admission
from smoke import ADMISSION_ERROR, require_success

TAG = "test-server"
PARENTS = {
    "network": {"shared-network-name": "m29-network"},
    "subnet": {"subnet-id": 980},
    "pool": {"subnet-id": 980, "start": "198.19.80.10", "end": "198.19.80.29"},
}


def request(send, scope, operation, option=None, tag=TAG, parent=None):
    args = {"server-tag": tag, "parent": parent or PARENTS[scope]}
    if option is not None:
        args["option"] = option
    return send(f"cb-option4-{scope}-{operation}", args)


def verify_scoped_options(send, snapshot, sql, config, save):
    """Read/refusal snapshots include all persisted objects and audit rows."""
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]

    def diagnostic(statements):
        prefix = (
            "BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
            "'all', 'M29 diagnostic fixture', false); "
            if backend == "postgresql" else
            "START TRANSACTION; CALL createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
            "'all', 'M29 diagnostic fixture', 0); "
        )
        sql(prefix + statements + "; COMMIT")

    def checked(scope, operation, option=None, result=0, **kwargs):
        before = snapshot()
        response = request(send, scope, operation, option, **kwargs)
        assert response["result"] == result, response
        assert snapshot() == before, (scope, operation, "SQL/audit changed")
        return response.get("arguments")

    tables = ("dhcp4_subnet", "dhcp4_subnet_server", "dhcp4_pool",
              "dhcp4_shared_network", "dhcp4_shared_network_server",
              "dhcp4_option_def", "dhcp4_option_def_server",
              "dhcp4_global_parameter", "dhcp4_global_parameter_server",
              "dhcp4_server")
    schema = "'public'" if backend == "postgresql" else "DATABASE()"
    columns = {}
    for table in tables:
        columns[table] = sql(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema = {schema} AND table_name = '{table}' "
            "ORDER BY ordinal_position").decode().splitlines()
        assert columns[table], table

    def parent_sql(scope, parent):
        # Native option audit triggers update only the owning parent's timestamp.
        # Compare all columns, masking that one timestamp in that one parent row.
        quote = '"' if backend == "postgresql" else "`"
        statements = []
        for table in tables:
            target = None
            if scope == "network" and table == "dhcp4_shared_network":
                name = parent["shared-network-name"].replace("'", "''")
                target = f"name = '{name}'"
            elif scope != "network" and table == "dhcp4_subnet":
                target = f"subnet_id = {parent['subnet-id']}"
            fields = []
            for column in columns[table]:
                field = f"{quote}{column}{quote}"
                if column == "modification_ts" and target:
                    field = f"CASE WHEN {target} THEN NULL ELSE {field} END"
                fields.append(field)
            statements.append(f"SELECT {', '.join(fields)} FROM {table} ORDER BY 1")
        return sql("; ".join(statements))

    def create(scope, option, **kwargs):
        parent = kwargs.get("parent", PARENTS[scope])
        before = parent_sql(scope, parent)
        option_ids = [int(row) for row in sql(
            "SELECT option_id FROM dhcp4_options ORDER BY option_id").decode().splitlines()]
        ids = ", ".join(str(value) for value in option_ids) or "NULL"
        existing_query = (
            f"SELECT * FROM dhcp4_options WHERE option_id IN ({ids}) ORDER BY option_id; "
            f"SELECT * FROM dhcp4_options_server WHERE option_id IN ({ids}) "
            "ORDER BY option_id, server_id")
        existing_options = sql(existing_query)
        response = require_success(request(send, scope, "set", option, **kwargs))
        assert sql(existing_query) == existing_options, "Existing options/associations changed"
        assert int(sql("SELECT COUNT(*) FROM dhcp4_options")) == len(option_ids) + 1
        assert parent_sql(scope, parent) == before, (
            "Scoped creation changed parent/association/definition SQL")
        assert response["count"] == 1, response
        assert response["associations-complete"] is False
        assert response["activation-requested"] is False
        row = response["options"][0]
        assert row["code"] == option["code"] and row["space"] == option["space"]
        return row

    def parent_evidence():
        # Full native parent serialization, excluding only the options under test.
        network = require_success(send("cb-shared-network4-get", {
            "server-tag": TAG, "name": "m29-network"}))["shared-networks"][0]
        subnet = require_success(send("cb-subnet4-get", {
            "server-tag": TAG, "id": 980}))["subnet4"][0]
        network = copy.deepcopy(network)
        subnet = copy.deepcopy(subnet)
        network.pop("option-data", None)
        subnet.pop("option-data", None)
        for pool in subnet["pools"]:
            pool.pop("option-data", None)
        return network, subnet

    require_success(send("cb-shared-network4-set", {
        "server-tag": TAG, "shared-network": {"name": "m29-network",
                                             "valid-lifetime": 900}}))
    require_success(send("cb-subnet4-set", {"server-tag": TAG, "subnet4": {
        "id": 980, "subnet": "198.19.80.0/24", "valid-lifetime": 900,
        "renew-timer": 200, "rebind-timer": 400, "boot-file-name": "m29.efi",
        "client-classes": ["ALL"],
        "pools": [{"start": "198.19.80.10", "end": "198.19.80.29",
                   "client-classes": ["ALL"]},
                  {"start": "198.19.80.40", "end": "198.19.80.49"}]}}))
    key = {"code": 15, "space": "dhcp4"}
    before_parent = parent_evidence()
    active_before = require_success(send("config-get"))
    for scope in PARENTS:
        checked(scope, "list", result=3)
        checked(scope, "get", key, result=3)
        checked(scope, "del", key, result=3)
        create(scope, dict(key, data=f"m29-{scope}.example", **{"always-send": True}))
        checked(scope, "get", key)
        assert checked(scope, "list")["count"] == 1
        for operation in ("set", "del"):
            option = dict(key, data="replacement") if operation == "set" else key
            checked(scope, operation, option, result=1)
        assert parent_evidence() == before_parent
    assert require_success(send("config-get")) == active_before

    # Selected M26 definitions, native CSV and binary parsing at all scopes.
    encodings = [
        {"code": 224, "space": "dhcp4", "data": "m29-custom"},
        {"code": 225, "space": "dhcp4", "data": "1234"},
        {"code": 226, "space": "m26", "data": "7, 192.0.2.1"},
        {"code": 227, "space": "m26", "data": "1, 2, 65535"},
        {"code": 224, "space": "m29", "data": "ab", "csv-format": False},
        {"code": 231, "space": "m29", "data": "0102ff", "csv-format": False},
        {"code": 232, "space": "m29", "data": "", "csv-format": False},
        {"code": 233, "space": "m29", "data": "ab", "csv-format": False,
         "client-classes": ["ALL"], "always-send": True},
        {"code": 6, "space": "dhcp4", "data": "192.0.2.53, 192.0.2.54"},
    ]
    for scope in PARENTS:
        for option in encodings:
            create(scope, option)
            identity = {k: v for k, v in option.items()
                        if k in ("code", "space", "client-classes")}
            row = checked(scope, "get", identity)["options"][0]
            if option.get("csv-format") is False:
                assert bytes.fromhex(row["data"]) == bytes.fromhex(option["data"]), row
            if "client-classes" in option:
                assert row["client-classes"] == option["client-classes"], row
            checked(scope, "del", identity, result=1)
        for option in (
            {"code": 234, "space": "m29", "data": "1"},
            {"code": 234, "space": "m29", "data": "zz", "csv-format": False},
            {"code": 234, "space": "m29", "data": 1},
            {"code": 234, "space": "m29", "data": "", "persistent": True},
            {"code": 234, "space": "m29", "data": "", "csv-format": "false"},
            {"code": 234, "space": "m29", "data": "", "client-classes": ["x", "x"]},
        ):
            checked(scope, "set", option, result=1)
        checked(scope, "get", key, tag="m25-server", result=1)
        invalid_parent = ({"shared-network-name": "missing-m29"} if scope == "network"
                          else {"subnet-id": 9999})
        if scope == "pool":
            invalid_parent.update(start="198.19.80.10", end="198.19.80.29")
        checked(scope, "set", dict(key, data="missing"), parent=invalid_parent, result=1)
    assert parent_evidence() == before_parent

    # Direct native scoped writes must coexist with M28's refusal to rewrite options.
    before = snapshot()
    assert send("cb-subnet4-set", {"server-tag": TAG, "subnet4": {
        "id": 980, "subnet": "198.19.80.0/24", "valid-lifetime": 1200}})["result"] == 1
    assert snapshot() == before

    # A common parent is visible through ONE without inventing option associations.
    common = {"shared-network-name": "m29-common"}
    require_success(send("cb-shared-network4-set", {
        "server-tag": "all", "shared-network": {"name": "m29-common"}}))
    create("network", dict(key, data="common.example"), tag="all", parent=common)
    checked("network", "get", key, parent=common)
    checked("network", "set", {"code": 12, "space": "dhcp4", "data": "wrong-owner"},
            parent=common, result=1)

    # Hidden parent/option links: diagnostic SQL creates evidence native option
    # readback cannot expose; no mutating command may treat it as sole ownership.
    diagnostic(
        "INSERT INTO dhcp4_shared_network_server "
        "(shared_network_id,server_id,modification_ts) "
        "SELECT n.id,s.id,CURRENT_TIMESTAMP FROM dhcp4_shared_network n "
        "JOIN dhcp4_server s ON s.tag='m25-server' WHERE n.name='m29-network'; "
        "INSERT INTO dhcp4_options_server (option_id,server_id,modification_ts) "
        "SELECT o.option_id,s.id,CURRENT_TIMESTAMP FROM dhcp4_options o "
        "JOIN dhcp4_server s ON s.tag='m25-server' "
        "WHERE o.scope_id=4 AND o.shared_network_name='m29-network' AND o.code=15")
    checked("network", "get", key, tag="m25-server")
    checked("network", "set", {"code": 12, "space": "dhcp4", "data": "hidden"},
            result=1)
    checked("network", "del", key, result=1)

    # Restore parent association; preserve the hidden option link across reads.
    diagnostic(
        "DELETE FROM dhcp4_shared_network_server WHERE shared_network_id IN "
        "(SELECT id FROM dhcp4_shared_network WHERE name='m29-network') "
        "AND server_id IN (SELECT id FROM dhcp4_server WHERE tag='m25-server')")
    checked("network", "del", key, result=1)

    # Range-only SQL APIs search globally, including UNASSIGNED parents.
    require_success(send("cb-subnet4-set", {"server-tag": TAG, "subnet4": {
        "id": 981, "subnet": "198.19.0.0/16", "valid-lifetime": 900,
        "pools": [{"start": "198.19.80.10", "end": "198.19.80.29"}]}}))
    diagnostic("DELETE FROM dhcp4_subnet_server WHERE subnet_id=981")
    checked("pool", "set", {"code": 12, "space": "dhcp4", "data": "ambiguous"},
            result=1)
    diagnostic("DELETE FROM dhcp4_subnet WHERE subnet_id=981")

    # Membership changes are diagnostic fixtures only. Scoped writes preserve it.
    diagnostic("UPDATE dhcp4_subnet SET shared_network_name='m29-network', "
               "modification_ts=CURRENT_TIMESTAMP WHERE subnet_id=980")
    before = snapshot()
    create("subnet", {"code": 12, "space": "dhcp4", "data": "m29-member"})
    assert snapshot() != before
    network = require_success(send("cb-shared-network4-get", {
        "server-tag": TAG, "name": "m29-network"}))["shared-networks"][0]
    assert [row["id"] for row in network["subnet4"]] == [980]
    diagnostic("UPDATE dhcp4_subnet SET shared_network_name=NULL, "
               "modification_ts=CURRENT_TIMESTAMP WHERE subnet_id=980")

    configure_admission(send, config, save, {"allow-mutations": False})
    for scope in PARENTS:
        for operation in ("set", "del"):
            before = snapshot()
            assert send(f"cb-option4-{scope}-{operation}", []) == ADMISSION_ERROR
            assert snapshot() == before
        checked(scope, "get", key)
    configure_admission(send, config, save, {"allow-mutations": True})
    require_success(send("config-reload"))
    verify_scoped_options_restart(send)
    print("PASS: M29 scoped native create/read, encodings, parent preservation, "
          "hidden associations, global pool ambiguity, SQL/audit-preserving "
          "refusals, admission and explicit activation")


def verify_scoped_options_restart(send):
    """Observe native SQL and active scope values after a fresh process starts."""
    for scope in PARENTS:
        rows = require_success(request(send, scope, "get",
                                       {"code": 15, "space": "dhcp4"}))
        assert rows["options"][0]["data"] == f"m29-{scope}.example", rows
    active = require_success(send("config-get"))["Dhcp4"]
    network = next(row for row in active["shared-networks"] if row["name"] == "m29-network")
    subnet = next(row for row in active["subnet4"] if row["id"] == 980)
    for scope, row in (("network", network), ("subnet", subnet), ("pool", subnet["pools"][0])):
        assert any(option["code"] == 15 and option["data"] == f"m29-{scope}.example"
                   for option in row["option-data"]), (scope, row)
    print("PASS: M29 scoped SQL readback and independently observed active options "
          "survive explicit activation/process restart")
