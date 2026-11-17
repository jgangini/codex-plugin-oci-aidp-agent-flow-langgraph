"""Composable commands for local iteration and bounded native operations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .campaign import campaign_status, finish_attempt, initialize_campaign, load_policy, reconcile_attempt, reserve_attempt
from .evaluation import run_cases
from .packaging import inspect_package
from .project import FlowError, adopt, canonical_hash, contained, doctor, initialize, load_project, sync_project
from .progress import initialize_progress, record_test_review, report_progress, try_report_progress
from .remote import WorkbenchClient, native_read


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise FlowError(message)


def parser():
    result = Parser(description="Develop AIDP LangGraph agents locally; native acceptance is separate.")
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("--project", default=".", help="Project containing aidp-agent.toml")
    result.add_argument("--json", action="store_true", help="Emit stable JSON without provider exception bodies")
    commands = result.add_subparsers(dest="command", required=True)
    from .workflow_status import register_parser
    register_parser(commands)
    project = commands.add_parser("project", help="Prepare or adopt a local project")
    actions = project.add_subparsers(dest="action", required=True)
    create = actions.add_parser("init", help="Create a modular starter; default prepares its uv environment")
    create.add_argument("--path", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--langgraph-version", help="Exact version consistent with the selected runtime profile")
    create.add_argument("--runtime-profile", help="New projects default to aidp-managed-1.2.4; historical and custom profiles remain explicit")
    create.add_argument("--no-sync", action="store_true", help="Create files without dependency downloads")
    attach = actions.add_parser("adopt", help="Add configuration and local ignore rules; preserve agent code")
    for flag in ("factory", "entry", "dependencies"):
        attach.add_argument("--" + flag, required=True)
    attach.add_argument("--python-path", default=".")
    actions.add_parser("sync", help="Prepare the existing uv environment, respecting a present lockfile")
    commands.add_parser("doctor", help="Offline environment check; no model calls or cloud writes")
    runtime = commands.add_parser("runtime", help="Compare observed runtime versions with documented Oracle support")
    check = runtime.add_subparsers(dest="action", required=True).add_parser("check")
    check.add_argument("--observations", help="Project-relative JSON containing candidate-bound TEST/PROD version observations")
    check.add_argument("--runtime-profile", help="Override the project runtime profile for this check")
    check.add_argument("--require-profile", action="store_true", help="Fail unless observed local packages match the selected runtime profile")
    check.add_argument("--require-parity", action="store_true", help="Fail unless TEST and PROD observations match this candidate and local versions")
    test = commands.add_parser("test", help="Run selected local node/graph experiments")
    test.add_argument("--cases", required=True, help="Reviewed case JSON; reference labels stay outside graph input")
    test.add_argument("--case", action="append", help="Repeat to select cases rather than rerunning the whole set")
    test.add_argument("--real", action="store_true", help="Call the configured OCI model within its call/token limits")
    test.add_argument("--plan", action="store_true", help="Validate preparation and forecast campaign capacity without executing or reserving")
    test.add_argument("--timeout", type=int, default=120)
    test.add_argument("--max-steps", type=int, default=20)
    _experiment_arguments(test)
    quality = commands.add_parser("quality", help="Grade saved answers and calibrate a judge without retrieval or application execution")
    quality_actions = quality.add_subparsers(dest="action", required=True)
    for mode in ("calibrate", "assess"):
        grade = quality_actions.add_parser(mode)
        grade.add_argument("--cases", required=True)
        grade.add_argument("--case", action="append")
        grade.add_argument("--real", action="store_true")
        grade.add_argument("--timeout", type=int, default=120)
        grade.add_argument("--plan", action="store_true")
        if mode == "assess":
            grade.add_argument("--calibration", required=True, help="Current reviewed calibration report; never a native acceptance")
        _experiment_arguments(grade)
    campaign = commands.add_parser("campaign", help="Bound experiments, hypotheses, repetitions and accumulated reservations")
    actions = campaign.add_subparsers(dest="action", required=True)
    prepare_campaign = actions.add_parser("init", help="Install an explicit local experiment policy without cloud calls")
    prepare_campaign.add_argument("--definition", required=True)
    actions.add_parser("status", help="Read limits, attempts and unknown costs")
    upgrade = actions.add_parser("upgrade", help="Inspect a changed engine against preserved campaign accounting; no cloud calls")
    upgrade.add_argument("--apply", action="store_true", help="Append an adoption receipt without rewriting history or limits")
    upgrade.add_argument("--expected-snapshot", help="adoption_sha256 returned by the current inspection")
    reconcile = actions.add_parser("reconcile", help="Record an operator decision with project evidence; never retry automatically")
    reconcile.add_argument("--attempt", required=True)
    reconcile.add_argument("--model-calls", type=int, required=True)
    reconcile.add_argument("--cost-usd", help="Actual cost; omission preserves an unknown cost reservation")
    reconcile.add_argument("--evidence", required=True)
    reconcile.add_argument("--note", required=True)
    experiments = commands.add_parser("experiment", help="Diagnose and compare saved local experiments without new model calls")
    experiment_actions = experiments.add_subparsers(dest="action", required=True)
    diagnose = experiment_actions.add_parser("diagnose")
    diagnose.add_argument("--receipt", required=True, help="Project-relative saved local-run JSON")
    diagnose.add_argument("--case")
    compare = experiment_actions.add_parser("compare")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    progress = commands.add_parser("progress", help="Maintain evidence-backed node validation percentages and a Markdown table")
    actions = progress.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("init", help="Install a reviewed node/criteria map without overwriting an existing plan")
    prepare.add_argument("--definition", required=True, help="Project-relative JSON definition; requirements stay in the existing checklist")
    actions.add_parser("report", help="Rebuild the table from current evidence without running tests")
    review = actions.add_parser("review-test", help="Record an explicit functional review of a native TEST receipt; no cloud call")
    review.add_argument("--node", required=True)
    review.add_argument("--criterion", required=True)
    review.add_argument("--receipt", required=True, help="Project-relative native invocation receipt")
    review.add_argument("--verdict", choices=("accepted", "rejected"), required=True)
    review.add_argument("--note", required=True, help="Nonsecret reason against the criterion's rubric")
    package = commands.add_parser("package", help="Inspect deployment boundaries without uploading")
    package.add_subparsers(dest="action", required=True).add_parser("check")
    models = commands.add_parser("models", help="Read regional OCI model inventory without selecting or invoking")
    listing = models.add_subparsers(dest="action", required=True).add_parser("list")
    listing.add_argument("--limit", type=int, default=100, help="Page size; bounded pagination must complete")
    credentials = commands.add_parser("credentials", help="Inspect or explicitly create Credential Store entries")
    actions = credentials.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list")
    listing.add_argument("--name")
    listing.add_argument("--limit", type=int, default=100)
    for action in ("ensure-runtime", "ensure-service-account", "ensure-token"):
        action_parser = actions.add_parser(action, help="Read/plan by default; explicit --apply may create")
        action_parser.add_argument("--name", required=True)
        action_parser.add_argument("--apply", action="store_true")
        if action == "ensure-token":
            action_parser.add_argument("--env", required=True, help="Name of environment variable; never the token value")
            action_parser.add_argument("--key-name", default="token")
    native = commands.add_parser("native", help="Inspect AIDP or explicitly apply a scoped CODE-agent lifecycle operation")
    actions = native.add_subparsers(dest="action", required=True)
    for action in ("agents", "deployments"):
        actions.add_parser(action)
    session = actions.add_parser("session")
    session.add_argument("--session", required=True)
    session.add_argument("--trace")
    for action in ("sync", "ensure-agent", "test-init", "test-refresh", "status", "inspect-binding", "inspect-layout", "retire-agent", "prune-tree", "rebind", "session-create", "publish"):
        operation = actions.add_parser(action, help="Read/plan by default; mutations require --apply")
        if action == "prune-tree":
            operation.add_argument("--definition", required=True)
        if action == "sync":
            operation.add_argument("--for-rebind", action="store_true", help="Stage a new code root without overwriting old or conflicting files")
            operation.add_argument("--expected-inventory", help="Project-relative sealed before/target hashes for every existing package file")
        if action == "test-refresh":
            operation.add_argument("--recover-failed", action="store_true", help="Explicitly recover an existing terminal failed TEST; pending writes must already be reconciled")
        if action in {"rebind", "retire-agent"}:
            operation.add_argument("--expected-binding", help="binding_sha256 from the current read-only rebind plan")
        if action == "rebind":
            operation.add_argument("--allow-no-etag", action="store_true", help="Explicit readback-verified update without ETag; no atomic concurrency control")
        if action not in {"status", "inspect-binding", "inspect-layout"}:
            operation.add_argument("--apply", action="store_true")
    invoke = actions.add_parser("invoke", help="Plan or explicitly invoke one reviewed native case")
    invoke.add_argument("--question-file", required=True)
    invoke.add_argument("--surface", choices=("TEST", "PROD"), required=True)
    invoke.add_argument("--session")
    invoke.add_argument("--expect", action="append", default=[])
    invoke.add_argument("--timeout", type=int, default=90)
    invoke.add_argument("--apply", action="store_true")
    _experiment_arguments(invoke)
    registry = commands.add_parser("registry", help="Inspect, adopt or explicitly register the selected native AIDP agent")
    registry_actions = registry.add_subparsers(dest="action", required=True)
    listing = registry_actions.add_parser("list")
    listing.add_argument("--limit", type=int, default=100)
    registry_actions.add_parser("inspect")
    registry_actions.add_parser("inspect-card", help="Observe the authenticated public card without granting normalized Registry inspection or readiness")
    registry_actions.add_parser("status")
    registry_actions.add_parser("readiness", help="Fail unless this native agent has a published endpoint and verified ACTIVE Registry binding")
    registry_actions.add_parser("portal-link", help="Return the verified configured portal URL without claiming agent readiness")
    registry_actions.add_parser("hub-link", help="Return the configured Agent Hub portal after ACTIVE Registry verification")
    adopt_registry = registry_actions.add_parser("adopt")
    adopt_registry.add_argument("--registry-key", required=True)
    register = registry_actions.add_parser("register")
    register.add_argument("--metadata", required=True)
    register.add_argument("--apply", action="store_true")
    commands.add_parser("capabilities", help="Show implemented operations and remaining contract gaps")
    return result


def capabilities():
    return {"version": __version__,
            "preparation_preview": "test_plan_read_only_capacity_no_reservations",
            "boundary_evidence": "checkpoint_frontier_stop_reason_optional_bounded_hash_trace",
            "scope_exclusions": "version_2_append_only_inventory_retained_exclusions_not_passes",
            "execution_identity": "engine_hash_declared_environment_and_selected_runtime_metadata_not_native_parity",
            "local_project_and_test": "implemented_and_fixture_tested",
            "focused_test_evidence": "case_config_fingerprints_and_safe_failure_progress_local_assertions_only",
            "node_validation_progress": "explicit_criteria_weighted_local_evidence_and_reviewed_TEST_separate_from_execution",
            "campaign_admission": "persistent_limits_and_hypotheses_required_for_paid_CLI_experiments_unknown_cost_is_explicit",
            "campaign_upgrade": "snapshot_bound_append_only_adoption_preserves_unknown_usage_and_requires_affected_revalidation",
            "semantic_quality": "evidence_bound_posthoc_model_judge_finite_set_calibration_no_native_credit",
            "experiment_diagnosis": "saved_receipts_and_controlled_comparison_no_model_calls_or_semantic_acceptance",
            "criterion_progress": "explicit_gate_group_scope_case_evidence_and_staleness_not_project_effort",
            "reasoning_effort": "optional_sdk_validated_request_field_not_native_model_quality_acceptance",
            "mcp_rag_table_replay": "implemented_recorded_results_only_live_adapters_project_owned",
            "real_oci_model": "generic_family_live_smoke_accepted_other_models_require_tests",
            "model_inventory": "regional_sdk_inventory_live_read_accepted_not_model_quality_ranking",
            "credential_create": "dedicated_runtime_created_and_native_consumed_rest_values_omitted",
            "native_metadata_reads": "documented_20260430_live_read_accepted",
            "native_layout_acceptance": "exact_inventory_hash_and_metadata_gate_before_TEST_or_PROD_no_legacy_coexistence",
            "native_agent_retirement": "explicit_exact_key_development_only_journaled_delete_preserves_compute",
            "native_binding_inspection": "read_only_identity_and_path_drift_TEST_PROD_separate_not_migration_acceptance",
            "native_rebind": "documented_UpdateAgent_inputs_only_journal_ETag_fixture_checks_not_live_acceptance",
            "test_refresh": "explicit_legacy_test_adapter_target_verified",
            "first_playground_initialization": "explicit_legacy_async_action_target_verified",
            "production_publish": "explicit_ga_deploy_redeploy_target_verified_after_test",
            "native_invocation": "scoped_gateway_sse_requires_reviewed_case_and_explicit_apply",
            "registry_registration": "explicit_legacy_aidp_a2a_inspect_register_active_readback_target_verified",
            "agent_hub_portal_link": "verified_configured_navigation_separate_from_registry_readiness_sign_in_required",
            "agent_hub_registry_readiness": "selected_published_endpoint_and_active_binding_not_client_acceptance",
            "runtime_compatibility": "documented_oracle_profile_and_candidate_bound_observation_comparison_not_certification"}


def credential_command(args, root, config, client):
    from . import credential_store
    if args.action == "list":
        return credential_store.list_credentials(client, args.name, args.limit)
    if args.action == "ensure-token":
        return credential_store.ensure_secret_token(client, args.name, args.env, args.key_name, args.apply)
    auth = config.get("oci", {})
    path = Path(auth.get("config_file", ".oci/config")).expanduser()
    if not path.is_absolute():
        path = root / path
    function = (credential_store.ensure_runtime_credential if args.action == "ensure-runtime"
                else credential_store.ensure_service_account)
    return function(client, args.name, str(path), auth.get("profile", "DEFAULT"), args.apply)


def progress_command(args):
    if args.action == "init":
        return initialize_progress(args.project, args.definition)
    if args.action == "review-test":
        return record_test_review(args.project, args.node, args.criterion, args.receipt, args.verdict, args.note)
    return report_progress(args.project)


def _experiment_arguments(command):
    command.add_argument("--hypothesis", help="Nonsecret experiment hypothesis; required by a configured campaign")
    command.add_argument("--evidence", action="append", default=[], help="Project-relative evidence for the current hypothesis")
    command.add_argument("--repeat-reason", help="Explicit reason for a pre-authorized repeated identical trial")


def campaign_command(args):
    if args.action == "upgrade":
        from .campaign_upgrade import upgrade_campaign
        return upgrade_campaign(args.project, apply=args.apply, expected_snapshot=args.expected_snapshot)
    if args.action == "init":
        return initialize_campaign(args.project, args.definition)
    if args.action == "reconcile":
        return reconcile_attempt(args.project, args.attempt, model_calls=args.model_calls,
                                 cost_usd=args.cost_usd, evidence=args.evidence, note=args.note)
    return campaign_status(args.project)


def _campaign_invoke(args, lifecycle, root, config):
    from .native_invoke import invoke, preflight_invoke
    from .identity import execution_identity
    question = preflight_invoke(lifecycle, args.question_file, surface=args.surface, session_key=args.session,
                                expected=args.expect, timeout=args.timeout)["case"]
    policy = load_policy(root)
    identity = {"question": question, "surface": args.surface, "expected": args.expect, "timeout_seconds": args.timeout,
                "config": canonical_hash(config), "package": inspect_package(root)["package_sha256"],
                "deployment": lifecycle.state.get(args.surface.lower() + "_receipt"), "evaluator": __version__, **execution_identity(root)}
    attempt = reserve_attempt(root, case_id=question["id"], experiment_sha256=canonical_hash(identity),
        kind="native", model_calls=policy["native_call_ceiling"], hypothesis=args.hypothesis,
        evidence=args.evidence, repeat_reason=args.repeat_reason)
    result = invoke(lifecycle, args.question_file, surface=args.surface, session_key=args.session,
                    expected=args.expect, timeout=args.timeout)
    result["campaign_attempt_id"] = attempt
    try:
        finish_attempt(root, attempt, result, Path(result["artifact"]).relative_to(root))
    except Exception:
        result["campaign_error"] = "Invocation receipt saved; reconcile campaign completion before another paid experiment"
    return result


def runtime_command(args):
    from .compatibility import assess_runtime
    root, config = load_project(args.project)
    observation = None
    if args.observations:
        relative = Path(args.observations)
        if relative.is_absolute() or ".." in relative.parts:
            raise FlowError("Runtime observation file must be project-relative")
        try:
            path = contained(root, relative)
            with path.open("rb") as stream:
                data = stream.read(65_537)
            if len(data) > 65_536:
                raise ValueError
            observation = json.loads(data)
        except (OSError, ValueError, UnicodeError):
            raise FlowError("Runtime observations must be a valid JSON document of at most 64 KiB") from None
    report = assess_runtime(doctor(root)["runtime_compatibility"]["local"], observation,
                            inspect_package(root)["package_sha256"],
                            runtime_profile=args.runtime_profile or config.get("runtime", {}).get("profile"),
                            langgraph_version=None if args.runtime_profile else config.get("runtime", {}).get("langgraph_version"))
    report["passed"] = ((not args.require_profile or report["selected_profile_status"] == "target_match")
                        and (not args.require_parity or report["observed_shared_dependency_parity"]))
    report["required_checks"] = {"profile": args.require_profile, "parity": args.require_parity}
    return report


_LIFECYCLE_ACTIONS = {"sync": "sync_package", "ensure-agent": "ensure_agent", "test-init": "test_init",
                     "test-refresh": "test_refresh", "status": "status", "session-create": "create_test_session",
                     "publish": "publish", "inspect-binding": "inspect_binding", "inspect-layout": "inspect_layout", "retire-agent": "retire_agent", "prune-tree": "prune_tree", "rebind": "rebind"}


def _native_lifecycle_command(args, root, config):
    from .native_lifecycle import NativeLifecycle
    lifecycle = NativeLifecycle(root, config)
    try:
        if args.action == "invoke":
            if not args.apply:
                return {"action": "invoke", "applied": False, "surface": args.surface,
                        "native_test_accepted": False}
            result = _campaign_invoke(args, lifecycle, root, config)
            if (root / "node-progress.json").exists():
                result["progress"] = try_report_progress(root)
            return result
        if args.action == "sync":
            return lifecycle.sync_package(apply=args.apply, for_rebind=args.for_rebind,
                **({"expected_inventory": args.expected_inventory} if args.expected_inventory else {}))
        if args.action == "prune-tree":
            return lifecycle.prune_tree(args.definition, apply=args.apply)
        if args.action == "retire-agent":
            return lifecycle.retire_agent(apply=args.apply, expected_binding=args.expected_binding)
        if args.action == "rebind":
            return lifecycle.rebind(apply=args.apply, expected_binding=args.expected_binding, allow_no_etag=args.allow_no_etag)
        if args.action == "test-refresh":
            return lifecycle.test_refresh(apply=args.apply, recover_failed=args.recover_failed)
        operation = getattr(lifecycle, _LIFECYCLE_ACTIONS[args.action])
        return operation() if args.action in {"status", "inspect-binding", "inspect-layout"} else operation(apply=args.apply)
    finally:
        lifecycle.close()


def _registry_command(args, root, config):
    from .registry import Registry
    registry = Registry(root, config)
    try:
        if args.action == "list":
            return registry.list(args.limit)
        if args.action == "inspect-card":
            return registry.inspect_card()
        if args.action == "register":
            return registry.register(args.metadata, apply=args.apply)
        if args.action == "adopt":
            return registry.adopt(args.registry_key)
        if args.action == "portal-link":
            return registry.portal_link()
        if args.action == "hub-link":
            return registry.hub_link()
        return getattr(registry, args.action)()
    finally:
        registry.close()


def _project_command(args):
    if args.action == "init":
        result = initialize(args.path, args.name, sync=not args.no_sync, langgraph_version=args.langgraph_version, runtime_profile=args.runtime_profile)
        result["campaign"] = initialize_campaign(args.path, "tests/campaign-policy.json")
        result["progress"] = try_report_progress(args.path)
        return result
    if args.action == "adopt":
        return adopt(args.project, args.factory, args.entry, args.dependencies, args.python_path)
    return sync_project(args.project)


def execute(args):
    if args.command == "workflow":
        from .workflow_status import command
        return command(args)
    if args.command == "capabilities":
        return capabilities()
    if args.command == "project":
        return _project_command(args)
    if args.command == "doctor":
        return doctor(args.project)
    if args.command == "runtime":
        return runtime_command(args)
    if args.command == "test":
        return run_cases(args.project, args.cases, selected=args.case, real=args.real,
                         timeout=args.timeout, max_steps=args.max_steps, hypothesis=args.hypothesis,
                         evidence=args.evidence, repeat_reason=args.repeat_reason, require_campaign=True, plan=args.plan)
    if args.command == "quality":
        from .quality import run_quality
        return run_quality(args.project, args.cases, mode=args.action, selected=args.case, real=args.real,
                           timeout=args.timeout, hypothesis=args.hypothesis, evidence=args.evidence,
                           repeat_reason=args.repeat_reason, plan=args.plan,
                           calibration=getattr(args, "calibration", None))
    if args.command == "campaign":
        return campaign_command(args)
    if args.command == "experiment":
        from .experiments import compare_experiments, diagnose_experiment
        if args.action == "diagnose":
            return diagnose_experiment(args.project, args.receipt, case_id=args.case)
        return compare_experiments(args.project, args.baseline, args.candidate)
    if args.command == "progress":
        return progress_command(args)
    if args.command == "package":
        return inspect_package(args.project)
    if args.command == "models":
        from .models import list_models
        return list_models(args.project, args.limit)
    root, config = load_project(args.project)
    if args.command == "registry":
        return _registry_command(args, root, config)
    if args.command == "native" and args.action in {*_LIFECYCLE_ACTIONS, "invoke"}:
        return _native_lifecycle_command(args, root, config)
    client = WorkbenchClient(root, config)
    try:
        if args.command == "credentials":
            return credential_command(args, root, config, client)
        return native_read(client, config.get("native", {}), args.action,
                           session=getattr(args, "session", None), trace=getattr(args, "trace", None))
    finally:
        if client.session is not None:
            client.session.close()


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    json_output = "--json" in arguments
    try:
        args = parser().parse_args(arguments)
        result = execute(args)
        success = result.get("passed", result.get("local_ready", True)) if isinstance(result, dict) else True
        if args.command == "workflow":
            success = result["observation_complete"]
        print(json.dumps({"ok": bool(success), "result": result}, ensure_ascii=json_output, indent=None if json_output else 2))
        return 0 if success else 1
    except Exception as error:
        from .credential_store import CredentialStoreError
        safe = isinstance(error, (FlowError, CredentialStoreError))
        print(json.dumps({"ok": False, "error": {"type": type(error).__name__,
              "message": str(error) if safe else "Command failed; inspect the selected configuration and operation state"}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
