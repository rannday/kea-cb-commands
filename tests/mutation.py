"""Shared real-backend mutation and activation assertions (no SQL in the hook)."""

# SPDX-License-Identifier: MPL-2.0
import time

from smoke import require_success


def request(subnet_id=900, prefix="198.18.0.0/24", lifetime=600, tag="test-server"):
    return {"server-tag": tag, "subnet4": {
        "id": subnet_id, "subnet": prefix, "valid-lifetime": lifetime}}


def verify_mutations(send, snapshot, sql, config, save, deny_association, restore_privileges):
    """Called after read-only regression checks, with a disposable writer account."""
    def active():
        return {row["id"]: row for row in
                require_success(send("config-get"))["Dhcp4"]["subnet4"]}

    def stored():
        return {row["id"]: row for row in
                require_success(send("cb-subnet4-list"))["subnet4"]}

    def reject(arguments):
        before = snapshot()
        response = send("cb-subnet4-set", arguments)
        assert response["result"] == 1 and "arguments" not in response, response
        assert snapshot() == before, "Rejected write changed table contents"
        return response

    config["Dhcp4"]["server-tag"] = "test-server"
    save()
    require_success(send("config-reload"))
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
    for field in ("pools", "option-data", "client-classes", "shared-network-name",
                  "user-context", "renew-timer", "rebind-timer", "unknown"):
        arguments = request()
        arguments["subnet4"][field] = []
        reject(arguments)
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
                   "SELECT * FROM dhcp4_pool ORDER BY id; "
                   "SELECT * FROM dhcp4_options ORDER BY option_id")

    def persist(arguments):
        before = protected_rows()
        result = require_success(send("cb-subnet4-set", arguments))
        assert protected_rows() == before, "Write changed unrelated subnet configuration"
        assert result == dict(arguments, persisted=True, **{"activation-requested": False})
        row = stored()[arguments["subnet4"]["id"]]
        for key, value in arguments["subnet4"].items():
            assert row[key] == value
        assert row["pools"] == [] and row["option-data"] == []
        assert row["renew-timer"] == row["rebind-timer"] == 0
        return row

    assert 900 not in active()
    persist(request())
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
    # Kea timestamps have second precision; cross a boundary before updating.
    time.sleep(1.1)
    persist(request(prefix="198.18.1.0/24", lifetime=1200))
    assert active()[900]["subnet"] == "198.18.0.0/24"
    assert sql("SELECT modification_ts FROM dhcp4_subnet WHERE subnet_id=900").strip() != stamp
    assert int(sql("SELECT COUNT(*) FROM dhcp4_audit WHERE object_type='dhcp4_subnet' "
                   "AND object_id=900").strip()) > int(audit)
    assert {key: row for key, row in stored().items() if key != 900} == original
    reject(request(901, "198.18.1.0/24"))
    reject(request(900, "192.0.2.0/24"))
    reject(request(900, "198.18.1.0/24", tag="other-server"))

    # Fail after the native audit revision and subnet INSERT/UPDATE, at the
    # association INSERT. Compare every table, including audit tables, on rollback.
    deny_association()
    try:
        reject(request(901, "198.18.2.0/24"))
        reject(request(900, "198.18.3.0/24"))
    finally:
        restore_privileges()
    assert stored()[900]["subnet"] == "198.18.1.0/24"
    assert 901 not in stored()

    # Native pull activates both creation and updates; this hook never invokes it.
    require_success(send("config-backend-pull"))
    assert active()[900]["subnet"] == "198.18.1.0/24"
    persist(request(prefix="198.18.4.0/24", lifetime=1800))
    assert active()[900]["subnet"] == "198.18.1.0/24"
    require_success(send("config-backend-pull"))
    assert active()[900]["subnet"] == "198.18.4.0/24"
    require_success(send("config-reload"))
    assert active()[900]["subnet"] == "198.18.4.0/24"
    assert active()[900]["valid-lifetime"] == 1800

    # The universal selector is explicit and does not create server records.
    persist(request(902, "198.19.0.0/24", tag="all"))
    assert sql("SELECT s.tag FROM dhcp4_server s JOIN dhcp4_subnet_server ss "
               "ON s.id=ss.server_id WHERE ss.subnet_id=902").strip() == b"all"
    assert 902 not in active()
    require_success(send("config-reload"))
    assert active()[902]["subnet"] == "198.19.0.0/24"
    assert {key: row for key, row in stored().items() if key not in (900, 902)} == original
    print("PASS: native create/update, validation, identity/tag guards, all-table rollback, "
          "audit/timestamps, persistence distinct from pull/reload activation")
