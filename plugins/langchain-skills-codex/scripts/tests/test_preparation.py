import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
from aidp_agent_flow.campaign import initialize_campaign, reserve_attempt, finish_attempt
from aidp_agent_flow.capacity import preview_capacity
from aidp_agent_flow.cases import validate_case
from aidp_agent_flow.diagnostics import FixtureContractError, ModelSetupError, ProviderInvocationError, failure_details
from aidp_agent_flow.evaluation import run_cases
from aidp_agent_flow.identity import execution_identity
from aidp_agent_flow.model import FixtureModel, OCIModel
from aidp_agent_flow.project import initialize, canonical_hash, FlowError


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / "validation-work")
        self.root = Path(self.temp.name) / "project"
        initialize(self.root, "Preparation", sync=False)
        self.policy = {"version": 1, "max_attempts": 2, "max_model_calls": 4,
                       "max_identical_trials": 1, "native_call_ceiling": 2,
                       "budget_usd": "2", "real_cost_ceiling_usd": "1", "native_cost_ceiling_usd": "1"}
        (self.root / "policy.json").write_text(json.dumps(self.policy))
        initialize_campaign(self.root, "policy.json")
        self.case = {"id": "case", "input": {}, "assertions": [{"path": "answer", "not_empty": True}]}

    def tearDown(self):
        self.temp.cleanup()

    def candidates(self, count=3):
        return [{"case_id": str(i), "experiment_sha256": canonical_hash(i)} for i in range(count)]

    def test_malformed_fixture_rejected_before_worker_or_reservation(self):
        for invalid in ("text", {"answer": "yes"}, [1], [{"content": "yes"}]):
            with self.subTest(invalid=invalid):
                (self.root / "cases.json").write_text(json.dumps([{**self.case, "model_responses": invalid}]))
                with patch("aidp_agent_flow.evaluation.subprocess.run") as worker:
                    with self.assertRaises(FixtureContractError):
                        run_cases(self.root, "cases.json", hypothesis="Check malformed fixture")
                    worker.assert_not_called()
        self.assertFalse((self.root / ".aidp-local/campaign/attempts").exists())

    def test_service_and_clock_contracts_rejected_before_execution(self):
        for extra in ({"service_records": "invalid"}, {"clock_at": "2026-11-04"}, {"trace_boundaries": 1}):
            with self.subTest(extra=extra), self.assertRaises(FlowError):
                validate_case({**self.case, **extra})

    def test_bad_second_case_prevents_first_case_reservation(self):
        (self.root / "cases.json").write_text(json.dumps([self.case,
            {**self.case, "id": "invalid", "model_responses": "not-a-list"}]))
        with patch("aidp_agent_flow.evaluation.reserve_attempt") as reserve:
            with self.assertRaises(FixtureContractError):
                run_cases(self.root, "cases.json", hypothesis="Validate the whole selection first")
            reserve.assert_not_called()

    def test_fixture_exhaustion_is_preparation_not_prompt_failure(self):
        model = FixtureModel([])
        with self.assertRaises(FixtureContractError) as caught:
            asyncio.run(model.complete("system", "question"))
        self.assertEqual(failure_details(caught.exception, "execution")["failure_code"], "fixture_contract")
        self.assertEqual(model.calls, 1)
        self.assertEqual(model.completed_responses, 0)

    def test_provider_status_does_not_invent_quota_or_expose_body(self):
        result = failure_details(ProviderInvocationError(429), "execution", real=True)
        self.assertEqual(result["provider_http_status"], 429)
        self.assertEqual(result["provider_cause"], "unverified")
        self.assertEqual(result["next_action"], "inspect_provider_evidence_before_retry")

    def test_local_setup_failure_is_not_classified_as_provider(self):
        model = OCIModel("never-read", "DEFAULT", {"region": "us-chicago-1",
                         "model_id": "synthetic", "compartment_id": "synthetic"})
        with patch.object(model, "_request", side_effect=FileNotFoundError("private path")):
            with self.assertRaises(ModelSetupError) as caught:
                asyncio.run(model.complete("system", "question"))
        self.assertEqual(failure_details(caught.exception, "execution")["failure_category"], "preparation")
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(model.completed_responses, 0)

    def test_capacity_forecast_uses_full_ceilings_and_does_not_mutate(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        result = preview_capacity(self.root, self.candidates(), real=True, model_calls=2)
        self.assertEqual(result["fits_at_reserved_ceilings"], ["0", "1"])
        self.assertEqual(result["not_planned"], ["2"])
        self.assertFalse(result["reservation_created"])
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_unknown_consumption_blocks_paid_forecast_but_not_fixture(self):
        key = reserve_attempt(self.root, case_id="old", experiment_sha256=canonical_hash("old"),
                              kind="real", model_calls=2, hypothesis="Check")
        (self.root / "evidence.json").write_text("{}")
        finish_attempt(self.root, key, {"passed": False, "error_type": "Timeout"}, "evidence.json")
        paid = preview_capacity(self.root, self.candidates(1), real=True, model_calls=2)
        self.assertEqual(paid["fits_at_reserved_ceilings"], [])
        self.assertIn("unresolved", paid["blocked_reason"])
        self.assertEqual(preview_capacity(self.root, self.candidates(1))["fits_at_reserved_ceilings"], ["0"])

    def test_forecast_and_admission_reject_the_same_invalid_reservations(self):
        for case_id, digest, calls in (("case", canonical_hash("case"), -1),
                                       ("x" * 129, canonical_hash("case"), 1),
                                       ("case", "not-a-digest", 1)):
            with self.subTest(case_id=case_id, calls=calls):
                preview = preview_capacity(self.root, [{"case_id": case_id,
                    "experiment_sha256": digest}], real=True, model_calls=calls)
                self.assertEqual(preview["fits_at_reserved_ceilings"], [])
                with self.assertRaises(FlowError) as rejected:
                    reserve_attempt(self.root, case_id=case_id, experiment_sha256=digest,
                                    kind="real", model_calls=calls, hypothesis="Check admission")
                self.assertEqual(preview["blocked_reason"], str(rejected.exception))
        self.assertFalse((self.root / ".aidp-local/campaign/attempts").exists())

    def test_plan_checks_contracts_without_importing_agent_or_reserving(self):
        (self.root / "cases.json").write_text(json.dumps([self.case]))
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)), \
             patch("aidp_agent_flow.identity.observe_local", return_value={"status": "observed"}), \
             patch("aidp_agent_flow.evaluation.subprocess.run") as worker:
            result = run_cases(self.root, "cases.json", plan=True)
            worker.assert_not_called()
        self.assertEqual(result["fits_at_reserved_ceilings"], ["case"])
        self.assertIn("provider_access", result["not_checked"])
        self.assertFalse((self.root / ".aidp-local/campaign/attempts").exists())

    def test_environment_declaration_change_invalidates_identity(self):
        with patch("aidp_agent_flow.identity.observe_local", return_value={"status": "unavailable"}):
            before = execution_identity(self.root)
            (self.root / "uv.lock").write_text("changed dependency declaration")
            after = execution_identity(self.root)
        self.assertEqual(before["engine_sha256"], after["engine_sha256"])
        self.assertNotEqual(before["environment_sha256"], after["environment_sha256"])

    def test_unobserved_environment_cannot_reserve_or_run(self):
        (self.root / "cases.json").write_text(json.dumps([self.case]))
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)), \
             patch("aidp_agent_flow.identity.observe_local", return_value={"status": "unavailable"}), \
             patch("aidp_agent_flow.evaluation.reserve_attempt") as reserve:
            with self.assertRaisesRegex(FlowError, "metadata is unavailable"):
                run_cases(self.root, "cases.json", hypothesis="Check unavailable environment")
            reserve.assert_not_called()
