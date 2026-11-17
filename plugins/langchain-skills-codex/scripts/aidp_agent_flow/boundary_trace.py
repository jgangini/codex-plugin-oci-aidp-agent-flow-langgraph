"""Bounded, value-free observations of completed local graph updates."""
import hashlib
import json
from itertools import islice
import math
import time


class _Untraceable(ValueError):
    pass


def _scalar_size(value):
    if type(value) is str:
        return len(value) * 6  # Conservative bound for JSON escaping.
    if value is None or type(value) is bool:
        return 0
    if type(value) is int and value.bit_length() <= 4096:
        return 2 + value.bit_length() // 3
    if type(value) is float and math.isfinite(value):
        return 32
    raise _Untraceable()


def _children(value, budget):
    if type(value) is dict:
        if len(value) * 2 > budget or any(type(key) is not str for key in value):
            raise _Untraceable()
        return [part for pair in value.items() for part in pair]
    if type(value) in (list, tuple):
        if len(value) > budget:
            raise _Untraceable()
        return value
    return None


def _bounded_json(value, limit):
    pending, items = [(value, 0)], 1024
    while pending:
        item, depth = pending.pop()
        items -= 1
        limit -= 8
        if depth > 16 or items < 0 or limit < 0:
            raise _Untraceable()
        children = _children(item, items - len(pending))
        if children is None:
            limit -= _scalar_size(item)
        else:
            pending.extend((child, depth + 1) for child in children)
    if limit < 0:
        raise _Untraceable()
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


class BoundaryTrace:
    MAX_NODES = 64
    MAX_FIELDS = 32
    MAX_FIELD_BYTES = 65536
    MAX_TOTAL_BYTES = 262144

    def __init__(self, value):
        self.remaining = self.MAX_TOTAL_BYTES
        self.last_event = time.monotonic()
        self.data = {"format": "sha256-canonical-json-v1", "nodes": [], "nodes_truncated": False,
                     "input": self.fields(value)}

    def digest(self, value):
        try:
            encoded = _bounded_json(value, min(self.MAX_FIELD_BYTES, self.remaining))
        except _Untraceable:
            return {"status": "omitted_unsupported_or_limit"}
        self.remaining -= len(encoded)
        return {"sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded)}

    def fields(self, value):
        if type(value) is not dict:
            return {"fields": {}, "status": "omitted_non_object"}
        fields = {}
        for key in islice(value, self.MAX_FIELDS):
            if type(key) is str and len(key) <= 128:
                fields[key] = self.digest(value[key])
        return {"fields": fields, "fields_truncated": len(fields) != len(value)}

    def completed(self, node, update):
        now = time.monotonic()
        elapsed, self.last_event = now - self.last_event, now
        if len(self.data["nodes"]) >= self.MAX_NODES:
            self.data["nodes_truncated"] = True
            return
        self.data["nodes"].append({"node": node, "wall_seconds_since_previous_event": elapsed,
                                   "update": self.fields(update)})

    def finish(self, value):
        self.data["output"] = self.fields(value)
