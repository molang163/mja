"""
Removal command for the mja CLI.

This module encapsulates the logic for removing a previously installed
package. Removal is supported for both host repository packages and
packages installed inside the AUR container. For container-based
packages, optional unexport of previously exported desktop files or
binaries is supported via the ``--unexport`` flag.

State mutations follow the same pattern as installation: the package
record's ``install_status`` transitions through ``removing`` and
``removed`` states, and any errors encountered are persisted in
``last_error``. Removal does not delete the record entirely from the
state file, providing a history of past actions.
"""

from __future__ import annotations

from typing import Any, Dict

from .errors import MjaError
from .models import (
    ExportStatus,
    InstallStatus,
    SourceKind,
    now_iso,
)
from .runtime import require_binary, run, command_failure_details
from .state import StateStore

from .install import (
    DEFAULT_CONTAINER_NAME,
    DEFAULT_EXPORT_PATH,
    require_container_exists,
    require_paru_ready,
    container_run,
    sh_quote,
)

from pathlib import Path, PurePosixPath


def remove(
    name: str,
    *,
    unexport: bool = False,
    state_store: StateStore | None = None,
) -> Dict[str, Any]:
    """Remove an installed package and optionally unexport its artifacts.

    :param name: The package name recorded in the state file. This must
        exactly match the key used at installation time.
    :param unexport: When True, also remove any desktop or binary exports
        created during installation. This option only has an effect for
        AUR container packages.
    :param state_store: Optional custom StateStore instance.
    :returns: A dictionary summarising the outcome of the removal.
    :raises MjaError: If the package is not recorded or removal fails.
    """
    state_store = state_store or StateStore()
    state = state_store.load()
    record = state.packages.get(name)
    if not record:
        # Nothing to remove
        raise MjaError(
            "E050 NOT_INSTALLED",
            f"package not recorded: {name}",
        )

    # If the package is already marked as removed, do not call the package
    # manager again. We may still need to handle leftover exports when
    # --unexport is provided.
    # Normalise removed status check by comparing string literal. Avoid accidental
    # mismatch if enums change in future.
    if record.install_status == InstallStatus.REMOVED.value or record.install_status == "removed":
        # Optionally attempt unexport for AUR packages
        if unexport and record.source == SourceKind.AUR_CONTAINER.value:
            container_name = record.container or DEFAULT_CONTAINER_NAME
            try:
                # Unexport desktop entries
                for desktop_file in record.desktop_entries:
                    res = container_run(
                        container_name,
                        f"distrobox-export --app {sh_quote(desktop_file)} --delete",
                        check=False,
                    )
                    # Determine whether to fall back to host-side deletion.  We
                    # consider both a non-zero return code and a success code
                    # that nonetheless reports "cannot find" in the output.
                    fallback = False
                    if res.returncode != 0:
                        fallback = True
                    else:
                        combined_output = (res.stdout or "") + (res.stderr or "")
                        if "cannot find" in combined_output.lower():
                            fallback = True
                    if fallback:
                        try:
                            basename = PurePosixPath(desktop_file).name
                            # distrobox-export prepends the container name to the exported
                            # desktop file; attempt to remove both prefixed and unprefixed
                            # variants on the host.  See state.rebuild for similar logic.
                            candidates = [basename, f"{container_name}-{basename}"]
                            for candidate in candidates:
                                host_path = Path.home() / ".local/share/applications" / candidate
                                if host_path.exists():
                                    host_path.unlink()
                            # treat missing host files as success
                        except Exception:
                            raise MjaError(
                                "E053 UNEXPORT_FAILED",
                                f"failed to unexport desktop: {desktop_file}",
                                command_failure_details(res),
                            )
                # Unexport binary wrappers
                for binary_path in record.binaries:
                    res = container_run(
                        container_name,
                        f"distrobox-export --bin {sh_quote(binary_path)} --export-path {sh_quote(DEFAULT_EXPORT_PATH)} --delete",
                        check=False,
                    )
                    # Determine whether to fall back to host-side deletion.
                    fallback = False
                    if res.returncode != 0:
                        fallback = True
                    else:
                        combined_output = (res.stdout or "") + (res.stderr or "")
                        # distrobox-export may exit with code 0 but still report missing target
                        if "cannot find" in combined_output.lower():
                            fallback = True
                    if fallback:
                        # Attempt to remove the host-side wrapper directly.
                        try:
                            wrapper_name = PurePosixPath(binary_path).name
                            host_path = Path(DEFAULT_EXPORT_PATH) / wrapper_name
                            if host_path.exists():
                                host_path.unlink()
                            # treat as success if file removed or did not exist
                        except Exception:
                            raise MjaError(
                                "E053 UNEXPORT_FAILED",
                                f"failed to unexport binary: {binary_path}",
                                command_failure_details(res),
                            )
                # After successful unexport, reset export related fields.  Regardless of
                # previous export_status, if we have removed any exported entries
                # (desktop entries or binaries), mark the export as not requested
                # and clear the lists.
                if record.desktop_entries or record.binaries:
                    record.export_status = ExportStatus.NOT_REQUESTED.value
                    record.desktop_entries = []
                    record.binaries = []
                    # Clear any previous error after a successful unexport
                    record.last_error = None
                    record.updated_at = now_iso()
                    state_store.upsert_package(name, record)
            except MjaError as exc:
                # Unexport failed: mark export_status as failed; install_status stays removed
                record.export_status = ExportStatus.FAILED.value
                record.last_error = str(exc)
                record.updated_at = now_iso()
                state_store.upsert_package(name, record)
                raise
        # Return current state without invoking package manager
        return {
            "package": name,
            "source": record.source,
            "install_status": record.install_status,
            "export_status": record.export_status,
            "container": record.container,
        }

    # Update status to REMOVING and persist immediately
    record.install_status = InstallStatus.REMOVING.value
    record.updated_at = now_iso()
    record.last_error = None
    state_store.upsert_package(name, record)

    # First stage: perform the removal itself. Failures here set the
    # install_status to FAILED and skip any unexport processing.
    try:
        if record.source == SourceKind.HOST_REPO.value:
            # Remove via pamac on the host. Do not raise immediately on failure;
            # we verify with pacman below to support 'target not found' cases.
            require_binary("pamac", "E001 PAMAC_NOT_FOUND")
            run(["pamac", "remove", name], capture=False, check=False)
            # Verify whether the package still exists using pacman -Q. If the package
            # is still installed (exit code 0), treat as removal failure; otherwise
            # consider removal successful even if pamac returned a non-zero code.
            result = run(["pacman", "-Q", name], check=False)
            if result.returncode == 0:
                raise MjaError(
                    "E051 HOST_REMOVE_FAILED",
                    f"host package still installed after removal: {name}",
                )

        elif record.source == SourceKind.AUR_CONTAINER.value:
            container_name = record.container or DEFAULT_CONTAINER_NAME
            # Require the container to exist and have paru available.  These
            # helpers will raise errors if the environment is not ready but
            # will not create containers or bootstrap tooling.
            require_container_exists(container_name, state_store=state_store)
            require_paru_ready(container_name, state_store=state_store)
            # Remove via paru inside the container
            cmd = f"paru -R --noconfirm {sh_quote(name)}"
            # Capture output to detect "target not found"
            result = container_run(container_name, cmd, check=False, capture=True)
            if result.returncode != 0:
                # If the package is already absent, paru reports "target not found: <name>"
                combined_output = (result.stdout or "") + (result.stderr or "")
                if "target not found" not in combined_output.lower():
                    raise MjaError(
                        "E052 CONTAINER_REMOVE_FAILED",
                        f"failed to remove AUR package: {name}",
                        command_failure_details(result),
                    )
            # Verify the package is gone using pacman -Q
            verify = container_run(container_name, f"pacman -Q {sh_quote(name)}", check=False)
            if verify.returncode == 0:
                # pacman still sees the package; treat as a removal failure
                raise MjaError(
                    "E052 CONTAINER_REMOVE_FAILED",
                    f"container package still installed after removal: {name}",
                )
        else:
            # Unknown source kind; should not happen but handle defensively
            raise MjaError(
                "E051 UNKNOWN_SOURCE",
                f"unknown source for removal: {record.source}",
            )

    except MjaError as exc:
        # Removal failed: mark failed and propagate
        record.install_status = InstallStatus.FAILED.value
        record.last_error = str(exc)
        record.updated_at = now_iso()
        state_store.upsert_package(name, record)
        raise

    # At this point removal was successful
    record.install_status = InstallStatus.REMOVED.value
    record.updated_at = now_iso()
    state_store.upsert_package(name, record)

    # Second stage: unexport if requested and applicable. Errors here should
    # not flip the install_status back to failed; instead they update
    # export_status to failed.
    if unexport and record.source == SourceKind.AUR_CONTAINER.value:
        container_name = record.container or DEFAULT_CONTAINER_NAME
        try:
            # Unexport desktop entries
            for desktop_file in record.desktop_entries:
                res = container_run(
                    container_name,
                    f"distrobox-export --app {sh_quote(desktop_file)} --delete",
                    check=False,
                )
                # Determine whether to fall back to host-side deletion.
                fallback = False
                if res.returncode != 0:
                    fallback = True
                else:
                    combined_output = (res.stdout or "") + (res.stderr or "")
                    if "cannot find" in combined_output.lower():
                        fallback = True
                if fallback:
                    try:
                        basename = PurePosixPath(desktop_file).name
                        candidates = [basename, f"{container_name}-{basename}"]
                        for candidate in candidates:
                            host_path = Path.home() / ".local/share/applications" / candidate
                            if host_path.exists():
                                host_path.unlink()
                        # treat missing host files as success
                    except Exception:
                        raise MjaError(
                            "E053 UNEXPORT_FAILED",
                            f"failed to unexport desktop: {desktop_file}",
                            command_failure_details(res),
                        )
            # Unexport binary wrappers
            for binary_path in record.binaries:
                res = container_run(
                    container_name,
                    f"distrobox-export --bin {sh_quote(binary_path)} --export-path {sh_quote(DEFAULT_EXPORT_PATH)} --delete",
                    check=False,
                )
                fallback = False
                if res.returncode != 0:
                    fallback = True
                else:
                    combined_output = (res.stdout or "") + (res.stderr or "")
                    if "cannot find" in combined_output.lower():
                        fallback = True
                if fallback:
                    try:
                        wrapper_name = PurePosixPath(binary_path).name
                        host_path = Path(DEFAULT_EXPORT_PATH) / wrapper_name
                        if host_path.exists():
                            host_path.unlink()
                    except Exception:
                        raise MjaError(
                            "E053 UNEXPORT_FAILED",
                            f"failed to unexport binary: {binary_path}",
                            command_failure_details(res),
                        )
            # After successful unexport, reset export related fields.  Regardless of previous
            # export_status, if we removed any exported entries, mark the export as
            # not requested and clear lists.
            if record.desktop_entries or record.binaries:
                record.export_status = ExportStatus.NOT_REQUESTED.value
                record.desktop_entries = []
                record.binaries = []
                # Clear any previous error after a successful unexport
                record.last_error = None
                record.updated_at = now_iso()
                state_store.upsert_package(name, record)
        except MjaError as exc:
            # Unexport failed: mark export_status as failed but keep install_status as removed
            record.export_status = ExportStatus.FAILED.value
            record.last_error = str(exc)
            record.updated_at = now_iso()
            state_store.upsert_package(name, record)
            raise

    # Build and return result summary
    return {
        "package": name,
        "source": record.source,
        "install_status": record.install_status,
        "export_status": record.export_status,
        "container": record.container,
    }