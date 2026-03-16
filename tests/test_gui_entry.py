"""
Minimal tests for the GUI entry point.

These tests verify that the graphical interface can be imported and that
the console script declaration exists in the project metadata.  The
tests are intentionally lightweight and do not attempt to launch the
GUI itself; they simply ensure that the entry point function is
exposed and that the pyproject declares the ``mja-gui`` script.  If
the GUI dependencies (PySide6) are unavailable, the import will
still succeed because the ``main`` function falls back to the
``FallbackConsoleApp``.
"""

from __future__ import annotations

import unittest
from pathlib import Path


class TestGuiEntry(unittest.TestCase):
    def test_main_callable(self) -> None:
        """Ensure that mja.gui.app exposes a callable main()."""
        from mja.gui.app import main  # type: ignore

        # The main attribute should be callable
        self.assertTrue(callable(main))

    def test_pyproject_declares_mja_gui(self) -> None:
        """Verify that the pyproject.toml declares an mja-gui script."""
        # Locate the project root relative to this test file
        project_root = Path(__file__).resolve().parents[1]
        pyproject = project_root / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        # The scripts table should include an mja-gui declaration
        self.assertIn("mja-gui", content)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()