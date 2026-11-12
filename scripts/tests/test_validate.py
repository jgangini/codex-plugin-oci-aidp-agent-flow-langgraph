"""Public package identity, skill ownership and documentation contracts."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('distribution_validator', Path(__file__).parents[1] / 'validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class VersionContractTests(unittest.TestCase):
    def test_distinct_plugin_and_engine_versions_are_valid(self):
        version = validator.check_manifest()
        self.assertEqual(version, '0.4.46')

    def test_mismatched_executable_is_rejected(self):
        original = Path.read_text
        def changed(path, *args, **kwargs):
            if path == validator.PLUGIN / 'scripts/aidp_agent_flow/__init__.py':
                return '__version__ = "0.0.0"'
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', changed), self.assertRaisesRegex(ValueError, 'executable versions differ'):
            validator.check_manifest()

    def test_invalid_plugin_version_is_rejected(self):
        original = validator.load_json
        def changed(path):
            value = original(path)
            if path.name == 'plugin.json':
                value['version'] = 'invalid'
            return value
        with patch.object(validator, 'load_json', changed), self.assertRaisesRegex(ValueError, 'Invalid plugin version'):
            validator.check_manifest()

    def test_framework_skill_cannot_be_declared_as_bundled(self):
        declared = [f"./skills/{name}/" for name in validator.AIDP_SKILLS]
        declared.append("./skills/langgraph-fundamentals/")
        with self.assertRaisesRegex(ValueError, "Manifest must declare only"):
            validator.check_skill_boundary(declared)

    def test_unlisted_framework_copy_is_rejected(self):
        original = Path.iterdir
        def with_copy(path):
            entries = list(original(path))
            if path == validator.PLUGIN / "skills":
                entries.append(path / "langgraph-fundamentals")
            return iter(entries)
        declared = [f"./skills/{name}/" for name in validator.AIDP_SKILLS]
        with patch.object(Path, "iterdir", with_copy), self.assertRaisesRegex(ValueError, "Package must contain only"):
            validator.check_skill_boundary(declared)

    def test_missing_or_duplicate_aidp_skill_is_rejected(self):
        declared = [f"./skills/{name}/" for name in sorted(validator.AIDP_SKILLS)]
        for invalid in (declared[:-1], declared + [declared[0]]):
            with self.subTest(skills=invalid), self.assertRaisesRegex(ValueError, "Manifest must declare only"):
                validator.check_skill_boundary(invalid)

    def test_internal_references_are_rejected_before_distribution(self):
        original = Path.read_text
        def internal(path, *args, **kwargs):
            if path == validator.ROOT / "README.md":
                return "[internal](https://oracle.enterprise.slack.com/example)"
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", internal), self.assertRaisesRegex(ValueError, "Internal enterprise"):
            validator.check_documentation()
