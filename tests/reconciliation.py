"""Read-only reconciliation evidence and a fail-closed local recovery journal.

This is diagnostic/test tooling, not a distributed fencing service.
"""
# SPDX-License-Identifier: MPL-2.0
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import time
from collections.abc import Callable
from typing import Any, TypedDict


# Evidence documents carry backend-specific JSON fields; gate results have a fixed schema.
class Classification(TypedDict):
    state: str
    reasons: list[str]


class ObservationResult(Classification):
    evidence: dict[str, Any]


class Journal(TypedDict):
    version: int
    deployment: str
    held: bool
    unknown: bool
    reason: str


def canonical(value, field=None):
    """Preserve every field; sort only collections with known set semantics."""
    if isinstance(value, dict):
        result = {key: canonical(item, key) for key, item in value.items()}
        if "pool" in result:
            pool = result["pool"]
            text = ("-".join(pool) if isinstance(pool, list) else pool).replace(" ", "")
            if "/" in text:
                network = ipaddress.IPv4Network(text)
                ends = (network.network_address, network.broadcast_address)
            else:
                ends = tuple(ipaddress.IPv4Address(item) for item in text.split("-"))
            if len(ends) != 2 or ends[0] > ends[1]:
                raise ValueError("Invalid pool")
            result["pool"] = [str(item) for item in ends]
        return result
    if isinstance(value, list):
        result = [canonical(item) for item in value]
        if field in ("subnet4", "pools", "associations", "server-tags"):
            result.sort(key=encoded)
        return result
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    raise ValueError("Unsupported evidence type")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def evidence(value):
    data = canonical(value)
    return {"data": data, "sha256": hashlib.sha256(encoded(data).encode("utf-8")).hexdigest()}


def process_identity(pid):
    """Linux boot identity and start ticks distinguish PID reuse."""
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    return {"pid": pid, "start-ticks": int(stat.rsplit(")", 1)[1].split()[19]),
            "boot-id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}


def classify(observation: dict[str, Any]) -> Classification:
    """Return primary status plus all reasons, in documented precedence."""
    reasons = []
    if not observation.get("ownership"):
        reasons.append("WRITER_UNFENCED")
    if observation.get("unknown"):
        reasons.append("UNKNOWN_COMMIT")
    consumers = observation.get("consumers", {})
    if (not observation.get("complete") or not consumers or
            not set(observation.get("required", consumers)).issubset(consumers) or
            observation.get("persisted") is None or observation.get("intended") is None or any(
                row.get("active") is None or row.get("intended") is None
                for row in consumers.values())):
        reasons.append("EVIDENCE_INCOMPLETE")
    matches = [row.get("active") == row.get("intended") for row in consumers.values()
               if row.get("active") is not None]
    if matches and not all(matches):
        # Compare each consumer to its own selector-specific target.
        differing = any(a.get("intended") == b.get("intended") and
                        a.get("active") != b.get("active")
                        for a in consumers.values() for b in consumers.values()
                        if a.get("active") is not None and b.get("active") is not None)
        reasons.append("PARTIAL_ACTIVATION" if any(matches) or differing else "PENDING_ACTIVATION")
    if observation.get("persisted") != observation.get("intended"):
        reasons.append("RECOVERY_REQUIRED")
    return {"state": reasons[0] if reasons else "CONVERGED", "reasons": reasons}


class RecoveryGate:
    """Atomic local hold. Restarts always invalidate observations.

    Only collect() may establish fresh evidence. Stored snapshots and operator
    acknowledgements cannot clear a hold. Caller must supervise all writers.
    """
    def __init__(self, path, deployment: str, collect: Callable[[], dict[str, Any]]):
        self.path = Path(path)
        self.deployment = deployment
        self.collect = collect
        self.session = secrets.token_hex(16)
        self.serial = 0
        self.last: dict[str, Any] | None = None
        self.state: Journal = {"version": 1, "deployment": deployment, "held": True,
                      "unknown": False, "reason": "fresh reconciliation required"}
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if (saved["version"] != 1 or saved["deployment"] != deployment or
                    type(saved["held"]) is not bool or type(saved["unknown"]) is not bool):
                raise ValueError("Invalid journal")
            self.state["unknown"] = saved["unknown"]
        except (OSError, ValueError, KeyError, TypeError):
            self.state["reason"] = "missing or invalid journal"
            self.state["unknown"] = True
        self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + "." + self.session + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(encoded(self.state) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def observe(self) -> ObservationResult:
        # No API accepts a caller-supplied old observation.
        self.serial += 1
        observation = copy.deepcopy(self.collect())
        observation.update(session=self.session, serial=self.serial, observed=time.time())
        observation["unknown"] = self.state["unknown"]
        self.last = observation
        return {**classify(observation), "evidence": observation}

    def recover(self) -> ObservationResult:
        self.state.update(held=True, reason="recovery in progress")
        self._save()
        result = self.observe()
        observation = result["evidence"]
        # Unknown outcomes resolve only with fresh complete persisted comparison.
        # No mutation is retried; disagreement remains an operator decision.
        if (observation.get("complete") and observation.get("ownership") and
                observation.get("persisted") is not None and
                observation.get("intended") is not None and
                observation.get("persisted") == observation.get("intended")):
            self.state["unknown"] = False
            observation["unknown"] = False
            result: ObservationResult = {**classify(observation), "evidence": observation}
        if result["state"] == "CONVERGED":
            self.state.update(held=False, reason="fresh convergence verified")
        self._save()
        return result

    def mutate(self, dispatch):
        if self.state["held"]:
            raise RuntimeError("Mutation hold")
        self.state.update(held=True, reason="pre-dispatch reconciliation")
        self._save()
        if self.observe()["state"] != "CONVERGED":
            raise RuntimeError("Mutation hold")
        # Durable uncertainty BEFORE dispatch, including exceptions/crashes.
        self.state.update(held=True, unknown=True, reason="mutation outcome requires reconciliation")
        self._save()
        return dispatch()

    def promote(self, verify_fence, start):
        # Execute a fresh supervisor check; never accept a stored acknowledgement.
        self.state.update(held=True, reason="promotion requires reconciliation")
        self._save()
        result = self.observe()
        if (not verify_fence() or result["state"] != "CONVERGED" or self.state["unknown"]):
            raise RuntimeError("Promotion refused")
        return start()
