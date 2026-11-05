"""One isolated local experiment using the project's own interpreter."""
from __future__ import annotations

import asyncio
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import importlib
import io
import json
from pathlib import Path
import sys
from uuid import uuid4

from .model import FixtureModel, OCIModel
from .boundary_trace import BoundaryTrace
from .cases import validate_case
from .diagnostics import failure_details
from .project import FlowError, contained, load_project, redact
from .services import RecordedServices


def _json_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_json_equal(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_json_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _contains(value, expected):
    if isinstance(value, list):
        return any(_json_equal(item, expected) for item in value)
    return isinstance(value, (str, dict)) and isinstance(expected, str) and expected in value


def assertion_results(output, assertions):
    verdicts = []
    for assertion in assertions:
        value, exists = output, True
        for key in assertion["path"].split("."):
            if not isinstance(value, dict) or key not in value:
                exists = False
                break
            value = value[key]
        if "equals" in assertion:
            passed = exists and _json_equal(value, assertion["equals"])
        elif "contains" in assertion:
            passed = exists and _contains(value, assertion["contains"])
        elif "not_empty" in assertion:
            passed = exists and bool(value) == assertion["not_empty"]
        else:
            raise FlowError("Unknown assertion; supported: equals, contains, not_empty")
        verdicts.append({"path": assertion["path"], "passed": passed})
    return verdicts


async def _observe_frontier(graph, invocation, progress):
    if not getattr(graph, "checkpointer", None) or not callable(getattr(graph, "aget_state", None)):
        return False
    snapshot = await graph.aget_state(invocation)
    progress["frontier"]["observed"] = list(snapshot.next)
    progress["frontier"]["snapshot_supported"] = True
    return any(getattr(task, "interrupts", ()) for task in snapshot.tasks)


async def _execute(graph, case, invocation, progress, trace=None):
    progress["stage"] = "execution"
    progress["frontier"] = {"expected": [case["stop_before"]] if case.get("stop_before") else [],
                            "observed": None, "snapshot_supported": False}
    progress["stop_reason"] = "error"
    try:
        await _stream_execution(graph, case, invocation, progress, trace)
    except Exception:
        progress["stop_reason"] = "error"
        try:
            await _observe_frontier(graph, invocation, progress)
        except Exception:
            pass  # Snapshot inspection must not replace the original execution failure.
        raise
    finally:
        if trace is not None:
            trace.finish(progress.get("output", {}))


async def _stream_execution(graph, case, invocation, progress, trace):
    if case.get("node"):
        progress["output"] = await graph.nodes[case["node"]].ainvoke(case["input"], invocation)
        progress["visited_nodes"].append(case["node"])
        progress["stop_reason"] = "node_completed"
        if trace is not None:
            trace.completed(case["node"], progress["output"])
        return
    value = case["input"]
    if (case.get("start_after") or case.get("stop_before")) and not getattr(graph, "checkpointer", None):
        raise FlowError("Partial execution requires the factory to use the supplied checkpointer")
    if case.get("start_after"):
        await graph.aupdate_state(invocation, value, as_node=case["start_after"])
        value = None
    kwargs = {"stream_mode": ["updates", "values"]}
    if case.get("stop_before"):
        kwargs["interrupt_before"] = [case["stop_before"]]
    interrupted = await _consume_events(graph.astream(value, invocation, **kwargs), progress, trace)
    interrupted = await _observe_frontier(graph, invocation, progress) or interrupted
    progress["stop_reason"] = _stop_reason(case, progress, interrupted)


async def _consume_events(events, progress, trace):
    interrupted = False
    async for kind, event in events:
        if kind == "values":
            progress["output"] = event
        elif kind == "updates":
            interrupted = interrupted or bool(event.get("__interrupt__"))
            for node, update in event.items():
                if node != "__interrupt__":
                    progress["visited_nodes"].append(node)
                    if trace is not None:
                        trace.completed(node, update)
    return interrupted


def _stop_reason(case, progress, interrupted):
    observed = progress["frontier"]["observed"]
    if interrupted:
        return "dynamic_interrupt"
    if not case.get("stop_before"):
        return "other_frontier" if observed else "completed"
    if observed is None:
        raise FlowError("Partial execution requires checkpoint frontier inspection")
    if case["stop_before"] in observed and case["stop_before"] not in progress["visited_nodes"]:
        return "requested_stop_before"
    return "other_frontier" if observed else "terminal_before_requested"


def _verdicts(case, progress, model):
    verdicts = assertion_results(progress["output"], case.get("assertions", []))
    if case.get("stop_before"):
        verdicts.append({"path": "stop_before", "passed": progress["stop_reason"] == "requested_stop_before"})
    elif progress["stop_reason"] not in ("completed", "node_completed"):
        verdicts.append({"path": "execution_completed", "passed": False})
    expected = case.get("expected_nodes")
    if expected is not None:
        verdicts.append({"path": "visited_nodes", "passed": progress["visited_nodes"] == expected})
    if case.get("require_model_call"):
        verdicts.append({"path": "completed_model_responses", "passed": model.completed_responses > 0})
    return verdicts


async def experiment(job, progress=None):
    from langgraph.checkpoint.memory import InMemorySaver
    case = job["case"]
    progress = {} if progress is None else progress
    progress.update(stage="validate_case", visited_nodes=[], model_calls=0, completed_model_responses=0, service_calls=[],
                    native_test_accepted=False)
    model, services = None, None
    try:
        validate_case(case)
        progress.update(case_id=case["id"], mode="local_real_oci_model" if job["real"] else "local_fixture_model",
                        selection={key: case[key] for key in ("node", "start_after", "stop_before") if key in case},
                        checkpointer_scope="bypassed_by_node" if case.get("node") else "in_memory_local_only")
        progress["stage"] = "load_project"
        root, config = load_project(job["project"])
        sys.path.insert(0, str(contained(root, config["agent"]["python_path"])))
        oci_config = Path(config.get("oci", {}).get("config_file", ".oci/config")).expanduser()
        if not oci_config.is_absolute():
            oci_config = root / oci_config
        progress["stage"] = "model_setup"
        model = (OCIModel(oci_config, config.get("oci", {}).get("profile", "DEFAULT"), config.get("model", {}))
                 if job["real"] else FixtureModel(case.get("model_responses", ["Recorded fixture response"])))
        progress["stage"] = "services_setup"
        services = RecordedServices(case.get("service_records", []))
        runtime = {"model": model, "services": services, "checkpointer": InMemorySaver(), "external_effects_allowed": False}
        if case.get("clock_at"):
            fixed_time = datetime.fromisoformat(case["clock_at"].replace("Z", "+00:00"))
            runtime["clock"] = lambda: fixed_time
        else:
            runtime["clock"] = lambda: datetime.now(timezone.utc)
        module, function = config["agent"]["factory"].split(":")
        progress["stage"] = "factory"
        graph = getattr(importlib.import_module(module), function)(runtime)
        if getattr(graph, "checkpointer", None) not in (None, runtime["checkpointer"]):
            raise FlowError("Local factory must use the supplied test checkpointer, not a managed or shared checkpoint")
        invocation = {"configurable": {"thread_id": uuid4().hex}, "recursion_limit": job["max_steps"]}
        progress["output"] = {}
        trace = BoundaryTrace(case["input"]) if case.get("trace_boundaries") else None
        if trace is not None:
            progress["boundary_trace"] = trace.data
        await _execute(graph, case, invocation, progress, trace)
        progress["stage"] = "assertions"
        verdicts = _verdicts(case, progress, model)
        progress["assertions"] = verdicts
        if isinstance(model, FixtureModel):
            progress["stage"] = "model_contract"
            model.assert_recorded_calls()
        else:
            progress["stage"] = "model_contract"
            model.assert_complete()
        progress["stage"] = "service_contract"
        services.assert_consumed()
        passed = all(item["passed"] for item in verdicts)
        progress.update(passed=passed, model_cost="unknown", stage="complete",
                        failure_stage=None if passed else "assertions")
        if not passed:
            progress.pop("output", None)
            progress.update(failure_details(None, "assertions", real=job["real"]))
        return progress
    finally:
        progress.update(model_calls=model.calls if model is not None else 0,
                        completed_model_responses=getattr(model, "completed_responses", 0),
                        model_response_metadata=getattr(model, "response_metadata", []) if model is not None else [],
                        service_calls=services.calls if services is not None else [],
                        last_completed_node=next(reversed(progress["visited_nodes"]), None))
        if model is not None and callable(getattr(model, "close", None)):
            model.close()


def main():
    job = json.load(sys.stdin)
    progress = {}
    try:
        # Agent debug output is not a safe JSON protocol and may contain secrets.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = asyncio.run(experiment(job, progress))
        result = json.loads(json.dumps(result, default=lambda item: item.model_dump(mode="json")))
        print(json.dumps({"ok": True, "result": redact(result)}, ensure_ascii=False))
    except Exception as error:
        # Keep safe progress, not intermediate business output or provider exceptions.
        progress.pop("output", None)
        progress.update(passed=False, failure_stage=progress.get("stage"))
        progress.setdefault("stop_reason", "error")
        progress.update(failure_details(error, progress.get("stage"), real=job.get("real", False)))
        print(json.dumps(redact({"ok": False, "error_type": type(error).__name__,
                          "message": "Local agent execution failed; inspect the failure code and stage",
                          "result": progress})))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
