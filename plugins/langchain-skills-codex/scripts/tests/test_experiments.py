import json
from pathlib import Path
import unittest

try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory

from aidp_agent_flow.experiments import compare_experiments, diagnose_experiment
from aidp_agent_flow.project import FlowError, initialize


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / "validation-work")
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Prompt experiments", sync=False)
        self.row = {"case_id": "positive", "passed": False, "case_sha256": "a" * 64,
                    "environment_observed": True, "engine_sha256": "1" * 64, "environment_sha256": "2" * 64,
                    "config_sha256": "b" * 64, "package_sha256": "c" * 64,
                    "evaluator_version": "0.4.5", "mode": "local_fixture_model", "experiment_sha256": "d" * 64,
                    "failure_stage": "assertions", "assertions": [{"path": "answer", "passed": False}],
                    "output": {"answer": "PRIVATE OUTPUT MUST NOT LEAK"}, "visited_nodes": ["draft"],
                    "model_calls": 1, "duration_seconds": 0.2}
        self.control = {"experiment_sha256": "d" * 64, "max_steps": 20, "timeout_seconds": 120,
                        "requested_model_settings": {"reasoning_effort": "LOW"}}

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, rows, controls=None):
        path = self.root / name
        path.write_text(json.dumps({"results": rows, "experiments": [self.control] if controls is None else controls}))
        return name

    def passed_row(self, **changes):
        return {**self.row, "passed": True, "assertions": [{"path": "answer", "passed": True}], **changes}

    def test_corrected_package_shows_assertion_gain_not_semantic_acceptance(self):
        self.write("before.json", [self.row])
        self.write("after.json", [self.passed_row(package_sha256="f" * 64)])
        result = compare_experiments(self.root, "before.json", "after.json")
        self.assertEqual(result["assertion_gains"], 1)
        self.assertFalse(result["semantic_acceptance"])
        self.assertNotIn("PRIVATE OUTPUT", json.dumps(result))

    def test_changed_criteria_model_evaluator_or_controls_do_not_claim_gain(self):
        self.write("before.json", [self.row])
        for change in ({"environment_observed": False}, {"engine_sha256": "f" * 64}, {"environment_sha256": "f" * 64}, {"case_sha256": "f" * 64}, {"config_sha256": "f" * 64},
                       {"evaluator_version": "0.4.6"}, {"mode": "local_real_oci_model"}):
            with self.subTest(change=change):
                self.write("after.json", [self.passed_row(**change)])
                self.assertEqual(compare_experiments(self.root, "before.json", "after.json")["comparable_cases"], 0)
        self.write("after.json", [self.passed_row()], [{**self.control, "timeout_seconds": 600}])
        self.assertEqual(compare_experiments(self.root, "before.json", "after.json")["assertion_gains"], 0)

    def test_control_regression_and_removed_case_remain_visible(self):
        self.write("before.json", [self.passed_row(), {**self.row, "case_id": "removed"}])
        self.write("after.json", [self.row])
        result = compare_experiments(self.root, "before.json", "after.json")
        self.assertEqual(result["regressions"], 1)
        self.assertEqual(result["cases"][1]["comparison"], "missing_candidate")

    def test_missing_identity_or_control_metadata_is_not_comparable(self):
        self.write("before.json", [self.row], [])
        self.write("after.json", [self.passed_row()])
        self.assertEqual(compare_experiments(self.root, "before.json", "after.json")["comparable_cases"], 0)

    def test_diagnosis_selects_first_layer_and_never_runs_an_agent(self):
        self.write("receipt.json", [{**self.row, "error_type": "Timeout"}])
        result = diagnose_experiment(self.root, "receipt.json", case_id="positive")
        self.assertEqual(result["cases"][0]["first_check"], "reconcile_execution_before_retry")
        self.assertFalse(result["agent_invoked"])
        self.assertEqual(result["cases"][0]["failed_assertions"], ["answer"])
        self.assertNotIn("PRIVATE OUTPUT", json.dumps(result))

    def test_duplicate_cases_and_escape_paths_fail(self):
        self.write("receipt.json", [self.row, self.row])
        with self.assertRaises(FlowError):
            diagnose_experiment(self.root, "receipt.json")
        with self.assertRaises(FlowError):
            diagnose_experiment(self.root, "../receipt.json")

    def test_malformed_assertions_nodes_or_identity_are_rejected(self):
        for change in ({"assertions": None}, {"assertions": [{"path": "answer", "passed": "yes"}]},
                       {"visited_nodes": {}}, {"case_sha256": {"fake": "identity"}}, {"evaluator_version": []}):
            with self.subTest(change=change):
                self.write("receipt.json", [{**self.row, **change}])
                with self.assertRaises(FlowError):
                    diagnose_experiment(self.root, "receipt.json")

    def test_passing_verdict_with_failed_assertion_is_rejected(self):
        self.write("before.json", [self.row])
        self.write("after.json", [{**self.row, "passed": True}])
        with self.assertRaises(FlowError):
            compare_experiments(self.root, "before.json", "after.json")


if __name__ == "__main__":
    unittest.main()
