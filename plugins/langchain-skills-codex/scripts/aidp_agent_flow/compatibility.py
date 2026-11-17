"""Offline runtime observations and the documented Oracle LangGraph profile."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from .project import FlowError


PROFILE = {
    "id": "oracle-aidp-langgraph-1.0.1",
    "langgraph": "1.0.1",
    "source_url": "https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html",
    "reviewed_on": "2026-11-02",
    "claim": "Oracle documentation lists LangGraph 1.0.1 as supported; this is not a plugin certification",
}
MANAGED_PROFILE = {
    "id": "aidp-managed-1.2.4",
    "langgraph": "1.2.4",
    "packages": {"langgraph": "1.2.4", "langgraph-checkpoint": "4.1.1", "langgraph-prebuilt": "1.1.0"},
    "reviewed_on": "2026-11-08",
    "claim": "Observed managed target requirements; verify each tenant; not universal Oracle certification",
}


def select_profile(name=None, langgraph_version=None, *, new_project=False):
    if name is None:
        name = (MANAGED_PROFILE["id"] if new_project else PROFILE["id"]) if langgraph_version is None else (
            PROFILE["id"] if langgraph_version == "1.0.1" else MANAGED_PROFILE["id"] if langgraph_version == "1.2.4" else "custom")
    if name == "custom":
        if not isinstance(langgraph_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", langgraph_version):
            raise FlowError("A custom runtime profile requires an exact LangGraph version")
        return {"id": "custom", "langgraph": langgraph_version, "packages": {"langgraph": langgraph_version},
                "claim": "Explicit project version; not Oracle certification"}
    if name not in (PROFILE["id"], MANAGED_PROFILE["id"]):
        raise FlowError("Unknown runtime profile")
    selected = dict(MANAGED_PROFILE if name == MANAGED_PROFILE["id"] else PROFILE)
    selected.setdefault("packages", {"langgraph": selected["langgraph"]})
    if langgraph_version is not None and langgraph_version != selected["langgraph"]:
        raise FlowError("LangGraph version contradicts the selected runtime profile")
    return selected


def selected_status(local, profile):
    if local["status"] != "observed":
        return "unknown"
    actual = local["packages"]
    if any(actual.get(name) is None for name in profile["packages"]):
        return "unknown"
    return "target_match" if all(actual[name] == version for name, version in profile["packages"].items()) else "target_mismatch"


SHARED_PACKAGES = ("langgraph", "langchain-core", "langgraph-checkpoint", "oci")
PACKAGES = (*SHARED_PACKAGES, "aidputils", "langgraph-prebuilt", "langchain", "aidp-agent-runtime", "aidp-utils")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+!_-]{0,79}\Z")
_PYTHON = re.compile(r"(\d+)\.(\d+)(?:\.\d+)?\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def documented_status(langgraph_version):
    if langgraph_version is None:
        return "missing"
    return "documented_match" if langgraph_version == PROFILE["langgraph"] else "outside_documented_profile"


def _versions(value):
    if not isinstance(value, dict) or set(value) - set(PACKAGES):
        raise FlowError("Runtime packages must use the documented distribution names")
    if any(item is not None and (not isinstance(item, str) or not _VERSION.fullmatch(item))
           for item in value.values()):
        raise FlowError("Runtime package versions must be version strings or null")
    return {name: value.get(name) for name in PACKAGES}


def _python(value):
    if value is not None and (not isinstance(value, str) or not _PYTHON.fullmatch(value)):
        raise FlowError("Runtime Python must be a numeric version string or null")
    return value


def observe_local(executable):
    """Read metadata in the selected environment without importing agent code."""
    unknown = {"status": "unavailable", "python": None, "packages": dict.fromkeys(PACKAGES)}
    if executable is None or not Path(executable).is_file():
        return unknown
    code = """import importlib.metadata,json,platform
packages={}
for name in %r:
    try: packages[name]=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: packages[name]=None
