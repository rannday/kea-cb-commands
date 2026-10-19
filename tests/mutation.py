"""Shared real-backend mutation and activation assertions (no SQL in the hook)."""

# SPDX-License-Identifier: MPL-2.0
import ipaddress
import time
from typing import Any

from smoke import ADMISSION_ERROR, require_success, verify_denied


def request(subnet_id=900, prefix="198.18.0.0/24", lifetime=600, tag="test-server",
            pools=None) -> dict[str, Any]:
    arguments: dict[str, Any] = {"server-tag": tag, "subnet4": {
        "id": subnet_id, "subnet": prefix, "valid-lifetime": lifetime}}
    if pools is not None:
        arguments["subnet4"]["pools"] = pools
    return arguments


def configure_admission(send, config, save, parameters):
    """Reload only this hook's admission parameters; preserve native SQL hooks."""
    hooks = [hook for hook in config["Dhcp4"]["hooks-libraries"]
             if hook["library"].endswith("/libdhcp_db_commands.so")]
    assert len(hooks) == 1
    hook = hooks[0]
    hook.pop("parameters", None)
    if parameters is not None:
        hook["parameters"] = parameters
    save()
    require_success(send("config-reload"))


def verify_admission(send, snapshot, config, save):
    """Default/explicit consumers cannot mutate tables, audit or active state."""
    for parameters in (None, {}, {"allow-mutations": False}):
        configure_admission(send, config, save, parameters)
        before = snapshot()
        active = require_success(send("config-get"))
        listed = require_success(send("cb-subnet4-list"))
        require_success(send("cb-subnet4-get", {"id": 42}))
        verify_denied(send)
        for arguments in (request(), request(subnet_id=42, prefix="192.0.2.0/24", tag="all")):
            assert send("cb-subnet4-set", arguments) == ADMISSION_ERROR
        assert send("cb-subnet4-del", {
            "id": 42, "server-tag": "all", "preserve-leases": True}) == ADMISSION_ERROR
        assert snapshot() == before, "Admission rejection changed SQL tables/audit"
        assert require_success(send("config-get")) == active, "Rejection activated configuration"
        assert require_success(send("cb-subnet4-list")) == listed
        print(f"PASS: admission {parameters!r}: create/update/delete denied; "
              "SQL tables/audit and active state unchanged; list/get available")
    configure_admission(send, config, save, {"allow-mutations": True})
    assert require_success(send("db-commands-diagnostic"))["allow-mutations"] is True


