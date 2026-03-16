"""
Unit tests for improvements made to the mja GUI and helper functions.

These tests focus on verifying the search result ordering, popularity
formatting, desktop shortcut creation, and translation behaviour.  They
do not require a full GUI environment and will run in headless test
contexts.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import unittest

# Ensure the parent directory (project root) is on sys.path so that
# `import mja` works when running the tests directly from the tests
# directory.  Without this, Python will not locate the local package.
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mja.search import SearchResult, sort_results, sort_search_dicts, format_popularity, format_search
from mja.gui.app import copy_desktop_shortcut, tr, set_language


class TestSearchOrdering(unittest.TestCase):
    def test_main_package_sorted_before_suffix(self) -> None:
        """Ensure that the main package appears before auxiliary variants."""
        # Two AUR results: one main package, one with a suffix (-devtools)
        results = [
            SearchResult(source="aur", name="wechat-devtools", version="1", description="devtools", popularity=5.0, votes=10),
            SearchResult(source="aur", name="wechat", version="1", description="main", popularity=4.0, votes=20),
        ]
        sorted_results = sort_results(results, "wechat")
        # The exact package name should sort first despite lower popularity
        self.assertEqual(sorted_results[0].name, "wechat")

    def test_prefix_match_sorted_before_substring(self) -> None:
        """Prefix matches should rank higher than substring matches."""
        results = [
            SearchResult(source="aur", name="firefox-addon", description="addon for browser", popularity=10.0, votes=100),
            SearchResult(source="aur", name="browser-firefox", description="contains firefox", popularity=8.0, votes=50),
        ]
        sorted_results = sort_results(results, "firefox")
        # Name starting with the query (firefox-addon) should come first
        self.assertEqual(sorted_results[0].name, "firefox-addon")

    def test_global_sort_across_repo_and_aur_dicts(self) -> None:
        payload = [
            {"source": "repo", "repo": "extra", "name": "wechat-theme", "description": "theme", "version": "1"},
            {"source": "aur", "name": "wechat", "description": "main package", "version": "1", "popularity": 1.0, "votes": 10},
            {"source": "aur", "name": "wechat-git", "description": "git version", "version": "1", "popularity": 9.0, "votes": 100},
        ]
        sorted_payload = sort_search_dicts(payload, "wechat")
        self.assertEqual(sorted_payload[0]["name"], "wechat")

    def test_tie_break_sorts_names_ascending(self) -> None:
        results = [
            SearchResult(source="aur", name="bbb", version="1", description="same", popularity=1.0, votes=1),
            SearchResult(source="aur", name="aaa", version="1", description="same", popularity=1.0, votes=1),
        ]
        sorted_results = sort_results(results, "zzz")
        self.assertEqual([item.name for item in sorted_results], ["aaa", "bbb"])

    def test_cli_format_uses_global_sorting(self) -> None:
        results = {
            "repo": [SearchResult(source="repo", repo="extra", name="wechat-theme", version="1", description="theme")],
            "aur": [SearchResult(source="aur", name="wechat", version="1", description="main", popularity=1.0, votes=5)],
        }
        rendered = format_search(results, query="wechat")
        self.assertLess(rendered.find("aur/wechat"), rendered.find("extra/wechat-theme"))


class TestPopularityFormatting(unittest.TestCase):
    def test_small_popularity(self) -> None:
        self.assertEqual(format_popularity(1e-7), "<0.000001")

    def test_regular_popularity(self) -> None:
        self.assertEqual(format_popularity(1.23456789), "1.234568")


class TestDesktopShortcut(unittest.TestCase):
    def test_copy_shortcut_exact_and_prefixed(self) -> None:
        """Verify that both exact and prefixed desktop files are detected and copied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup a fake home directory structure
            home = Path(tmpdir) / "home"
            apps = home / ".local/share/applications"
            apps.mkdir(parents=True)
            desktop_dir = home / "Desktop"
            desktop_dir.mkdir(parents=True)
            # Create an exact match desktop file
            exact_file = apps / "foo.desktop"
            exact_file.write_text("[Desktop Entry]\nName=Foo\n", encoding="utf-8")
            # Create a prefixed match desktop file
            prefixed_file = apps / "mja-arch-bar.desktop"
            prefixed_file.write_text("[Desktop Entry]\nName=Bar\n", encoding="utf-8")
            # Patch Path.home() to return our fake home directory
            with mock.patch("pathlib.Path.home", return_value=home):
                # Copy foo.desktop
                result_foo = copy_desktop_shortcut("foo")
                self.assertTrue(result_foo)
                self.assertTrue((desktop_dir / "foo.desktop").exists())
                # Copy bar.desktop using prefixed name
                result_bar = copy_desktop_shortcut("bar")
                self.assertTrue(result_bar)
                self.assertTrue((desktop_dir / "mja-arch-bar.desktop").exists())

    def test_copy_shortcut_uses_state_desktop_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            apps = home / ".local/share/applications"
            state_dir = home / ".local/state/mja"
            apps.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            desktop_dir = home / "Desktop"
            desktop_dir.mkdir(parents=True)
            exported = apps / "mja-arch-com.google.Chrome.desktop"
            exported.write_text("[Desktop Entry]\nName=Chrome\n", encoding="utf-8")
            state_path = state_dir / "state.json"
            state_path.write_text('{"packages":{"google-chrome":{"desktop_entries":["/usr/share/applications/com.google.Chrome.desktop"]}}}', encoding="utf-8")
            with mock.patch("pathlib.Path.home", return_value=home):
                self.assertTrue(copy_desktop_shortcut("google-chrome"))
                self.assertTrue((desktop_dir / "mja-arch-com.google.Chrome.desktop").exists())

    def test_copy_shortcut_not_found(self) -> None:
        """Return False when no matching desktop file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            (home / ".local/share/applications").mkdir(parents=True)
            (home / "Desktop").mkdir(parents=True)
            with mock.patch("pathlib.Path.home", return_value=home):
                result = copy_desktop_shortcut("doesnotexist")
                self.assertFalse(result)
                # Desktop directory should remain empty
                self.assertEqual(list((home / "Desktop").iterdir()), [])


class TestTranslations(unittest.TestCase):
    def test_language_switch(self) -> None:
        """The tr() function should return different strings based on the current language."""
        # Default language is Chinese
        set_language("zh")
        self.assertEqual(tr("搜索"), "搜索")
        # Switch to English
        set_language("en")
        self.assertEqual(tr("搜索"), "Search")
        # Switch back to Chinese
        set_language("zh")
        self.assertEqual(tr("搜索"), "搜索")


if __name__ == "__main__":
    unittest.main()