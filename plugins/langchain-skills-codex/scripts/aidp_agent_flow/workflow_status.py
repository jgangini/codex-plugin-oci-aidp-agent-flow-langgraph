"""Consolidate existing observations without publishing or accepting a candidate."""
from __future__ import annotations

from .campaign import campaign_status
from .native_lifecycle import NativeLifecycle
from .progress import report_progress
from .project import FlowError, load_project, redact
from .registry import Registry


def register_parser(commands):
    workflow = commands.add_parser("workflow", help="Summarize existing evidence and optional native observations")
    status = workflow.add_subparsers(dest="action", required=True).add_parser("status")
    status.add_argument("--native", action="store_true",
                        help="Also read native/Registry state and reconcile existing local receipts; no cloud writes")


def _observe(operation):
    try:
        return {"state": "available", "result": operation()}
    except Exception as error:
        message = str(error) if isinstance(error, FlowError) else "Observation failed; run its individual command for diagnosis"
        return {"state": "error", "error": {"type": type(error).__name__, "message": redact(message)}}


def _native_status(root, config):
    lifecycle = NativeLifecycle(root, config)
    try:
        result = lifecycle.status()
        operations = result.get("operations", [])
        return {**result,
                "pending_operations": [item for item in operations
                                       if item.get("state") not in {"RECONCILED", "FAILED_RECONCILED"}],
                "failed_operations": [item for item in operations if item.get("state") == "FAILED_RECONCILED"]}
    finally:
        lifecycle.close()


def _registry_status(root, config):
    registry = Registry(root, config)
    try:
        return registry.readiness()
    finally:
        registry.close()


def command(args):
    root, config = load_project(args.project)
    sections = {
        "campaign": (_observe(lambda: campaign_status(root)) if (root / "test-campaign.json").exists()
                     else {"state": "missing", "required": False}),
        "progress": (_observe(lambda: report_progress(root)) if (root / "node-progress.json").exists()
                     else {"state": "missing", "required": True}),
        "native": {"state": "not_requested"},
        "registry": {"state": "not_requested"},
    }
    if args.native:
        sections["native"] = _observe(lambda: _native_status(root, config))
        sections["registry"] = _observe(lambda: _registry_status(root, config))
    complete = all(section["state"] != "error"
                   and not (section["state"] == "missing" and section.get("required"))
                   for section in sections.values())
    return redact({
        "observation_complete": complete,
        "scope": "native_and_local" if args.native else "local",
        "sections": sections,
        "local_artifacts_may_be_updated": True,
        "cloud_changed": False,
        "client_invocation_verified": False,
        "acceptance_basis": "observations_only_not_publication_authorization_or_client_acceptance",
    })
