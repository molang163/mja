"""
State rebuild command for the mja CLI.

This module implements the ``mja state rebuild`` operation introduced
in version 0.3.0. Rebuilding the state file inspects each recorded
package and attempts to reconcile the stored metadata with the actual
system state. The goal is to detect when packages have been removed
outside of mja, or when exported artifacts have been manually deleted
or created.

The rebuild process adheres to the following policy:

* Only packages already present in the state file are considered. No
  attempt is made to discover and import unknown packages from the
  host or container environments.
* For host repository packages the presence of the package is
  determined via ``pacman -Q <name>``. A zero exit status indicates the
  package is still installed on the host.
* For AUR container packages the presence of the package is checked
  using ``pacman -Q`` within the appropriate distrobox container. When
  the container or package cannot be verified the package is treated
  as removed.
* The existence of exported desktop entries is verified by looking
  for files under ``~/.local/share/applications`` whose basename matches
  the original desktop file path stored in the record. Binary wrappers
  are verified by checking for executables under ``~/.local/bin``
  whose basename matches the candidate recorded in the state.
* After determining the installed and exported status, the record's
  ``install_status``, ``export_status``, ``desktop_entries`` and
  ``binaries`` fields are updated to reflect reality. Previous errors
  are cleared upon successful reconciliation.

The primary entry point :func:`rebuild_state` returns a list of
summary dictionaries, one per package, that mirrors the format used by
other commands in the CLI.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Dict, List

from .models import (
    ExportMode,
    ExportStatus,
    InstallStatus,
    SourceKind,
    now_iso,
)
from .state import StateStore
from .runtime import run
from .install import (
    DEFAULT_CONTAINER_NAME,
    list_installed_files_in_container,
    find_desktop_files,
    find_bin_candidates,
    container_run,
    sh_quote,
)


def rebuild_state(*, state_store: StateStore | None = None) -> List[Dict[str, Any]]:
    """Rebuild the state file for all recorded packages.

    This function iterates over each package stored in the state file and
    reconciles the recorded metadata with the current system. Installation
    status is verified using the appropriate package manager (host
    pacman or container pacman). Exported artifacts are probed on the
    host filesystem. The record is updated in-place and persisted
    through the provided state store.

    :param state_store: Optional custom state store. A new one will be
      created if not provided.
    :returns: A list of dictionaries summarising the reconciled state of
      each package.
    """
    state_store = state_store or StateStore()
    state = state_store.load()
    summaries: list[dict[str, Any]] = []
    # Precompute host directories for exported artifacts.
    desktop_base = Path.home() / ".local/share/applications"
    bin_base = Path.home() / ".local/bin"

    for name, record in state.packages.items():
        # Track whether the record was updated so we can persist and clear
        # outdated error messages.
        updated = False
        # Determine installation status based on source kind.
        if record.source == SourceKind.HOST_REPO.value:
            # host repo: use pacman -Q
            try:
                res = run(["pacman", "-Q", name], check=False)
                installed = res.returncode == 0
            except Exception:
                installed = False
            desired_status = InstallStatus.INSTALLED.value if installed else InstallStatus.REMOVED.value
            if record.install_status != desired_status:
                record.install_status = desired_status
                updated = True
            # For host packages export is never requested; normalise export_status
            if record.export_status != ExportStatus.NOT_REQUESTED.value:
                record.export_status = ExportStatus.NOT_REQUESTED.value
                updated = True
            # Clear any residual export data
            if record.desktop_entries or record.binaries:
                record.desktop_entries = []
                record.binaries = []
                updated = True

        elif record.source == SourceKind.AUR_CONTAINER.value:
            container_name = record.container or DEFAULT_CONTAINER_NAME
            # Attempt to query the package inside the container. If this
            # fails we treat the package as removed. We do not call
            # ensure_container_exists here because rebuild should not
            # implicitly create containers; absence of the container
            # counts as removed.
            installed = False
            try:
                # Query pacman inside the container. A zero exit code
                # means the package is present.
                result = container_run(
                    container_name,
                    f"pacman -Q {sh_quote(name)}",
                    check=False,
                )
                installed = result.returncode == 0
            except Exception:
                installed = False

            desired_status = InstallStatus.INSTALLED.value if installed else InstallStatus.REMOVED.value
            if record.install_status != desired_status:
                record.install_status = desired_status
                updated = True

            # For installed packages, probe export status and update lists.
            if installed:
                # Refresh the list of possible exportable files to
                # reflect any package updates. Errors here are
                # tolerated: if we cannot inspect the container, we
                # leave the old lists untouched but still evaluate
                # export_status based on existing exports.
                new_desktops: list[str] | None = None
                new_bins: list[str] | None = None
                try:
                    files = list_installed_files_in_container(container_name, name)
                    new_desktops = find_desktop_files(files)
                    new_bins = find_bin_candidates(files)
                except Exception:
                    # Unable to inspect container; leave lists as‑is
                    pass
                # Update record with new lists if they differ. Use the
                # computed lists only if successfully obtained.
                if new_desktops is not None and new_desktops != record.desktop_entries:
                    record.desktop_entries = new_desktops
                    updated = True
                if new_bins is not None and new_bins != record.binaries:
                    record.binaries = new_bins
                    updated = True
                # Determine whether exported artifacts still exist on the
                # host. Use the (possibly updated) record lists so that
                # renamed or changed desktop files are properly matched.
                exported_desktop = False
                exported_bin = False
                for path_str in record.desktop_entries:
                    try:
                        basename = PurePosixPath(path_str).name
                        # The host exported desktop files are prefixed with the
                        # container name (e.g. mja-arch-) by distrobox-export.
                        # To detect a valid export we look for either the
                        # unprefixed basename or a prefixed variant.
                        candidate_names = [basename, f"{container_name}-{basename}"]
                        # Check all candidates for existence
                        for candidate in candidate_names:
                            if (desktop_base / candidate).exists():
                                exported_desktop = True
                                break
                        if exported_desktop:
                            break
                    except Exception:
                        continue
                for path_str in record.binaries:
                    try:
                        basename = PurePosixPath(path_str).name
                        if (bin_base / basename).exists():
                            exported_bin = True
                            break
                    except Exception:
                        continue
                # Derive export_status based on host existence and
                # available exportable content. If exported files exist,
                # reflect that in the status. Otherwise, distinguish
                # between cases where exports were not requested and
                # cases where exportable content exists but has not
                # been exported.
                new_export_status: str
                if exported_desktop:
                    new_export_status = ExportStatus.DESKTOP_EXPORTED.value
                elif exported_bin:
                    new_export_status = ExportStatus.BIN_EXPORTED.value
                else:
                    # No exported artifacts found on host.  Distinguish between
                    # three cases: (1) user explicitly disabled exports
                    # (export_mode == none) -> not_requested; (2) there are
                    # exportable files but no corresponding host export ->
                    # export_missing; (3) there are no exportable files at
                    # all -> none_available.
                    if record.export_mode == ExportMode.NONE.value:
                        new_export_status = ExportStatus.NOT_REQUESTED.value
                    else:
                        if record.desktop_entries or record.binaries:
                            new_export_status = ExportStatus.EXPORT_MISSING.value
                        else:
                            new_export_status = ExportStatus.NONE_AVAILABLE.value
                if record.export_status != new_export_status:
                    record.export_status = new_export_status
                    updated = True
            else:
                # Package is removed: mark export as not requested and
                # clear recorded exportable lists.
                if record.export_status != ExportStatus.NOT_REQUESTED.value:
                    record.export_status = ExportStatus.NOT_REQUESTED.value
                    updated = True
                if record.desktop_entries or record.binaries:
                    record.desktop_entries = []
                    record.binaries = []
                    updated = True

        else:
            # Unknown source type; treat as removed and clear export.
            if record.install_status != InstallStatus.REMOVED.value:
                record.install_status = InstallStatus.REMOVED.value
                updated = True
            if record.export_status != ExportStatus.NOT_REQUESTED.value:
                record.export_status = ExportStatus.NOT_REQUESTED.value
                updated = True
            if record.desktop_entries or record.binaries:
                record.desktop_entries = []
                record.binaries = []
                updated = True

        # Clear any previous error on successful reconciliation.
        if updated or record.last_error:
            record.last_error = None
            record.updated_at = now_iso()
            state_store.upsert_package(name, record)
        summaries.append(
            {
                "package": name,
                "source": record.source,
                "install_status": record.install_status,
                "export_status": record.export_status,
                "container": record.container,
                "desktop_entries": record.desktop_entries,
                "binaries": record.binaries,
            }
        )

    return summaries