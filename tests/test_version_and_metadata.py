"""
Additional tests ensuring version consistency and script declarations.

These tests verify that the package exposes a unified version string of
"1.0", that the pyproject.toml declares the correct scripts and
version, and that the GUI entry module can be imported.  Keeping the
version in sync across the codebase and metadata prevents confusion
around multiple patch identifiers.
"""

from __future__ import annotations

import unittest
from pathlib import Path


class TestVersionAndMetadata(unittest.TestCase):
    def test_version_constant(self) -> None:
        """Ensure that mja.__version__ is exactly "1.0"."""
        import mja  # import inside test to avoid top‑level dependency

        self.assertEqual(mja.__version__, "1.0")

    def test_pyproject_scripts_and_version(self) -> None:
        """Verify pyproject.toml declares the correct scripts and version."""
        # Locate the project root relative to this test file
        project_root = Path(__file__).resolve().parents[1]
        pyproject_path = project_root / "pyproject.toml"
        # tomllib is available in Python 3.11+
        import tomllib  # type: ignore

        content = pyproject_path.read_bytes().decode("utf-8")
        data = tomllib.loads(content)
        project = data["project"]
        self.assertEqual(project["version"], "1.0")
        scripts = project["scripts"]
        self.assertEqual(scripts["mja"], "mja.cli:main")
        self.assertEqual(scripts["mja-gui"], "mja.gui.app:main")

    def test_gui_entry_import(self) -> None:
        """Ensure that the GUI main function can be imported and is callable."""
        from mja.gui.app import main  # type: ignore

        self.assertTrue(callable(main))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()