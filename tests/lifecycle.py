"""Native get/delete assertions against each disposable SQL backend."""

# SPDX-License-Identifier: MPL-2.0
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from mutation import request
from smoke import require_success


def delete_request(**selector):
    return {"server-tag": "test-server", "preserve-leases": True, **selector}


def verify_lifecycle(send, snapshot, sql, config, save):
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    pg = backend == "postgresql"

    def fixture(statement):
        audit = ("SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', "
                 "'lifecycle fixture', false); " if pg else
                 "CALL createAuditRevisionDHCP4(NOW(), 'all', 'lifecycle fixture', 0); ")
        sql("START TRANSACTION; " + audit + statement + "; COMMIT")

    def active():
        return {row["id"]: row for row in
                require_success(send("config-get"))["Dhcp4"]["subnet4"]}

    def checked(name, arguments, result):
        before = snapshot()
        response = send(name, arguments)
        assert response["result"] == result, response
        assert snapshot() == before, f"{name} unexpectedly changed database contents"
        return response

    # Native serialization includes the complete rich subnet/pool/option fixture.
    before = snapshot()
    listed = require_success(send("cb-subnet4-list"))["subnet4"]
    for row in listed:
        for selector in ({"id": row["id"]}, {"subnet": row["subnet"]}):
            response = checked("cb-subnet4-get", selector, 0)
            assert response["arguments"] == {"server-tag": "test-server", "subnet4": [row]}
    assert before == snapshot()
    for selector in ({"id": 919}, {"subnet": "198.20.99.0/24"}):
        assert checked("cb-subnet4-get", selector, 3)["arguments"]["subnet4"] == []
        response = checked("cb-subnet4-del", delete_request(**selector), 3)
        assert response["arguments"]["deleted"] == 0
    assert checked("cb-subnet4-get", {"id": 44, "server-tag": "other-server"}, 0)
    assert checked("cb-subnet4-get", {"id": 44}, 3)
    assert checked("cb-subnet4-get", {"id": 46}, 3)  # unassigned
    # Universal rows are readable through ONE, but deletion needs exact association.
    checked("cb-subnet4-del", delete_request(id=42), 1)
    checked("cb-subnet4-del", delete_request(id=44), 1)
    checked("cb-subnet4-del", delete_request(id=46), 1)

    bad = (None, [], False, {}, {"id": 1, "subnet": "198.20.0.0/24"},
           {"id": True}, {"id": 0}, {"id": -1}, {"id": 4294967295}, {"id": "920"},
           {"subnet": "198.20.0.1/24"}, {"subnet": "198.20.0.0/024"},
           {"subnet": "198.20.0.0/33"}, {"subnet": "::/64"}, {"subnet": []},
           {"subnet": "bad"}, {"id": 920, "unexpected": 1},
           {"id": 920, "server-tag": []}, {"id": 920, "server-tag": ""},
           {"id": 920, "server-tag": "any"}, {"id": 920, "server-tag": "ALL"},
           {"id": 920, "server-tag": " all "})
    for arguments in bad:
        checked("cb-subnet4-get", arguments, 1)
        deletion = delete_request(**arguments) if isinstance(arguments, dict) else arguments
        checked("cb-subnet4-del", deletion, 1)
    for arguments in ({"id": 920}, {"id": 920, "server-tag": "test-server"},
                      delete_request(id=920, **{"preserve-leases": False}),
                      delete_request(id=920, **{"preserve-leases": "true"}),
                      delete_request(id=920, **{"server-tag": "missing-server"})):
        checked("cb-subnet4-del", arguments, 1)

    require_success(send("cb-subnet4-set", request(
        920, "198.20.0.0/24", pools=[{"start": "198.20.0.10", "end": "198.20.0.20"}])))
    fixture("INSERT INTO dhcp4_shared_network(name,valid_lifetime,modification_ts) "
            "VALUES ('m7-shared',600,CURRENT_TIMESTAMP); "
            "UPDATE dhcp4_subnet SET shared_network_name='m7-shared' WHERE subnet_id=920")
    for selector in ({"id": 920}, {"subnet": "198.20.0.0/24"}):
        checked("cb-subnet4-get", selector, 1)
        checked("cb-subnet4-del", delete_request(**selector), 1)
    fixture("UPDATE dhcp4_subnet SET shared_network_name=NULL WHERE subnet_id=920; "
            "DELETE FROM dhcp4_shared_network WHERE name='m7-shared'; "
            "INSERT INTO dhcp4_subnet_server(subnet_id,server_id,modification_ts) "
            "SELECT 920,id,CURRENT_TIMESTAMP FROM dhcp4_server WHERE tag='other-server'")
    checked("cb-subnet4-del", delete_request(id=920), 1)
    fixture("DELETE FROM dhcp4_subnet_server WHERE subnet_id=920 AND server_id IN "
            "(SELECT id FROM dhcp4_server WHERE tag='other-server')")

    # Fail AFTER DELETE, after native child/audit work. Disposable fault fixture
    # only: no production schema changes and no replacement of upstream triggers.
    if pg:
        sql("CREATE FUNCTION m7_delete_fault() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'injected delete failure'; END $$; "
            "CREATE TRIGGER m7_delete_fault AFTER DELETE ON dhcp4_subnet "
            "FOR EACH ROW EXECUTE FUNCTION m7_delete_fault()")
    else:
        sql("CREATE TRIGGER m7_delete_fault AFTER DELETE ON dhcp4_subnet "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='injected delete failure'")
    try:
        for selector in ({"id": 920}, {"subnet": "198.20.0.0/24"}):
            response = checked("cb-subnet4-del", delete_request(**selector), 1)
            assert response["text"].startswith("Configuration backend deletion failed"), response
            assert "arguments" not in response
    finally:
        sql("DROP TRIGGER m7_delete_fault ON dhcp4_subnet; DROP FUNCTION m7_delete_fault()"
            if pg else "DROP TRIGGER m7_delete_fault")
    assert int(sql("SELECT COUNT(*) FROM dhcp4_pool WHERE subnet_id=920")) == 1
    print("PASS: failed native deletion rolls back subnet, pools, associations and audit rows")

    # Preserve all unrelated configuration tables including modification timestamps.
    def unrelated():
        result = {}
        for table, condition in (("dhcp4_subnet", "subnet_id<>920"),
                                 ("dhcp4_pool", "subnet_id<>920"),
                                 ("dhcp4_subnet_server", "subnet_id<>920"),
                                 ("dhcp4_options", "1=1"), ("dhcp4_server", "1=1")):
            result[table] = sorted(sql(f"SELECT * FROM {table} WHERE {condition}").splitlines())
        return result

    for selector in ({"id": 920}, {"subnet": "198.20.0.0/24"}):
        # Recreate only after deletion has been activated; no leases in this fixture.
        if 920 not in active():
            require_success(send("config-reload"))
        assert 920 in active()
        before = unrelated()
        stamp = sql("SELECT modification_ts FROM dhcp4_subnet WHERE subnet_id=920").strip()
        audit_id = int(sql("SELECT COALESCE(MAX(id),0) FROM dhcp4_audit_revision"))
        time.sleep(1.1)
        response = require_success(send("cb-subnet4-del", delete_request(**selector)))
        assert response == {"server-tag": "test-server", "deleted": 1,
                            "leases-deleted": False, "activation-requested": False}
        assert unrelated() == before
        for table in ("dhcp4_subnet", "dhcp4_pool", "dhcp4_subnet_server"):
            assert int(sql(f"SELECT COUNT(*) FROM {table} WHERE subnet_id=920")) == 0
        audit = sql("SELECT a.object_type,a.object_id,a.modification_type "
                    "FROM dhcp4_audit a WHERE a.revision_id>" + str(audit_id)).splitlines()
        separator = b"|" if pg else b"\t"
        assert audit == [separator.join((b"dhcp4_subnet", b"920", b"2"))], audit
        assert sql("SELECT log_message FROM dhcp4_audit_revision WHERE id>" +
                   str(audit_id)).strip() == b"subnet deleted"
        # Timestamp comparison occurs in SQL to avoid client timezone/format differences.
        assert int(sql("SELECT COUNT(*) FROM dhcp4_audit_revision WHERE id>" +
                       str(audit_id) + f" AND modification_ts>='{stamp.decode()}'")) == 1
        checked("cb-subnet4-get", {"id": 920}, 3)
        checked("cb-subnet4-del", delete_request(id=920), 3)
        assert 920 in active(), "Deletion unexpectedly activated runtime configuration"
        require_success(send("config-backend-pull"))
        assert 920 not in active()
        require_success(send("config-reload"))
        assert 920 not in active()
        if "id" in selector:
            require_success(send("cb-subnet4-set", request(
                920, "198.20.0.0/24", pools=[{"start": "198.20.0.10", "end": "198.20.0.20"}])))

    # Universal deletion must explicitly name all; universal native audit activates too.
    require_success(send("cb-subnet4-set", request(921, "198.21.0.0/24", tag="all")))
    require_success(send("config-reload"))
    checked("cb-subnet4-del", delete_request(id=921), 1)
    time.sleep(1.1)
    require_success(send("cb-subnet4-del", delete_request(id=921, **{"server-tag": "all"})))
    require_success(send("config-backend-pull"))
    assert 921 not in active()

    # Independent control connections arrive together. Kea must serialize the
    # preflight and native mutation even when packet multithreading is enabled.
    # Two different IDs competing for one prefix must never rename each other.
    def simultaneous(name, arguments):
        barrier = Barrier(2)

        def invoke(argument):
            barrier.wait(timeout=10)
            return send(name, argument)

        with ThreadPoolExecutor(max_workers=2) as workers:
            return list(workers.map(invoke, arguments))

    runtime = active()
    audit_id = int(sql("SELECT COALESCE(MAX(id),0) FROM dhcp4_audit_revision"))
    requests = [request(identity, "198.22.0.0/24") for identity in (930, 931)]
    responses = simultaneous("cb-subnet4-set", requests)
    assert sorted(response["result"] for response in responses) == [0, 1], responses
    winner = requests[next(i for i, response in enumerate(responses)
                           if response["result"] == 0)]["subnet4"]["id"]
    loser = 931 if winner == 930 else 930
    assert checked("cb-subnet4-get", {"id": winner}, 0)["arguments"]["subnet4"][0]["id"] == winner
    checked("cb-subnet4-get", {"id": loser}, 3)
    assert int(sql("SELECT COUNT(*) FROM dhcp4_audit a WHERE a.revision_id>" +
                   str(audit_id))) == 1, "Rejected concurrent write left audit changes"
    before = snapshot()
    reads = simultaneous("cb-subnet4-list", [{}, {}])
    assert reads[0] == reads[1] and reads[0]["result"] == 0, reads
    assert snapshot() == before
    responses = simultaneous("cb-subnet4-del", [delete_request(id=winner)] * 2)
    assert sorted(response["result"] for response in responses) == [0, 3], responses
    checked("cb-subnet4-get", {"id": winner}, 3)
    assert active() == runtime, "Concurrent mutations activated configuration"
    print("PASS: concurrent control connections serialize conflicting writes, reads and deletion")
    print("PASS: native get/delete by ID/prefix, exact tags, guards, child cleanup, "
          "audit/timestamps, unrelated rows, explicit pull/reload activation")
