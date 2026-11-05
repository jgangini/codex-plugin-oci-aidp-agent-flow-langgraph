import json
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory

from aidp_agent_flow.campaign import campaign_status, finish_attempt, reserve_attempt, require_campaign_clear, reconcile_attempt
from aidp_agent_flow.campaign_upgrade import upgrade_campaign
from aidp_agent_flow.project import FlowError, canonical_hash, initialize


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / "validation-work")
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Upgrade checks", sync=False)
        policy = {"version": 1, "max_attempts": 12, "max_model_calls": 100,
                  "max_identical_trials": 1, "native_call_ceiling": 83, "budget_usd": None,
                  "real_cost_ceiling_usd": None, "native_cost_ceiling_usd": None}
        (self.root / "test-campaign.json").write_text(json.dumps(policy))

    def tearDown(self):
        self.temporary.cleanup()

    def reserve(self, kind="real", calls=83, identity="trial"):
        return reserve_attempt(self.root, case_id=identity, experiment_sha256=canonical_hash(identity),
                               kind=kind, model_calls=calls, hypothesis="Reproduce a bounded failure")

    def unknown(self):
        attempt = self.reserve()
        path = self.root / ".aidp-local/campaign/attempts" / (attempt + ".json")
        row = json.loads(path.read_text())
        row.update(state="TERMINAL_USAGE_UNKNOWN", decision="terminal worker verified; usage unknown")
        path.write_text(json.dumps(row))
        return path

    def test_terminal_usage_unknown_retains_83_calls_and_only_admits_zero_call_fixture(self):
        path = self.unknown()
        before = path.read_bytes()
        status = campaign_status(self.root)
        self.assertEqual(status["model_calls_used_or_reserved"], 83)
        self.assertEqual(len(status["unresolved_attempts"]), 1)
        with self.assertRaises(FlowError):
            self.reserve(calls=1, identity="paid-retry")
        with self.assertRaises(FlowError):
            require_campaign_clear(self.root)
        fixture = self.reserve(kind="fixture", calls=0, identity="recorded-replay")
        finish_attempt(self.root, fixture, {"passed": True, "model_calls": 3}, "recorded.json")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(campaign_status(self.root)["model_calls_used_or_reserved"], 83)

    def test_partial_counts_do_not_release_unknown_reservation(self):
        path = self.unknown()
        row = json.loads(path.read_text())
        row.update(model_calls=2, cost_usd="1", reserved_cost_usd="5")
        path.write_text(json.dumps(row))
        status = campaign_status(self.root)
        self.assertEqual(status["model_calls_used_or_reserved"], 83)
        self.assertEqual(status["cost_used_or_reserved_usd"], "5")

    def test_unknown_state_and_malformed_accounting_fail_closed_including_fixture(self):
        path = self.unknown()
        original = json.loads(path.read_text())
        for change in ({"state": "FUTURE_UNKNOWN"}, {"reserved_model_calls": -1},
                       {"reserved_model_calls": True}, {"model_calls": -2}, {"history": {}},
                       {"id": "0" * 32}, {"kind": "fixture"}, {"reserved_cost_usd": "NaN"}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**original, **change}))
                with self.assertRaises(FlowError):
                    self.reserve(kind="fixture", calls=0, identity="offline")
                with self.assertRaises(FlowError):
                    upgrade_campaign(self.root)

    def test_inspection_does_not_mutate_and_apply_appends_only_adoption(self):
        path = self.unknown()
        policy = self.root / "test-campaign.json"
        history, limits = path.read_bytes(), policy.read_bytes()
        plan = upgrade_campaign(self.root)
        self.assertFalse((self.root / ".aidp-local/campaign/upgrades").exists())
        self.assertFalse(plan["adoption_blocked"])
        result = upgrade_campaign(self.root, apply=True, expected_snapshot=plan["adoption_sha256"])
        self.assertTrue(result["applied"])
        self.assertFalse(result["historical_acceptance_transferred"])
        self.assertFalse(result["project_supplements_verified"])
        self.assertEqual(path.read_bytes(), history)
        self.assertEqual(policy.read_bytes(), limits)
        self.assertTrue(Path(result["artifact"]).is_file())
        with self.assertRaises(FlowError):
            self.reserve(calls=1, identity="after-upgrade")

    def test_submitted_attempt_prevents_apply(self):
        self.reserve()
        plan = upgrade_campaign(self.root)
        self.assertTrue(plan["adoption_blocked"])
        with self.assertRaises(FlowError):
            upgrade_campaign(self.root, apply=True, expected_snapshot=plan["adoption_sha256"])

    def test_malformed_historical_version_does_not_expose_its_contents(self):
        folder = self.root / ".aidp-local/runs"
        folder.mkdir(parents=True)
        (folder / "old.json").write_text(json.dumps({"results": [
            {"evaluator_version": {"password": "private-canary"}},
            {"evaluator_version": "private arbitrary value"}, {"evaluator_version": "0.4.3"}]}))
        plan = upgrade_campaign(self.root)
        self.assertEqual(plan["historical_receipt_versions"]["local_runs"], {"0.4.3": 1, "invalid_metadata": 2})
        result = upgrade_campaign(self.root, apply=True, expected_snapshot=plan["adoption_sha256"])
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("private", Path(result["artifact"]).read_text())

    def test_invalid_fixture_reconciliation_preserves_ledger(self):
        attempt = self.reserve(kind="fixture", calls=0)
        path = self.root / ".aidp-local/campaign/attempts" / (attempt + ".json")
        before = path.read_bytes()
        (self.root / "proof.json").write_text('{}')
        with self.assertRaises(FlowError):
            reconcile_attempt(self.root, attempt, model_calls=1, cost_usd=None,
                              evidence="proof.json", note="Fixture cannot have paid calls")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(campaign_status(self.root)["model_calls_used_or_reserved"], 0)

    def test_concurrent_policy_or_engine_change_rejects_old_plan(self):
        plan = upgrade_campaign(self.root)
        with patch("aidp_agent_flow.campaign_upgrade.engine_identity", return_value={"version": "future", "sha256": "a" * 64}):
            with self.assertRaises(FlowError):
                upgrade_campaign(self.root, apply=True, expected_snapshot=plan["adoption_sha256"])
        policy = self.root / "test-campaign.json"
        row = json.loads(policy.read_text())
        row["max_attempts"] += 1
        policy.write_text(json.dumps(row))
        with self.assertRaises(FlowError):
            upgrade_campaign(self.root, apply=True, expected_snapshot=plan["adoption_sha256"])

    def test_old_receipts_are_historical_and_unchanged(self):
        path = self.root / ".aidp-local/runs/older.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"results": [{"case_id": "kept", "passed": True, "evaluator_version": "0.4.3"}]}))
        before = path.read_bytes()
        plan = upgrade_campaign(self.root)
        self.assertEqual(plan["historical_receipt_versions"]["local_runs"], {"0.4.3": 1})
        upgrade_campaign(self.root, apply=True, expected_snapshot=plan["adoption_sha256"])
        self.assertEqual(path.read_bytes(), before)

    def test_native_receipts_remain_a_separate_history(self):
        folder = self.root / ".aidp-local/invocations"
        folder.mkdir(parents=True)
        (folder / "old.json").write_text(json.dumps({"evaluator_version": "0.4.3", "state": "RESPONDED"}))
        plan = upgrade_campaign(self.root)
        self.assertEqual(plan["historical_receipt_versions"]["native_invocations"], {"0.4.3": 1})
        self.assertEqual(plan["historical_receipt_versions"]["local_runs"], {})
        self.assertFalse(plan["native_test_accepted"])


if __name__ == "__main__":
    unittest.main()
