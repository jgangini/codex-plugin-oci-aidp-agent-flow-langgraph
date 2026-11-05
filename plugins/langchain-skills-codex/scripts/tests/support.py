"""Bounded cleanup for Windows directories with pending filesystem deletions."""
from pathlib import Path
import os
import tempfile
import time

_WINDOWS = os.name == "nt"
_ROOT = Path(__file__).resolve().parents[3] / "validation-work"


class TemporaryDirectory(tempfile.TemporaryDirectory):
    def cleanup(self):
        if not Path(self.name).resolve().is_relative_to(_ROOT.resolve()):
            raise ValueError("Test cleanup must remain inside validation-work")
        for attempt in range(4):
            try:
                return super().cleanup()
            except OSError as error:
                if not _WINDOWS or getattr(error, "winerror", None) != 145 or attempt == 3:
                    raise
                time.sleep(0.05 * (attempt + 1))
