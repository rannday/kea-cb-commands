"""Regression tests for evidence preservation and durable recovery admission."""
# SPDX-License-Identifier: MPL-2.0
import copy
import json
from pathlib import Path
import tempfile
import unittest

from reconciliation import RecoveryGate, canonical, classify, evidence


def observation():
    return {"ownership": True, "complete": True, "persisted": {"id": 1},
            "intended": {"id": 1}, "consumers": {
                "a": {"active": {"id": 1}, "intended": {"id": 1}},
                "b": {"active": {"id": 2}, "intended": {"id": 2}}}}


class ReconciliationTests(unittest.TestCase):
    def test_canonicalization_preserves_fields_and_semantics(self):
        left = {"subnet4": [{"id": 2, "pools": [{"pool": "192.0.2.0/25", "x": []}]},
                            {"id": 1}], "associations": ["b", "a"]}
        right = {"associations": ["a", "b"], "subnet4": [
            {"id": 1}, {"pools": [{"x": [], "pool": "192.0.2.0 - 192.0.2.127"}], "id": 2}]}
        self.assertEqual(evidence(left), evidence(right))
        self.assertEqual(canonical(canonical(left)), canonical(left))
        for changed in ({"id": 1}, {"id": 1, "pools": []}, {"id": 1, "pools": None}):
            self.assertNotEqual(evidence(changed), evidence({"id": 1, "pools": [{}]}))
        self.assertNotEqual(evidence({"options": [1, 2]}), evidence({"options": [2, 1]}))
        self.assertNotEqual(evidence(left), evidence({**left, "associations": ["a"]}))
        self.assertEqual(canonical({"unknown-field": {"a": []}}),
                         {"unknown-field": {"a": []}})

    def test_precedence_and_independent_targets(self):
        current = observation()
        self.assertEqual(classify(current)["state"], "CONVERGED")
        current["consumers"]["a"]["active"] = {}
        self.assertEqual(classify(current)["state"], "PARTIAL_ACTIVATION")
        current["consumers"]["b"]["active"] = {}
        self.assertEqual(classify(current)["state"], "PENDING_ACTIVATION")
        current["consumers"]["b"]["active"] = None
        self.assertEqual(classify(current)["state"], "EVIDENCE_INCOMPLETE")
        current["unknown"] = True
        self.assertEqual(classify(current)["state"], "UNKNOWN_COMMIT")
        current["ownership"] = False
        self.assertEqual(classify(current)["state"], "WRITER_UNFENCED")

    def test_journal_restart_unknown_and_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hold.json"
            current = observation()
            gate = RecoveryGate(path, "fixture", lambda: current)
            self.assertTrue(gate.state["held"])
            self.assertEqual(gate.recover()["state"], "CONVERGED")
            calls = []
            gate.mutate(lambda: calls.append(1))
            restarted = RecoveryGate(path, "fixture", lambda: current)
            self.assertTrue(restarted.state["held"])
            self.assertTrue(restarted.state["unknown"])
            with self.assertRaises(RuntimeError):
                restarted.mutate(lambda: calls.append(2))
            self.assertEqual(calls, [1])
            current["persisted"] = {}
            self.assertEqual(restarted.recover()["state"], "UNKNOWN_COMMIT")
            current["persisted"] = current["intended"]
            current["complete"] = False
            restarted.recover()
            self.assertTrue(restarted.state["held"])
            current["complete"] = True
            self.assertEqual(restarted.recover()["state"], "CONVERGED")
            self.assertFalse(restarted.state["held"])
            # Even a stored converged result is invalid after process restart.
            again = RecoveryGate(path, "fixture", lambda: current)
            self.assertTrue(again.state["held"])
            current["ownership"] = False
            self.assertEqual(again.recover()["state"], "WRITER_UNFENCED")
            self.assertTrue(again.state["held"])

    def test_missing_inventory_and_collector_failure(self):
        current = observation()
        current["required"] = ["a", "b", "missing"]
        self.assertEqual(classify(current)["state"], "EVIDENCE_INCOMPLETE")
        current.pop("required")
        current["consumers"]["a"]["active"] = {"old": 1}
        current["consumers"]["b"]["intended"] = current["consumers"]["a"]["intended"]
        self.assertEqual(classify(current)["state"], "PARTIAL_ACTIVATION")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hold.json"
            gate = RecoveryGate(path, "fixture", observation)
            gate.recover()
            def unavailable():
                raise OSError("control endpoint unavailable")
            gate.collect = unavailable
            with self.assertRaises(OSError):
                gate.mutate(lambda: self.fail("dispatched"))
            self.assertTrue(json.loads(path.read_text())["held"])

    def test_invalid_missing_and_stale_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hold.json"
            current = observation()
            gate = RecoveryGate(path, "fixture", lambda: current)
            old = copy.deepcopy(gate.recover())
            current["consumers"]["b"]["active"] = None
            self.assertEqual(gate.recover()["state"], "EVIDENCE_INCOMPLETE")
            self.assertNotEqual(old["evidence"]["serial"], gate.last["serial"])
            for content in ("invalid", "{}", json.dumps({"version": 99})):
                path.write_text(content)
                invalid = RecoveryGate(path, "fixture", lambda: current)
                self.assertTrue(invalid.state["held"])
                self.assertTrue(invalid.state["unknown"])
            path.unlink()
            missing = RecoveryGate(path, "fixture", lambda: current)
            self.assertTrue(missing.state["held"])
            with self.assertRaises(RuntimeError):
                missing.promote(lambda: False, lambda: self.fail("started"))
