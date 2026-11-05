from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from aidp_agent_flow.cli import main
from aidp_agent_flow.compatibility import assess_runtime
from aidp_agent_flow.packaging import inspect_package
from aidp_agent_flow.project import initialize
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory


class RuntimeCLITests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Runtime contract", sync=False)
        self.local = {"status": "observed", "python": "3.11.11", "packages": {
            "langgraph": "1.0.1", "langchain-core": "1.0.0", "langgraph-checkpoint": "3.0.0",
            "oci": "2.189.0", "aidputils": None}}

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, *flags):
        output = io.StringIO()
        report = assess_runtime(self.local)
        with patch("aidp_agent_flow.cli.doctor", return_value={"runtime_compatibility": report}), \
                patch("aidp_agent_flow.remote.signer_for", side_effect=AssertionError("No signing")), \
                redirect_stdout(output):
            code = main(["--project", str(self.root), "--json", "runtime", "check", *flags])
        return code, json.loads(output.getvalue())

    def observations(self):
        item = {"candidate_sha256": inspect_package(self.root)["package_sha256"],
                "python": self.local["python"], "packages": {**self.local["packages"], "aidputils": "0.1.0"},
                "evidence": "private reference is not echoed"}
        path = self.root / "runtime-observations.json"
        path.write_text(json.dumps({"schema_version": 1, "TEST": item, "PROD": item}), encoding="utf-8")
        return path

    def test_documented_local_profile_does_not_accept_unknown_hosted_runtime(self):
        code, result = self.command("--require-profile")
        self.assertEqual(code, 0)
        self.assertFalse(result["result"]["oracle_certified"])
        self.assertEqual(result["result"]["native"]["TEST"]["status"], "unknown")
        self.assertEqual(self.command("--require-parity")[0], 1)

    def test_newer_local_version_remains_available_but_does_not_pass_profile_gate(self):
        self.local["packages"]["langgraph"] = "1.2.16"
        self.assertEqual(self.command()[0], 0)
        self.assertEqual(self.command("--require-profile")[0], 1)

    def test_supplied_same_candidate_parity_is_not_certification_or_functional_acceptance(self):
        path = self.observations()
        code, result = self.command("--observations", path.name, "--require-profile", "--require-parity")
        self.assertEqual(code, 0)
        self.assertFalse(result["result"]["native_functional_acceptance"])
        self.assertIn("not_independently_attested", result["result"]["observation_provenance"])
        self.assertNotIn("private reference", json.dumps(result))
        (self.root / "agent/core/graph.py").write_text("# Changed candidate\n", encoding="utf-8")
        code, result = self.command("--observations", path.name, "--require-parity")
        self.assertEqual(code, 1)
        self.assertEqual(result["result"]["native"]["TEST"]["status"], "stale")

    def test_malformed_or_external_observation_is_rejected_without_echoing_contents(self):
        path = self.root / "malformed.json"
        path.write_text('{"private":"secret placeholder"}', encoding="utf-8")
        code, result = self.command("--observations", path.name)
        self.assertEqual(code, 2)
        self.assertNotIn("secret placeholder", json.dumps(result))
        self.assertEqual(self.command("--observations", "../external.json")[0], 2)
        path.write_text(" " * 65_537)
        self.assertEqual(self.command("--observations", path.name)[0], 2)


if __name__ == "__main__":
    unittest.main()
