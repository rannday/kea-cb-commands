"""Run hook validation, commands, unload/reload and shutdown on real Kea."""

# SPDX-License-Identifier: MPL-2.0
import argparse
import base64
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from control import Response, command

DIAGNOSTIC = "db-commands-diagnostic"
SUBNET_LIST = "cb-subnet4-list"
RECORD_COMMANDS = tuple(
    f"cb-{family}4-{operation}"
    for family in ("server", "global-parameter")
    for operation in ("list", "get", "set", "del")
)
OPTION_COMMANDS = tuple(
    f"cb-{family}-{operation}"
    for family in ("option-def4", "option4-global", "option4-network",
                   "option4-subnet", "option4-pool")
    for operation in ("list", "get", "set", "del")
)
SHARED_NETWORK_COMMANDS = tuple(
    f"cb-shared-network4-{operation}" for operation in ("list", "get", "set", "del")
)
ADMISSION_ERROR = {"result": 1, "text": (
    "Mutations are disabled; configure allow-mutations: true on the "
    "designated administrative writer.")}


def verify_denied(send):
    """All mutation entry points reject malformed input before backend access."""
    mutations: dict[str, Any] = {
        "cb-subnet4-set": {"server-tag": "all", "subnet4": {
            "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600}},
        "cb-subnet4-del": {"id": 900, "server-tag": "all", "preserve-leases": True},
        "cb-server4-set": {"server-tag": "test-server", "description": "test"},
        "cb-server4-del": {"server-tag": "test-server"},
        "cb-global-parameter4-set": {
            "server-tag": "all", "name": "authoritative", "value": False},
        "cb-global-parameter4-del": {"server-tag": "all", "name": "authoritative"},
        "cb-option-def4-set": {"server-tag": "all", "option-def": {
            "name": "test", "code": 224, "space": "dhcp4", "type": "string"}},
        "cb-option-def4-del": {"server-tag": "all", "option-def": {
            "code": 224, "space": "dhcp4"}},
        "cb-option4-global-set": {"server-tag": "all", "option": {
            "code": 3, "space": "dhcp4", "data": "192.0.2.1"}},
        "cb-option4-global-del": {"server-tag": "all", "option": {
            "code": 3, "space": "dhcp4"}},
        "cb-shared-network4-set": {"server-tag": "all", "shared-network": {"name": "test"}},
        "cb-shared-network4-del": {"server-tag": "all", "name": "test"},
    }
    for scope, parent in (
        ("network", {"shared-network-name": "test"}),
        ("subnet", {"subnet-id": 900}),
        ("pool", {"subnet-id": 900, "start": "198.18.0.10", "end": "198.18.0.20"}),
    ):
        for operation in ("set", "del"):
            option = {"code": 15, "space": "dhcp4"}
            if operation == "set":
                option["data"] = "test.example"
            mutations[f"cb-option4-{scope}-{operation}"] = {
                "server-tag": "all", "parent": parent, "option": option}
    for name, valid in mutations.items():
        for arguments in (valid, None, {}, [], False, 1, "invalid", {"unexpected": True}):
            assert send(name, arguments) == ADMISSION_ERROR
    assert require_success(send(DIAGNOSTIC))["allow-mutations"] is False
    for name, arguments in ((SUBNET_LIST, None), ("cb-subnet4-get", {"id": 900})):
        assert send(name, arguments) != ADMISSION_ERROR, "Read command was gated"


def require_success(response: Response) -> Any:
    if response["result"] != 0:
        raise AssertionError(response)
    return response.get("arguments")


def verify_argument_contracts(send):
    """Assert complete public error envelopes through the real command dispatch."""
    arguments: Any  # Negative cases deliberately include malformed JSON values.
    cases = [
        ("cb-subnet4-get", None,
         "Expected one id or subnet selector and optional server-tag."),
        ("cb-subnet4-get", {},
         "Expected exactly one id or subnet selector and optional server-tag."),
        ("cb-subnet4-get", {"id": 900, "subnet": "198.18.0.0/24"},
         "Expected exactly one id or subnet selector and optional server-tag."),
        ("cb-subnet4-get", {"id": "900"},
         "id must be an integer in 1..4294967294."),
        ("cb-subnet4-get", {"id": True},
         "id must be an integer in 1..4294967294."),
        ("cb-subnet4-get", {"subnet": "198.18.0.1/24"},
         "subnet must be a canonical IPv4 CIDR string."),
        ("cb-subnet4-get", {"id": 900, "server-tag": None},
         "server-tag must be an explicit string."),
        ("cb-subnet4-get", {"id": 900, "server-tag": "WRITER"},
         "server-tag must be lowercase without surrounding whitespace."),
        ("cb-subnet4-del", {"id": 900, "server-tag": "all"},
         "Deletion requires server-tag and preserve-leases: true."),
        ("cb-subnet4-del", {"id": 900, "server-tag": "all", "preserve-leases": 1},
         "Deletion requires server-tag and preserve-leases: true."),
        ("cb-subnet4-set", {"subnet4": {}},
         "Expected only server-tag and one subnet4 map."),
        ("cb-subnet4-set", {"server-tag": False, "subnet4": {}},
         "server-tag must be an explicit string."),
        ("cb-subnet4-set", {"server-tag": "all", "subnet4": []},
         "subnet4 requires id, subnet and valid-lifetime; only pools is optional."),
        ("cb-subnet4-set", {"server-tag": "all", "subnet4": {
            "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": "600"}},
         "id and valid-lifetime must be integers in 1..4294967294."),
        ("cb-subnet4-set", {"server-tag": "all", "subnet4": {
            "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600,
            "pools": {}}},
         "pools must be a list of start/end address maps."),
        ("cb-subnet4-set", {"server-tag": "all", "subnet4": {
            "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600,
            "pools": [{"start": "198.18.0.10"}]}},
         "Each pool supports only required start and end strings."),
    ]
    for name, arguments, text in cases:
        assert send(name, arguments) == {"result": 1, "text": text}, (name, arguments)

    # Optional tags, either lookup identity, and omitted/empty pools reach the
    # backend boundary only after the same validation used with a real backend.
    for arguments in (
        {"id": 900}, {"id": 900, "server-tag": "all"},
        {"subnet": "198.18.0.0/24", "server-tag": "consumer-a"},
    ):
        assert send("cb-subnet4-get", arguments) == {
            "result": 1,
            "text": "Subnet lookup/deletion requires exactly one configured SQL backend.",
        }
    for optional_pools in ({}, {"pools": []}):
        assert send("cb-subnet4-set", {"server-tag": "all", "subnet4": {
            "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600,
            **optional_pools}}) == {
                "result": 1,
                "text": "cb-subnet4-set requires exactly one configured SQL backend.",
            }
    for name, text in (
        (DIAGNOSTIC, "This diagnostic accepts only absent or empty arguments."),
        (SUBNET_LIST, "cb-subnet4-list accepts only absent or empty arguments."),
    ):
        for arguments in ([], False, 1, "invalid", {"unexpected": True}):
            assert send(name, arguments) == {"result": 1, "text": text}
    for arguments in (None, {}):
        assert send(SUBNET_LIST, arguments) == {
            "result": 1, "text": "No configuration backend is configured."}

    backend_error = {"result": 1, "text": "Exactly one SQL configuration backend is required."}
    for name, arguments in (
        ("cb-server4-list", None), ("cb-server4-list", {}),
        ("cb-server4-get", {"server-tag": "test-server"}),
        ("cb-server4-set", {"server-tag": "test-server", "description": ""}),
        ("cb-server4-del", {"server-tag": "test-server"}),
        ("cb-global-parameter4-list", {"server-tag": "all"}),
        ("cb-global-parameter4-get", {"server-tag": "all", "name": "authoritative"}),
        ("cb-global-parameter4-set", {
            "server-tag": "all", "name": "authoritative", "value": False}),
        ("cb-global-parameter4-del", {"server-tag": "all", "name": "authoritative"}),
    ):
        assert send(name, arguments) == backend_error, (name, arguments)
    for name in RECORD_COMMANDS + OPTION_COMMANDS + SHARED_NETWORK_COMMANDS:
        for arguments in ([], False, 1, "invalid", {"unexpected": True}):
            assert send(name, arguments)["result"] == 1, (name, arguments)
    for family, field in (("option-def4", "option-def"), ("option4-global", "option")):
        for operation in ("list", "get", "set", "del"):
            arguments = {"server-tag": "all"}
            if operation != "list":
                obj = {"code": 224, "space": "dhcp4"}
                if operation == "set":
                    obj.update({"name": "test", "type": "string"} if field == "option-def"
                               else {"data": "abc", "csv-format": False})
                arguments[field] = obj
            assert send(f"cb-{family}-{operation}", arguments) == backend_error
    for operation in ("list", "get", "set", "del"):
        arguments = {"server-tag": "all"}
        if operation == "set":
            arguments["shared-network"] = {"name": "test"}
        elif operation != "list":
            arguments["name"] = "test"
        assert send(f"cb-shared-network4-{operation}", arguments) == backend_error
    for scope, parent in (
        ("network", {"shared-network-name": "test"}),
        ("subnet", {"subnet-id": 900}),
        ("pool", {"subnet-id": 900, "start": "198.18.0.10", "end": "198.18.0.20"}),
    ):
        for operation in ("list", "get", "set", "del"):
            arguments = {"server-tag": "all", "parent": parent}
            if operation != "list":
                arguments["option"] = {"code": 15, "space": "dhcp4"}
                if operation == "set":
                    arguments["option"]["data"] = "test.example"
            name = f"cb-option4-{scope}-{operation}"
            assert send(name, arguments) == backend_error, (name, arguments)
            for invalid in ({}, [], None, {"server-tag": "all", "parent": []},
                            dict(arguments, **{"server-tag": False}),
                            dict(arguments, **{"server-tag": "UPPER"})):
                assert send(name, invalid)["result"] == 1, (name, invalid)
    for name, value in (("authoritative", 1), ("renew-timer", True),
                        ("boot-file-name", []), ("dhcp-ddns", {})):
        assert send("cb-global-parameter4-set", {
            "server-tag": "all", "name": name, "value": value})["result"] == 1


def run_case(server, hook, directory, multithreading, *, mutation_admission=True):
    """Test current admission by default; v0.1.0 predates that contract."""
    password = secrets.token_urlsafe(24)
    credentials_path = directory / "test-credentials"
    credentials_path.write_text(f"hook-test:{password}", encoding="ascii")
    authorization = "Basic " + base64.b64encode(
        f"hook-test:{password}".encode("ascii")
    ).decode("ascii")
    # Let the OS select a free loopback port. A bind race remains possible between
    # closing this reservation and Kea starting; a collision fails the test.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    def send(name, arguments=None):
        return command(port, name, arguments, authorization=authorization)

    config_path = directory / "kea.json"
    config: dict[str, Any] = {
        "Dhcp4": {
            "interfaces-config": {"interfaces": []},
            "lease-database": {"type": "memfile", "persist": False},
            "valid-lifetime": 600,
            "subnet4": [],
            "control-sockets": [
                {
                    "socket-type": "http",
                    "socket-address": "127.0.0.1",
                    "socket-port": port,
                    "authentication": {
                        "type": "basic",
                        "realm": "hook-lifecycle-test",
                        "clients": [{"password-file": str(credentials_path)}],
                    },
                }
            ],
            "multi-threading": {"enable-multi-threading": multithreading},
            "hooks-libraries": [{"library": str(hook)}],
            "loggers": [
                {
                    "name": "kea-dhcp4",
                    "severity": "INFO",
                    "output-options": [{"output": "stdout"}],
                }
            ],
        }
    }

    def save():
        config_path.write_text(json.dumps(config), encoding="utf-8")

    save()
    environment = os.environ.copy()
    environment.update(
        KEA_PIDFILE_DIR=str(directory),
        KEA_LOCKFILE_DIR=str(directory),
        KEA_HOOKS_PATH=str(hook.parent),
    )
    log_path = directory / "server.log"
    server_command = [str(server)]
    process = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            subprocess.run(
                [*server_command, "-T", str(config_path)],
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=environment,
                cwd=directory,
                timeout=20,
            )
            process = subprocess.Popen(
                [*server_command, "-d", "-c", str(config_path)],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=environment,
                cwd=directory,
            )
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise AssertionError("Kea exited during startup")
                try:
                    names = require_success(send("list-commands"))
                    break
                except (OSError, ValueError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            if DIAGNOSTIC not in names:
                raise AssertionError("Diagnostic command was not registered")
            if SUBNET_LIST not in names:
                raise AssertionError("Subnet list command was not registered")
            assert "cb-subnet4-set" in names
            assert not any(name.startswith("remote-") for name in names)
            if mutation_admission:
                registered = RECORD_COMMANDS + OPTION_COMMANDS + SHARED_NETWORK_COMMANDS
                assert set(registered) <= set(names), names
                verify_denied(send)
                config["Dhcp4"]["hooks-libraries"][0]["parameters"] = {"allow-mutations": True}
                save()
                require_success(send("config-reload"))
                assert require_success(send(DIAGNOSTIC))["allow-mutations"] is True
                verify_argument_contracts(send)
            for name in ("cb-subnet4-get", "cb-subnet4-del"):
                assert name in names
                arguments: Any = {"id": 900}
                if name.endswith("-del"):
                    arguments.update({"server-tag": "all", "preserve-leases": True})
                assert send(name, arguments)["text"] == (
                    "Subnet lookup/deletion requires exactly one configured SQL backend.")
                for invalid in (None, {}, [], {"unexpected": True}):
                    assert send(name, invalid)["result"] == 1
            valid_set = {"server-tag": "all", "subnet4": {
                "id": 900, "subnet": "198.18.0.0/24", "valid-lifetime": 600}}
            assert send("cb-subnet4-set", valid_set)["text"] == (
                "cb-subnet4-set requires exactly one configured SQL backend.")
            for arguments in (None, {}, {"unexpected": True}, []):
                assert send("cb-subnet4-set", arguments)["result"] == 1
            for arguments in (None, {}, {"unexpected": True}, []):
                if send(SUBNET_LIST, arguments)["result"] != 1:
                    raise AssertionError("Missing backend or invalid arguments were accepted")
            for arguments in (None, {}):
                result = require_success(send(DIAGNOSTIC, arguments))
                if (
                    result["configuration-backend-pool-accessible"] is not True
                    or result["database-connectivity-tested"] is not False
                    or result["mutations-supported"] is not True
                    or result["kea-hooks-version"] not in (30201, 30004)
                ):
                    raise AssertionError(result)
            if send(DIAGNOSTIC, {"unexpected": True})["result"] != 1:
                raise AssertionError("Invalid diagnostic arguments were accepted")

            config["Dhcp4"]["hooks-libraries"] = []
            save()
            require_success(send("config-reload"))
            assert "cb-subnet4-set" not in require_success(send("list-commands"))
            if mutation_admission:
                for name in RECORD_COMMANDS + OPTION_COMMANDS + SHARED_NETWORK_COMMANDS:
                    assert name not in require_success(send("list-commands"))
                    assert send(name)["result"] == 2
            for name in ("cb-subnet4-get", "cb-subnet4-del"):
                assert name not in require_success(send("list-commands"))
                assert send(name)["result"] == 2
            if DIAGNOSTIC in require_success(send("list-commands")):
                raise AssertionError("Command remained registered after unload")
            if SUBNET_LIST in require_success(send("list-commands")):
                raise AssertionError("Subnet list remained registered after unload")
            if send(DIAGNOSTIC)["result"] != 2:
                raise AssertionError("Unloaded command did not become unsupported")
            config["Dhcp4"]["hooks-libraries"] = [{"library": str(hook)}]
            save()
            require_success(send("config-reload"))
            require_success(send(DIAGNOSTIC))
            if mutation_admission:
                verify_denied(send)
                for parameters in ({"allow-mutations": False}, {}, {"allow-mutations": True}):
                    config["Dhcp4"]["hooks-libraries"][0]["parameters"] = parameters
                    save()
                    require_success(send("config-reload"))
                    if parameters.get("allow-mutations", False):
                        assert require_success(send(DIAGNOSTIC))["allow-mutations"] is True
                    else:
                        verify_denied(send)
                # Kea owns failed-load cleanup. Remove the writer first, then reject
                # invalid candidates and reload an omitted/false role in this process.
                config["Dhcp4"]["hooks-libraries"] = []
                save()
                require_success(send("config-reload"))
                invalid_parameters = [
                    {"allow-mutations": value} for value in
                    ("true", "false", 0, 1, 1.5, None, [], {})
                ] + [{"unknown": True}, {"allow-mutations": True, "unknown": False},
                     None, [], "true", False, 1]
                for parameters in invalid_parameters:
                    config["Dhcp4"]["hooks-libraries"] = [
                        {"library": str(hook), "parameters": parameters}]
                    save()
                    assert send("config-reload")["result"] == 1
                    assert "cb-subnet4-set" not in require_success(send("list-commands"))
                config["Dhcp4"]["hooks-libraries"] = [{"library": str(hook)}]
                save()
                require_success(send("config-reload"))
                verify_denied(send)
            assert "cb-subnet4-set" in require_success(send("list-commands"))
            for name in ("cb-subnet4-get", "cb-subnet4-del"):
                assert name in require_success(send("list-commands"))
            if send(SUBNET_LIST)["result"] != 1:
                raise AssertionError("Missing backend error changed after reload")
            require_success(send("shutdown"))
            if process.wait(timeout=10) != 0:
                raise AssertionError("Kea shutdown failed")
    except Exception:
        print(log_path.read_text(encoding="utf-8", errors="replace"))
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, type=Path)
    parser.add_argument("--hook", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    for multithreading in (False, True):
        with tempfile.TemporaryDirectory(
            prefix="t", dir=args.work_dir.resolve()
        ) as directory:
            run_case(
                args.server.resolve(),
                args.hook.resolve(),
                Path(directory),
                multithreading,
            )
    print(
        "PASS: validation, commands, reload, unload, and shutdown in both threading modes"
    )


if __name__ == "__main__":
    main()
