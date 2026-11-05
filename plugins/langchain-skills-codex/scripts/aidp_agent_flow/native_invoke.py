"""One explicitly selected native invocation with a protected, stable case ID."""

import hashlib
from datetime import datetime
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from . import __version__
from .identity import execution_identity
from .native_lifecycle import NativeLifecycle, _key, _read_json, _unlinked
from .project import FlowError, canonical_hash, private_json, redact


_MAX_BYTES = 2 * 1024 * 1024
_MAX_FRAME = 256 * 1024
_MAX_EVENTS = 512
_MAX_ANSWER = 20000


class _StreamFailure(Exception):
    pass


def _question(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise FlowError("Invocation question file must be relative to the selected project")
    path = root / path
    _unlinked(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise FlowError("Invocation question file escaped the selected project")
    try:
        with path.open("rb") as stream:
            data = stream.read(32769)
        value = json.loads(data) if len(data) <= 32768 else None
    except (OSError, ValueError):
        raise FlowError("Cannot read the bounded invocation question JSON") from None
    if (not isinstance(value, dict) or set(value) != {"id", "question"}
            or not isinstance(value["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value["id"])
            or not isinstance(value["question"], str) or not value["question"].strip() or len(value["question"]) > 4000):
        raise FlowError("Question JSON requires a stable nonsecret id and a nonempty question of at most 4000 characters")
    try:
        value["question"].encode("utf-8")
    except UnicodeError:
        raise FlowError("Invocation question must contain valid UTF-8 text") from None
    return value


def _native_region(lifecycle):
    def canonical(region):
        if not isinstance(region, str) or not re.fullmatch(r"[a-z][a-z0-9-]+", region):
            return None
        if "-" in region:
            return region
        from oci.regions import REGIONS_SHORT_NAMES
        return REGIONS_SHORT_NAMES.get(region)

    host = urlsplit(lifecycle.base).hostname or ""
    match = re.fullmatch(r"(?:aidp|datalake)\.([a-z][a-z0-9-]+)\.oci\.oraclecloud\.com", host)
    endpoint_region = canonical(match[1]) if match else None
    platform = lifecycle.config.get("native", {}).get("platform_id") or urlsplit(lifecycle.base).path.rsplit("/", 1)[-1]
    pieces = platform.split(".") if isinstance(platform, str) else []
    platform_region = canonical(pieces[3]) if len(pieces) >= 5 and pieces[0] == "ocid1" and pieces[3] else None
    if endpoint_region and platform_region and endpoint_region != platform_region:
        raise FlowError("Native endpoint and platform OCID regions disagree")
    if not (endpoint_region or platform_region):
        raise FlowError("Cannot establish the approved native invocation region")
    return endpoint_region or platform_region


def _endpoint(lifecycle, rows, surface):
    region = _native_region(lifecycle)
    expected_host = "gateway.aidp." + region + ".oci.oraclecloud.com"
    expected_path = "/agentendpoint/" + _key(lifecycle.agent_key) + ("_TEST" if surface == "TEST" else "") + "/chat"
    active = [row for row in rows if row.get("lifecycleState") == "ACTIVE"]
    if not active:
        raise FlowError("The selected native surface has no ACTIVE deployment")
    endpoints = set()
    for row in active:
        endpoint = row.get("endpointUrl") or row.get("uri")
        try:
            parsed = urlsplit(endpoint or "")
            valid = (parsed.scheme == "https" and parsed.hostname == expected_host and parsed.path == expected_path
                     and not parsed.username and not parsed.password and not parsed.port and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise FlowError("Deployment endpoint does not match the approved native gateway, agent and surface")
        endpoints.add(endpoint)
    if len(endpoints) != 1:
        raise FlowError("ACTIVE deployment endpoints are ambiguous")
    selected = active[0]
    if len(active) > 1:
        try:
            dated = [(datetime.fromisoformat(row["timeCreated"].replace("Z", "+00:00")), row) for row in active]
            if any(created.tzinfo is None for created, _ in dated):
                raise ValueError("Missing timezone")
            latest = max(created for created, _ in dated)
            candidates = [row for created, row in dated if created == latest]
        except (KeyError, TypeError, ValueError, AttributeError):
            raise FlowError("Retained ACTIVE deployments need valid creation times to select the latest revision") from None
        if len(candidates) != 1:
            raise FlowError("The latest ACTIVE deployment creation time is ambiguous")
        selected = candidates[0]
    return next(iter(endpoints)), selected


def _claim_case(artifact, record):
    if not artifact.exists():
        private_json(artifact, record)
        return
    prior = _read_json(artifact)
    identity = ("target", "workspace", "agent_key", "surface", "case_id")
    if any(prior.get(key) != record[key] for key in identity):
        raise FlowError("This native invocation case is already recorded with a different target identity")
    if prior.get("question_sha256") != record["question_sha256"]:
        raise FlowError("This native invocation case is already recorded with a different frozen question")
    if (prior.get("state") != "RESPONDED" or prior.get("error_count") != 0
            or prior.get("failure") is not None or prior.get("stream_complete") is not True):
        raise FlowError("This native invocation case is already recorded with an uncertain response; reconcile before another paid start")
    if not prior.get("deployment_key"):
        raise FlowError("The prior invocation receipt has no native deployment identity; reconcile before another start")
    previous = (prior["deployment_key"], prior.get("deployment_version"))
    current = (record["deployment_key"], record["deployment_version"])
    if previous == current:
        raise FlowError("This native invocation case is already recorded for the same deployment")
    history = artifact.parent / "history" / (canonical_hash(prior)[:32] + ".json")
    try:
        # Exclusive creation also claims this transition. A crash or competing
        # start after archiving requires reconciliation rather than a second POST.
        private_json(history, prior)
    except FileExistsError:
        raise FlowError("This invocation revision transition is already recorded; reconcile before another start") from None
    record["previous_receipt"] = "history/" + history.name
    private_json(artifact, record, overwrite=True)


def _event_error(event):
    pending, count, failed = [(event, 0)], 0, False
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 32 or count > 10000:
            raise _StreamFailure("event_limit")
        if isinstance(value, dict):
            for key, item in value.items():
                lower = key.lower()
                if ((lower in {"error", "errormessage", "error_message"} and bool(item))
                        or lower == "iserror" and item is True
                        or lower == "success" and item is False
                        or lower == "type" and isinstance(item, str) and ("error" in item.lower() or item.lower().endswith((".failed", ".incomplete", ".canceled", ".cancelled")))
                        or lower == "status" and item in ("failed", "canceled", "cancelled", "incomplete")):
                    failed = True
                pending.append((item, depth + 1))
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return failed


def _safe_event(value):
    if isinstance(value, dict):
        sensitive = {"authorization", "cookie", "token", "password", "privatekey", "private_key",
                     "secretvalue", "pass_phrase", "key_content", "headers", "context"}
        return {key: "[REDACTED]" if key.lower() in sensitive else _safe_event(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_event(item) for item in value]
    return redact(value)


def _answer(output):
    if not isinstance(output, list) or len(output) > 256:
        raise _StreamFailure("output_shape")
    parts = []
    length = 0
    for message in output:
        if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
            continue
        content = message.get("content", [])
        if not isinstance(content, list) or len(content) > 256:
            raise _StreamFailure("output_shape")
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if not isinstance(text, str):
                    raise _StreamFailure("output_shape")
                length += len(text)
                if length > _MAX_ANSWER:
                    raise _StreamFailure("answer_limit")
                parts.append(text)
    return "\n".join(parts)


def _consume(response, deadline, events):
    pending, data_lines, frame_bytes, total_bytes = bytearray(), [], 0, 0
    latest_output, errors, done, event_name, completion = None, 0, False, None, None

    def finish_event():
        nonlocal latest_output, errors, done, completion
        if not data_lines:
            if event_name:
                if len(events) >= _MAX_EVENTS:
                    raise _StreamFailure("event_limit")
                failed = "error" in event_name.lower() or event_name.lower().endswith((".failed", ".incomplete", ".canceled", ".cancelled"))
                errors += int(failed)
                events.append({"type": "stream_error" if failed else "sse_control", "sse_event": redact(event_name)})
            return
        data = b"\n".join(data_lines)
        if len(events) >= _MAX_EVENTS:
            raise _StreamFailure("event_limit")
        if data.strip() == b"[DONE]":
            done = True
            completion = "done"
            events.append({"type": "sse_done", "sse_event": redact(event_name)})
            return
        try:
            event = json.loads(data)
        except (ValueError, UnicodeError, RecursionError):
            raise _StreamFailure("invalid_event") from None
        if not isinstance(event, dict):
            raise _StreamFailure("invalid_event")
        framing_error = bool(event_name and ("error" in event_name.lower() or event_name.lower().endswith((".failed", ".incomplete", ".canceled", ".cancelled"))))
        failed = _event_error(event) or framing_error
        errors += int(failed)
        captured = {"type": "stream_error", "details": "[REDACTED]"} if failed else _safe_event(event)
        if event_name:
            captured["sse_event"] = redact(event_name)
        events.append(captured)
        returned = event.get("response")
        if not failed and isinstance(returned, dict) and "output" in returned:
            latest_output = returned["output"]
        status = returned.get("status") if isinstance(returned, dict) else None
        terminal = event.get("type") == "response.completed" or event_name == "response.completed" or status == "completed"
        if terminal and not failed:
            if status not in (None, "completed"):
                raise _StreamFailure("invalid_completion")
            completion = "response.completed" if event.get("type") == "response.completed" or event_name == "response.completed" else "response.status.completed"
            latest_output = returned.get("output", []) if isinstance(returned, dict) else []

    # Byte-sized reads let the elapsed-budget check observe even a peer that
    # trickles data without finishing an SSE line. The socket has a finite timeout.
    for chunk in response.iter_content(chunk_size=1):
        if time.monotonic() >= deadline:
            raise _StreamFailure("timeout")
        if not chunk:
            continue
        total_bytes += len(chunk)
        if total_bytes > _MAX_BYTES:
            raise _StreamFailure("byte_limit")
        for byte in chunk:
            if byte != 10:
                pending.append(byte)
                if len(pending) + frame_bytes > _MAX_FRAME:
                    raise _StreamFailure("frame_limit")
                continue
            line = bytes(pending).rstrip(b"\r")
            pending.clear()
            if not line:
                finish_event()
                data_lines, frame_bytes, event_name = [], 0, None
                if done:
                    break
            elif line.startswith(b"data:"):
                field = line[5:].removeprefix(b" ")
                data_lines.append(field)
                frame_bytes += len(field)
            elif line.startswith(b"event:"):
                try:
                    event_name = line[6:].strip().decode("utf-8")
                except UnicodeError:
                    raise _StreamFailure("invalid_event") from None
                if len(event_name) > 128:
                    raise _StreamFailure("frame_limit")
        if done:
            break
    if not done:
        if pending:
            tail = bytes(pending)
            if not tail.startswith(b"data:"):
                raise _StreamFailure("truncated_event")
            data_lines.append(tail[5:].removeprefix(b" ").rstrip(b"\r"))
        finish_event()
    if completion is None:
        raise _StreamFailure("incomplete_stream")
    return _answer(latest_output) if latest_output is not None else "", errors, completion


def invoke(lifecycle, question_file, *, surface="TEST", session_key=None, expected=None, timeout=90):
    """POST once to the selected agent; keep answers/events in a private artifact.

    Question JSON is ``{"id": "stable-case-id", "question": "..."}``.
    Expected substrings are assertions only and are never sent to the agent.
    """
    if not isinstance(surface, str) or surface not in {"TEST", "PROD"}:
        raise FlowError("Invocation surface must be explicitly TEST or PROD")
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 1 <= timeout <= 300:
        raise FlowError("Invocation timeout must be finite and between 1 and 300 seconds")
    expected = [] if expected is None else expected
    if (not isinstance(expected, list) or len(expected) > 20
            or any(not isinstance(item, str) or not item or len(item) > 200 for item in expected)):
        raise FlowError("Use at most 20 nonempty expected substrings of at most 200 characters")
    if surface == "PROD" and session_key is not None:
        raise FlowError("A TEST session cannot be supplied to a PROD invocation")
    case = _question(lifecycle.root, question_file)
    lifecycle._agent()
    deployments = lifecycle._deployments(surface)
    endpoint, selected = _endpoint(lifecycle, deployments, surface)
    deployment_snapshot = NativeLifecycle._snapshot(deployments)
    session_info = {}
    if surface == "TEST":
        session_key = session_key or lifecycle.state.get("test_session_key")
        if not session_key:
            raise FlowError("Create or select a validated TEST session before invoking")
        saved = lifecycle._session_info(_key(session_key), [selected])
        if saved["lifecycleState"] not in (None, "ACTIVE"):
            raise FlowError("The selected TEST session is not ACTIVE")
        session_info = {"session_binding_verified": True, "session_state": saved["lifecycleState"],
                        "session_state_reported": saved["lifecycleState"] is not None}
    identity = {"target": lifecycle.base, "workspace": lifecycle.workspace, "agent_key": lifecycle.agent_key,
                "surface": surface, "case_id": case["id"]}
    artifact = lifecycle.root / ".aidp-local/invocations" / (canonical_hash(identity)[:32] + ".json")
    _unlinked(artifact)
    receipt = lifecycle.state.get(surface.lower() + "_receipt", {})
    package_hash = receipt.get("package_sha256") if isinstance(receipt, dict) else None
    package_verified = (isinstance(package_hash, str) and re.fullmatch(r"[a-f0-9]{64}", package_hash) is not None
                        and receipt.get("deployments") == deployment_snapshot)
    executor = execution_identity(lifecycle.root)
    record = {**identity, "state": "SUBMITTED", "evaluator_version": __version__, **executor,
              "environment_identity_scope": "local_test_harness_not_native_runtime",
              "question_sha256": hashlib.sha256(case["question"].encode()).hexdigest(),
              "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(), "session_key": session_key,
              "expected": expected, "deployment_key": _key(selected["key"]),
              "deployment_version": selected.get("deploymentVersion"),
              "deployment_snapshot": deployment_snapshot,
              "package_sha256": package_hash if package_verified else None,
              "package_binding_verified": package_verified,
              "package_binding_reason": None if package_verified else "no_matching_reconciled_receipt", **session_info}
    _claim_case(artifact, record)
    headers = {"Accept": "text/event-stream", "Accept-Encoding": "identity", "x-deployment-type": surface}
    payload = {"isStreamEnabled": True, "input": [{"role": "user", "content": [{"type": "INPUT_TEXT", "text": case["question"]}]}], "metadata": {}}
    if surface == "TEST":
        headers["x-session-id"] = session_key
        payload.update(sessionId=session_key, session_id=session_key)
    response, events, answer, errors, failure, completion = None, [], "", 0, None, None
    deadline = time.monotonic() + timeout
    try:
        response = lifecycle._session().request("POST", endpoint, headers=headers, json=payload, stream=True,
            timeout=(5, max(0.001, deadline - time.monotonic())), allow_redirects=False)
        content_type = response.headers.get("Content-Type", response.headers.get("content-type", "")).split(";", 1)[0].strip().lower()
        if response.status_code != 200 or content_type != "text/event-stream":
            raise _StreamFailure("http_or_content_type")
        answer, errors, completion = _consume(response, deadline, events)
    except _StreamFailure as error:
        failure = str(error)
    except Exception:
        failure = "transport_or_stream_failure"
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                failure = "stream_close_failure"
    errors = max(errors, sum(event.get("type") == "stream_error" for event in events))
    if errors and failure is None:
        failure = "stream_error"
    try:
        if NativeLifecycle._snapshot(lifecycle._deployments(surface)) != deployment_snapshot:
            record.update(package_sha256=None, package_binding_verified=False,
                          package_binding_reason="deployment_changed_during_invocation")
    except Exception:
        record.update(package_sha256=None, package_binding_verified=False,
                      package_binding_reason="deployment_readback_unavailable")
    assertions = [{"index": index, "passed": fragment in answer} for index, fragment in enumerate(expected)]
    passed = bool(answer.strip()) and not errors and failure is None and all(item["passed"] for item in assertions)
    record.update(state="UNCERTAIN" if failure else "RESPONDED", passed=passed, events=events,
                  answer=redact(answer), assertions=assertions, error_count=errors, failure=failure,
                  stream_complete=completion is not None, completion_marker=completion)
    private_json(artifact, record, overwrite=True)
    return {"case_id": case["id"], "surface": surface, "passed": passed, "assertions": assertions,
            "evaluator_version": __version__, **executor,
            "event_count": len(events), "error_count": errors, "failure": failure, "artifact": str(artifact),
            "stream_complete": completion is not None,
            "deployment_key": record["deployment_key"], "deployment_version": record["deployment_version"],
            "package_binding_verified": record["package_binding_verified"],
            "package_binding_reason": record["package_binding_reason"],
            "native_test_accepted": False, "semantic_review_required": True, **session_info}
