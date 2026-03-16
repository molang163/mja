"""
List command implementation for the mja CLI.

This module provides a simple interface to inspect the recorded state
file and present a summary of known packages. It intentionally does
not attempt to revalidate the state against the system; it simply
reports what the installer has recorded. Consumers can use the
``--json`` flag from the CLI to retrieve a machine-readable payload.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .state import StateStore


def list_packages(*, state_store: StateStore | None = None) -> List[Dict[str, Any]]:
    """Return a list of package summaries from the current state.

    Each entry in the returned list contains the package name and a few
    selected fields from the saved :class:`PackageRecord`.

    :param state_store: Optional custom StateStore instance. A new one
        will be created if not provided.
    :returns: A list of dictionaries, each representing a package.
    """
    state_store = state_store or StateStore()
    state = state_store.load()
    results: list[dict[str, Any]] = []
    for name, record in state.packages.items():
        results.append(
            {
                "name": name,
                "source": record.source,
                "install_status": record.install_status,
                "export_status": record.export_status,
                "container": record.container,
                "installed_at": record.installed_at,
            }
        )
    return results


def format_list(packages: List[Dict[str, Any]]) -> str:
    """Format a list of package summaries into a human friendly string.

    The output is a simple whitespace-separated table. If no packages
    have been recorded yet, a short message is returned instead.
    """
    if not packages:
        return "No packages recorded."
    # Prepare a header and compute column widths
    headers = [
        "name",
        "source",
        "install_status",
        "export_status",
        "container",
        "installed_at",
    ]
    # Determine width for each column
    widths = {h: len(h) for h in headers}
    for item in packages:
        for h in headers:
            value = str(item.get(h) or "")
            if len(value) > widths[h]:
                widths[h] = len(value)
    # Build header line
    lines: list[str] = []
    header_line = " ".join(h.ljust(widths[h]) for h in headers)
    lines.append(header_line)
    # Build each row
    for item in packages:
        row = []
        for h in headers:
            value = str(item.get(h) or "")
            row.append(value.ljust(widths[h]))
        lines.append(" ".join(row))
    return "\n".join(lines)