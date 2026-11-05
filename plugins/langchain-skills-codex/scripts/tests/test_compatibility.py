import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aidp_agent_flow.compatibility import PACKAGES, assess_runtime, documented_status, observe_local
from aidp_agent_flow.project import FlowError, doctor, initialize
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory


CANDIDATE = "a" * 64


def observation():
    return {"status": "observed", "python": "3.11.14", "packages": {
        "langgraph": "1.0.1", "langchain-core": "1.0.4", "langgraph-checkpoint": "3.0.1",
        "oci": "2.170.0", "aidputils": None}}


def native_observations():
    value = observation()
    value.pop("status")
    value.update(candidate_sha256=CANDIDATE, evidence="receipts/runtime.json")
    value["packages"]["aidputils"] = "1.0.0"
    return {"schema_version": 1, "TEST": copy.deepcopy(value), "PROD": value}


class CompatibilityTests(unittest.TestCase):
    def test_documented_profile_is_not_a_certification(self):
        result = assess_runtime(observation())
        self.assertEqual(result["local_profile_status"], "documented_match")
        self.assertIn("docs.oracle.com", result["profile"]["source_url"])
        self.assertFalse(result["oracle_certified"])
        self.assertFalse(result["compatibility_guaranteed"])
        self.assertFalse(result["observed_shared_dependency_parity"])
        self.assertEqual(result["native"]["TEST"]["status"], "unknown")

    def test_missing_and_outside_profile_are_distinct(self):
        local = observation()
        local["packages"]["langgraph"] = None
        self.assertEqual(assess_runtime(local)["local_profile_status"], "missing")
        local["packages"]["langgraph"] = "1.2.16"
        self.assertEqual(assess_runtime(local)["local_profile_status"], "outside_documented_profile")
        local["status"] = "unavailable"
        self.assertEqual(assess_runtime(local)["local_profile_status"], "unknown")
        self.assertEqual(documented_status("1.0.1"), "documented_match")

    def test_shared_parity_requires_both_surfaces_for_same_candidate(self):
        supplied = native_observations()
        original = copy.deepcopy(supplied)
        result = assess_runtime(observation(), supplied, CANDIDATE)
        self.assertTrue(result["observed_shared_dependency_parity"])
        self.assertEqual(result["native"]["TEST"]["status"], "matched_observation")
        self.assertEqual(result["native"]["TEST"]["managed_aidputils_version"], "1.0.0")
        self.assertFalse(result["native_functional_acceptance"])
        self.assertFalse(result["oracle_certified"])
        self.assertNotIn("receipts/runtime.json", json.dumps(result))
        self.assertEqual(supplied, original)
        supplied.pop("PROD")
        self.assertFalse(assess_runtime(observation(), supplied, CANDIDATE)["observed_shared_dependency_parity"])

    def test_stale_candidate_cannot_establish_parity(self):
        supplied = native_observations()
        supplied["TEST"]["candidate_sha256"] = "b" * 64
        result = assess_runtime(observation(), supplied, CANDIDATE)
        self.assertEqual(result["native"]["TEST"]["status"], "stale")
        self.assertFalse(result["observed_shared_dependency_parity"])

    def test_distribution_drift_is_reported_per_package(self):
        for name in ("langgraph", "langchain-core", "langgraph-checkpoint", "oci"):
            with self.subTest(package=name):
                supplied = native_observations()
                supplied["TEST"]["packages"][name] = "99.0.0"
                result = assess_runtime(observation(), supplied, CANDIDATE)
                self.assertEqual(result["native"]["TEST"]["status"], "mismatch")
                self.assertEqual(result["native"]["TEST"]["package_status"][name], "mismatch")

    def test_unknown_packages_are_not_a_match(self):
        for name in ("langgraph", "langchain-core", "langgraph-checkpoint", "oci"):
            with self.subTest(package=name):
                supplied = native_observations()
                supplied["TEST"]["packages"].pop(name)
                result = assess_runtime(observation(), supplied, CANDIDATE)
                self.assertEqual(result["native"]["TEST"]["status"], "unknown")

    def test_python_minor_drift_is_distinct_from_patch(self):
        supplied = native_observations()
        supplied["TEST"]["python"] = "3.11.13"
        self.assertEqual(assess_runtime(observation(), supplied, CANDIDATE)["native"]["TEST"]["status"], "matched_observation")
        supplied["TEST"]["python"] = "3.12.1"
        self.assertEqual(assess_runtime(observation(), supplied, CANDIDATE)["native"]["TEST"]["status"], "mismatch")
        supplied["TEST"]["python"] = None
        self.assertEqual(assess_runtime(observation(), supplied, CANDIDATE)["native"]["TEST"]["status"], "unknown")

    def test_malformed_native_observations_fail_closed(self):
        bad = [[], {"schema_version": True}, {"schema_version": 2},
               {"schema_version": 1, "secret": "must not echo"}]
        for field, value in (("candidate_sha256", "invalid"), ("python", "secret"),
                             ("packages", {"token": "secret"}), ("evidence", "")):
            supplied = native_observations()
            supplied["TEST"][field] = value
            bad.append(supplied)
        for supplied in bad:
            with self.subTest(value=type(supplied).__name__), self.assertRaises(FlowError):
                assess_runtime(observation(), supplied, CANDIDATE)
        with self.assertRaises(FlowError):
            assess_runtime(observation(), native_observations())

    def test_missing_environment_does_not_invoke_any_process(self):
        with patch("aidp_agent_flow.compatibility.subprocess.run") as run:
            result = observe_local(None)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(set(result["packages"]), set(PACKAGES))
        run.assert_not_called()

    def test_probe_uses_isolated_metadata_and_no_sdk_or_agent_import(self):
        expected = observation()
        output = {key: expected[key] for key in ("python", "packages")}
        with patch("aidp_agent_flow.compatibility.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(output))) as run:
            self.assertEqual(observe_local(sys.executable), expected)
        command = run.call_args.args[0]
        self.assertEqual(command[1:3], ["-I", "-c"])
        self.assertNotIn("import aidputils", command[-1])
        self.assertNotIn("import oci", command[-1])

    def test_failed_probe_does_not_expose_subprocess_output(self):
        for result in (SimpleNamespace(returncode=1, stdout="private"),
                       SimpleNamespace(returncode=0, stdout="private"),
                       SimpleNamespace(returncode=0, stdout='{"python":"bad","packages":{}}')):
            with patch("aidp_agent_flow.compatibility.subprocess.run", return_value=result):
                value = observe_local(sys.executable)
            self.assertEqual(value["status"], "unavailable")
            self.assertNotIn("private", json.dumps(value))
        with patch("aidp_agent_flow.compatibility.subprocess.run", side_effect=subprocess.TimeoutExpired("probe", 10)):
            self.assertEqual(observe_local(sys.executable)["status"], "unavailable")

    def test_doctor_reports_compatibility_without_changing_project(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=base) as temporary:
            root = Path(temporary) / "project"
            initialized = initialize(root, "Agent", sync=False)
            self.assertEqual(initialized["runtime_profile_status"], "documented_match")
            self.assertIn('"langgraph==1.0.1"', (root / "pyproject.toml").read_text(encoding="utf-8"))
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            with patch("aidp_agent_flow.compatibility.observe_local", return_value=observation()):
                result = doctor(root)
            self.assertTrue(result["local_ready"])
            self.assertEqual(result["runtime_compatibility"]["local_profile_status"], "documented_match")
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_custom_version_remains_explicit_without_false_support(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=base) as temporary:
            root = Path(temporary) / "custom"
            result = initialize(root, "Agent", sync=False, langgraph_version="1.2.16")
            self.assertEqual(result["runtime_profile_status"], "outside_documented_profile")
            self.assertFalse(result["oracle_certified"])
            self.assertIn("langgraph==1.2.16", (root / "agent/requirements.txt").read_text(encoding="utf-8"))
