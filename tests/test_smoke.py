"""
Minimal smoke tests for the mja package.

These tests are intentionally lightweight and do not rely on the
presence of Manjaro‑specific tooling such as pacman, pamac or
distrobox.  They exercise core logic like CLI argument parsing,
state persistence, formatting helpers, basic doctor behaviour and
error JSON reporting.  The goal is to catch obvious regressions
without requiring a full Manjaro environment.  Manual testing is
still required for full coverage; see TEST_MATRIX.md for details.
"""

import io
import json
import contextlib
import types
from pathlib import Path
import tempfile

import unittest

import os
import sys

# Ensure the parent directory (project root) is on sys.path so that
# `import mja` works when running the tests directly from the tests
# directory.  Without this, Python will not locate the local package.
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from unittest import mock

from mja.cli import build_parser, main
from mja.state import StateStore
from mja.models import (
    PackageRecord,
    InstallStatus,
    ExportStatus,
    ExportMode,
    SourceKind,
    StateFile,
)
from mja.doctor import run_doctor
from mja.search import format_search, SearchResult
from mja.state_rebuild import rebuild_state
from mja.errors import MjaError


class TestCliParser(unittest.TestCase):
    def test_subcommand_parsing(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["search", "pkg"])
        self.assertEqual(args.command, "search")
        self.assertEqual(args.query, "pkg")
        args = parser.parse_args(["install", "foo", "--source", "repo"])
        self.assertEqual(args.command, "install")
        self.assertEqual(args.name, "foo")
        args = parser.parse_args(["doctor"])
        self.assertEqual(args.command, "doctor")
        args = parser.parse_args(["list"])
        self.assertEqual(args.command, "list")
        args = parser.parse_args(["remove", "bar"])
        self.assertEqual(args.command, "remove")
        args = parser.parse_args(["state", "rebuild"])
        self.assertEqual(args.command, "state")
        self.assertEqual(args.state_command, "rebuild")


class TestStateStore(unittest.TestCase):
    def test_load_save_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = StateStore(path)
            # New store should load empty state
            state = store.load()
            self.assertEqual(state.packages, {})
            # Insert a package record
            record = PackageRecord(
                source=SourceKind.HOST_REPO.value,
                container=None,
                install_status=InstallStatus.INSTALLED.value,
                export_status=ExportStatus.NOT_REQUESTED.value,
                export_mode=ExportMode.NONE.value,
            )
            store.upsert_package("nano", record)
            # Load again
            loaded = store.load()
            self.assertIn("nano", loaded.packages)
            self.assertEqual(loaded.packages["nano"].source, SourceKind.HOST_REPO.value)


class TestFormatHelpers(unittest.TestCase):
    def test_format_search(self) -> None:
        # Construct a dummy search result
        repo_result = SearchResult(
            source="repo",
            repo="extra",
            name="pkg",
            version="1.0",
            description="a test package",
            exact=True,
        )
        results = {"repo": [repo_result], "aur": []}
        text = format_search(results)
        # Expect repo section and package line
        self.assertIn("[repo]", text)
        self.assertIn("extra/pkg 1.0", text)
        self.assertIn("a test package", text)


class TestDoctor(unittest.TestCase):
    def test_container_checks_skipped_on_fresh_state(self) -> None:
        # Use a fresh, empty state file
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = StateStore(path)
            store.save(StateFile())
            # Patch runtime and install functions to avoid external calls
            with mock.patch("mja.runtime.which", return_value="/usr/bin/true"), \
                 mock.patch("mja.runtime.detect_container_runtime", return_value="docker"), \
                 mock.patch("mja.doctor.distrobox_exists", return_value=False), \
                 mock.patch("mja.doctor.container_run", return_value=types.SimpleNamespace(returncode=0)):
                report = run_doctor(state_store=store)
            # Find container checks
            checks = {chk["name"]: chk for chk in report["checks"]}
            self.assertIn("container-exists", checks)
            self.assertTrue(checks["container-exists"]["skipped"])
            # We do not assert on report["ok"] here because other base checks
            # (e.g. pacman/pamac/distrobox) may be missing in the test
            # environment.  The important property is that container checks
            # are skipped when no container is configured.


class TestStateRebuild(unittest.TestCase):
    def test_empty_state_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = StateStore(path)
            store.save(StateFile())
            # No packages recorded, should return empty list and not crash
            with mock.patch("mja.runtime.run") as mock_run:
                mock_run.return_value = types.SimpleNamespace(returncode=1)
                results = rebuild_state(state_store=store)
            self.assertEqual(results, [])


class TestErrorJson(unittest.TestCase):
    def test_error_json_output(self) -> None:
        # Simulate list subcommand raising an MjaError and ensure JSON is printed
        def raise_error(*args, **kwargs):
            raise MjaError("E123", "unit test", {"foo": "bar"})

        # Patch the bound function in the CLI module, not the underlying list_cmd
        with mock.patch("mja.cli.list_packages", side_effect=raise_error):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = main(["list", "--json"])
            # The command should exit with non‑zero status
            self.assertEqual(rc, 1)
            # Error should be reported to stderr as JSON
            err = stderr.getvalue().strip()
            # stderr may include newlines; parse as JSON
            data = json.loads(err)
            self.assertIn("error", data)
            self.assertEqual(data["error"]["code"], "E123")
            self.assertEqual(data["error"]["message"], "unit test")
            self.assertEqual(data["error"]["details"], {"foo": "bar"})


if __name__ == "__main__":
    unittest.main()