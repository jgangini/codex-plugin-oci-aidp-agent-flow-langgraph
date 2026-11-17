import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aidp_agent_flow.cli import main
from aidp_agent_flow.project import FlowError
from aidp_agent_flow.workflow_status import command, register_parser


class WorkflowStatusTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("synthetic-project")
        self.args = SimpleNamespace(project=str(self.root), native=False)
        self.config = {"native": {}}
        self.load = patch("aidp_agent_flow.workflow_status.load_project",
                          return_value=(self.root, self.config)).start()
        self.exists = patch("pathlib.Path.exists", return_value=True).start()
        self.campaign = patch("aidp_agent_flow.workflow_status.campaign_status",
                              return_value={"unresolved_attempts": []}).start()
        self.progress = patch("aidp_agent_flow.workflow_status.report_progress",
                              return_value={"publication_ready": True}).start()
        self.native = patch("aidp_agent_flow.workflow_status.NativeLifecycle").start()
        self.registry = patch("aidp_agent_flow.workflow_status.Registry").start()
        self.addCleanup(patch.stopall)

    def test_cli_complete_observations_succeed_without_destination_acceptance(self):
        report = {"observation_complete": True, "client_invocation_verified": False,
                  "sections": {"registry": {"state": "available", "result": {
                      "passed": False, "registry_ready": False, "blockers": ["published_endpoint_missing"]}}}}
        output = io.StringIO()
        with patch("aidp_agent_flow.workflow_status.command", return_value=report) as selected, redirect_stdout(output):
            code = main(["--project", str(self.root), "--json", "workflow", "status", "--native"])
        self.assertEqual(code, 0)
        envelope = json.loads(output.getvalue())
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["result"], report)
        self.assertFalse(envelope["result"]["client_invocation_verified"])
        self.assertFalse(envelope["result"]["sections"]["registry"]["result"]["registry_ready"])
        self.assertTrue(selected.call_args.args[0].native)

    def test_cli_incomplete_observations_fail_without_acceptance_claim(self):
        report = {"observation_complete": False, "client_invocation_verified": False,
                  "sections": {"progress": {"state": "error", "error": {"type": "FlowError", "message": "Invalid evidence"}}}}
        output = io.StringIO()
        with patch("aidp_agent_flow.workflow_status.command", return_value=report), redirect_stdout(output):
            code = main(["--project", str(self.root), "--json", "workflow", "status"])
        self.assertEqual(code, 1)
        envelope = json.loads(output.getvalue())
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["result"], report)
        self.assertNotIn("publication_ready", envelope["result"])
        self.assertFalse(envelope["result"]["client_invocation_verified"])

    def test_parser_defaults_offline_and_exposes_no_apply(self):
        parser = argparse.ArgumentParser()
        register_parser(parser.add_subparsers(dest="command"))
        self.assertFalse(parser.parse_args(["workflow", "status"]).native)
        self.assertTrue(parser.parse_args(["workflow", "status", "--native"]).native)
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            parser.parse_args(["workflow", "status", "--apply"])

    def test_offline_observation_never_constructs_cloud_adapters(self):
        result = command(self.args)
        self.native.assert_not_called()
        self.registry.assert_not_called()
        self.assertTrue(result["observation_complete"])
        self.assertEqual(result["scope"], "local")
        self.assertEqual(result["sections"]["native"]["state"], "not_requested")
        self.assertTrue(result["sections"]["progress"]["result"]["publication_ready"])
        self.assertNotIn("publication_ready", result)
        self.assertNotIn("passed", result)
        self.assertFalse(result["client_invocation_verified"])

    def test_missing_campaign_is_optional_but_missing_progress_is_incomplete(self):
        self.exists.side_effect = lambda: False
        result = command(self.args)
        self.assertFalse(result["observation_complete"])
        self.assertEqual(result["sections"]["campaign"], {"state": "missing", "required": False})
        self.assertEqual(result["sections"]["progress"], {"state": "missing", "required": True})
        self.campaign.assert_not_called()
        self.progress.assert_not_called()
        self.exists.side_effect = iter([False, True])
        result = command(self.args)
        self.assertTrue(result["observation_complete"])

    def test_native_preserves_pending_failed_and_registry_blockers(self):
        self.args.native = True
        operations = [{"kind": "publish", "state": "ACKNOWLEDGED"},
                      {"kind": "test-refresh", "state": "FAILED_RECONCILED"},
                      {"kind": "file", "state": "RECONCILED"}]
        self.native.return_value.status.return_value = {"operations": operations, "native_test_accepted": False}
        self.registry.return_value.readiness.return_value = {
            "passed": False, "registry_ready": False, "blockers": ["published_endpoint_missing"]}
        result = command(self.args)
        self.assertTrue(result["observation_complete"])
        native = result["sections"]["native"]["result"]
        self.assertEqual(native["pending_operations"], operations[:1])
        self.assertEqual(native["failed_operations"], operations[1:2])
        self.assertFalse(result["sections"]["registry"]["result"]["passed"])
        self.native.return_value.close.assert_called_once_with()
        self.registry.return_value.close.assert_called_once_with()
        self.native.return_value.publish.assert_not_called()
        self.registry.return_value.register.assert_not_called()
        self.registry.return_value.adopt.assert_not_called()

    def test_registry_drift_is_error_not_missing_or_unregistered(self):
        self.args.native = True
        self.native.return_value.status.return_value = {"operations": []}
        self.registry.return_value.readiness.side_effect = FlowError("Registry binding differs")
        result = command(self.args)
        self.assertFalse(result["observation_complete"])
        self.assertEqual(result["sections"]["registry"]["state"], "error")
        self.assertEqual(result["sections"]["registry"]["error"]["message"], "Registry binding differs")
        self.registry.return_value.close.assert_called_once_with()

    def test_adapter_failure_closes_resources_and_keeps_other_sections(self):
        self.args.native = True
        self.native.return_value.status.side_effect = RuntimeError("private provider payload")
        self.registry.return_value.readiness.return_value = {"passed": True, "registry_ready": True}
        result = command(self.args)
        self.assertFalse(result["observation_complete"])
        self.assertEqual(result["sections"]["native"]["state"], "error")
        self.assertNotIn("private provider payload", str(result))
        self.assertTrue(result["sections"]["registry"]["result"]["registry_ready"])
        self.assertFalse(result["client_invocation_verified"])
        self.native.return_value.close.assert_called_once_with()
        self.registry.return_value.close.assert_called_once_with()

    def test_local_error_is_redacted_and_does_not_hide_campaign_uncertainty(self):
        self.campaign.return_value = {"unresolved_attempts": ["trial-1"]}
        self.progress.side_effect = FlowError("Invalid apify_api_" + "a" * 25)
        result = command(self.args)
        self.assertFalse(result["observation_complete"])
        self.assertEqual(result["sections"]["campaign"]["result"]["unresolved_attempts"], ["trial-1"])
        self.assertEqual(result["sections"]["progress"]["state"], "error")
        self.assertNotIn("apify_api_", str(result))
        self.assertIn("[REDACTED TOKEN]", result["sections"]["progress"]["error"]["message"])


if __name__ == "__main__":
    unittest.main()
