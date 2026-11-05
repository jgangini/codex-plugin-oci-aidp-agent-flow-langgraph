from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import support
except ImportError:
    import support


class CleanupTests(unittest.TestCase):
    def setUp(self):
        support._ROOT.mkdir(exist_ok=True)
        self.directory = support.TemporaryDirectory(dir=support._ROOT)

    def tearDown(self):
        self.directory.cleanup()

    def error(self, winerror):
        error = OSError("Synthetic cleanup error")
        error.winerror = winerror
        return error

    def test_pending_windows_directory_delete_retries_then_succeeds(self):
        with patch.object(support, "_WINDOWS", True), patch.object(support.time, "sleep"), \
                patch.object(tempfile.TemporaryDirectory, "cleanup", side_effect=[self.error(145), None]) as cleanup:
            self.directory.cleanup()
            self.assertEqual(cleanup.call_count, 2)

    def test_persistent_error_is_not_ignored(self):
        with patch.object(support, "_WINDOWS", True), patch.object(support.time, "sleep"), \
                patch.object(tempfile.TemporaryDirectory, "cleanup", side_effect=self.error(145)) as cleanup:
            with self.assertRaises(OSError):
                self.directory.cleanup()
            self.assertEqual(cleanup.call_count, 4)

    def test_unrelated_cleanup_error_is_not_retried(self):
        with patch.object(support, "_WINDOWS", True), \
                patch.object(tempfile.TemporaryDirectory, "cleanup", side_effect=self.error(5)) as cleanup:
            with self.assertRaises(OSError):
                self.directory.cleanup()
            cleanup.assert_called_once()
