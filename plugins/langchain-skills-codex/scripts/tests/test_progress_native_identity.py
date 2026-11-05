import json
from pathlib import Path
import unittest

try:
    from . import test_progress as fixtures
    from .test_native_invoke import FakeLifecycle, FakeSSE, output_event, stream
except ImportError:
    import test_progress as fixtures
    from test_native_invoke import FakeLifecycle, FakeSSE, output_event, stream

from aidp_agent_flow.identity import execution_identity
from aidp_agent_flow.native_invoke import invoke
from aidp_agent_flow.native_lifecycle import NativeLifecycle
from aidp_agent_flow.packaging import inspect_package
from aidp_agent_flow.progress import record_test_review, require_publication_acceptance


class NativeProgressIdentityTests(unittest.TestCase):
    setUp = fixtures.ProgressTests.setUp
    tearDown = fixtures.ProgressTests.tearDown
    write = fixtures.ProgressTests.write
    identity = fixtures.ProgressTests.identity
    local = fixtures.ProgressTests.local

    def test_generated_native_receipt_can_be_reviewed_and_published_with_matching_identity(self):
        response = FakeSSE(stream(output_event("Verified support answer")))
        lifecycle = FakeLifecycle(self.root, response)
        config = self.root / "aidp-agent.toml"
        prefix = config.read_text(encoding="utf-8").split("[native]", 1)[0]
        config.write_text(prefix + '[native]\nendpoint="https://aidp.region-one.oci.oraclecloud.com"\n'
                          'platform_id="platform-one"\nworkspace_key="workspace-one"\nagent_key="agent-one"\n', encoding="utf-8")
        self.plan["nodes"] = self.plan["nodes"][:1]
        self.plan["acceptance"] = [{"id": "integrated", "description": "Integrated answer satisfies the rubric",
                                    "layer": "TEST", "case_id": "native-positive"}]
        self.write("node-progress.json", self.plan)
        self.write("tests/native-identity.json", {"id": "native-positive", "question": "Synthetic support question"})
        snapshot = NativeLifecycle._snapshot(lifecycle.rows["TEST"])
        lifecycle.state["test_receipt"] = {"package_sha256": inspect_package(self.root)["package_sha256"],
                                           "deployments": snapshot}
        result = invoke(lifecycle, "tests/native-identity.json")
        receipt_path = Path(result["artifact"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        expected = execution_identity(self.root)
        self.assertTrue(result["passed"])
        self.assertEqual({key: receipt[key] for key in expected}, expected)
        self.assertEqual(receipt["environment_identity_scope"], "local_test_harness_not_native_runtime")
        self.assertEqual(len(lifecycle.transport.calls), 1)
        self.local()
        relative = receipt_path.relative_to(self.root).as_posix()
        record_test_review(self.root, "respond", "native-positive", relative, "accepted", "Reviewed node rubric")
        report = record_test_review(self.root, "__agent__", "integrated", relative, "accepted", "Reviewed integration rubric")
        self.assertTrue(report["publication_ready"])
        self.assertTrue(require_publication_acceptance(self.root, snapshot)["publication_ready"])
        self.assertEqual(len(lifecycle.transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