def verify_mutations(send, snapshot, sql, config, save, deny_association, restore_privileges):
    """Called after read-only regression checks, with a disposable writer account."""
    def active():
        return {row["id"]: row for row in
                require_success(send("config-get"))["Dhcp4"]["subnet4"]}

    def stored():
        return {row["id"]: row for row in
                require_success(send("cb-subnet4-list"))["subnet4"]}

    def pool(start, end):
        return {"start": start, "end": end}

    def ranges(row):
        normalized = []
        for item in row["pools"]:
            value = item["pool"]
            if "/" in value:
                network = ipaddress.IPv4Network(value)
                value = f"{network.network_address} - {network.broadcast_address}"
            else:
                first, last = value.split("-")
                value = f"{first.strip()} - {last.strip()}"
            normalized.append(value)
        return sorted(normalized)

    def reject(arguments):
        before = snapshot()
        response = send("cb-subnet4-set", arguments)
        assert response["result"] == 1 and "arguments" not in response, response
        assert snapshot() == before, "Rejected write changed table contents"
        return response

    def fixture(statement):
        # Test-only SQL creates configurations this command deliberately cannot edit.
        backend_type = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
        audit = ("SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                 "'pool guard fixture', false); " if backend_type == "postgresql" else
                 "CALL createAuditRevisionDHCP4(NOW(), 'all', 'pool guard fixture', 0); ")
        sql("START TRANSACTION; " + audit + statement + "; COMMIT")

    config["Dhcp4"]["server-tag"] = "test-server"
    save()
    require_success(send("config-reload"))
    verify_admission(send, snapshot, config, save)
    original = stored()
    # All supplied fields are checked, including explicitly empty unsupported ones.
    for arguments in (None, {}, [], False, "bad", {"server-tag": "all"}):
        reject(arguments)
    for field, values in (("id", (0, -1, True, "900", 4294967295)),
                          ("valid-lifetime", (0, -1, False, "600", 4294967295)),
                          ("subnet", ("198.18.0.1/24", "::/64", "bad", "198.18.0.0/33"))):
        for value in values:
            arguments = request()
            arguments["subnet4"][field] = value
            reject(arguments)
    for tag in ("", "any", "ALL", " all ", "missing-server", 4):
        arguments = request()
        arguments["server-tag"] = tag
        reject(arguments)
    for field in ("option-data", "shared-network-name",
                  "user-context", "renew-timer", "rebind-timer", "unknown"):
        arguments = request()
        arguments["subnet4"][field] = []
        reject(arguments)
    valid_pool = pool("198.18.0.10", "198.18.0.20")
    for pools in (None, {}, "bad", False, [None], [[]], ["198.18.0.10 - 198.18.0.20"],
                  [{}], [{"start": "198.18.0.10"}], [{"end": "198.18.0.20"}],
                  [pool(10, "198.18.0.20")], [pool("198.18.0.10", False)],
                  [pool("bad", "198.18.0.20")], [pool("198.18.0.10", "bad")],
                  [pool("::1", "::2")], [pool("198.18.0.256", "198.18.0.20")],
                  [pool("198.18.0.20", "198.18.0.10")],
                  [pool("198.17.255.255", "198.18.0.20")],
                  [pool("198.18.0.10", "198.18.1.1")],
                  [valid_pool, valid_pool],
                  [valid_pool, pool("198.18.0.20", "198.18.0.30")],
                  [valid_pool, pool("198.18.0.11", "198.18.0.19")]):
        arguments = request()
        arguments["subnet4"]["pools"] = pools
        reject(arguments)
    for field in ("pool", "option-data", "require-client-classes",
                  "reservations", "excluded-addresses",
                  "user-context", "unknown"):
        reject(request(pools=[dict(valid_pool, **{field: []})]))
    for field in ("client-classes", "evaluate-additional-classes"):
        for value in (None, "class", [""], [1], ["duplicate", "duplicate"]):
            arguments = request()
            arguments["subnet4"][field] = value
            reject(arguments)
            reject(request(pools=[dict(valid_pool, **{field: value})]))
    for field, values in (
            ("renew-timer", (None, -1, True, "1", 2147483648, 4294967295, 600)),
            ("rebind-timer", (None, -1, True, "1", 2147483648, 4294967295, 600)),
            ("next-server", (None, 1, "::1", "invalid")),
            ("server-hostname", (None, 1, "x" * 64)),
            ("boot-file-name", (None, 1, "x" * 128))):
        for value in values:
            arguments = request()
            arguments["subnet4"][field] = value
            reject(arguments)
    for field in ("renew-timer", "rebind-timer"):
        arguments = request(lifetime=3000000000)
        arguments["subnet4"][field] = 2147483648
        reject(arguments)
    arguments = request()
    arguments["subnet4"].update({"renew-timer": 300, "rebind-timer": 200})
    reject(arguments)
    for prefix in ("198.18.0.1/28", "198.18.0.0/33", "::/64", "bad",
                   "198.18.1.0/28", None):
        reject(request(pools=[{"pool": prefix}]))
    reject(request(pools=[{"pool": "198.18.0.0/28",
                           "start": "198.18.0.1", "end": "198.18.0.2"}]))
    reject(request(pools=[{"pool": "198.18.0.0/28"},
                           {"pool": "198.18.0.0/28"}]))
    reject(request(prefix="0.0.0.0/0", pools=[pool("0.0.0.0", "0.0.0.10")]))
    reject(request(prefix="0.0.0.0/0", pools=[pool("0.0.0.0", "0.0.0.0")]))
    arguments = request()
    arguments["backend-index"] = 0
    reject(arguments)
    # The ID is the update identity. Never silently rename an existing prefix.
    reject(request(901, "192.0.2.0/24"))
    reject(request(42, "198.18.0.0/24", tag="all"))  # existing pools/options
    reject(request(43, "198.18.0.0/24", tag="all"))  # another association
    reject(request(46, "198.18.0.0/24"))  # unassigned rows cannot be retagged

    def protected_rows():
        # Include rows hidden by the active server selector as well as all
        # existing pools/options, not just the objects visible in list results.
        return sql("SELECT * FROM dhcp4_subnet WHERE subnet_id NOT IN (900,902) "
                   "ORDER BY subnet_id; "
                   "SELECT * FROM dhcp4_subnet_server WHERE subnet_id NOT IN (900,902) "
                   "ORDER BY subnet_id,server_id; "
                   "SELECT * FROM dhcp4_pool WHERE subnet_id NOT IN (900,902) "
                   "ORDER BY id; "
                   "SELECT * FROM dhcp4_options ORDER BY option_id")

    def persist(arguments):
        before = protected_rows()
        subnet_id = arguments["subnet4"]["id"]
        previous = stored().get(subnet_id, {"pools": []})
        expected_pools = arguments["subnet4"].get("pools")
        expected_ranges = (ranges(previous) if expected_pools is None else
                           ranges({"pools": [{"pool": item["pool"]} if "pool" in item else
                                              {"pool": f"{item['start']} - {item['end']}"}
                                             for item in expected_pools]}))
        result = require_success(send("cb-subnet4-set", arguments))
        assert protected_rows() == before, "Write changed unrelated subnet configuration"
        assert result == dict(arguments, persisted=True, **{"activation-requested": False})
        row = stored()[arguments["subnet4"]["id"]]
        for key, value in arguments["subnet4"].items():
            if key in ("client-classes", "evaluate-additional-classes"):
                # Native serialization omits an empty class collection. Only
                # these known optional lists treat omission as empty; nonempty
                # values must still be returned exactly.
                assert row.get(key, []) == value, (key, row, value)
            elif key != "pools":
                assert row[key] == value
        assert ranges(row) == expected_ranges, row
        assert row["option-data"] == []
        for item in row["pools"]:
            assert item.get("option-data", []) == []
        for field in ("renew-timer", "rebind-timer", "next-server", "server-hostname",
                      "boot-file-name", "client-classes", "evaluate-additional-classes"):
            if field not in arguments["subnet4"] and field in previous:
                assert row.get(field) == previous[field], (field, row, previous)
        return row

    assert 900 not in active()
    persist(request())
    assert stored()[900]["pools"] == [], "New subnet omission must create no pools"
    persist(request(pools=[pool("198.18.0.10", "198.18.0.10")]))
    persist(request(pools=[pool("198.18.0.32", "198.18.0.47")]))
    persist(request(pools=[valid_pool]))
    rich = request(lifetime=1200, pools=[{"pool": "198.18.0.32/28",
                                        "client-classes": ["pool-rich"],
                                        "evaluate-additional-classes": ["pool-evaluate"]}])
    rich["subnet4"].update({
        "renew-timer": 200, "rebind-timer": 400, "next-server": "192.0.2.9",
        "server-hostname": "m28-host", "boot-file-name": "m28.efi",
        "client-classes": ["subnet-rich"], "evaluate-additional-classes": ["subnet-evaluate"]})
    rich_row = persist(rich)
    assert rich_row["pools"][0]["client-classes"] == ["pool-rich"]
    assert rich_row["pools"][0]["evaluate-additional-classes"] == ["pool-evaluate"]
    assert ranges(rich_row) == ["198.18.0.32 - 198.18.0.47"]
    assert 900 not in active(), "Rich persistence unexpectedly activated configuration"
    preserved = persist(request(lifetime=1500))
    assert preserved["pools"] == rich_row["pools"]
    for field in ("client-classes", "evaluate-additional-classes"):
        assert preserved["pools"][0][field] == rich["subnet4"]["pools"][0][field]
    reject(request(pools=[]))
    reject(request(pools=[valid_pool]))
    reject(request(pools=rich["subnet4"]["pools"]))
    # Explicit empty subnet values clear only the named supported properties.
    cleared = request(lifetime=1500)
    cleared["subnet4"].update({
        "renew-timer": 0, "rebind-timer": 0, "next-server": "0.0.0.0",
        "server-hostname": "", "boot-file-name": "",
        "client-classes": [], "evaluate-additional-classes": []})
    persist(cleared)
    # Pool classes cannot be removed through replacement: test-only fixture reset.
    fixture("UPDATE dhcp4_pool SET client_classes=NULL, "
            "evaluate_additional_classes=NULL WHERE subnet_id=900")
    persist(request(pools=[valid_pool]))
    # Unsupported min/max bounds cannot be silently collapsed by an update.
    fixture("UPDATE dhcp4_subnet SET min_valid_lifetime=100 WHERE subnet_id=900")
    try:
        reject(request())
    finally:
        fixture("UPDATE dhcp4_subnet SET min_valid_lifetime=valid_lifetime "
                "WHERE subnet_id=900")
    # Pool-scoped options likewise prohibit omission, replacement and removal.
    fixture("INSERT INTO dhcp4_options(code, formatted_value, space, scope_id, pool_id, "
            "client_classes) SELECT 15, 'm28-pool.example', 'dhcp4', 5, id, '[]' FROM dhcp4_pool "
            "WHERE subnet_id=900")
    try:
        reject(request())
        reject(request(pools=[valid_pool]))
        reject(request(pools=[]))
    finally:
        fixture("DELETE FROM dhcp4_options WHERE scope_id=5 AND pool_id IN "
                "(SELECT id FROM dhcp4_pool WHERE subnet_id=900)")
    # Isolate pool attributes from rich subnet attributes in the original fixtures.
    for field, value in (("client_classes", '["pool-only"]'),
                         ("evaluate_additional_classes", '["pool-only"]'),
                         ("user_context", '{"pool-only":true}')):
        fixture(f"UPDATE dhcp4_pool SET {field}='{value}' WHERE subnet_id=900")
        try:
            if field == "user_context":
                reject(request())
            else:
                row = persist(request())
                assert row["pools"][0][field.replace("_", "-")] == ["pool-only"]
            reject(request(pools=[valid_pool]))
            reject(request(pools=[]))
        finally:
            fixture(f"UPDATE dhcp4_pool SET {field}=NULL WHERE subnet_id=900")
    fixture("INSERT INTO dhcp4_shared_network(name, valid_lifetime, modification_ts) "
            "VALUES ('m5-shared', 600, CURRENT_TIMESTAMP); "
            "UPDATE dhcp4_subnet SET shared_network_name='m5-shared' WHERE subnet_id=900")
    try:
        reject(request())
        reject(request(pools=[]))
    finally:
        fixture("UPDATE dhcp4_subnet SET shared_network_name=NULL WHERE subnet_id=900; "
                "DELETE FROM dhcp4_shared_network WHERE name='m5-shared'")
    fixture("INSERT INTO dhcp4_subnet_server(subnet_id,server_id,modification_ts) "
            "SELECT 900,id,CURRENT_TIMESTAMP FROM dhcp4_server WHERE tag='other-server'")
    try:
        reject(request())
        reject(request(pools=[valid_pool]))
    finally:
        fixture("DELETE FROM dhcp4_subnet_server WHERE subnet_id=900 AND server_id IN "
                "(SELECT id FROM dhcp4_server WHERE tag='other-server')")
    assert 900 not in active(), "Write unexpectedly activated configuration"
    assert sql("SELECT s.tag FROM dhcp4_server s JOIN dhcp4_subnet_server ss "
               "ON s.id=ss.server_id WHERE ss.subnet_id=900").strip() == b"test-server"
    stamp = sql("SELECT modification_ts FROM dhcp4_subnet WHERE subnet_id=900").strip()
    assert stamp
    audit = sql("SELECT COUNT(*) FROM dhcp4_audit WHERE object_type='dhcp4_subnet' "
                "AND object_id=900").strip()
    assert int(audit) >= 1, "Native mutation created no subnet audit record"
    require_success(send("config-backend-pull"))
    assert active()[900]["subnet"] == "198.18.0.0/24"
    assert ranges(active()[900]) == ["198.18.0.10 - 198.18.0.20"]
    # Omission preserves pools, even when other supported fields change.
    persist(request(lifetime=900))
    assert ranges(stored()[900]) == ["198.18.0.10 - 198.18.0.20"]
    reject(request(prefix="198.18.1.0/24"))  # retained pool outside new prefix
    stamp = sql("SELECT modification_ts FROM dhcp4_subnet WHERE subnet_id=900").strip()
    audit = sql("SELECT COUNT(*) FROM dhcp4_audit WHERE object_type='dhcp4_subnet' "
                "AND object_id=900").strip()
    time.sleep(1.1)
    persist(request(pools=[pool("198.18.0.10", "198.18.0.25")]))
    assert sql("SELECT modification_ts FROM dhcp4_subnet WHERE subnet_id=900").strip() != stamp
    assert int(sql("SELECT COUNT(*) FROM dhcp4_audit WHERE object_type='dhcp4_subnet' "
                   "AND object_id=900").strip()) > int(audit)
    assert ranges(active()[900]) == ["198.18.0.10 - 198.18.0.20"]
    persist(request(pools=[pool("198.18.0.30", "198.18.0.40"),
                           pool("198.18.0.50", "198.18.0.60")]))
    persist(request(pools=[]))
    assert stored()[900]["pools"] == []
    require_success(send("config-backend-pull"))
    assert active()[900]["pools"] == []
    stamp = sql("SELECT modification_ts FROM dhcp4_subnet WHERE subnet_id=900").strip()
    audit = sql("SELECT COUNT(*) FROM dhcp4_audit WHERE object_type='dhcp4_subnet' "
                "AND object_id=900").strip()
    # Kea timestamps have second precision; cross a boundary before updating.
    time.sleep(1.1)
    updated_pools = [pool("198.18.1.10", "198.18.1.20"),
                     pool("198.18.1.30", "198.18.1.40")]
    persist(request(prefix="198.18.1.0/24", lifetime=1200, pools=updated_pools))
    assert active()[900]["subnet"] == "198.18.0.0/24"
    assert sql("SELECT modification_ts FROM dhcp4_subnet WHERE subnet_id=900").strip() != stamp
    assert int(sql("SELECT COUNT(*) FROM dhcp4_audit WHERE object_type='dhcp4_subnet' "
                   "AND object_id=900").strip()) > int(audit)
    assert {key: row for key, row in stored().items() if key != 900} == original
    reject(request(901, "198.18.1.0/24"))
    reject(request(900, "192.0.2.0/24"))
    reject(request(900, "198.18.1.0/24", tag="other-server"))

    # Fail after the native audit revision and subnet INSERT/UPDATE, at the
    # association INSERT, after native pool deletion/insertion. Compare every table,
    # including pools and audit tables, on rollback.
    deny_association()
    try:
        reject(request(901, "198.18.2.0/24",
                       pools=[pool("198.18.2.10", "198.18.2.20")]))
        reject(request(900, "198.18.3.0/24",
                       pools=[pool("198.18.3.10", "198.18.3.20")]))
    finally:
        restore_privileges()
    assert stored()[900]["subnet"] == "198.18.1.0/24"
    assert ranges(stored()[900]) == ["198.18.1.10 - 198.18.1.20",
                                    "198.18.1.30 - 198.18.1.40"]
    assert 901 not in stored()

    # Native pull activates both creation and updates; this hook never invokes it.
    require_success(send("config-backend-pull"))
    assert active()[900]["subnet"] == "198.18.1.0/24"
    assert ranges(active()[900]) == ranges(stored()[900])
    persist(request(prefix="198.18.4.0/24", lifetime=1800,
                    pools=[pool("198.18.4.10", "198.18.4.20")]))
    assert active()[900]["subnet"] == "198.18.1.0/24"
    require_success(send("config-backend-pull"))
    assert active()[900]["subnet"] == "198.18.4.0/24"
    assert ranges(active()[900]) == ["198.18.4.10 - 198.18.4.20"]
    require_success(send("config-reload"))
    assert active()[900]["subnet"] == "198.18.4.0/24"
    assert active()[900]["valid-lifetime"] == 1800
    assert ranges(active()[900]) == ["198.18.4.10 - 198.18.4.20"]

    # The universal selector is explicit and does not create server records.
    persist(request(902, "198.19.0.0/24", tag="all",
                    pools=[pool("198.19.0.10", "198.19.0.20"),
                           pool("198.19.0.30", "198.19.0.40")]))
    assert sql("SELECT s.tag FROM dhcp4_server s JOIN dhcp4_subnet_server ss "
               "ON s.id=ss.server_id WHERE ss.subnet_id=902").strip() == b"all"
    assert 902 not in active()
    require_success(send("config-reload"))
    assert active()[902]["subnet"] == "198.19.0.0/24"
    assert ranges(active()[902]) == ["198.19.0.10 - 198.19.0.20",
                                    "198.19.0.30 - 198.19.0.40"]
    assert {key: row for key, row in stored().items() if key not in (900, 902)} == original
    print("PASS: native subnet/pool create/update, omission/replacement/removal, validation, "
          "identity/tag guards, all-table rollback, "
          "audit/timestamps, persistence distinct from pull/reload activation")
