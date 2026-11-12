"""Public package validation accepts distinct plugin/engine versions only."""
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
        self.assertEqual(version, '0.4.45')

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

    def test_internal_references_are_rejected_before_distribution(self):
        original = Path.read_text
        def internal(path, *args, **kwargs):
            if path == validator.ROOT / "README.md":
                return "[internal](https://oracle.enterprise.slack.com/example)"
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", internal), self.assertRaisesRegex(ValueError, "Internal enterprise"):
            validator.check_documentation()
