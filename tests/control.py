"""Bounded clients for Kea's JSON control interfaces."""

# SPDX-License-Identifier: MPL-2.0
import json
from http.client import HTTPConnection
from collections.abc import Callable
from typing import Any

# Command arguments are heterogeneous JSON, including malformed negative-test inputs.
Response = dict[str, Any]

MAX_RESPONSE = 1024 * 1024


def receive_response(read: Callable[[int], bytes], limit: int = MAX_RESPONSE) -> Response:
    data = bytearray()
    decoder = json.JSONDecoder()
    while True:
        chunk = read(min(4096, limit + 1 - len(data)))
        if not chunk:
            raise ValueError("Control socket closed before a complete response")
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError("Control response exceeds the size limit")
        try:
            value, end = decoder.raw_decode(data.decode("utf-8").lstrip())
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if data.decode("utf-8").lstrip()[end:].strip():
            raise ValueError("Unexpected trailing control response data")
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, dict) or not isinstance(value.get("result"), int):
            raise TypeError("Expected a native Kea command response object")
        return value


def command(port: int, name: str, arguments: Any = None, *, authorization: str) -> Response:
    request: dict[str, Any] = {"command": name}
    if arguments is not None:
        request["arguments"] = arguments
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            "/",
            json.dumps(request),
            {"Content-Type": "application/json", "Authorization": authorization},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("Invalid HTTP control response status")
        return receive_response(response.read1)
    finally:
        connection.close()
