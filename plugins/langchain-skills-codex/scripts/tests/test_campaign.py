import json
from pathlib import Path
import subprocess
import sys
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
import unittest
from unittest.mock import patch

from aidp_agent_flow.campaign import campaign_status, finish_attempt, initialize_campaign, reconcile_attempt, require_campaign_clear, reserve_attempt
from aidp_agent_flow.evaluation import run_cases
from aidp_agent_flow.project import FlowError, canonical_hash, initialize


class CampaignTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Campaign checks", sync=False)
        self.policy = {"version": 1, "max_attempts": 10, "max_model_calls": 10, "max_identical_trials": 1,
            "native_call_ceiling": 2, "budget_usd": "5", "real_cost_ceiling_usd": "1", "native_cost_ceiling_usd": "2"}
        self.write("policy.json", self.policy)
        initialize_campaign(self.root, "policy.json")
        self.write("evidence.json", {"observation": "Synthetic reviewed result"})

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, value):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value), encoding="utf-8")

    def configure(self, **values):
        self.policy.update(values)
        self.write("test-campaign.json", self.policy)

    def reserve(self, identity="first", **values):
        options = {"case_id": "positive", "experiment_sha256": canonical_hash(identity), "kind": "real",
                   "model_calls": 2, "hypothesis": "Test the corrected behavior"}
        options.update(values)
        return reserve_attempt(self.root, **options)

    def finish(self, attempt, **result):
        finish_attempt(self.root, attempt, {"passed": True, "model_calls": 1, **result}, "evidence.json")

    def test_missing_hypothesis_stops_before_admission(self):
        with self.assertRaises(FlowError):
            self.reserve(hypothesis=None)
        self.assertEqual(campaign_status(self.root)["attempts"], [])

    def test_identical_trial_needs_reason_and_stays_within_repetition_limit(self):
        self.configure(max_identical_trials=2)
        self.finish(self.reserve())
        with self.assertRaises(FlowError):
            self.reserve(hypothesis="A reworded hypothesis does not change the experiment")
        self.finish(self.reserve(repeat_reason="Second of two declared stochastic trials"))
        with self.assertRaises(FlowError):
            self.reserve(repeat_reason="Third trial would exceed the declared limit")

    def test_submitted_attempt_blocks_another_case(self):
        self.reserve()
        with self.assertRaises(FlowError):
            self.reserve("different")

    def test_timeout_keeps_calls_and_cost_reservations_until_reconciled(self):
        attempt = self.reserve()
        self.finish(attempt, passed=False, error_type="Timeout", model_calls=None)
        status = campaign_status(self.root)
        self.assertEqual(status["unresolved_attempts"], [attempt])
        self.assertEqual(status["model_calls_used_or_reserved"], 2)
        self.assertEqual(status["cost_used_or_reserved_usd"], "1")
        with self.assertRaises(FlowError):
            self.reserve("different")
        reconcile_attempt(self.root, attempt, model_calls=1, cost_usd="0.25", evidence="evidence.json", note="Reconciled synthetic usage")
        self.assertEqual(campaign_status(self.root)["unresolved_attempts"], [])
        self.reserve("different")

    def test_finite_budget_reserves_unknown_cost_instead_of_treating_it_as_zero(self):
        self.configure(budget_usd="1.5")
        self.finish(self.reserve())
        self.assertEqual(campaign_status(self.root)["unknown_cost_attempts"], 1)
        with self.assertRaises(FlowError):
            self.reserve("second")

    def test_finite_budget_cannot_admit_an_unpriced_attempt(self):
        self.configure(real_cost_ceiling_usd=None)
        with self.assertRaises(FlowError):
            self.reserve()
        self.assertEqual(campaign_status(self.root)["attempts"], [])

    def test_new_finite_budget_cannot_hide_previous_unpriced_consumption(self):
        self.configure(budget_usd=None, real_cost_ceiling_usd=None)
        attempt = self.reserve()
        self.finish(attempt)
        self.assertEqual(campaign_status(self.root)["unpriced_attempts"], 1)
        self.configure(budget_usd="5", real_cost_ceiling_usd="1")
        with self.assertRaises(FlowError):
            self.reserve("second")

    def test_accumulated_model_call_limit_blocks_before_start(self):
        self.configure(max_model_calls=2)
        self.finish(self.reserve(), model_calls=2)
        with self.assertRaises(FlowError):
            self.reserve("second")

    def test_fixture_adapter_calls_do_not_spend_real_model_budget(self):
        self.configure(max_model_calls=0, budget_usd="0")
        self.finish(self.reserve(kind="fixture", model_calls=0), model_calls=3)
        self.assertEqual(campaign_status(self.root)["model_calls_used_or_reserved"], 0)
        self.finish(self.reserve("second", kind="fixture", model_calls=0), model_calls=2)

    def test_terminal_uncertainty_allows_fixture_without_changing_history(self):
        attempt = self.reserve()
        self.finish(attempt, passed=False, error_type="Timeout", model_calls=None)
        receipt = self.root / ".aidp-local/campaign/attempts" / (attempt + ".json")
        before = receipt.read_bytes()
        fixture = self.reserve("offline-reproduction", kind="fixture", model_calls=0)
        self.finish(fixture, model_calls=3)
        status = campaign_status(self.root)
        self.assertEqual(receipt.read_bytes(), before)
        self.assertEqual(status["unresolved_attempts"], [attempt])
        self.assertEqual(status["model_calls_used_or_reserved"], 2)
        self.assertEqual(status["cost_used_or_reserved_usd"], "1")
        with self.assertRaises(FlowError):
            require_campaign_clear(self.root)
        for kind in ("real", "native"):
            with self.subTest(kind=kind), self.assertRaises(FlowError):
                self.reserve("paid-retry-" + kind, kind=kind)

    def test_submitted_owner_still_blocks_fixture(self):
        self.reserve()
        with self.assertRaises(FlowError):
            self.reserve("offline", kind="fixture", model_calls=0)

    def test_fixture_cannot_relabel_a_paid_call_reservation(self):
        with self.assertRaises(FlowError):
            self.reserve(kind="fixture", model_calls=1)
        self.assertEqual(campaign_status(self.root)["attempts"], [])

    def test_exhausted_calls_and_costs_do_not_block_offline_fixture(self):
        attempt = self.reserve()
        self.finish(attempt)
        reconcile_attempt(self.root, attempt, model_calls=12, cost_usd="7",
            evidence="evidence.json", note="Record actual synthetic usage beyond the original ceiling")
        before = campaign_status(self.root)
        self.finish(self.reserve("offline", kind="fixture", model_calls=0))
        after = campaign_status(self.root)
        self.assertEqual(after["model_calls_used_or_reserved"], before["model_calls_used_or_reserved"])
        self.assertEqual(after["cost_used_or_reserved_usd"], before["cost_used_or_reserved_usd"])
        for kind in ("real", "native"):
            with self.subTest(kind=kind), self.assertRaises(FlowError):
                self.reserve("paid-" + kind, kind=kind)

    def test_unpriced_history_allows_fixture_but_not_finite_budget_paid_work(self):
        self.configure(budget_usd=None, real_cost_ceiling_usd=None)
        self.finish(self.reserve())
        self.configure(budget_usd="5", real_cost_ceiling_usd="1")
        self.finish(self.reserve("offline", kind="fixture", model_calls=0))
        self.assertEqual(campaign_status(self.root)["unpriced_attempts"], 1)
        for kind in ("real", "native"):
            with self.subTest(kind=kind), self.assertRaises(FlowError):
                self.reserve("paid-" + kind, kind=kind)

    def test_offline_exception_preserves_attempt_and_identical_trial_limits(self):
        attempt = self.reserve()
        self.finish(attempt, passed=False, error_type="Timeout", model_calls=None)
        self.configure(max_attempts=2)
        self.finish(self.reserve("offline", kind="fixture", model_calls=0))
        with self.assertRaises(FlowError):
            self.reserve("another-offline", kind="fixture", model_calls=0)
        self.configure(max_attempts=3)
        with self.assertRaises(FlowError):
            self.reserve("offline", kind="fixture", model_calls=0,
                         repeat_reason="A rationale does not override the identical-trial ceiling")

    def test_actual_overspend_is_recorded_truthfully_and_blocks_future_attempts(self):
        attempt = self.reserve()
        self.finish(attempt)
        status = reconcile_attempt(self.root, attempt, model_calls=2, cost_usd="7", evidence="evidence.json", note="Record actual synthetic charge")
        self.assertEqual(status["cost_used_or_reserved_usd"], "7")
        with self.assertRaises(FlowError):
            self.reserve("second")

    def test_evidence_parent_path_and_linked_journal_are_rejected(self):
        with self.assertRaises(FlowError):
            self.reserve(evidence=["../outside.json"])
        with patch.object(Path, "is_symlink", lambda path: path.name == ".aidp-local"):
            with self.assertRaises(FlowError):
                self.reserve()

    def test_existing_lock_is_not_deleted_by_a_second_owner(self):
        lock = self.root / ".aidp-local/campaign/lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("other owner", encoding="utf-8")
        with self.assertRaises(FlowError):
            self.reserve()
        self.assertEqual(lock.read_text(encoding="utf-8"), "other owner")

    def test_policy_rejects_boolean_limits_and_nonfinite_costs(self):
        for field, value in (("max_attempts", True), ("budget_usd", "NaN"), ("max_model_calls", -1)):
            bad = dict(self.policy, **{field: value})
            self.write("test-campaign.json", bad)
            with self.subTest(field=field), self.assertRaises(FlowError):
                campaign_status(self.root)

    def test_partial_batch_retains_completed_receipt_when_next_attempt_is_denied(self):
        self.configure(max_attempts=1, max_model_calls=0)
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, "tests/cases.json", hypothesis="Check fixture mechanics")
        self.assertFalse(result["passed"])
        self.assertTrue(result["cases"][0]["passed"])
        self.assertEqual(len(result["cases"]), 1)
        self.assertTrue(Path(result["artifact"]).is_file())
        self.assertEqual(result["not_run"], ["node-fixture"])
        self.assertEqual(campaign_status(self.root)["attempts"][0]["targets"], ["respond/graph-response"])

    def test_failed_completion_keeps_execution_receipt_and_blocks_retry(self):
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)), \
                patch("aidp_agent_flow.evaluation.finish_attempt", side_effect=OSError("synthetic failure")):
            result = run_cases(self.root, "tests/cases.json", selected=["graph-fixture"], hypothesis="Check result preservation")
        self.assertFalse(result["passed"])
        self.assertTrue(result["cases"][0]["passed"])
        self.assertTrue(Path(result["artifact"]).is_file())
        self.assertEqual(len(campaign_status(self.root)["unresolved_attempts"]), 1)
        with self.assertRaises(FlowError):
            self.reserve("second")

    def test_real_run_without_policy_never_starts_worker(self):
        other = Path(self.temporary.name) / "no-policy"
        initialize(other, "No policy", sync=False)
        with patch("aidp_agent_flow.evaluation.subprocess.run") as process:
            with self.assertRaises(FlowError):
                run_cases(other, "tests/cases.json", selected=["graph-fixture"], real=True)
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
