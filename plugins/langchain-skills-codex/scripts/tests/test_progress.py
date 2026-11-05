from copy import deepcopy
import json
from pathlib import Path
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
import unittest
from unittest.mock import patch

from aidp_agent_flow import __version__
from aidp_agent_flow.identity import execution_identity
from aidp_agent_flow.packaging import inspect_package
from aidp_agent_flow.progress import initialize_progress, load_progress_plan, record_test_review, report_progress, try_report_progress, require_publication_acceptance
from aidp_agent_flow.project import FlowError, canonical_hash, initialize, load_project


class ProgressTests(unittest.TestCase):
    def setUp(self):
        observed = patch("aidp_agent_flow.identity.observe_local", return_value={
            "status": "observed", "python": "3.12.11", "packages": {}})
        observed.start()
        self.addCleanup(observed.stop)
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Progress test", sync=False)
        self.case = {"id": "positive", "input": {"question": "Review"},
                     "assertions": [{"path": "answer", "equals": "verified"}]}
        self.write("tests/progress-cases.json", [self.case])
        self.plan = {"version": 1, "requirements_ref": "README.md", "nodes": [
            {"id": "respond", "implementation": "declared", "criteria": [
                {"id": "local-positive", "description": "Returns the reviewed outcome", "layer": "local",
                 "case_id": "positive", "cases_file": "tests/progress-cases.json"},
                {"id": "native-positive", "description": "Native answer meets the rubric", "layer": "TEST",
                 "case_id": "native-positive"}]},
            {"id": "never-run", "criteria": []}]}
        self.write("node-progress.json", self.plan)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, data):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding="utf-8")
        return target

    def identity(self):
        _, config = load_project(self.root)
        return {"package_sha256": inspect_package(self.root)["package_sha256"],
                "config_sha256": canonical_hash(config), "progress_plan_sha256": canonical_hash(self.plan),
                "evaluator_version": __version__, **execution_identity(self.root)}

    def local(self, *, passed=True, second=1, visited=None, **changes):
        value = {**self.identity(), "case_id": "positive", "case_sha256": canonical_hash(self.case),
                 "mode": "local_fixture_model", "recorded_at": f"2026-11-02T12:00:{second:02d}+00:00",
                 "passed": passed, "visited_nodes": ["respond"] if visited is None else visited,
                 "model_calls": 1, **changes}
        return self.write(f".aidp-local/runs/run-{second}.json", {"results": [value]})

    def native(self, **changes):
        config = self.root / "aidp-agent.toml"
        prefix = config.read_text(encoding="utf-8").split("[native]", 1)[0]
        config.write_text(prefix + '[native]\nendpoint="https://aidp.us-chicago-1.oci.oraclecloud.com"\n'
                          'platform_id="platform"\nworkspace_key="workspace"\nagent_key="agent"\n', encoding="utf-8")
        value = {"target": "https://aidp.us-chicago-1.oci.oraclecloud.com/20260430/aiDataPlatforms/platform",
                 "workspace": "workspace", "agent_key": "agent", "surface": "TEST", "case_id": "native-positive",
                 "package_sha256": self.identity()["package_sha256"], "deployment_key": "deployment",
                 "evaluator_version": __version__, **execution_identity(self.root),
                 "deployment_version": 1, "package_binding_verified": True,
                 "deployment_snapshot": [{"key": "deployment", "deploymentVersion": 1, "lifecycleState": "ACTIVE"}],
                 "question_sha256": "question-hash", "state": "RESPONDED", "passed": True,
                 "stream_complete": True, "failure": None, "error_count": 0,
                 "answer": "PRIVATE ANSWER NEVER IN TABLE", **changes}
        self.write(".aidp-local/invocations/native.json", value)
        return ".aidp-local/invocations/native.json"

    def test_inventory_includes_never_run_and_unplanned_nodes(self):
        report = report_progress(self.root)
        self.assertEqual([node["id"] for node in report["nodes"]], ["respond", "never-run"])
        self.assertIsNone(report["nodes"][1]["validation"]["percent"])
        self.assertEqual(report["nodes"][0]["validation"]["percent"], 0)
        self.assertFalse(report["scope_complete"])

    def test_local_pass_does_not_accept_test_and_implementation_is_separate(self):
        self.local()
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["local"], {"approved": 1, "required": 1,
                                        "approved_count": 1, "required_count": 1, "percent": 100.0,
                                        "excluded": 0, "excluded_count": 0, "inventoried": 1, "inventoried_count": 1})
        self.assertEqual(node["TEST"]["percent"], 0)
        self.assertEqual(node["validation"]["percent"], 50.0)
        self.assertEqual(node["state"], "local_validated")

    def test_visited_node_alone_does_not_approve_a_criterion(self):
        self.local(passed=False)
        self.assertEqual(report_progress(self.root)["nodes"][0]["validation"]["percent"], 0)
        self.local(second=2, visited=[])
        self.assertEqual(report_progress(self.root)["nodes"][0]["state"], "failed")

    def test_failure_after_pass_reopens_the_criterion(self):
        self.local(second=20)
        self.local(passed=False, second=21, failure_stage="assertions")
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["state"], "failed")
        self.assertEqual(node["local"]["percent"], 0)
        self.assertEqual(len(list((self.root / ".aidp-local/runs").glob("*.json"))), 2)

    def test_receipt_order_uses_timestamp_not_filename(self):
        newer = self.local(passed=False, second=2)
        older = self.local(second=1)
        newer.rename(newer.with_name("aaaa.json"))
        older.rename(older.with_name("zzzz.json"))
        self.assertEqual(report_progress(self.root)["nodes"][0]["state"], "failed")

    def test_other_package_configuration_or_case_is_stale(self):
        for field in ("package_sha256", "config_sha256", "case_sha256", "progress_plan_sha256"):
            with self.subTest(field=field):
                self.local(**{field: "different"})
                node = report_progress(self.root)["nodes"][0]
                self.assertEqual(node["state"], "stale")
                self.assertEqual(node["validation"]["percent"], 0)

    def test_case_and_plan_edits_invalidate_previous_evidence(self):
        self.local()
        self.case["assertions"][0]["equals"] = "new expected result"
        self.write("tests/progress-cases.json", [self.case])
        self.assertEqual(report_progress(self.root)["nodes"][0]["state"], "stale")
        self.case["assertions"][0]["equals"] = "verified"
        self.write("tests/progress-cases.json", [self.case])
        self.plan["nodes"][0]["criteria"][0]["description"] = "Stricter reviewed criterion"
        self.write("node-progress.json", self.plan)
        self.assertEqual(report_progress(self.root)["nodes"][0]["state"], "stale")

    def test_real_mode_requires_actual_model_call_and_matching_mode(self):
        self.plan["nodes"][0]["criteria"][0]["mode"] = "real"
        self.case["node"] = "respond"
        self.write("tests/progress-cases.json", [self.case])
        self.write("node-progress.json", self.plan)
        self.local()
        self.assertEqual(report_progress(self.root)["nodes"][0]["state"], "stale")
        self.local(second=2, mode="local_real_oci_model", model_calls=0)
        self.assertEqual(report_progress(self.root)["nodes"][0]["state"], "failed")

    def test_legacy_undated_receipts_cannot_earn_credit(self):
        self.local(recorded_at=None)
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["state"], "stale")
        self.assertEqual(node["local"]["percent"], 0)

    def test_blocker_is_visible_despite_local_success(self):
        self.plan["nodes"][0]["blocker"] = "Review permission boundary"
        self.write("node-progress.json", self.plan)
        self.local()
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["state"], "blocked")
        self.assertEqual(node["validation"]["percent"], 50)

    def test_shared_case_requires_each_node_actually_completed(self):
        other = deepcopy(self.plan["nodes"][0])
        other["id"] = "other"
        self.plan["nodes"].append(other)
        self.write("node-progress.json", self.plan)
        self.local(visited=["respond", "other", "not-in-plan"])
        report = report_progress(self.root)
        self.assertEqual([report["nodes"][i]["local"]["percent"] for i in (0, 2)], [100, 100])
        self.assertEqual(report["unplanned_observed_nodes"], ["not-in-plan"])
        self.assertFalse(report["scope_complete"])

    def test_weighted_denominator_and_invalid_weights(self):
        self.plan["nodes"][0]["criteria"][0]["weight"] = 3
        self.write("node-progress.json", self.plan)
        self.local()
        coverage = report_progress(self.root)["nodes"][0]["validation"]
        self.assertEqual(coverage["percent"], 75)
        self.assertEqual((coverage["approved_count"], coverage["required_count"]), (1, 2))
        for weight in (True, 0, -1, 1.5, float("nan"), 101):
            with self.subTest(weight=weight):
                self.plan["nodes"][0]["criteria"][0]["weight"] = weight
                self.write("node-progress.json", self.plan)
                with self.assertRaises(FlowError):
                    load_progress_plan(self.root)

    def test_rounded_percentage_cannot_claim_completion_with_pending_weight(self):
        positive = self.plan["nodes"][0]["criteria"][0]
        criteria = [{**positive, "id": f"positive-{index}", "weight": 100} for index in range(20)]
        criteria.append({**positive, "id": "pending", "case_id": "pending", "weight": 1})
        self.plan["nodes"][0]["criteria"] = criteria
        self.write("node-progress.json", self.plan)
        pending_case = {**self.case, "id": "pending"}
        self.write("tests/progress-cases.json", [self.case, pending_case])
        self.local()
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["local"]["approved"], 2000)
        self.assertEqual(node["local"]["required"], 2001)
        self.assertEqual(node["local"]["percent"], 99.9)
        self.assertEqual(node["validation"]["percent"], 99.9)
        self.assertEqual(node["state"], "pending")

    def test_native_technical_pass_needs_semantic_review(self):
        receipt = self.native()
        self.local()
        self.assertEqual(report_progress(self.root)["nodes"][0]["TEST"]["percent"], 0)
        report = record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Reviewed against the business rubric")
        self.assertEqual(report["nodes"][0]["state"], "accepted")
        self.assertEqual(report["nodes"][0]["validation"]["percent"], 100)
        self.assertFalse(report["native_test_accepted"])
        self.assertNotIn("PRIVATE ANSWER", Path(report["table"]).read_text(encoding="utf-8"))
        self.assertNotIn("PRIVATE ANSWER", Path(report["artifact"]).read_text(encoding="utf-8"))

    def test_mutated_native_receipt_invalidates_review(self):
        receipt = self.native()
        record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Checked")
        value = json.loads((self.root / receipt).read_text(encoding="utf-8"))
        value["answer"] = "Changed after review"
        self.write(receipt, value)
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["TEST"]["percent"], 0)
        self.assertEqual(node["state"], "stale")

    def test_native_review_rejects_other_target_prod_incomplete_and_missing_note(self):
        receipt = self.native()
        original = json.loads((self.root / receipt).read_text(encoding="utf-8"))
        for changes in ({"surface": "PROD"}, {"agent_key": "other"}, {"workspace": "other"},
                        {"package_sha256": "other"}, {"passed": False}, {"stream_complete": False},
                        {"target": "https://other"}, {"error_count": False},
                        {"package_binding_verified": False}, {"deployment_snapshot": []}):
            with self.subTest(changes=changes):
                self.write(receipt, {**original, **changes})
                with self.assertRaises(FlowError):
                    record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Checked")
        self.write(receipt, original)
        with self.assertRaises(FlowError):
            record_test_review(self.root, "respond", "native-positive", receipt, "accepted", " ")

    def test_explicit_rejection_reopens_accepted_test(self):
        receipt = self.native()
        record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Initial review")
        report = record_test_review(self.root, "respond", "native-positive", receipt, "rejected", "Counterexample found")
        self.assertEqual(report["nodes"][0]["TEST"]["percent"], 0)
        self.assertEqual(report["nodes"][0]["state"], "failed")

    def test_invalid_paths_and_linked_artifacts_are_rejected(self):
        self.plan["nodes"][0]["criteria"][0]["cases_file"] = "../outside.json"
        self.write("node-progress.json", self.plan)
        with self.assertRaises(FlowError):
            load_progress_plan(self.root)
        self.plan["nodes"][0]["criteria"][0]["cases_file"] = "tests/progress-cases.json"
        self.write("node-progress.json", self.plan)
        with patch.object(Path, "is_symlink", lambda path: path.name == ".aidp-local"):
            with self.assertRaises(FlowError):
                report_progress(self.root)

    def test_missing_case_does_not_block_other_progress(self):
        self.write("tests/progress-cases.json", [])
        report = report_progress(self.root)
        self.assertEqual(report["nodes"][0]["criteria"][0]["state"], "pending")
        self.assertEqual(report["nodes"][0]["criteria"][0]["configuration"], "reviewed_case_unavailable")

    def test_criterion_matrix_shows_mapping_labels_and_separate_group_views(self):
        criterion = self.plan["nodes"][0]["criteria"][0]
        criterion.update(gate="G1", group="routing")
        self.write("node-progress.json", self.plan)
        self.local()
        report = report_progress(self.root)
        item = report["nodes"][0]["criteria"][0]
        self.assertEqual((item["mode"], item["scope"], item["case_id"], item["cases_file"]),
                         ("fixture", "integration", "positive", "tests/progress-cases.json"))
        self.assertEqual([(group["dimension"], group["label"]) for group in report["groups"]],
                         [("gate", "G1"), ("group", "routing")])
        self.assertEqual([group["node_criteria"]["required_count"] for group in report["groups"]], [1, 1])
        self.assertEqual(report["overall_validation"]["required_count"], 2)
        table = Path(report["table"]).read_text(encoding="utf-8")
        for expected in ("respond/local-positive", "Returns the reviewed outcome", "G1 / routing",
                         "tests/progress-cases.json#positive", ".aidp-local/runs/run-1.json",
                         report["progress_plan_sha256"], "must not be added together"):
            self.assertIn(expected, table)

    def test_missing_and_malformed_cases_have_actionable_diagnostics_without_credit(self):
        for cases in ([], [self.case, self.case], [{**self.case, "assertions": [{"path": "answer"}]}]):
            with self.subTest(cases=cases):
                self.write("tests/progress-cases.json", cases)
                report = report_progress(self.root)
                issue = report["diagnostics"]["configuration_issues"][0]
                self.assertFalse(report["diagnostics"]["configuration_valid"])
                self.assertEqual((issue["node_id"], issue["id"], issue["case_id"]),
                                 ("respond", "local-positive", "positive"))
                self.assertEqual(issue["cases_file"], "tests/progress-cases.json")
                self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)
                self.assertIn("repair cases_file/case_id", Path(report["table"]).read_text(encoding="utf-8"))

    def test_stale_dimensions_and_historical_pass_are_visible_without_carry_forward(self):
        receipt = self.local(evaluator_version="old", package_sha256="old-package")
        original = receipt.read_bytes()
        report = report_progress(self.root)
        item = report["nodes"][0]["criteria"][0]
        self.assertEqual(item["state"], "stale")
        self.assertEqual(set(item["stale_reasons"]), {"changed_evaluator_version", "changed_package_sha256"})
        self.assertEqual(item["historical_pass"]["evaluator_version"], "old")
        self.assertEqual(item["historical_pass"]["basis"], "recorded_pass_not_current_acceptance")
        self.assertIsNone(item["evidence"])
        self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)
        self.assertFalse(report["publication_ready"])
        self.assertEqual(receipt.read_bytes(), original)
        self.assertIn("changed_package_sha256", Path(report["table"]).read_text(encoding="utf-8"))

    def test_failure_retains_previous_pass_as_history_without_acceptance(self):
        self.local(second=1)
        self.local(second=2, passed=False)
        report = report_progress(self.root)
        item = report["nodes"][0]["criteria"][0]
        self.assertEqual(item["state"], "failed")
        self.assertEqual(item["historical_pass"]["evidence"], ".aidp-local/runs/run-1.json")
        self.assertEqual(item["evidence"], ".aidp-local/runs/run-2.json")
        self.assertIn("runner_did_not_pass", item["failure_reasons"])
        self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)

    def test_fixture_pass_cannot_be_presented_as_historical_real_reasoning_pass(self):
        self.plan["nodes"][0]["criteria"][0]["mode"] = "real"
        self.case["node"] = "respond"
        self.write("node-progress.json", self.plan)
        self.write("tests/progress-cases.json", [self.case])
        self.local()
        item = report_progress(self.root)["nodes"][0]["criteria"][0]
        self.assertIn("changed_mode", item["stale_reasons"])
        self.assertIsNone(item["historical_pass"])

    def test_agent_matrix_and_groups_keep_integration_denominator_separate(self):
        self.plan["acceptance"] = [{"id": "integrated", "description": "Whole agent acceptance",
            "case_id": "integrated-case", "layer": "TEST", "gate": "G2"}]
        self.plan["nodes"][0]["criteria"][0]["gate"] = "G2"
        self.write("node-progress.json", self.plan)
        self.local()
        report = report_progress(self.root)
        group = report["groups"][0]
        self.assertEqual(group["node_criteria"]["approved_count"], 1)
        self.assertEqual(group["agent_acceptance"]["approved_count"], 0)
        self.assertEqual(group["agent_acceptance"]["required_count"], 1)
        self.assertEqual(report["overall_validation"]["required_count"], 2)
        table = Path(report["table"]).read_text(encoding="utf-8")
        self.assertIn("__agent__/integrated", table)
        self.assertIn("native case: integrated-case", table)
        self.assertIn("This denominator is separate from node coverage", table)
        self.assertFalse(report["publication_ready"])

    def test_optional_label_metadata_is_bounded_and_escaped(self):
        criterion = self.plan["nodes"][0]["criteria"][0]
        for label in ("gate", "group"):
            for value in (None, [], {}, True, "", "x" * 129):
                with self.subTest(label=label, value=value):
                    criterion[label] = value
                    self.write("node-progress.json", self.plan)
                    with self.assertRaises(FlowError):
                        load_progress_plan(self.root)
            criterion.pop(label)
        criterion.update(gate="G1|<script>", group="[unsafe](javascript:alert(1))")
        criterion["description"] = "Review `value`\n<script>"
        self.write("node-progress.json", self.plan)
        table = Path(report_progress(self.root)["table"]).read_text(encoding="utf-8")
        self.assertIn("G1&#124;&lt;script&gt;", table)
        self.assertIn("\\[unsafe\\]", table)
        self.assertIn("\\`value\\`", table)
        self.assertNotIn("<script>", table)

    def test_native_scope_validation_precedes_report_write(self):
        criterion = self.plan["nodes"][0]["criteria"][1]
        for scope in ({}, [], None, True, "unexpected"):
            with self.subTest(scope=scope):
                criterion["scope"] = scope
                self.write("node-progress.json", self.plan)
                with self.assertRaisesRegex(FlowError, "scope must be node or integration"):
                    report_progress(self.root)
                self.assertFalse((self.root / ".aidp-local/progress/report.json").exists())
                self.assertFalse((self.root / ".aidp-local/progress/table.md").exists())
        criterion["scope"] = "integration"
        self.write("node-progress.json", self.plan)
        self.assertEqual(report_progress(self.root)["nodes"][0]["criteria"][1]["scope"], "integration")

    def test_native_cases_file_is_rejected_before_report_write(self):
        criterion = self.plan["nodes"][0]["criteria"][1]
        for reference in ({"unexpected": "value"}, "tests/progress-cases.json", None):
            with self.subTest(reference=reference):
                criterion["cases_file"] = reference
                self.write("node-progress.json", self.plan)
                with self.assertRaisesRegex(FlowError, "native case_id, not a local cases_file"):
                    report_progress(self.root)
                self.assertFalse((self.root / ".aidp-local/progress/report.json").exists())
                self.assertFalse((self.root / ".aidp-local/progress/table.md").exists())

    def test_malformed_response_or_node_metadata_cannot_crash_or_earn_credit(self):
        self.plan["nodes"][0]["criteria"][0]["mode"] = "real"
        self.case["node"] = "respond"
        self.write("node-progress.json", self.plan)
        self.write("tests/progress-cases.json", [self.case])
        for metadata in (None, {"complete": True}, [True], [{"complete": 1}]):
            with self.subTest(metadata=metadata):
                self.local(mode="local_real_oci_model", model_response_metadata=metadata)
                item = report_progress(self.root)["nodes"][0]["criteria"][0]
                self.assertEqual(item["state"], "failed")
                self.assertIn("complete_model_response_missing", item["failure_reasons"])
        self.local(visited=None, visited_nodes=None)
        report = report_progress(self.root)
        self.assertEqual(report["unplanned_observed_nodes"], [])
        self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)

    def test_markdown_escapes_names_and_blockers(self):
        self.plan["nodes"][0]["id"] = "node|with\nline<script>"
        self.plan["nodes"][0]["blocker"] = "blocked|reason\nnext"
        self.write("node-progress.json", self.plan)
        report = report_progress(self.root)
        table = Path(report["table"]).read_text(encoding="utf-8")
        self.assertIn("node&#124;with line&lt;script&gt;", table)
        self.assertIn("blocked&#124;reason next", table)
        self.assertNotIn("<script>", table)

    def test_initialize_preserves_existing_plan(self):
        definition = self.write("tests/progress-definition.json", self.plan)
        with self.assertRaises(FlowError):
            initialize_progress(self.root, definition.relative_to(self.root))
        (self.root / "node-progress.json").unlink()
        report = initialize_progress(self.root, definition.relative_to(self.root))
        self.assertEqual(report["nodes"][0]["id"], "respond")

    def test_report_redacts_known_secret_markers_on_stdout_and_disk(self):
        self.plan["nodes"][0]["blocker"] = "apify_api_" + "A" * 25
        self.write("node-progress.json", self.plan)
        report = report_progress(self.root)
        self.assertNotIn("apify_api_", json.dumps(report))
        self.assertNotIn("apify_api_", Path(report["table"]).read_text(encoding="utf-8"))
        self.assertNotIn("apify_api_", Path(report["artifact"]).read_text(encoding="utf-8"))

    def test_history_and_linked_project_limits_fail_before_report_write(self):
        self.local()
        with patch("aidp_agent_flow.progress._MAX_HISTORY_BYTES", 1):
            with self.assertRaises(FlowError):
                report_progress(self.root)
        with patch.object(Path, "is_symlink", lambda path: path == self.root):
            with self.assertRaises(FlowError):
                report_progress(self.root)

    def test_automatic_report_failure_does_not_leak_exception_body(self):
        with patch("aidp_agent_flow.progress.report_progress", side_effect=RuntimeError("private provider detail")):
            result = try_report_progress(self.root)
        self.assertFalse(result["updated"])
        self.assertNotIn("private provider detail", json.dumps(result))
        self.assertIn("receipts were preserved", result["error"])

    def test_old_or_missing_evaluator_cannot_grant_local_or_review_credit(self):
        for evaluator in (None, "older-evaluator"):
            with self.subTest(evaluator=evaluator):
                self.local(evaluator_version=evaluator)
                self.assertEqual(report_progress(self.root)["nodes"][0]["local"]["percent"], 0)
        receipt = self.native()
        record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Reviewed")
        review = next((self.root / ".aidp-local/progress/reviews").glob("*.json"))
        value = json.loads(review.read_text(encoding="utf-8"))
        value["evaluator_version"] = "older-evaluator"
        review.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(report_progress(self.root)["nodes"][0]["TEST"]["percent"], 0)

    def test_current_review_cannot_accept_old_native_evaluator_artifact(self):
        receipt = self.native()
        original = json.loads((self.root / receipt).read_text(encoding="utf-8"))
        for evaluator in (None, "older-evaluator"):
            with self.subTest(evaluator=evaluator):
                self.write(receipt, {**original, "evaluator_version": evaluator})
                with self.assertRaises(FlowError):
                    record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Reviewed now")

    def test_real_node_scope_requires_direct_case_not_another_nodes_model_call(self):
        self.plan["nodes"][0]["criteria"][0]["mode"] = "real"
        self.write("node-progress.json", self.plan)
        self.local(mode="local_real_oci_model", model_calls=1, visited=["planner", "respond"])
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["local"]["percent"], 0)
        self.assertEqual(node["criteria"][0]["configuration"], "direct_node_case_required")
        self.plan["nodes"][0]["criteria"][0]["scope"] = "integration"
        self.write("node-progress.json", self.plan)
        self.local(second=2, mode="local_real_oci_model", model_calls=1, visited=["planner", "respond"],
                   model_response_metadata=[{"complete": True, "finish_reason": "stop"}])
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["local"]["percent"], 100)
        self.assertEqual(node["criteria"][0]["scope"], "integration")

    def test_caught_transport_failure_does_not_credit_model_reasoning(self):
        self.plan["nodes"][0]["criteria"][0]["mode"] = "real"
        self.case["node"] = "respond"
        self.write("tests/progress-cases.json", [self.case])
        self.write("node-progress.json", self.plan)
        self.local(mode="local_real_oci_model", model_calls=1, model_response_metadata=[])
        self.assertEqual(report_progress(self.root)["nodes"][0]["local"]["percent"], 0)
        self.local(second=2, mode="local_real_oci_model", model_calls=1,
                   model_response_metadata=[{"complete": True, "finish_reason": "stop"}])
        self.assertEqual(report_progress(self.root)["nodes"][0]["local"]["percent"], 100)

    def ready_plan(self):
        self.plan["nodes"] = self.plan["nodes"][:1]
        self.plan["acceptance"] = [{"id": "integrated", "description": "Agent integration meets its rubric",
                                    "layer": "TEST", "case_id": "native-positive"}]
        self.write("node-progress.json", self.plan)
        receipt = self.native()
        self.local()
        record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Node reviewed")
        return receipt

    def test_publication_requires_agent_integration_not_only_node_percentages(self):
        receipt = self.ready_plan()
        report = report_progress(self.root)
        self.assertEqual(report["nodes"][0]["validation"]["percent"], 100)
        self.assertFalse(report["publication_ready"])
        snapshot = json.loads((self.root / receipt).read_text(encoding="utf-8"))["deployment_snapshot"]
        with self.assertRaisesRegex(FlowError, "agent integration"):
            require_publication_acceptance(self.root, snapshot)
        report = record_test_review(self.root, "__agent__", "integrated", receipt, "accepted", "Full agent reviewed")
        self.assertTrue(report["publication_ready"])
        self.assertTrue(require_publication_acceptance(self.root, snapshot)["publication_ready"])

    def test_publication_rejects_blocker_failure_stale_and_changed_native_snapshot(self):
        receipt = self.ready_plan()
        record_test_review(self.root, "__agent__", "integrated", receipt, "accepted", "Full agent reviewed")
        snapshot = json.loads((self.root / receipt).read_text(encoding="utf-8"))["deployment_snapshot"]
        with self.assertRaisesRegex(FlowError, "different deployment"):
            require_publication_acceptance(self.root, [{**snapshot[0], "deploymentVersion": 2}])
        self.local(second=2, passed=False)
        with self.assertRaises(FlowError):
            require_publication_acceptance(self.root, snapshot)
        self.local(second=3)
        self.plan["nodes"][0]["blocker"] = "Review scope"
        self.write("node-progress.json", self.plan)
        with self.assertRaises(FlowError):
            require_publication_acceptance(self.root, snapshot)

    def test_publication_requires_plan_local_and_TEST_criteria_and_agent_scope(self):
        (self.root / "node-progress.json").unlink()
        with self.assertRaises(FlowError):
            require_publication_acceptance(self.root, [])
        self.write("node-progress.json", self.plan)
        self.plan["nodes"][0]["id"] = "__agent__"
        self.write("node-progress.json", self.plan)
        with self.assertRaises(FlowError):
            load_progress_plan(self.root)

    def test_publication_rejects_unresolved_campaign_with_accepted_criteria(self):
        from aidp_agent_flow.campaign import reserve_attempt
        receipt = self.ready_plan()
        record_test_review(self.root, "__agent__", "integrated", receipt, "accepted", "Full agent reviewed")
        snapshot = json.loads((self.root / receipt).read_text(encoding="utf-8"))["deployment_snapshot"]
        if not (self.root / "test-campaign.json").exists():
            self.write("test-campaign.json", {"version": 1, "max_attempts": 10, "max_model_calls": 10,
                "max_identical_trials": 1, "native_call_ceiling": 1, "budget_usd": "1",
                "real_cost_ceiling_usd": "0.1", "native_cost_ceiling_usd": "0.1"})
        reserve_attempt(self.root, case_id="unresolved", experiment_sha256="a" * 64,
                        kind="fixture", model_calls=0, hypothesis="Synthetic unfinished experiment")
        with self.assertRaises(FlowError):
            require_publication_acceptance(self.root, snapshot)


if __name__ == "__main__":
    unittest.main()
