"""
Repair utilities for the mja CLI.

This module implements the logic behind the ``mja repair export`` subcommand
introduced in version 0.3.0. The goal of the repair operation is to
re-evaluate and, if necessary, re-export the artifacts (desktop entries
and binary wrappers) for a package that is already installed inside the
container. It only works on packages that were originally installed via
the AUR container path. Host repository packages are not eligible for
export repair because they never create exported artifacts.

The repair process performs the following high‑level steps:

* Load the package record from the state file and verify it originates
  from an AUR container. If the package is unknown or was installed
  from the host repo, an error is raised.
* Ensure the target container exists and has the appropriate tools
  installed. This reuses the install‑time helpers to check for
  distrobox and the presence of paru within the container.
* Check that the package is still installed inside the container. A
  missing package results in a failure for the repair export operation.
* Rebuild the list of installed files in the container, extract
  desktop files and binary candidates, and store those lists back
  into the record. This accounts for package updates that may change
  the installed file set.
* Depending on the selected repair mode (auto, desktop or bin), call
  the appropriate export helper. In ``auto`` mode the repair will
  prefer desktop exports when at least one desktop file exists;
  otherwise it falls back to exporting a binary wrapper if possible.
* Update the record's export status, clear any previous error and
  persist the updated state. On failures the record's install status
  is left untouched and only the export status and ``last_error`` are
  modified.

The function :func:`repair_export` encapsulates this behaviour and is
invoked from the CLI. The return value mirrors the structure of
installation operations and can be formatted using the existing
helpers in :mod:`mja.cli`.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Dict

from .errors import MjaError
from .models import (
    ExportMode,
    ExportStatus,
    InstallStatus,
    SourceKind,
    now_iso,
)
from .state import StateStore
from .install import (
    DEFAULT_CONTAINER_NAME,
    find_bin_candidates,
    find_desktop_files,
    list_installed_files_in_container,
    export_desktop_files,
    export_binary,
    choose_binary,
    # verify_container_install,  # avoid using install‑specific verification
    require_container_exists,
    require_paru_ready,
    container_run,
    sh_quote,
)


def repair_export(
    name: str,
    *,
    mode: ExportMode = ExportMode.AUTO,
    selected_bin: str | None = None,
    state_store: StateStore | None = None,
) -> Dict[str, Any]:
    """Attempt to re‑export the artifacts for a previously installed package.

    This function re-evaluates the exportable files for the given package
    and, based on the chosen repair mode, attempts to export desktop
    entries or binary wrappers as appropriate. The underlying package
    installation is not modified – only export related information is
    refreshed. If the package no longer exists in the container, the
    repair operation will fail and the record will reflect that failure
    in its ``export_status`` and ``last_error`` fields.

    :param name: The exact package name recorded in the state file.
    :param mode: The repair mode. ``auto`` prefers desktop export and
      falls back to binary export if no desktop entries exist.
    :param selected_bin: When repairing in binary mode, optionally
      specify which binary candidate to wrap. This mirrors the
      ``--bin`` flag of the install command.
    :param state_store: Optional alternate state store.
    :returns: A summary dictionary describing the new state of the
      package after the repair attempt.
    :raises MjaError: If the package is unknown, not an AUR container
      package, or if re-export fails.
    """
    state_store = state_store or StateStore()
    state = state_store.load()
    record = state.packages.get(name)
    if not record:
        raise MjaError(
            "E050 NOT_INSTALLED",
            f"package not recorded: {name}",
        )
    # Only AUR container packages support exporting artifacts. Host repo
    # packages never receive desktop or binary exports.
    if record.source != SourceKind.AUR_CONTAINER.value:
        raise MjaError(
            "E054 NOT_AUR_CONTAINER",
            f"repair export only supported for AUR container packages: {name}",
        )

    # Determine the effective container name. If none is stored we fall
    # back to the default container used at install time.
    container_name = record.container or DEFAULT_CONTAINER_NAME

    # Require the container to exist and have the necessary tooling.  These
    # helpers will raise if the environment is not prepared but will not
    # create containers or bootstrap tooling, avoiding unintended side effects.
    try:
        require_container_exists(container_name, state_store=state_store)
        require_paru_ready(container_name, state_store=state_store)
    except MjaError as exc:
        # Mark export as failed; do not modify installation status.
        record.export_status = ExportStatus.FAILED.value
        record.last_error = str(exc)
        record.updated_at = now_iso()
        state_store.upsert_package(name, record)
        raise

    # Verify the package is still installed inside the container.
    # Using verify_container_install here would surface the generic
    # ``E024 VERIFY_INSTALL_FAILED`` error which conflates missing
    # installations during repair with install‑time verification failures.
    # Instead, probe pacman directly and raise a more specific error
    # when the package is not installed. This avoids leaking install
    # semantics into the repair/export path. See issue #v0.3‑repair-not-installed.
    try:
        probe = container_run(container_name, f"pacman -Q {sh_quote(name)}", check=False)
        if probe.returncode != 0:
            # Package is not present inside the container. Mark export as
            # failed and raise a dedicated error. Do not modify
            # install_status; only export_status and last_error are
            # updated.
            err = MjaError(
                "E055 REPAIR_EXPORT_NOT_INSTALLED",
                f"package not installed; cannot repair export: {name}",
            )
            record.export_status = ExportStatus.FAILED.value
            record.last_error = str(err)
            record.updated_at = now_iso()
            state_store.upsert_package(name, record)
            raise err
    except MjaError as exc:
        # Unexpected error while probing. Preserve installation status and
        # surface the error.
        record.export_status = ExportStatus.FAILED.value
        record.last_error = str(exc)
        record.updated_at = now_iso()
        state_store.upsert_package(name, record)
        raise

    # Recompute the list of installed files and derive desktop files and
    # binary candidates. Always update the record so future operations
    # have accurate metadata.
    try:
        files = list_installed_files_in_container(container_name, name)
    except MjaError as exc:
        # Unexpected failure to list files. Treat as export failure.
        record.export_status = ExportStatus.FAILED.value
        record.last_error = str(exc)
        record.updated_at = now_iso()
        state_store.upsert_package(name, record)
        raise

    desktop_files = find_desktop_files(files)
    bin_candidates = find_bin_candidates(files)
    record.desktop_entries = desktop_files
    record.binaries = bin_candidates

    # Perform the export according to the chosen mode. Clearing last_error
    # only upon success avoids hiding previous error context.
    try:
        # Convert string inputs into Enum for robust comparisons.
        if isinstance(mode, str):
            mode_enum = ExportMode(mode)
        else:
            mode_enum = mode
        # auto: prefer desktop; fallback to binary
        if mode_enum == ExportMode.AUTO:
            if desktop_files:
                export_desktop_files(container_name, desktop_files)
                record.export_status = ExportStatus.DESKTOP_EXPORTED.value
            elif bin_candidates:
                target = choose_binary(bin_candidates, selected_bin)
                export_binary(container_name, target)
                record.export_status = ExportStatus.BIN_EXPORTED.value
            else:
                record.export_status = ExportStatus.NONE_AVAILABLE.value
        elif mode_enum == ExportMode.DESKTOP:
            if desktop_files:
                export_desktop_files(container_name, desktop_files)
                record.export_status = ExportStatus.DESKTOP_EXPORTED.value
            else:
                # In desktop repair mode, align semantics with install-time
                # behaviour by raising an error when no desktop files are
                # available.  This avoids silently recording a none_available
                # status and instead surfaces a clear E030 error to the user.
                raise MjaError(
                    "E030 NO_DESKTOP_FILES",
                    "desktop export requested, but no desktop files were installed",
                )
        elif mode_enum == ExportMode.BIN:
            # Choose the appropriate binary. If no candidates exist this
            # helper will raise E031/E032/E033 accordingly.
            target = choose_binary(bin_candidates, selected_bin)
            export_binary(container_name, target)
            record.export_status = ExportStatus.BIN_EXPORTED.value
        else:
            raise MjaError(
                "E099 INVALID_EXPORT_MODE",
                f"unsupported repair mode: {mode_enum}",
            )
        # On success clear previous error
        record.last_error = None
    except MjaError as exc:
        # Export failed; preserve installation status and note error.
        record.export_status = ExportStatus.FAILED.value
        record.last_error = str(exc)
        record.updated_at = now_iso()
        state_store.upsert_package(name, record)
        raise

    record.updated_at = now_iso()
    state_store.upsert_package(name, record)
    return {
        "package": name,
        "source": record.source,
        "container": container_name,
        "install_status": record.install_status,
        "export_status": record.export_status,
        "desktop_entries": record.desktop_entries,
        "binaries": record.binaries,
    }