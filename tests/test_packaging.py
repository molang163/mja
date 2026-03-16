"""
Minimal packaging tests for the mja project.

These tests exercise the basic release mechanics without invoking
Manjaro‑specific tooling.  They verify that a source distribution (sdist)
and wheel can be built using the local build backend and that the
expected entry points are present in the resulting wheel.  A final
check ensures that invoking the package via ``python -m mja --help``
returns successfully.  The tests are intentionally lightweight: if
required tooling (such as the ``build`` module) is unavailable they
will skip rather than fail.
"""

from __future__ import annotations

import unittest
import subprocess
import sys
import tempfile
import os
from pathlib import Path
import zipfile


class TestPackaging(unittest.TestCase):
    def setUp(self) -> None:
        # Determine the project root by ascending two levels from this file
        self.project_root = Path(__file__).resolve().parents[1]

    def _has_build_module(self) -> bool:
        """Return True if the external ``build`` module is importable.

        The check runs in a temporary directory with PYTHONPATH cleared so a
        local ``build/`` directory in the project tree cannot masquerade as the
        third-party ``build`` module.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('build') else 1)",
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0

    def test_can_build_sdist(self) -> None:
        """The project should build a source distribution without errors."""
        if not self._has_build_module():
            self.skipTest("'build' module not available; skipping sdist test")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-m", "build", "--sdist", "--outdir", tmpdir],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Provide captured output in the assertion message for easier debugging
                self.fail(f"sdist build failed:\nstdout={result.stdout}\nstderr={result.stderr}")
            # Verify an archive has been produced (tar.gz or zip)
            filenames = os.listdir(tmpdir)
            self.assertTrue(
                any(name.endswith((".tar.gz", ".zip")) for name in filenames),
                msg=f"no sdist archive found in {tmpdir}: {filenames}",
            )
            # Inspect the contents of the sdist to ensure it does not include
            # unwanted build artefacts such as __pycache__, *.pyc, build/, dist/ or
            # *.egg-info directories, and that the desktop file is present.
            archive_name = next(name for name in filenames if name.endswith((".tar.gz", ".zip")))
            archive_path = Path(tmpdir) / archive_name
            members: list[str]
            if archive_name.endswith(".tar.gz"):
                import tarfile  # imported here to avoid a hard test dependency

                with tarfile.open(archive_path, "r:gz") as tf:
                    members = tf.getnames()
            else:
                import zipfile  # imported here to avoid a hard test dependency

                with zipfile.ZipFile(archive_path, "r") as zf:
                    members = zf.namelist()
            # Ensure no unwanted artefacts are present
            for name in members:
                self.assertNotIn("__pycache__", name, msg=f"unexpected __pycache__ in sdist: {name}")
                self.assertFalse(name.endswith(".pyc"), msg=f"unexpected .pyc in sdist: {name}")
                # Normalise path separators for portability
                parts = name.strip("/").split("/")
                self.assertNotIn("build", parts, msg=f"unexpected build dir in sdist: {name}")
                self.assertNotIn("dist", parts, msg=f"unexpected dist dir in sdist: {name}")
                # any egg-info directory
                self.assertFalse(any(part.endswith(".egg-info") for part in parts), msg=f"unexpected egg-info dir in sdist: {name}")
            # The desktop file should be included under mja/resources
            self.assertTrue(any("mja/resources/mja-gui.desktop" in name for name in members), msg="desktop file missing from sdist")

    def test_can_build_wheel(self) -> None:
        """The project should build a wheel without errors."""
        if not self._has_build_module():
            self.skipTest("'build' module not available; skipping wheel test")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-m", "build", "--wheel", "--outdir", tmpdir],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self.fail(f"wheel build failed:\nstdout={result.stdout}\nstderr={result.stderr}")
            files = [f for f in os.listdir(tmpdir) if f.endswith(".whl")]
            self.assertTrue(files, msg=f"no wheel file produced in {tmpdir}: {os.listdir(tmpdir)}")

    def test_wheel_contains_entry_point(self) -> None:
        """Built wheel should expose the mja console entry point."""
        if not self._has_build_module():
            self.skipTest("'build' module not available; skipping entry point test")
        with tempfile.TemporaryDirectory() as tmpdir:
            # Build wheel into temporary directory
            result = subprocess.run(
                [sys.executable, "-m", "build", "--wheel", "--outdir", tmpdir],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self.fail(f"wheel build failed:\nstdout={result.stdout}\nstderr={result.stderr}")
            wheel_files = [f for f in os.listdir(tmpdir) if f.endswith(".whl")]
            self.assertTrue(wheel_files, msg="no wheel file produced")
            wheel_path = Path(tmpdir) / wheel_files[0]
            # Inspect the wheel for entry_points.txt
            with zipfile.ZipFile(wheel_path, "r") as zf:
                namelist = zf.namelist()
                # Find the entry_points.txt in the .dist-info directory
                entry_candidates = [n for n in namelist if n.endswith("entry_points.txt")]
                self.assertTrue(entry_candidates, msg="entry_points.txt missing from wheel")
                entry_data = zf.read(entry_candidates[0]).decode()
                # The console scripts should map 'mja' and 'mja-gui' to their entry points
                self.assertIn("mja = mja.cli:main", entry_data)
                self.assertIn("mja-gui = mja.gui.app:main", entry_data)

                # Also ensure the wheel does not contain unwanted build artefacts and
                # includes the desktop file.  Inspect the file list of the wheel.
                bad_paths = []
                desktop_present = False
                for name in namelist:
                    if "__pycache__" in name or name.endswith(".pyc"):
                        bad_paths.append(name)
                    parts = name.strip("/").split("/")
                    if "build" in parts or "dist" in parts or any(part.endswith(".egg-info") for part in parts):
                        bad_paths.append(name)
                    if name.endswith("mja/resources/mja-gui.desktop"):
                        desktop_present = True
                self.assertFalse(bad_paths, msg=f"unexpected artefacts in wheel: {bad_paths}")
                self.assertTrue(desktop_present, msg="desktop file missing from wheel")

    def test_module_invocation_help(self) -> None:
        """Invoking the package via python -m mja should print a help message."""
        # This test does not rely on the build module; it runs against the
        # local source checkout.  As such it should always run.
        result = subprocess.run(
            [sys.executable, "-m", "mja", "--help"],
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # Expect usage information in the output
        self.assertIn("usage", result.stdout.lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()