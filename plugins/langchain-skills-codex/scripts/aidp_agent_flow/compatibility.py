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
SHARED_PACKAGES = ("langgraph", "langchain-core", "langgraph-checkpoint", "oci")
PACKAGES = (*SHARED_PACKAGES, "aidputils")
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


def _parity(local, native, candidate_sha256):
    if native is None:
        return {"status": "unknown", "candidate_matches": None, "package_status": {},
                "python_minor_match": None, "managed_aidputils_version": None}
    matches = native["candidate_sha256"] == candidate_sha256
    packages = {}
    for name in SHARED_PACKAGES:
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


def assess_runtime(local, native=None, candidate_sha256=None):
    """Compare supplied observations; never infer hosted versions or certify them."""
    if not isinstance(local, dict) or local.get("status") not in {"observed", "unavailable"}:
        raise FlowError("Local runtime observation is invalid")
    local = {"status": local["status"], "python": _python(local.get("python")),
             "packages": _versions(local.get("packages", {}))}
    observations = _native_observations(native, candidate_sha256)
    surfaces = {surface: _parity(local, observations.get(surface), candidate_sha256) for surface in ("TEST", "PROD")}
    return {"profile": dict(PROFILE), "local": local,
            "local_profile_status": documented_status(local["packages"]["langgraph"]) if local["status"] == "observed" else "unknown",
            "native": surfaces,
            "observed_shared_dependency_parity": all(item["status"] == "matched_observation" for item in surfaces.values()),
            "observation_provenance": "caller_supplied_native_metadata_not_independently_attested",
            "native_functional_acceptance": False, "oracle_certified": False,
            "compatibility_guaranteed": False}
