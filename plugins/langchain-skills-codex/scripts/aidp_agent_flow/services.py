"""Offline, consume-once results for project-owned MCP, RAG and table tools."""

import asyncio
from collections import defaultdict, deque
import json
import math
import re

from .project import FlowError


class ServiceError(FlowError):
    """A safe-to-display recorded-service failure."""


_KINDS = {"mcp", "rag", "table"}
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_ERROR_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")
_MAX_RECORDS = 1000
_MAX_CALLS = 1000
_MAX_RECORD_BYTES = 1024 * 1024
_MAX_TOTAL_BYTES = 8 * 1024 * 1024
_MAX_DEPTH = 32
_MAX_NODES = 100000


def _json_bytes(value):
    """Validate plain JSON data before making a bounded canonical snapshot."""
    pending = [(value, 0)]
    visited, raw_bytes = 0, 0
    try:
        while pending:
            current, depth = pending.pop()
            visited += 1
            if depth > _MAX_DEPTH or visited > _MAX_NODES:
                raise ServiceError("Recorded service data exceeds the nesting or item limit.")
            kind = type(current)
            if kind is str:
                if len(current) > _MAX_RECORD_BYTES:
                    raise ServiceError("Recorded service data exceeds the size limit.")
                raw_bytes += len(current.encode("utf-8"))
            elif kind is dict:
                if len(current) > _MAX_NODES - visited:
                    raise ServiceError("Recorded service data exceeds the item limit.")
                for key, item in current.items():
                    if type(key) is not str:
                        raise ServiceError("Recorded service data must contain only JSON objects with string keys.")
                    if len(key) > _MAX_RECORD_BYTES:
                        raise ServiceError("Recorded service data exceeds the size limit.")
                    raw_bytes += len(key.encode("utf-8"))
                    pending.append((item, depth + 1))
            elif kind is list:
                if len(current) > _MAX_NODES - visited:
                    raise ServiceError("Recorded service data exceeds the item limit.")
                pending.extend((item, depth + 1) for item in current)
            elif kind is float:
                if not math.isfinite(current):
                    raise ServiceError("Recorded service data must contain finite JSON numbers.")
            elif current is not None and kind not in (bool, int):
                raise ServiceError("Recorded service data must contain only plain JSON values.")
            if raw_bytes > _MAX_RECORD_BYTES:
                raise ServiceError("Recorded service data exceeds the size limit.")
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise ServiceError("Recorded service data is not supported JSON.") from None
    if len(encoded) > _MAX_RECORD_BYTES:
        raise ServiceError("Recorded service data exceeds the size limit.")
    return encoded


def _identity(kind, name, arguments):
    if type(kind) is not str or kind not in _KINDS:
        raise ServiceError("Recorded service kind must be mcp, rag or table.")
    if type(name) is not str or not _NAME.fullmatch(name):
        raise ServiceError("Recorded service name must use 1 to 128 letters, digits, underscores, dots or hyphens.")
    if type(arguments) is not dict:
        raise ServiceError("Recorded service arguments must be a JSON object.")
    return kind, name, _json_bytes(arguments)


class RecordedServices:
    """Replay frozen tool outcomes without connecting to any external service.

    Matching ignores object key order but preserves JSON types and array order.
    Identical input records are consumed in fixture order. A configured error
    is consumed once and raises ServiceError without exposing its raw message.
    Instances are intended for one graph run on one asyncio event loop.
    """

    def __init__(self, records):
        if type(records) is not list or len(records) > _MAX_RECORDS:
            raise ServiceError("Recorded services require a JSON list of at most 1000 records.")
        self._records = []
        self._pending = defaultdict(deque)
        self._calls = []
        self._contract_failed = False
        self._loop = None
        total_bytes = 0
        for index, original in enumerate(records):
            encoded = _json_bytes(original)
            total_bytes += len(encoded)
            if total_bytes > _MAX_TOTAL_BYTES:
                raise ServiceError("Recorded services exceed the total fixture size limit.")
            record = json.loads(encoded)
            if (type(record) is not dict
                    or not {"kind", "name", "arguments"}.issubset(record)
                    or set(record) - {"kind", "name", "arguments", "result", "error"}
                    or ("result" in record) == ("error" in record)):
                raise ServiceError("Each recorded service requires kind, name, arguments and exactly one result or error.")
            identity = _identity(record["kind"], record["name"], record["arguments"])
            if "error" in record:
                error = record["error"]
                if (type(error) is not dict or set(error) - {"code", "message"}
                        or type(error.get("code")) is not str or not _ERROR_CODE.fullmatch(error["code"])
                        or ("message" in error and type(error["message"]) is not str)):
                    raise ServiceError("Recorded service errors require a nonsecret code and an optional message.")
                outcome = None
            else:
                outcome = _json_bytes(record["result"])
            self._records.append(("error" in record, outcome))
            self._pending[identity].append(index)

    @property
    def calls(self):
        """Metadata snapshot; arguments, results and provider messages are omitted."""
        return [dict(call) for call in self._calls]

    async def call(self, kind, name, arguments):
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            self._contract_failed = True
            raise ServiceError("A recorded service instance cannot be shared between event loops.")
        self._loop = loop
        if len(self._calls) >= _MAX_CALLS:
            self._contract_failed = True
            raise ServiceError("Recorded service call count exceeds the limit.")
        try:
            identity = _identity(kind, name, arguments)
        except ServiceError:
            self._contract_failed = True
            raise
        queue = self._pending.get(identity)
        if not queue:
            self._calls.append({"kind": kind, "name": name, "status": "unmatched", "record_index": None})
            raise ServiceError("No unconsumed recorded service matches this call; no live request was made.")
        # No await occurs between matching and consumption, so concurrent tasks
        # on the owning loop cannot consume the same fixture record.
        index = queue.popleft()
        is_error, outcome = self._records[index]
        self._calls.append({"kind": kind, "name": name, "status": "error" if is_error else "ok", "record_index": index})
        if is_error:
            raise ServiceError("Recorded service returned its configured error; no retry was attempted.")
        return json.loads(outcome)

    def assert_consumed(self):
        """Require the expected calls and reject caught fixture-contract violations."""
        if any(self._pending.values()):
            raise ServiceError("The run left recorded service results unconsumed.")
        if self._contract_failed or any(call["status"] == "unmatched" for call in self._calls):
            raise ServiceError("The run made an unexpected recorded service call.")
