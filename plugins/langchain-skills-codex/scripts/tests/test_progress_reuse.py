from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

try:
    from . import test_progress as native_fixtures
    from . import test_progress_integration as local_fixtures
except ImportError:
    import test_progress as native_fixtures
    import test_progress_integration as local_fixtures

from aidp_agent_flow.identity import execution_identity
from aidp_agent_flow.progress import record_test_review, report_progress


class LocalCriterionReuseTests(unittest.TestCase):
    tearDown = local_fixtures.ProgressIntegrationTests.tearDown
    selected_run = local_fixtures.ProgressIntegrationTests.selected_run

    def setUp(self):
        local_fixtures.ProgressIntegrationTests.setUp(self)
        self.plan_path = self.root / "node-progress.json"
        self.plan = json.loads(self.plan_path.read_text(encoding="utf-8"))

    def save_plan(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")

    def change_other_criterion(self):
        self.plan["nodes"][0]["criteria"][1]["description"] += " Reviewed."
        self.save_plan()

    def criterion(self, report=None):
        return (report or report_progress(self.root))["nodes"][0]["criteria"][0]

    def test_real_writer_preserves_unchanged_criterion_and_original_receipt(self):
        run = self.selected_run()
        self.assertTrue(run["passed"])
        path = Path(run["artifact"])
        original = path.read_bytes()
        receipt = json.loads(original)["results"][0]
        self.assertIn("graph-response", receipt["criterion_bindings"]["respond"])
        self.assertNotIn("node-response", receipt["criterion_bindings"]["respond"])
        self.change_other_criterion()
        item = self.criterion()
        self.assertEqual(item["state"], "passed")
        self.assertTrue(item["evidence_reused"])
        self.assertEqual(item["evidence_plan_sha256"], receipt["progress_plan_sha256"])
        self.assertEqual(path.read_bytes(), original)

    def test_changed_criterion_requirements_policy_or_node_context_remains_stale(self):
        self.selected_run()
        original = deepcopy(self.plan)
        variants = []
        changed = deepcopy(original)
        changed["nodes"][0]["criteria"][0]["description"] += " Stronger rubric."
        variants.append(changed)
        changed = deepcopy(original)
        changed["requirements_ref"] = "changed-authority.md"
        variants.append(changed)
        changed = deepcopy(original)
        changed.update(version=2, revision=1, scope_decisions=[],
                       publication_policy="declared_requirements_v1",
                       publication_policy_reason="Explicit requirement policy")
        variants.append(changed)
        changed = deepcopy(original)
        changed["nodes"][0]["implementation"] = "pending"
        variants.append(changed)
        # Do not persist reports between independent plans: version 2 history
        # intentionally forbids returning to an older reviewed plan.
        for changed in variants:
            with self.subTest(changed=changed):
                self.plan = changed
                self.save_plan()
                with patch("aidp_agent_flow.progress._snapshot_plan", return_value="synthetic-plan.json"):
                    self.assertEqual(self.criterion()["state"], "stale")

    def test_candidate_model_source_case_and_executor_changes_never_reuse(self):
        self.selected_run()
        self.change_other_criterion()
        self.assertEqual(self.criterion()["state"], "passed")
        for relative, transform in (
            ("aidp-agent.toml", lambda text: text.replace('model_id = ""', 'model_id = "changed-model"')),
            ("agent/core/graph.py", lambda text: text + "\n# Different source candidate\n"),
            ("tests/cases.json", lambda text: text.replace("Summarize the supplied evidence.", "Changed question.")),
        ):
            path = self.root / relative
            original = path.read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertNotEqual(transform(original), original)
                path.write_text(transform(original), encoding="utf-8")
                try:
                    self.assertEqual(self.criterion()["state"], "stale")
                finally:
                    path.write_text(original, encoding="utf-8")
        identity = execution_identity(self.root)
        for field in ("engine_sha256", "environment_sha256", "environment_observed"):
            with self.subTest(field=field), patch("aidp_agent_flow.progress.execution_identity",
                    return_value={**identity, field: False if field == "environment_observed" else "different"}):
                self.assertEqual(self.criterion()["state"], "stale")
        with patch("aidp_agent_flow.progress.__version__", "different"):
            self.assertEqual(self.criterion()["state"], "stale")

    def test_legacy_receipts_require_whole_plan_and_missing_plan_provenance_is_stale(self):
        run = self.selected_run()
        path = Path(run["artifact"])
        original = json.loads(path.read_text(encoding="utf-8"))
        legacy = deepcopy(original)
        del legacy["results"][0]["criterion_bindings"]
        path.write_text(json.dumps(legacy), encoding="utf-8")
        self.assertEqual(self.criterion()["state"], "passed")
        self.change_other_criterion()
        self.assertEqual(self.criterion()["state"], "stale")
        for plan_hash in (None, "", "bad-hash"):
            broken = deepcopy(original)
            if plan_hash is None:
                del broken["results"][0]["progress_plan_sha256"]
            else:
                broken["results"][0]["progress_plan_sha256"] = plan_hash
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.subTest(plan_hash=plan_hash):
                self.assertEqual(self.criterion()["state"], "stale")

    def test_exclusion_and_reactivation_preserve_history_and_require_new_evidence(self):
        self.selected_run()
        self.plan.update(version=2, revision=1, scope_decisions=[{
            "revision": 1, "node_id": "respond", "criterion_id": "graph-response",
            "state": "excluded", "reason": "Explicit scope decision", "authorization_ref": "review-1"}])
        self.save_plan()
        self.assertEqual(self.criterion()["state"], "excluded")
        self.plan["revision"] = 2
        self.plan["scope_decisions"].append({
            "revision": 2, "node_id": "respond", "criterion_id": "graph-response",
            "state": "active", "reason": "Restore required scope", "authorization_ref": "review-2"})
        self.save_plan()
        self.assertEqual(self.criterion()["state"], "stale")
        self.assertTrue(self.selected_run()["passed"])
        self.assertEqual(self.criterion()["state"], "passed")

    def test_unrelated_scope_decision_does_not_invalidate_selected_criterion(self):
        self.selected_run()
        self.plan.update(version=2, revision=1, scope_decisions=[{
            "revision": 1, "node_id": "respond", "criterion_id": "node-response",
            "state": "excluded", "reason": "Different criterion deferred", "authorization_ref": "review-1"}])
        self.save_plan()
        report = report_progress(self.root)
        self.assertEqual(self.criterion(report)["state"], "passed")
        self.assertTrue(self.criterion(report)["evidence_reused"])
        self.assertFalse(report["publication_ready"])

    def test_latest_failure_survives_unrelated_plan_changes(self):
        self.selected_run()
        self.change_other_criterion()
        original_run = subprocess.run

        def timeout(command, **kwargs):
            if command[1:3] == ["-m", "aidp_agent_flow.worker"]:
                raise subprocess.TimeoutExpired("worker", 1)
            return original_run(command, **kwargs)

        with patch("aidp_agent_flow.evaluation.subprocess.run", side_effect=timeout):
            failed = self.selected_run()
        self.assertFalse(failed["passed"])
        self.change_other_criterion()
        item = self.criterion()
        self.assertEqual(item["state"], "failed")
        self.assertTrue(item["evidence_reused"])
        self.assertEqual(item["evidence"], Path(failed["artifact"]).relative_to(self.root).as_posix())

    def test_reused_receipt_keeps_all_actually_visited_nodes_in_inventory(self):
        graph_path = self.root / "agent/core/graph.py"
        graph = graph_path.read_text(encoding="utf-8").replace(
            'graph.add_edge("respond", END)',
            'graph.add_node("audit", lambda state: {})\n    graph.add_edge("respond", "audit")\n    graph.add_edge("audit", END)')
        graph_path.write_text(graph, encoding="utf-8")
        case_path = self.root / "tests/cases.json"
        cases = json.loads(case_path.read_text(encoding="utf-8"))
        cases[0]["expected_nodes"] = ["respond", "audit"]
        case_path.write_text(json.dumps(cases), encoding="utf-8")
        self.assertTrue(self.selected_run()["passed"])
        self.change_other_criterion()
        report = report_progress(self.root)
        self.assertEqual(self.criterion(report)["state"], "passed")
        self.assertEqual(report["unplanned_observed_nodes"], ["audit"])
        self.assertFalse(report["scope_complete"])
        self.assertFalse(report["publication_ready"])


class NativeCriterionReuseTests(unittest.TestCase):
    setUp = native_fixtures.ProgressTests.setUp
    tearDown = native_fixtures.ProgressTests.tearDown
    write = native_fixtures.ProgressTests.write
    identity = native_fixtures.ProgressTests.identity
    native = native_fixtures.ProgressTests.native

    def test_node_review_reuses_but_integrated_agent_review_remains_whole_plan(self):
        self.plan["acceptance"] = [{**self.plan["nodes"][0]["criteria"][1], "id": "agent-check"}]
        self.write("node-progress.json", self.plan)
        receipt = self.native()
        record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Checked node")
        record_test_review(self.root, "__agent__", "agent-check", receipt, "accepted", "Checked whole agent")
        self.plan["nodes"][1]["implementation"] = "declared"
        self.write("node-progress.json", self.plan)
        report = report_progress(self.root)
        item = report["nodes"][0]["criteria"][1]
        self.assertEqual(item["state"], "passed")
        self.assertTrue(item["evidence_reused"])
        self.assertEqual(report["agent_acceptance"]["state"], "stale")
        self.assertFalse(report["publication_ready"])
        value = json.loads((self.root / receipt).read_text(encoding="utf-8"))
        value["answer"] = "Mutated after review"
        self.write(receipt, value)
        self.assertEqual(report_progress(self.root)["nodes"][0]["criteria"][1]["state"], "stale")

    def test_newer_rejection_remains_current_across_unrelated_plan_changes(self):
        receipt = self.native()
        record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Initially accepted")
        record_test_review(self.root, "respond", "native-positive", receipt, "rejected", "Observed rubric defect")
        self.plan["nodes"][1]["implementation"] = "declared"
        self.write("node-progress.json", self.plan)
        item = report_progress(self.root)["nodes"][0]["criteria"][1]
        self.assertEqual(item["state"], "failed")
        self.assertTrue(item["evidence_reused"])

    def test_native_review_without_fingerprint_keeps_legacy_plan_binding(self):
        receipt = self.native()
        record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Checked")
        path = next((self.root / ".aidp-local/progress/reviews").glob("*.json"))
        review = json.loads(path.read_text(encoding="utf-8"))
        del review["criterion_bindings"]
        path.write_text(json.dumps(review), encoding="utf-8")
        self.plan["nodes"][1]["implementation"] = "declared"
        self.write("node-progress.json", self.plan)
        self.assertEqual(report_progress(self.root)["nodes"][0]["criteria"][1]["state"], "stale")


if __name__ == "__main__":
    unittest.main()
