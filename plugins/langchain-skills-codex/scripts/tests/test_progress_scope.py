from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from . import test_progress as fixtures
except ImportError:
    import test_progress as fixtures

from aidp_agent_flow.identity import execution_identity
from aidp_agent_flow.progress import load_progress_plan, record_test_review, report_progress, require_publication_acceptance
from aidp_agent_flow.project import FlowError, canonical_hash


class ProgressScopeTests(unittest.TestCase):
    tearDown = fixtures.ProgressTests.tearDown
    write = fixtures.ProgressTests.write
    identity = fixtures.ProgressTests.identity
    local = fixtures.ProgressTests.local
    native = fixtures.ProgressTests.native

    def setUp(self):
        fixtures.ProgressTests.setUp(self)
        report_progress(self.root)

    def decide(self, criterion="local-positive", *, node="respond", state="excluded", revision=1):
        self.plan.update(version=2, revision=revision)
        self.plan.setdefault("scope_decisions", []).append({
            "revision": revision, "node_id": node, "criterion_id": criterion, "state": state,
            "reason": "Deferred by the reviewed release scope", "authorization_ref": "docs/acceptance.md#decision-17"})
        self.write("node-progress.json", self.plan)

    def test_exclusion_keeps_inventory_history_and_skips_next_criterion(self):
        receipt = self.local()
        before = report_progress(self.root)
        prior = deepcopy(self.plan)
        self.decide()
        report = report_progress(self.root)
        node = report["nodes"][0]
        item = node["criteria"][0]
        self.assertEqual(item["state"], "excluded")
        self.assertIsNone(item["evidence"])
        self.assertEqual(item["historical_pass"]["evidence"], receipt.relative_to(self.root).as_posix())
        self.assertEqual(item["historical_pass"]["progress_plan_sha256"], canonical_hash(prior))
        self.assertEqual(node["next_criterion"], "native-positive")
        self.assertEqual(node["validation"]["required_count"], 1)
        self.assertEqual(node["validation"]["excluded_count"], 1)
        self.assertEqual(node["validation"]["inventoried_count"], 2)
        self.assertEqual(node["validation"]["approved_count"], 0)
        snapshot = json.loads((self.root / before["plan_snapshot"]).read_text(encoding="utf-8"))
        self.assertEqual(snapshot["plan"], prior)
        table = Path(report["table"]).read_text(encoding="utf-8")
        for text in ("excluded", "decision-17", "Deferred by", "scope revision 1", "2 inventoried"):
            self.assertIn(text, table)

    def test_all_excluded_has_no_active_percentage_or_next_criterion(self):
        self.decide()
        self.decide("native-positive")
        node = report_progress(self.root)["nodes"][0]
        self.assertEqual(node["state"], "excluded")
        self.assertIsNone(node["next_criterion"])
        self.assertIsNone(node["validation"]["percent"])
        self.assertEqual(node["validation"]["required"], 0)
        self.assertEqual(node["validation"]["excluded"], 2)
        self.assertEqual(node["validation"]["inventoried"], 2)

    def test_new_pass_for_excluded_scope_never_earns_credit(self):
        self.decide()
        receipt = self.local()
        report = report_progress(self.root)
        item = report["nodes"][0]["criteria"][0]
        self.assertEqual(item["state"], "excluded")
        self.assertIsNone(item["evidence"])
        self.assertEqual(item["historical_pass"]["evidence"], receipt.relative_to(self.root).as_posix())
        self.assertEqual(item["historical_pass"]["engine_sha256"], report["engine_sha256"])
        self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)
        snapshots = list((self.root / ".aidp-local/progress/plans").glob("*.json"))
        report_progress(self.root)
        self.assertEqual(list((self.root / ".aidp-local/progress/plans").glob("*.json")), snapshots)

    def test_scope_decisions_require_reason_authorization_and_revision(self):
        self.decide()
        valid = deepcopy(self.plan)
        for field, values in (("reason", [None, "", " "]), ("authorization_ref", [None, "", " "]),
                              ("revision", [None, 0, True, 2]), ("state", ["passed", "optional"]),
                              ("node_id", ["missing"]), ("criterion_id", ["missing"])):
            for value in values:
                with self.subTest(field=field, value=value):
                    broken = deepcopy(valid)
                    broken["scope_decisions"][0][field] = value
                    self.write("node-progress.json", broken)
                    with self.assertRaises(FlowError):
                        load_progress_plan(self.root)
        self.write("node-progress.json", {**valid, "revision": True})
        with self.assertRaises(FlowError):
            load_progress_plan(self.root)

    def test_unknown_and_legacy_exclusion_annotations_are_rejected(self):
        for version in (1, 2):
            valid = deepcopy(self.plan)
            if version == 2:
                valid.update(version=2, revision=1, scope_decisions=[])
            for location in ("plan", "node", "criterion"):
                for name in ("excluded", "optional", "scope_decison"):
                    with self.subTest(version=version, location=location, name=name):
                        broken = deepcopy(valid)
                        target = (broken if location == "plan" else broken["nodes"][0] if location == "node"
                                  else broken["nodes"][0]["criteria"][0])
                        target[name] = True
                        self.write("node-progress.json", broken)
                        with self.assertRaisesRegex(FlowError, "Unsupported"):
                            load_progress_plan(self.root)
        self.decide()
        self.plan["scope_decisions"][0]["authorized"] = True
        self.write("node-progress.json", self.plan)
        with self.assertRaisesRegex(FlowError, "Unsupported"):
            load_progress_plan(self.root)

    def test_prior_scope_history_cannot_be_rewritten_or_revision_reused(self):
        self.decide()
        report = report_progress(self.root)
        original_report = Path(report["artifact"]).read_bytes()
        valid = deepcopy(self.plan)
        variants = []
        altered = deepcopy(valid)
        altered["requirements_ref"] = "new-authority.md"
        variants.append(altered)
        altered = deepcopy(valid)
        altered["revision"] = 2
        altered["scope_decisions"][0]["reason"] = "Rewritten history"
        variants.append(altered)
        altered = deepcopy(valid)
        altered.update(revision=2, scope_decisions=[])
        variants.append(altered)
        variants.append({key: value for key, value in {**valid, "version": 1}.items()
                         if key not in ("revision", "scope_decisions")})
        for changed in variants:
            with self.subTest(changed=changed):
                self.write("node-progress.json", changed)
                with self.assertRaises(FlowError):
                    report_progress(self.root)
                self.assertEqual(Path(report["artifact"]).read_bytes(), original_report)

    def test_reactivation_appends_history_and_needs_new_evidence(self):
        self.local()
        self.decide()
        excluded = report_progress(self.root)
        self.decide(state="active", revision=2)
        active = report_progress(self.root)
        item = active["nodes"][0]["criteria"][0]
        self.assertEqual(item["state"], "stale")
        self.assertEqual(len(active["scope_decisions"]), 2)
        self.assertTrue((self.root / excluded["plan_snapshot"]).exists())
        self.local(second=2)
        self.assertEqual(report_progress(self.root)["nodes"][0]["criteria"][0]["state"], "passed")

    def test_reported_inventory_cannot_lose_node_or_agent_criteria(self):
        self.plan["acceptance"] = [{"id": "required-agent", "description": "Mandatory integrated acceptance",
                                    "layer": "TEST", "case_id": "native-positive"}]
        self.write("node-progress.json", self.plan)
        report_progress(self.root)
        for prior_version in (1, 2):
            if prior_version == 2:
                self.plan.update(version=2, revision=1, scope_decisions=[])
                self.write("node-progress.json", self.plan)
                report_progress(self.root)
            for target in ("node", "criterion", "acceptance"):
                with self.subTest(prior_version=prior_version, target=target):
                    changed = deepcopy(self.plan)
                    changed.update(version=2, revision=2, scope_decisions=[])
                    if target == "node":
                        changed["nodes"] = changed["nodes"][1:]
                    elif target == "criterion":
                        changed["nodes"][0]["criteria"].pop(0)
                    else:
                        changed["acceptance"] = []
                    self.write("node-progress.json", changed)
                    with self.assertRaisesRegex(FlowError, "retain prior criterion IDs"):
                        report_progress(self.root)
            self.write("node-progress.json", self.plan)

    def test_legacy_edits_remain_valid_and_migration_uses_last_reported_inventory(self):
        original = deepcopy(self.plan)
        self.plan["nodes"][0]["criteria"].pop(0)
        self.write("node-progress.json", self.plan)
        report_progress(self.root)
        shortened = deepcopy(self.plan)
        self.write("node-progress.json", original)
        report_progress(self.root)
        migration = {**shortened, "version": 2, "revision": 1, "scope_decisions": []}
        self.write("node-progress.json", migration)
        with self.assertRaisesRegex(FlowError, "retain prior criterion IDs"):
            report_progress(self.root)
        self.write("node-progress.json", shortened)
        report_progress(self.root)
        self.write("node-progress.json", migration)
        self.assertEqual(report_progress(self.root)["plan_version"], 2)

    def test_migration_rejects_malformed_last_report_pointer(self):
        for record in ([], {}, {"progress_plan_sha256": "missing-snapshot"}):
            with self.subTest(record=record):
                self.write(".aidp-local/progress/report.json", record)
                self.plan.update(version=2, revision=1, scope_decisions=[])
                self.write("node-progress.json", self.plan)
                with self.assertRaises(FlowError):
                    report_progress(self.root)

    def test_excluded_acceptance_blocks_publication_with_all_active_criteria_passed(self):
        self.plan["nodes"] = self.plan["nodes"][:1]
        self.plan["acceptance"] = [{"id": "integrated", "description": "Required integration rubric",
                                    "layer": "TEST", "case_id": "native-positive"}]
        self.decide("integrated", node="__agent__")
        receipt = self.native()
        self.local()
        report = record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Reviewed")
        self.assertEqual(report["nodes"][0]["state"], "accepted")
        self.assertEqual(report["agent_acceptance"]["state"], "excluded")
        self.assertTrue(report["publication_scope_blocked"])
        self.assertFalse(report["publication_ready"])
        with self.assertRaisesRegex(FlowError, "exclusions"):
            require_publication_acceptance(self.root, [])
        with self.assertRaisesRegex(FlowError, "Excluded"):
            record_test_review(self.root, "__agent__", "integrated", receipt, "accepted", "Cannot override scope")

    def test_snapshot_limits_and_links_fail_without_overwriting_report(self):
        report = report_progress(self.root)
        original = Path(report["artifact"]).read_bytes()
        self.decide()
        with patch("aidp_agent_flow.progress._MAX_HISTORY_BYTES", 1):
            with self.assertRaises(FlowError):
                report_progress(self.root)
        with patch.object(Path, "is_symlink", lambda path: path.name == "plans"):
            with self.assertRaises(FlowError):
                report_progress(self.root)
        self.assertEqual(Path(report["artifact"]).read_bytes(), original)

    def test_same_version_engine_change_makes_pass_historical(self):
        self.local()
        current = execution_identity(self.root)
        changed = {**current, "engine_sha256": "f" * 64 if current["engine_sha256"] != "f" * 64 else "e" * 64}
        with patch("aidp_agent_flow.progress.execution_identity", return_value=changed):
            report = report_progress(self.root)
        item = report["nodes"][0]["criteria"][0]
        self.assertEqual(item["state"], "stale")
        self.assertEqual(item["stale_reasons"], ["changed_engine_sha256"])
        self.assertEqual(item["historical_pass"]["engine_sha256"], current["engine_sha256"])
        self.assertEqual(report["engine_sha256"], changed["engine_sha256"])
        self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)

    def test_legacy_receipts_without_engine_identity_remain_historical(self):
        path = self.local()
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["results"][0].pop("engine_sha256")
        receipt["results"][0].pop("environment_sha256")
        path.write_text(json.dumps(receipt), encoding="utf-8")
        item = report_progress(self.root)["nodes"][0]["criteria"][0]
        self.assertEqual(item["state"], "stale")
        self.assertEqual(set(item["stale_reasons"]), {"missing_engine_sha256", "missing_environment_sha256"})
        self.assertIsNotNone(item["historical_pass"])

    def test_unobserved_local_receipt_never_earns_current_credit(self):
        self.local(environment_observed=False)
        item = report_progress(self.root)["nodes"][0]["criteria"][0]
        self.assertEqual(item["state"], "stale")
        self.assertIn("changed_environment_observed", item["stale_reasons"])
        self.assertFalse(item["historical_pass"]["environment_observed"])
        with patch("aidp_agent_flow.identity.observe_local", return_value={
                "status": "unavailable", "python": None, "packages": {}}):
            self.local(second=2)
            report = report_progress(self.root)
        self.assertFalse(report["environment_observed"])
        self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)
        self.assertIn("environment_observation_unavailable", report["nodes"][0]["criteria"][0]["stale_reasons"])

    def test_native_review_allows_explicitly_unobserved_local_harness(self):
        with patch("aidp_agent_flow.identity.observe_local", return_value={
                "status": "unavailable", "python": None, "packages": {}}):
            receipt = self.native()
            report = record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Native rubric reviewed")
        self.assertFalse(report["environment_observed"])
        self.assertEqual(report["nodes"][0]["TEST"]["approved_count"], 1)
        self.assertEqual(report["nodes"][0]["local"]["approved_count"], 0)
        self.assertFalse(report["publication_ready"])

    def test_native_review_requires_current_execution_identity(self):
        receipt = self.native()
        current = execution_identity(self.root)
        changed = {**current, "environment_sha256": "f" * 64}
        with patch("aidp_agent_flow.progress.execution_identity", return_value=changed):
            with self.assertRaises(FlowError):
                record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Wrong runtime")
        report = record_test_review(self.root, "respond", "native-positive", receipt, "accepted", "Reviewed")
        review_path = report["nodes"][0]["criteria"][1]["evidence"]
        review = json.loads((self.root / review_path).read_text(encoding="utf-8"))
        self.assertEqual({key: review[key] for key in current}, current)
        with patch("aidp_agent_flow.progress.execution_identity", return_value=changed):
            item = report_progress(self.root)["nodes"][0]["criteria"][1]
        self.assertEqual(item["state"], "stale")
        self.assertEqual(item["historical_pass"]["environment_sha256"], current["environment_sha256"])


if __name__ == "__main__":
    unittest.main()
