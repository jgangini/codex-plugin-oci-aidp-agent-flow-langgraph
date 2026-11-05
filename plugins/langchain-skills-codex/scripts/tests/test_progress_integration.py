from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from aidp_agent_flow.cli import main
from aidp_agent_flow.campaign import initialize_campaign
from aidp_agent_flow.evaluation import run_cases
from aidp_agent_flow.progress import report_progress
from aidp_agent_flow.project import FlowError, initialize


class ProgressIntegrationTests(unittest.TestCase):
    def setUp(self):
        executable = patch("aidp_agent_flow.identity.python_path", return_value=Path(sys.executable))
        executable.start()
        self.addCleanup(executable.stop)
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Node progress", sync=False)

    def tearDown(self):
        self.temporary.cleanup()

    def selected_run(self):
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            return run_cases(self.root, "tests/cases.json", selected=["graph-fixture"])

    def test_selected_test_automatically_refreshes_table_without_TEST_acceptance(self):
        result = self.selected_run()
        self.assertTrue(result["passed"], result)
        node = result["progress"]["nodes"][0]
        self.assertEqual(node["local"]["percent"], 50)
        self.assertEqual(node["TEST"]["percent"], 0)
        self.assertAlmostEqual(node["validation"]["percent"], 100 / 3, places=1)
        self.assertFalse(result["progress"]["native_test_accepted"])
        self.assertTrue((self.root / ".aidp-local/progress/table.md").is_file())
        receipt = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))
        case = receipt["results"][0]
        self.assertTrue(case["recorded_at"].endswith("+00:00"))
        self.assertEqual(len(case["progress_plan_sha256"]), 64)

    def test_timeout_reopens_previous_pass_in_same_case_and_revision(self):
        self.assertTrue(self.selected_run()["passed"])
        original_run = subprocess.run

        def worker_timeout(command, **kwargs):
            if command[1:3] == ["-m", "aidp_agent_flow.worker"]:
                raise subprocess.TimeoutExpired("worker", 1)
            return original_run(command, **kwargs)

        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)), \
                patch("aidp_agent_flow.evaluation.subprocess.run", side_effect=worker_timeout):
            result = run_cases(self.root, "tests/cases.json", selected=["graph-fixture"], timeout=1)
        self.assertFalse(result["passed"])
        node = result["progress"]["nodes"][0]
        self.assertEqual(node["local"]["percent"], 0)
        self.assertEqual(node["state"], "failed")

    def test_package_edit_invalidates_existing_credit_without_running_again(self):
        self.selected_run()
        source = self.root / "agent/core/graph.py"
        source.write_text(source.read_text(encoding="utf-8") + "\n# Changed candidate\n", encoding="utf-8")
        result = report_progress(self.root)
        self.assertEqual(result["nodes"][0]["state"], "stale")
        self.assertEqual(result["nodes"][0]["validation"]["percent"], 0)

    def test_cli_report_runs_without_signing_or_network(self):
        output = io.StringIO()
        with patch("aidp_agent_flow.remote.signer_for", side_effect=AssertionError("No signing")), redirect_stdout(output):
            code = main(["--project", str(self.root), "--json", "progress", "report"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())["result"]
        self.assertEqual(result["nodes"][0]["state"], "pending")
        self.assertEqual(result["nodes"][0]["validation"]["percent"], 0)

    def test_external_requirements_reference_is_preserved_without_opening_it(self):
        path = self.root / "node-progress.json"
        plan = json.loads(path.read_text(encoding="utf-8"))
        plan["requirements_ref"] = "D:/external-authority/acceptance.md#research"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = report_progress(self.root)
        self.assertEqual(result["requirements_ref"], plan["requirements_ref"])
        self.assertEqual(result["nodes"][0]["validation"]["percent"], 0)

    def test_cli_initialization_creates_pending_node_table(self):
        fresh = Path(self.temporary.name) / "fresh"
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--json", "project", "init", "--path", str(fresh), "--name", "Fresh agent", "--no-sync"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())["result"]
        self.assertEqual(result["progress"]["nodes"][0]["validation"]["percent"], 0)
        self.assertTrue((fresh / "node-progress.json").is_file())
        self.assertTrue((fresh / ".aidp-local/progress/table.md").is_file())

    def test_failed_derived_refresh_preserves_local_result_and_receipt(self):
        with patch("aidp_agent_flow.progress.report_progress", side_effect=FlowError("Private derived failure")):
            result = self.selected_run()
        self.assertTrue(result["passed"], result)
        self.assertTrue(Path(result["artifact"]).is_file())
        self.assertFalse(result["progress"]["updated"])
        self.assertNotIn("Private derived failure", json.dumps(result))

    def test_failed_derived_refresh_preserves_native_result_without_repeating_invocation(self):
        output = io.StringIO()
        lifecycle = Mock()
        lifecycle.state = {}
        policy = {"version": 1, "max_attempts": 2, "max_model_calls": 2, "max_identical_trials": 1,
                  "native_call_ceiling": 1, "budget_usd": "0", "real_cost_ceiling_usd": "0", "native_cost_ceiling_usd": "0"}
        (self.root / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        initialize_campaign(self.root, "policy.json")
        (self.root / "tests/native.json").write_text(json.dumps({"id": "native", "question": "Synthetic"}), encoding="utf-8")
        receipt_path = self.root / "saved-native-receipt.json"
        receipt_path.write_text("{}", encoding="utf-8")
        received = {"passed": True, "artifact": str(receipt_path), "native_test_accepted": False}
        with patch("aidp_agent_flow.native_lifecycle.NativeLifecycle", return_value=lifecycle), \
                patch("aidp_agent_flow.native_invoke.invoke", return_value=received) as invoke, \
                patch("aidp_agent_flow.progress.report_progress", side_effect=OSError("Private derived failure")), \
                redirect_stdout(output):
            code = main(["--project", str(self.root), "--json", "native", "invoke",
                         "--question-file", "tests/native.json", "--surface", "TEST", "--apply", "--hypothesis", "Check response"])
        result = json.loads(output.getvalue())["result"]
        self.assertEqual(code, 0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["artifact"], str(receipt_path))
        self.assertFalse(result["progress"]["updated"])
        self.assertNotIn("Private derived failure", json.dumps(result))
        invoke.assert_called_once()
        lifecycle.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
