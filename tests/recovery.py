"""Real native readback qualification, reusing M21 roles and SQL fixtures.

The observed subnet projection is useful but deliberately cannot unlock writes:
the current native hook cannot enumerate association/revision evidence.
"""
# SPDX-License-Identifier: MPL-2.0
import copy
import json
from pathlib import Path
import socket
import time

from designated_writer import Role, desired, exchange, managed
from reconciliation import RecoveryGate, classify, evidence, process_identity
from smoke import require_success


def verify_recovery(args, directory, config, environment, authorization, snapshot, sql):
    backend = config["Dhcp4"]["config-control"]["config-databases"][0]["type"]
    mt = config["Dhcp4"]["multi-threading"]["enable-multi-threading"]
    output = args.work_dir.resolve().parent / "reconciliation-results"
    output.mkdir(exist_ok=True)
    report = {"backend": backend, "packet-mt": mt, "status": "FAIL",
              "observations": [], "dora": [], "scenarios": {}}
    roles = []
    consumers = {}
    writer = None
    identities = {}
    intended = []
    journal = directory / "recovery-hold.json"

    def start(name, writer_role, port):
        user = None if writer_role else ("m22_consumer_a" if name == "consumer-a" else
                                         "m22_consumer_b")
        role = Role(args, directory, config, environment, authorization, name, writer_role, port,
                    database_user=user)
        roles.append(role)
        identities[name] = process_identity(role.process.pid)
        return role

    def persisted():
        # Deliberately narrow diagnostic SQL, not a production hook query.
        # Fixed projection preserves NULL versus empty and actual associations.
        if backend == "postgresql":
            statement = ("SELECT json_build_object('subnet-id',s.subnet_id,'prefix',s.subnet_prefix,"
                         "'modified',s.modification_ts::text,'tag',v.tag) "
                         "FROM dhcp4_subnet s LEFT JOIN dhcp4_subnet_server a "
                         "ON s.subnet_id=a.subnet_id LEFT JOIN dhcp4_server v ON a.server_id=v.id "
                         "ORDER BY s.subnet_id,v.tag")
            associations = [json.loads(line) for line in sql(statement, user="m22_reconcile").decode().splitlines()]
        else:
            statement = ("SELECT JSON_OBJECT('subnet-id',s.subnet_id,'prefix',s.subnet_prefix,"
                         "'modified',CAST(s.modification_ts AS CHAR),'tag',v.tag) "
                         "FROM dhcp4_subnet s LEFT JOIN dhcp4_subnet_server a "
                         "ON s.subnet_id=a.subnet_id LEFT JOIN dhcp4_server v ON a.server_id=v.id "
                         "ORDER BY s.subnet_id,v.tag")
            associations = [json.loads(line) for line in sql(
                statement, user="m22_reconcile").decode().splitlines()]
        # Dump content is intentionally NOT persisted: retain safe structured
        # comparison data and a digest, never arbitrary database text.
        observer = next((role for role in roles if role.process.poll() is None), None)
        native = require_success(observer.send("cb-subnet4-list"))["subnet4"] if observer else None
        return {"native-all": native, "associations": associations,
                "scope": "subnet fields; not full backend configuration"}

    def collect():
        stored = persisted()
        active = {}
        ownership = (writer is not None and writer.process.poll() is None and
                     sum(role.writer and role.process.poll() is None for role in roles) == 1)
        writer_evidence = None
        if ownership:
            identity = process_identity(writer.process.pid)
            diagnostic = require_success(writer.send("db-commands-diagnostic"))
            status = require_success(writer.send("status-get"))
            ownership = (identity == identities[writer.name] and
                         diagnostic["allow-mutations"] is True and status["pid"] == identity["pid"])
            writer.packetless()
            writer_evidence = {"identity": identity, "endpoint": ["127.0.0.1", writer.control_port],
                               "admission": diagnostic["allow-mutations"]}
        for name, role in consumers.items():
            row = {"intended": evidence({"subnet4": intended})["data"], "active": None,
                   "selector": role.name, "endpoint": ["127.0.0.1", role.control_port]}
            if role.process.poll() is None:
                reply = require_success(role.send("config-get"))["Dhcp4"]
                diagnostic = require_success(role.send("db-commands-diagnostic"))
                identity = process_identity(role.process.pid)
                status = require_success(role.send("status-get"))
                ownership = ownership and diagnostic["allow-mutations"] is False
                row.update(active=evidence({"subnet4": reply["subnet4"]})["data"],
                           identity=identity, admission=diagnostic["allow-mutations"],
                           backend={key: reply["config-control"]["config-databases"][0][key]
                                    for key in ("type", "name", "host", "port")
                                    if key in reply["config-control"]["config-databases"][0]},
                           runtime_selector=reply["server-tag"],
                           observed=time.time(), status={key: status[key] for key in
                                                        ("pid", "uptime", "reload") if key in status})
                ownership = ownership and identity == identities[role.name] and status["pid"] == identity["pid"]
            active[name] = row
        return {"ownership": ownership, "writer": writer_evidence, "complete": False,
                "limitations": ["Native list omits actual associations and modification times",
                                "SQL supplement covers subnets only; globals/options/audit unqualified",
                                "Runtime inheritance and default equivalence unqualified"],
                "required": ["consumer-a", "consumer-b"],
                "persisted": evidence({"subnet4": stored["native-all"]})["data"],
                "intended": evidence({"subnet4": intended})["data"],
                "persisted-evidence": evidence(stored), "consumers": active}

    def projection(row):
        row = copy.deepcopy(row)
        for pool in row["pools"]:
            if isinstance(pool["pool"], list):
                pool["pool"] = "-".join(pool["pool"])
        return managed(row)

    def record(name):
        result = gate.recover()
        bounded = {"ownership": result["evidence"]["ownership"], "complete": True,
                   "persisted": [projection(item) for item in
                                 result["evidence"]["persisted-evidence"]["data"]["native-all"]],
                   "intended": [managed(item) for item in intended], "consumers": {}}
        for consumer_name, row in result["evidence"]["consumers"].items():
            role = consumers[consumer_name]
            target = [managed(item) for item in intended]
            active = ([managed(item) for item in role.active().values()]
                      if role.process.poll() is None else None)
            bounded["consumers"][consumer_name] = {"active": active, "intended": target}
        report.setdefault("bounded-projection", {})[name] = classify(bounded)
        expected_projection = {"B-pending": "PENDING_ACTIVATION",
                               "C-partial": "PARTIAL_ACTIVATION",
                               "D-unavailable": "EVIDENCE_INCOMPLETE"}
        if name in expected_projection:
            assert report["bounded-projection"][name]["state"] == expected_projection[name]
        report["observations"].append({"scenario": name, **result})
        report["scenarios"][name] = result["state"]
        assert gate.state["held"], "Incomplete evidence released hold"
        try:
            gate.mutate(lambda: writer.send("cb-subnet4-set", desired(50)))
        except RuntimeError:
            pass
        else:
            raise AssertionError("Incomplete evidence authorized mutation")
        return result

    try:
        for user in ("m22_consumer_a", "m22_consumer_b", "m22_reconcile"):
            if backend == "postgresql":
                sql(f"CREATE ROLE {user} LOGIN; GRANT CONNECT ON DATABASE kea_test TO {user}; "
                    f"GRANT USAGE ON SCHEMA public TO {user}; "
                    f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {user}; "
                    f"ALTER ROLE {user} SET default_transaction_read_only=on")
            else:
                grants = "SELECT" if user == "m22_reconcile" else "SELECT,INSERT,UPDATE,DELETE"
                sql(f"CREATE USER '{user}'@'localhost'; "
                    f"GRANT {grants} ON kea_test.* TO '{user}'@'localhost'")
        assert sql("SELECT COUNT(*) FROM dhcp4_subnet", user="m22_reconcile").strip() == b"0"
        # Prove the same no-row statement is valid for the fixture owner,
        # then fails under the independently granted diagnostic account.
        sql("DELETE FROM dhcp4_subnet WHERE subnet_id=4294967294")
        try:
            sql("DELETE FROM dhcp4_subnet WHERE subnet_id=4294967294", user="m22_reconcile")
        except AssertionError:
            report["diagnostic-dml-denied"] = True
        else:
            raise AssertionError("Diagnostic account has DML permission")
        report["privileges"] = {
            "writer": "CRUD plus sequences and default PUBLIC routines" if backend == "postgresql"
            else "CRUD plus EXECUTE",
            "consumer-a": "SELECT, read-only transactions" if backend == "postgresql" else "CRUD",
            "consumer-b": "SELECT, read-only transactions" if backend == "postgresql" else "CRUD",
            "reconciliation": "SELECT, read-only transactions" if backend == "postgresql" else "SELECT",
            "scope": "effective schema-level grants; per-object minimum not established"}
        writer = start("admin-old", True, 1267)
        consumers["consumer-a"] = start("consumer-a", False, 1067)
        consumers["consumer-b"] = start("consumer-b", False, 1167)
        gate = RecoveryGate(journal, f"{backend}-mt-{int(mt)}", collect)
        record("A-empty-incomplete")
        # Scenario fixture setup is explicit, outside the recovery gate. It is
        # NOT evidence that the new gate authorized resumption.
        require_success(writer.send("cb-subnet4-set", desired()))
        stored = require_success(writer.send("cb-subnet4-get", {
            "id": 910, "server-tag": "all"}))["subnet4"][0]
        assert managed(stored) == (910, "127.0.0.0/24", 600, ["127.0.0.10-127.0.0.20"])
        intended = [copy.deepcopy(stored)]
        pending = record("B-pending")
        assert "PENDING_ACTIVATION" in pending["reasons"]
        require_success(consumers["consumer-a"].send("config-backend-pull"))
        partial = record("C-partial")
        # Entire native subtree comparison may expose defaults; retain it even
        # if only the bounded managed projection can establish partiality.
        assert managed(consumers["consumer-a"].active()[910]) == managed(stored)
        assert not consumers["consumer-b"].active()
        report["bounded-partial-activation"] = True
        report["full-subtree-partial-classification"] = partial["reasons"]
        require_success(consumers["consumer-b"].send("config-backend-pull"))
        record("A-active-incomplete")
        report["dora"].extend(exchange(role, 10) for role in consumers.values())
        consumers["consumer-b"].stop()
        unavailable = record("D-unavailable")
        assert unavailable["evidence"]["consumers"]["consumer-b"]["active"] is None
        # Supported clean start, new process instance, explicit activation.
        consumers.pop("consumer-b")
        consumers["consumer-b"] = start("consumer-b-recovered", False, 1167)
        require_success(consumers["consumer-b"].send("config-backend-pull"))
        record("D-restarted")
        # Simulate an orchestration-level uncertain outcome only. No SQL
        # connection is interrupted and no uncertain command is retried.
        gate.state.update(held=True, unknown=True, reason="simulated uncertain response")
        gate._save()
        gate = RecoveryGate(journal, f"{backend}-mt-{int(mt)}", collect)
        record("I-workflow-restart-unknown")
        assert gate.state["unknown"]
        # Selector qualification uses overlapping prefixes, distinct IDs, a
        # multi-association object and an unassigned object. Equal prefixes/IDs
        # cannot be independent namespaces under the upstream unique constraints.
        audit = ("SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', 'M22 fixture', false);"
                 if backend == "postgresql" else
                 "CALL createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', 'M22 fixture', false);")
        sql(audit + """
            INSERT INTO dhcp4_server(tag,description,modification_ts)
            VALUES ('consumer-a','M22',CURRENT_TIMESTAMP),
                   ('consumer-b-recovered','M22',CURRENT_TIMESTAMP);
            INSERT INTO dhcp4_subnet(subnet_id,subnet_prefix,valid_lifetime,modification_ts)
            VALUES (920,'198.18.0.0/24',600,CURRENT_TIMESTAMP),
                   (921,'198.18.0.0/25',600,CURRENT_TIMESTAMP),
                   (922,'198.19.0.0/24',600,CURRENT_TIMESTAMP),
                   (923,'198.19.1.0/24',600,CURRENT_TIMESTAMP);
            INSERT INTO dhcp4_subnet_server(subnet_id,server_id,modification_ts)
            SELECT 920,id,CURRENT_TIMESTAMP FROM dhcp4_server WHERE tag='consumer-a';
            INSERT INTO dhcp4_subnet_server(subnet_id,server_id,modification_ts)
            SELECT 921,id,CURRENT_TIMESTAMP FROM dhcp4_server WHERE tag='consumer-b-recovered';
            INSERT INTO dhcp4_subnet_server(subnet_id,server_id,modification_ts)
            SELECT 922,id,CURRENT_TIMESTAMP FROM dhcp4_server
            WHERE tag IN ('consumer-a','consumer-b-recovered');
        """)
        views = {}
        for tag, expected_ids in (("all", {910}), ("consumer-a", {910, 920, 922}),
                                  ("consumer-b-recovered", {910, 921, 922})):
            rows = []
            for subnet_id in (910, 920, 921, 922, 923):
                reply = writer.send("cb-subnet4-get", {"id": subnet_id, "server-tag": tag})
                if reply["result"] == 0:
                    rows.extend(require_success(reply)["subnet4"])
                else:
                    assert reply["result"] == 3
            assert {row["id"] for row in rows} == expected_ids
            views[tag] = evidence({"subnet4": rows})
        association_rows = persisted()["associations"]
        assert [row["tag"] for row in association_rows if row["subnet-id"] == 922] == [
            "consumer-a", "consumer-b-recovered"]
        assert [row["tag"] for row in association_rows if row["subnet-id"] == 923] == [None]
        report["selector-views"] = views
        report["association-evidence"] = evidence({"associations": association_rows})
        report["scenarios"]["association-selector"] = "PASS"
        old_identity = identities[writer.name]
        writer.stop()
        assert not Path(f"/proc/{writer.process.pid}").exists()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", writer.control_port)) != 0
        report["fence"] = {"previous": old_identity, "exit": writer.process.poll(),
                           "process-gone": True, "endpoint-closed": True,
                           "boundary": "supervised same-host processes without restart policies"}
        report["dora"].extend(exchange(role, 10) for role in consumers.values())
        record("E-writer-stopped")
        for scenario in ("F-promotion-incomplete", "G-missing", "H-stale"):
            if scenario == "G-missing":
                journal.unlink()
                gate = RecoveryGate(journal, f"{backend}-mt-{int(mt)}", collect)
            if scenario == "H-stale":
                # A retained or contradictory prior result has no authority:
                # promotion must call the live collector again.
                gate.last = {"ownership": True, "complete": True, "state": "CONVERGED",
                             "writer": old_identity, "observed": 0}
            before = snapshot()
            try:
                gate.promote(lambda: writer.process.poll() == 0 and not Path(
                    f"/proc/{writer.process.pid}").exists(),
                             lambda: start("admin-new", True, 1267))
            except RuntimeError:
                report["scenarios"][scenario] = "REFUSED"
            else:
                raise AssertionError("Incomplete evidence permitted promotion")
            assert snapshot() == before
        record("J-recovery-incomplete-hold-retained")
        report["status"] = "PARTIAL"
        print(f"PASS: reconciliation safety {backend} MT={mt}; milestone PARTIAL; "
              "incomplete native evidence cannot authorize resumption")
    finally:
        cleanup = True
        for role in reversed(roles):
            try:
                role.close()
            except (OSError, AssertionError):
                cleanup = False
        report["kea-cleanup"] = cleanup and all(role.process.poll() == 0 for role in roles)
        (output / f"{backend}-mt-{int(mt)}.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
        assert report["kea-cleanup"]
