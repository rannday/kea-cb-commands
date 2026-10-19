"""Native client-class contracts in disposable PostgreSQL/MariaDB backends."""

# SPDX-License-Identifier: MPL-2.0
from typing import Any

from mutation import configure_admission
from smoke import ADMISSION_ERROR, require_success

PREFIX = "cb-client-class4-"
TAG = "test-server"
BASE = "m30-z-base"
DEPENDENT = "m30-a-dependent"
COMMON = "m30-common"
REFUSAL = (
    "Existing client-class mutations are unsupported: complete associations "
    "and dependencies cannot be verified."
)


def verify_client_classes(send, snapshot, sql, config, save):
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]

    def request(operation, obj=None, tag: Any = TAG, follow: Any = ""):
        arguments: dict[str, Any] = {"server-tag": tag}
        if operation == "set":
            arguments.update({"client-class": obj, "follow-class-name": follow})
        elif operation != "list":
            arguments["name"] = obj
        return send(PREFIX + operation, arguments)

    def checked(operation, obj=None, tag: Any = TAG, result=0, follow: Any = ""):
        before = snapshot()
        response = request(operation, obj, tag, follow)
        assert response["result"] == result, response
        assert snapshot() == before, (operation, obj, "SQL/audit changed")
        return response

    def rows(response):
        result = response["arguments"]
        assert result["associations-complete"] is False
        assert result["dependencies-complete"] is False
        assert result["order-scope"] == "selected-view"
        assert result["count"] == len(result["client-classes"])
        return result["client-classes"]

    def order():
        return [row["name"] for row in rows(checked("list"))]

    checked("list", result=3)
    for operation in ("get", "del"):
        assert rows(checked(operation, BASE, result=3)) == []
    active = require_success(send("config-get"))
    unrelated_tables = (
        "dhcp4_subnet", "dhcp4_subnet_server", "dhcp4_pool",
        "dhcp4_shared_network", "dhcp4_shared_network_server",
        "dhcp4_options", "dhcp4_option_def", "dhcp4_option_def_server",
        "dhcp4_global_parameter", "dhcp4_global_parameter_server", "dhcp4_server",
    )

    def unrelated():
        # No class options are inserted until after these initial append checks.
        return sql("; ".join(f"SELECT * FROM {table} ORDER BY 1"
                             for table in unrelated_tables))

    definitions = (
        (TAG, {"name": BASE, "test": "option[60].exists",
               "valid-lifetime": 600, "min-valid-lifetime": 500,
               "max-valid-lifetime": 700, "next-server": "192.0.2.30",
               "server-hostname": "m30-server", "boot-file-name": "m30.efi",
               "user-context": {"milestone": 30}}),
        (TAG, {"name": DEPENDENT, "test": f"member('{BASE}')"}),
        ("all", {"name": COMMON, "test": "option[60].exists"}),
    )
    old_order: list[str] = []
    for tag, definition in definitions:
        before = unrelated()
        existing = sql("SELECT * FROM dhcp4_client_class ORDER BY id")
        response = require_success(request("set", definition, tag))
        assert response["activation-requested"] is False
        assert unrelated() == before, "Class append changed unrelated SQL"
        # Existing class rows and their native timestamps must remain intact.
        after = sql("SELECT * FROM dhcp4_client_class ORDER BY id")
        assert all(line in after.splitlines() for line in existing.splitlines())
        row = response["client-classes"][0]
        assert row["name"] == definition["name"]
        assert row["server-tags"] == [tag]
        assert row["modification-ts"]
        for field, value in definition.items():
            assert row[field] == value, (field, row)
        selected = order()
        assert selected == old_order + [definition["name"]], selected
        assert [r["evaluation-position"] for r in rows(checked("list"))] == list(range(len(selected)))
        old_order = selected
        assert require_success(send("config-get")) == active
    assert order() == [BASE, DEPENDENT, COMMON], "Class order was alphabetically sorted"
    assert rows(checked("get", DEPENDENT))[0]["referenced-classes"] == [BASE]
    assert [r["name"] for r in rows(checked("list", tag="all"))] == [COMMON]
    assert [r["name"] for r in rows(checked("list", tag="m25-server"))] == [COMMON]
    checked("get", BASE, "m25-server", result=3)
    for tag in (TAG, "m25-server", "all"):
        for operation, obj in (("set", {"name": BASE}), ("del", BASE)):
            assert checked(operation, obj, tag, result=1) == {"result": 1, "text": REFUSAL}

    for follow in (None, False, BASE, "missing-reference"):
        checked("set", {"name": "m30-refused-position"}, result=1, follow=follow)
    before = snapshot()
    assert send(PREFIX + "set", {"server-tag": TAG, "client-class": {"name": "m30-no-position"}})["result"] == 1
    assert snapshot() == before

    invalid = (
        None, [], {}, {"name": 1}, {"name": ""}, {"name": " leading"},
        {"name": "trailing "}, {"name": "x" * 129}, {"name": "nul\x00name"},
        {"name": "ALL"}, {"name": "KNOWN"}, {"name": "DROP"}, {"name": "SPAWN_bad"},
        {"name": "m30-invalid", "test": "member("},
        {"name": "m30-invalid", "test": "member('missing-m30-class')"},
        {"name": "m30-invalid", "test": "member('m30-invalid')"},
        {"name": "m30-invalid", "test": "option[not-a-defined-option].exists"},
        {"name": "m30-invalid", "test": 1},
        {"name": "m30-invalid", "template-test": "option[60].hex"},
        {"name": "m30-invalid", "offer-lifetime": 100},
        {"name": "m30-invalid", "renew-timer": 100},
        {"name": "m30-invalid", "required-client-classes": [BASE]},
        {"name": "m30-invalid", "only-in-additional-list": "yes"},
        {"name": "m30-invalid", "option-def": []},
        {"name": "m30-invalid", "option-data": False},
        {"name": "m30-invalid", "option-data": [{"code": 15, "space": "dhcp4", "data": 1}]},
        {"name": "m30-invalid", "option-data": [{"code": 250, "space": "dhcp4", "data": "x"}]},
        {"name": "m30-invalid", "next-server": "not-an-address"},
        {"name": "m30-invalid", "valid-lifetime": 0},
        {"name": "m30-invalid", "min-valid-lifetime": 300},
        {"name": "m30-invalid", "valid-lifetime": 300, "min-valid-lifetime": 400},
        {"name": "m30-invalid", "unexpected": True},
    )
    for obj in invalid:
        checked("set", obj, result=1)
    for operation in ("get", "del"):
        for name in (None, False, "", " trailing ", "x" * 129):
            checked(operation, name, result=1)
    for tag in (None, False, "", "UPPER", " any", "any", "missing-server"):
        checked("set", {"name": "m30-invalid"}, tag, result=1)

    checked("set", {"name": "m30-common-dependent", "test": f"member('{BASE}')"},
            tag="all", result=1)

    # A class-specific option is parsed using selected native definitions.
    option = {"code": 249, "space": "dhcp4", "data": "6d:33:30",
              "csv-format": False, "always-send": True}
    result = require_success(request("set", {
        "name": "m30-options", "test": f"member('{BASE}')", "option-data": [option]}))
    row = result["client-classes"][0]
    assert any(o["code"] == 249 and o["always-send"] is True
               for o in row["option-data"]), row
    for operation, obj in (("set", {"name": "m30-options"}), ("del", "m30-options")):
        checked(operation, obj, result=1)

    def diagnostic(statements):
        prefix = (
            "BEGIN; SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
            "'all', 'M30 diagnostic fixture', false); "
            if backend == "postgresql" else
            "START TRANSACTION; CALL createAuditRevisionDHCP4(CURRENT_TIMESTAMP, "
            "'all', 'M30 diagnostic fixture', 0); ")
        sql(prefix + statements + "; COMMIT")

    # Add a second association diagnostically, then prove no native upsert deletes it.
    diagnostic(
        "INSERT INTO dhcp4_client_class_server (class_id,server_id,modification_ts) "
        "SELECT c.id,s.id,CURRENT_TIMESTAMP FROM dhcp4_client_class c "
        f"JOIN dhcp4_server s ON s.tag='m25-server' WHERE c.name='{BASE}'")
    assert set(rows(checked("get", BASE))[0]["server-tags"]) == {TAG, "m25-server"}
    checked("del", BASE, "m25-server", result=1)
    checked("set", {"name": BASE}, "m25-server", result=1)

    # Latent references must not acquire new semantics by creating their target.
    for field, value in (
        ("client_classes", '["m30-dormant"]'),
        ("evaluate_additional_classes", '["m30-dormant"]'),
    ):
        diagnostic(f"UPDATE dhcp4_subnet SET {field}='{value}' WHERE subnet_id=970")
        checked("set", {"name": "m30-dormant"}, result=1)
        diagnostic(f"UPDATE dhcp4_subnet SET {field}=NULL WHERE subnet_id=970")
    for table, identity in (("dhcp4_pool", "subnet_id=980"),
                            ("dhcp4_shared_network", "name=\'m27-specific\'")):
        diagnostic(f"UPDATE {table} SET client_classes=\'[\"m30-dormant\"]\' WHERE {identity}")
        checked("set", {"name": "m30-dormant"}, result=1)
        diagnostic(f"UPDATE {table} SET client_classes=NULL WHERE {identity}")
    require_success(send("cb-option4-global-set", {
        "server-tag": TAG, "option": {
            "code": 244, "space": "m26", "data": "01", "csv-format": False,
            "client-classes": ["m30-dormant"]}}))
    checked("set", {"name": "m30-dormant"}, result=1)
    # Already existing targets fail closed regardless of consumer kind. Include
    # subnet, pool, network, option and additional-evaluation textual consumers.
    diagnostic(f"UPDATE dhcp4_subnet SET client_classes='[\"{BASE}\"]', "
               f"evaluate_additional_classes='[\"{DEPENDENT}\"]' WHERE subnet_id=970; "
               f"UPDATE dhcp4_pool SET client_classes='[\"{BASE}\"]' WHERE subnet_id=980; "
               f"UPDATE dhcp4_shared_network SET client_classes='[\"{BASE}\"]' "
               "WHERE name='m27-specific'")
    for operation, obj in (("set", {"name": BASE}), ("del", BASE), ("del", DEPENDENT)):
        checked(operation, obj, result=1)
    diagnostic("UPDATE dhcp4_subnet SET client_classes=NULL, "
               "evaluate_additional_classes=NULL WHERE subnet_id=970; "
               "UPDATE dhcp4_pool SET client_classes=NULL WHERE subnet_id=980; "
               "UPDATE dhcp4_shared_network SET client_classes=NULL WHERE name='m27-specific'")

    configure_admission(send, config, save, {"allow-mutations": False})
    before = snapshot()
    for operation in ("set", "del"):
        assert request(operation, []) == ADMISSION_ERROR
    assert snapshot() == before
    checked("get", BASE)
    configure_admission(send, config, save, {"allow-mutations": True})
    require_success(send("config-reload"))
    print("PASS: M30 native ordered client-class reads, explicit append, native "
          "expression/dependency validation, common/specific/mixed associations, "
          "dormant-consumer protection, SQL/audit-preserving refusals and admission")


def verify_client_classes_restart(send):
    result = require_success(send(PREFIX + "list", {"server-tag": TAG}))
    names = [row["name"] for row in result["client-classes"]]
    assert names[:3] == [BASE, DEPENDENT, COMMON], names
    active = require_success(send("config-get"))["Dhcp4"]["client-classes"]
    assert [row["name"] for row in active][:3] == [BASE, DEPENDENT, COMMON], active
    base = result["client-classes"][0]
    assert base["valid-lifetime"] == 600 and base["boot-file-name"] == "m30.efi"
    assert set(base["server-tags"]) == {TAG, "m25-server"}
    options = next(row for row in result["client-classes"] if row["name"] == "m30-options")
    assert any(option["code"] == 249 and option["always-send"] is True
               for option in options["option-data"])
    print("PASS: M30 actual process restart preserves classes, order, options and associations")
