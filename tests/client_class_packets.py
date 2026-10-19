"""Real DHCP classification in the disposable SQL/loopback packet fixtures."""

# SPDX-License-Identifier: MPL-2.0
import secrets

from smoke import require_success

BASE = "m30-packet-base"
DEPENDENT = "m30-packet-dependent"
ADDITIONAL = "m30-packet-additional"
DEPENDENT_OPTION = b"m30-dependent"
ADDITIONAL_OPTION = b"m30-additional"


def _hardware(matches: bool) -> bytes:
    """Use distinct unicast locally administered MAC prefixes for each case."""
    return (b"\x02" if matches else b"\x06") + secrets.token_bytes(5)


def _classes(send):
    return require_success(send("config-get"))["Dhcp4"].get("client-classes", [])


def _packet(exchange, directory, first, last, expected, *, matches=True,
            additional=False, expect_offer=True):
    payloads = dict(expected)
    absent = []
    if matches:
        payloads[247] = DEPENDENT_OPTION
    else:
        absent.append(247)
    if additional and matches:
        payloads[248] = ADDITIONAL_OPTION
    else:
        absent.append(248)
    return exchange(
        directory, first, last, expected_options=payloads,
        absent_options=tuple(absent), boot_file="m25-packet.efi",
        expect_offer=expect_offer, hardware=_hardware(matches))


def verify_client_class_packets(send, config, directory, snapshot, sql, expected,
                                exchange, subnets, pools, subnet_id):
    """Keep native persistence separate from explicit runtime activation.

    All packet traffic stays in the caller's disposable loopback namespace.
    Diagnostic SQL only clears protected pool classes during fixture cleanup.
    """
    before = require_success(send("config-get"))
    definitions = (
        {"name": BASE, "test": "substring(pkt4.mac, 0, 1) == 0x02"},
        {"name": DEPENDENT, "test": f"member('{BASE}')",
         "option-data": [{"code": 247, "space": "dhcp4",
                          "data": DEPENDENT_OPTION.hex(":"), "csv-format": False,
                          "always-send": True}]},
        {"name": ADDITIONAL, "test": f"member('{DEPENDENT}')",
         "only-in-additional-list": True,
         "option-data": [{"code": 248, "space": "dhcp4",
                          "data": ADDITIONAL_OPTION.hex(":"), "csv-format": False,
                          "always-send": True}]},
    )
    for definition in definitions:
        result = require_success(send("cb-client-class4-set", {
            "server-tag": "test-server", "follow-class-name": "",
            "client-class": definition}))
        assert result["activation-requested"] is False
        assert require_success(send("config-get")) == before
    exchange(directory, "127.0.0.10", "127.0.0.29",
              boot_file="m25-packet.efi", expected_options=expected,
              absent_options=(247, 248))

    original = subnets(send, "config-get")[subnet_id]
    original_pools = [
        {"start": start, "end": end} for start, end in pools(original)]
    request = {"server-tag": "test-server", "subnet4": {
        "id": subnet_id, "subnet": "127.0.0.0/24", "valid-lifetime": 600,
        "evaluate-additional-classes": [ADDITIONAL],
        "pools": [{"start": "127.0.0.96", "end": "127.0.0.126",
                   "client-classes": [DEPENDENT]}]}}
    result = require_success(send("cb-subnet4-set", request))
    assert result["activation-requested"] is False
    assert require_success(send("config-get")) == before
    exchange(directory, "127.0.0.10", "127.0.0.29",
              boot_file="m25-packet.efi", expected_options=expected,
              absent_options=(247, 248))

    require_success(send("config-reload"))
    classes = _classes(send)
    names = [row["name"] for row in classes]
    assert names.index(BASE) < names.index(DEPENDENT) < names.index(ADDITIONAL), names
    by_name = {row["name"]: row for row in classes}
    assert by_name[ADDITIONAL]["only-in-additional-list"] is True
    runtime = subnets(send, "config-get")[subnet_id]
    assert runtime["evaluate-additional-classes"] == [ADDITIONAL]
    assert runtime["pools"][0]["client-classes"] == [DEPENDENT]
    assert pools(runtime) == [("127.0.0.96", "127.0.0.126")], runtime
    _packet(exchange, directory, "127.0.0.96", "127.0.0.126", expected, additional=True)
    _packet(exchange, directory, None, None, expected, matches=False, expect_offer=False)

    # Refusing mutations of a pool-referenced class must preserve the complete
    # disposable configuration/audit snapshot, as well as active packet behavior.
    for operation, arguments in (
        ("set", {"client-class": definitions[1], "follow-class-name": ""}),
        ("del", {"name": DEPENDENT}),
    ):
        before_refusal = snapshot()
        response = send("cb-client-class4-" + operation, {
            "server-tag": "test-server", **arguments})
        assert response["result"] == 1, response
        assert snapshot() == before_refusal, "Refused class mutation changed SQL/audit"
    _packet(exchange, directory, "127.0.0.96", "127.0.0.126", expected, additional=True)

    # Reload repeats native SQL activation and must retain evaluation order.
    require_success(send("config-reload"))
    assert [row["name"] for row in _classes(send)] == names
    _packet(exchange, directory, "127.0.0.96", "127.0.0.126", expected, additional=True)
    _packet(exchange, directory, None, None, expected, matches=False, expect_offer=False)

    # Production pool replacement refuses removing protected class restrictions.
    # Clear only this disposable fixture's restriction, then restore its pool
    # natively. The dependent option remains for the real process-restart test.
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    audit = (
        "SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
        "'M30 packet fixture reset', false); "
        if backend == "postgresql" else
        "CALL createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
        "'M30 packet fixture reset', 0); ")
    sql("START TRANSACTION; " + audit +
        f"UPDATE dhcp4_pool SET client_classes=NULL WHERE subnet_id={subnet_id}; COMMIT")
    result = require_success(send("cb-subnet4-set", {
        "server-tag": "test-server", "subnet4": {
            "id": subnet_id, "subnet": "127.0.0.0/24", "valid-lifetime": 600,
            "evaluate-additional-classes": [], "pools": original_pools}}))
    assert result["activation-requested"] is False
    require_success(send("config-reload"))
    assert pools(subnets(send, "config-get")[subnet_id]) == pools(original)
    _packet(exchange, directory, "127.0.0.10", "127.0.0.29", expected)
    _packet(exchange, directory, "127.0.0.10", "127.0.0.29", expected, matches=False)
    print("PASS: native class expressions and ordered member dependencies; "
          "class-restricted pool allocates only to matching MACs; actual OFFER/ACK "
          "class option247 and additional-evaluation option248; no activation "
          "before explicit reload; refused class mutations preserve SQL/audit")


def verify_client_class_restart(send, directory, expected, exchange):
    """Run only after the owning harness restarts the same Kea process."""
    names = [row["name"] for row in _classes(send)]
    assert names.index(BASE) < names.index(DEPENDENT) < names.index(ADDITIONAL), names
    _packet(exchange, directory, "127.0.0.30", "127.0.0.40", expected)
    _packet(exchange, directory, "127.0.0.30", "127.0.0.40", expected, matches=False)
    print("PASS: actual process restart preserves class evaluation order and "
          "matching/nonmatching OFFER/ACK option247 classification; "
          "additional-only option248 stays absent without explicit evaluation")