print(json.dumps({'python':platform.python_version(),'packages':packages}))
""" % (PACKAGES,)
    try:
        result = subprocess.run([str(executable), "-I", "-c", code], capture_output=True,
                                text=True, timeout=10)
        if result.returncode:
            return unknown
        value = json.loads(result.stdout)
        return {"status": "observed", "python": _python(value["python"]),
                "packages": _versions(value["packages"])}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, FlowError):
        return unknown


def _native_entry(item):
    required = {"candidate_sha256", "python", "packages", "evidence"}
    if not isinstance(item, dict) or set(item) != required:
        raise FlowError("Each native runtime entry needs candidate_sha256, python, packages and evidence")
    digest = item["candidate_sha256"]
    if not isinstance(digest, str) or not _HASH.fullmatch(digest):
        raise FlowError("Native runtime candidate must be a SHA-256")
    evidence = item["evidence"]
    if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 500:
        raise FlowError("Native runtime entry needs a short nonsecret evidence reference")
    return {"candidate_sha256": digest, "python": _python(item["python"]),
            "packages": _versions(item["packages"])}


def _native_observations(value, candidate_sha256):
    if value is None:
        return {}
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1 or set(value) - {"schema_version", "TEST", "PROD"}):
        raise FlowError("Runtime observations require schema_version 1 and optional TEST/PROD entries")
    if not isinstance(candidate_sha256, str) or not _HASH.fullmatch(candidate_sha256):
        raise FlowError("Runtime observations require the current package SHA-256")
    return {surface: _native_entry(value[surface]) for surface in ("TEST", "PROD") if surface in value}


def _parity(local, native, candidate_sha256, shared_packages=SHARED_PACKAGES):
    if native is None:
        return {"status": "unknown", "candidate_matches": None, "package_status": {},
                "python_minor_match": None, "managed_aidputils_version": None}
    matches = native["candidate_sha256"] == candidate_sha256
    packages = {}
    for name in shared_packages:
        left, right = local["packages"].get(name), native["packages"].get(name)
        packages[name] = "unknown" if left is None or right is None else "match" if left == right else "mismatch"
    left, right = local["python"], native["python"]
    python_match = None if left is None or right is None else _PYTHON.fullmatch(left).groups() == _PYTHON.fullmatch(right).groups()
    if not matches:
        status = "stale"
    elif python_match is False or "mismatch" in packages.values():
        status = "mismatch"
    elif python_match is None or "unknown" in packages.values() or local["status"] != "observed":
        status = "unknown"
    else:
        status = "matched_observation"
    return {"status": status, "candidate_matches": matches, "package_status": packages,
            "python_minor_match": python_match, "managed_aidputils_version": native["packages"]["aidputils"]}


def assess_runtime(local, native=None, candidate_sha256=None, *, runtime_profile=None, langgraph_version=None):
    """Compare supplied observations; never infer hosted versions or certify them."""
    if not isinstance(local, dict) or local.get("status") not in {"observed", "unavailable"}:
        raise FlowError("Local runtime observation is invalid")
    local = {"status": local["status"], "python": _python(local.get("python")),
             "packages": _versions(local.get("packages", {}))}
    selected = select_profile(runtime_profile, langgraph_version)
    observations = _native_observations(native, candidate_sha256)
    shared = tuple(dict.fromkeys((*SHARED_PACKAGES, *selected["packages"])))
    surfaces = {surface: _parity(local, observations.get(surface), candidate_sha256, shared) for surface in ("TEST", "PROD")}
    return {"profile": dict(PROFILE), "selected_profile": selected,
            "selected_profile_status": selected_status(local, selected), "local": local,
            "local_profile_status": documented_status(local["packages"]["langgraph"]) if local["status"] == "observed" else "unknown",
            "native": surfaces,
            "observed_shared_dependency_parity": all(item["status"] == "matched_observation" for item in surfaces.values()),
            "observation_provenance": "caller_supplied_native_metadata_not_independently_attested",
            "native_functional_acceptance": False, "oracle_certified": False,
            "compatibility_guaranteed": False}


def observe_capabilities(executable):
    """Inspect installed APIs in isolation; presence is not native acceptance."""
    unknown = {"status": "unknown", "executed_probe": False}
    if executable is None or not Path(executable).is_file():
        return unknown
    code = """import inspect,json
from langgraph.graph import StateGraph
import langgraph.errors as errors
import langgraph.runtime as runtime
parameters=inspect.signature(StateGraph.add_node).parameters
print(json.dumps({'status':'observed','executed_probe':False,
 'node_timeout':'timeout' in parameters,
 'node_error_handler':'error_handler' in parameters and hasattr(errors,'NodeError'),
 'graph_defaults':hasattr(StateGraph,'set_node_defaults'),
 'cooperative_drain':hasattr(runtime,'RunControl')}))
"""
    try:
        result = subprocess.run([str(executable), "-I", "-c", code], capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout) if result.returncode == 0 else unknown
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return unknown
