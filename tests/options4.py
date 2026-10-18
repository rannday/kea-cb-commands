"""Native option assertions shared by disposable PostgreSQL/MariaDB fixtures."""

# SPDX-License-Identifier: MPL-2.0
from mutation import configure_admission
from smoke import ADMISSION_ERROR, require_success

DEF = "cb-option-def4-"
OPT = "cb-option4-global-"
TAG = "test-server"
PAYLOADS = {
    3: bytes((127, 0, 0, 1)),
    6: bytes((192, 0, 2, 53, 192, 0, 2, 54)),
    15: b"m26.example",
    224: b"m26-custom",
}


def verify_options(send, snapshot, sql, config, save):
    """Keep every refused/read operation and native audit byte-for-byte unchanged."""
    def request(prefix, operation, obj=None, tag=TAG):
        args = {"server-tag": tag}
        if obj is not None:
            args["option-def" if prefix == DEF else "option"] = obj
        return send(prefix + operation, args)

    def checked(prefix, operation, obj=None, tag=TAG, result=0):
        before = snapshot()
        response = request(prefix, operation, obj, tag)
        assert response["result"] == result, response
        assert snapshot() == before, (prefix, operation, "SQL/audit changed")
        return response.get("arguments")

    def create(prefix, obj, tag=TAG):
        result = require_success(request(prefix, "set", obj, tag))
        assert result["activation-requested"] is False
        assert result["associations-complete"] is False
        assert result["count"] == 1
        row = result["option-defs" if prefix == DEF else "options"][0]
        assert row["code"] == obj["code"] and row["space"] == obj["space"], row
        assert row["server-tags"] == [tag], row
        return row

    for prefix in (DEF, OPT):
        checked(prefix, "list", result=3)
        for operation in ("get", "del"):
            checked(prefix, operation, {"code": 224, "space": "dhcp4"}, result=3)

    definitions = [
        {"name": "m26-string", "code": 224, "space": "dhcp4", "type": "string"},
        {"name": "m26-number", "code": 225, "space": "dhcp4", "type": "uint16"},
        {"name": "m26-record", "code": 226, "space": "m26",
         "type": "record", "record-types": "uint8, ipv4-address"},
        {"name": "m26-array", "code": 227, "space": "m26",
         "type": "uint16", "array": True},
        {"name": "m26-encap", "code": 228, "space": "m26",
         "type": "empty", "encapsulate": "m26-child"},
    ]
    active_before = require_success(send("config-get"))["Dhcp4"].get("option-def", [])
    for obj in definitions:
        row = create(DEF, obj)
        assert row["name"] == obj["name"] and row["type"] == obj["type"], row
        for operation in ("set", "del"):
            selected = obj if operation == "set" else {
                "code": obj["code"], "space": obj["space"]}
            checked(DEF, operation, selected, result=1)
    assert require_success(send("config-get"))["Dhcp4"].get("option-def", []) == active_before

    invalid_definitions = [
        dict(definitions[0], code=229),  # Duplicate name.
        dict(definitions[0], code=230, name="bad", type="not-a-type"),
        dict(definitions[0], code=230, name="bad", type="record", **{"record-types": ""}),
        dict(definitions[0], code=230, name="bad", array="true"),
        dict(definitions[0], code=230, name="bad", space="bad space"),
        dict(definitions[0], code=230, name="bad", unexpected=True),
        dict(definitions[0], code=0), dict(definitions[0], code=255),
    ]
    for obj in invalid_definitions:
        checked(DEF, "set", obj, result=1)

    options = [
        {"code": 3, "space": "dhcp4", "data": "127.0.0.1"},
        {"code": 6, "space": "dhcp4", "data": "192.0.2.53, 192.0.2.54"},
        {"code": 15, "space": "dhcp4", "data": "m26.example"},
        {"code": 224, "space": "dhcp4", "data": "m26-custom"},
        {"code": 225, "space": "dhcp4", "data": "1234"},
        {"code": 226, "space": "m26", "data": "7, 192.0.2.1"},
        {"code": 227, "space": "m26", "data": "1, 2, 65535"},
        {"code": 231, "space": "m26", "data": "0102ff", "csv-format": False},
        {"code": 232, "space": "m26", "data": "", "csv-format": False},
        {"code": 233, "space": "m26", "data": "ab", "csv-format": False,
         "client-classes": ["m26-class"]},
    ]
    active_before = require_success(send("config-get"))["Dhcp4"].get("option-data", [])
    for obj in options:
        row = create(OPT, dict(obj, **{"always-send": True}))
        if obj.get("csv-format", True):
            assert row["data"] == obj["data"], row
        else:
            assert bytes.fromhex(row["data"]) == bytes.fromhex(obj["data"]), row
        assert row["always-send"] is True
        if "client-classes" in obj:
            assert row["client-classes"] == obj["client-classes"]
        for operation in ("set", "del"):
            selected = obj if operation == "set" else {
                key: value for key, value in obj.items()
                if key in ("code", "space", "client-classes")}
            checked(OPT, operation, selected, result=1)
    assert require_success(send("config-get"))["Dhcp4"].get("option-data", []) == active_before
    for obj in (
        {"code": 234, "space": "m26", "data": "1"},  # No definition for CSV.
        {"code": 234, "space": "m26", "data": "zz", "csv-format": False},
        {"code": 234, "space": "m26", "data": "ab:z", "csv-format": False},
        {"code": 234, "space": "m26", "data": 1},
        {"code": 234, "space": "m26", "data": "", "csv-format": "false"},
        {"code": 234, "space": "m26", "data": "", "client-classes": ["x", "x"]},
        {"code": 234, "space": "dhcp4", "data": "", "persistent": True},
    ):
        checked(OPT, "set", obj, result=1)

    # A different selected view must not reuse the writer's runtime definitions.
    checked(OPT, "set", {"code": 224, "space": "dhcp4", "data": "wrong-view"},
            tag="m25-server", result=1)
    # Create separate specific/common rows; ONE uses its specific row.
    for prefix, obj in (
        (DEF, {"name": "m26-common", "code": 240, "space": "m26", "type": "string"}),
        (OPT, {"code": 241, "space": "m26", "data": "01", "csv-format": False}),
    ):
        create(prefix, obj)
        common = dict(obj)
        if prefix == DEF:
            common["name"] = "m26-common-all"
        else:
            common["data"] = "02"
        create(prefix, common, "all")
        key = {"code": obj["code"], "space": obj["space"]}
        rows = checked(prefix, "get", key)
        assert rows["option-defs" if prefix == DEF else "options"][0]["server-tags"] == [TAG]
        for tag in ("all", TAG, "m25-server"):
            checked(prefix, "del", key, tag, result=1)

    # Diagnostic SQL only: native ONE readback hides these extra associations.
    for table, foreign, code in (("option_def", "option_def_id", 224),
                                  ("options", "option_id", 224)):
        primary = "id" if table == "option_def" else "option_id"
        sql(f"INSERT INTO dhcp4_{table}_server "
            f"({foreign}, server_id, modification_ts) "
            f"SELECT o.{primary}, s.id, CURRENT_TIMESTAMP FROM dhcp4_{table} o "
            "JOIN dhcp4_server s ON s.tag='m25-server' "
            f"WHERE o.code={code} AND o.space='dhcp4'")
    for prefix in (DEF, OPT):
        key = {"code": 224, "space": "dhcp4"}
        for tag in (TAG, "m25-server"):
            rows = checked(prefix, "get", key, tag)
            assert rows["associations-complete"] is False
            checked(prefix, "del", key, tag, result=1)

    configure_admission(send, config, save, {"allow-mutations": False})
    for prefix in (DEF, OPT):
        for operation in ("set", "del"):
            before = snapshot()
            assert request(prefix, operation, []) == ADMISSION_ERROR
            assert snapshot() == before
        checked(prefix, "get", {"code": 224, "space": "dhcp4"})
    configure_admission(send, config, save, {"allow-mutations": True})
    require_success(send("config-reload"))
    active = require_success(send("config-get"))["Dhcp4"]
    assert any(row["code"] == 224 for row in active["option-def"]), active["option-def"]
    assert any(row["code"] == 224 and row["data"] == "m26-custom"
               for row in active["option-data"]), active["option-data"]
    print("PASS: M26 native definitions/options, CSV/hex/empty/record/array, "
          "selector isolation, hidden associations, SQL/audit-preserving refusal, "
          "default-deny admission and independent explicit activation")


def verify_options_restart(send):
    """Fresh process reads SQL; observation is separate from prior mutation success."""
    for prefix, key, field, value in (
        (DEF, {"code": 224, "space": "dhcp4"}, "name", "m26-string"),
        (OPT, {"code": 224, "space": "dhcp4"}, "data", "m26-custom"),
    ):
        args = {"server-tag": TAG, "option-def" if prefix == DEF else "option": key}
        rows = require_success(send(prefix + "get", args))
        assert rows["option-defs" if prefix == DEF else "options"][0][field] == value, rows
    active = require_success(send("config-get"))["Dhcp4"]
    assert any(row["code"] == 224 and row["data"] == "m26-custom"
               for row in active["option-data"])
    print("PASS: M26 native option definition/global option survive process restart")
