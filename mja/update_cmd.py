"""
Update command for the mja CLI.

This module implements the ``mja update`` subcommand. Updating allows
the user to synchronise their host repository packages and/or AUR
container packages with the latest versions available in their
respective repositories. Unlike installation, the update operation does
not attempt to track individual package version changes – it merely
invokes the appropriate update commands and records a timestamp.

The supported command line flags map to the following behaviours:

* ``--host``: run the host package manager's update command. On
  Manjaro this is provided via pamac. The update is performed
  non-interactively. If pamac is missing, the operation fails.
* ``--container``: update all known containers recorded in the state
  file by invoking ``paru -Syu`` inside each one. If a container is
  unreachable, it is skipped.
* ``--all``: equivalent to specifying both ``--host`` and
  ``--container``.

If no flags are provided the default is ``--all``. The update
operation collects the outcome of each update step and returns a
summary dictionary. The last_update timestamp of each successfully
updated container is refreshed.
"""

from __future__ import annotations

from typing import Any, Dict

from .errors import MjaError
from .state import StateStore
from .runtime import require_binary, run
from .install import (
    require_container_exists,
    require_paru_ready,
    container_run,
)
from .models import now_iso


def update_packages(
    *,
    update_host: bool = False,
    update_container: bool = False,
    state_store: StateStore | None = None,
) -> Dict[str, Any]:
    """Perform update operations for host and/or container packages.

    :param update_host: If True, update host repository packages via pamac.
    :param update_container: If True, update AUR containers via paru.
    :param state_store: Optional alternate state store.
    :returns: A summary dictionary containing the outcome of each update
      category and any error messages.
    :raises MjaError: If the host update command is unavailable.
    """
    state_store = state_store or StateStore()
    state = state_store.load()
    results: dict[str, Any] = {"host": None, "containers": {}}

    # Determine default behaviour: if neither flag is set, treat as both.
    if not update_host and not update_container:
        update_host = True
        update_container = True

    # Host update via pamac
    if update_host:
        try:
            require_binary("pamac", "E001 PAMAC_NOT_FOUND")
            # Run the update with streaming output.  Do not enforce a zero
            # return code so we can inspect failures.  Output is not
            # captured but will appear on the user's terminal.  run() will
            # append a brief entry to ~/.local/state/mja/logs/latest.log when
            # capture=False.
            res = run(["pamac", "update", "--no-confirm"], check=False, capture=False)
            # If the initial streaming run succeeds, mark as ok.
            if res.returncode == 0:
                host_result: dict[str, Any] = {"ok": True}
                results["host"] = host_result
            else:
                # Do not rerun the update command.  Instead, surface a concise
                # message directing the user to the terminal.  The optional
                # log file (~/.local/state/mja/logs/latest.log) only records
                # the command and return code and does not include full
                # stdout/stderr.  Be explicit so users know where to look
                # for complete diagnostics.
                err_msg = (
                    "host update failed; see terminal output for details "
                    "(latest.log only records the command and return code)"
                )
                host_result = {"ok": False, "error": err_msg}
                results["host"] = host_result
        except MjaError as exc:
            results["host"] = {"ok": False, "error": str(exc)}

    # Container updates via paru
    if update_container:
        for container_name, container_record in state.containers.items():
            # Attempt to update only containers that are tracked in the state
            # and have a ready status. If not ready, skip.
            if getattr(container_record, "status", "") != "ready":
                continue
            try:
                # Require container existence and paru readiness.  These calls will
                # raise errors instead of creating containers or bootstrapping paru.
                require_container_exists(container_name, state_store=state_store)
                require_paru_ready(container_name, state_store=state_store)
                # Run paru update inside the container with streaming output.  Do not
                # enforce a zero return code here so that we can inspect failures.
                result = container_run(
                    container_name,
                    "paru -Syu --noconfirm",
                    check=False,
                    capture=False,
                )
                if result.returncode == 0:
                    # First attempt succeeded; mark container as updated and update last_update.
                    container_record.last_update = now_iso()
                    state_store.save(state)
                    container_result: dict[str, Any] = {"ok": True}
                    results["containers"][container_name] = container_result
                else:
                    # Do not rerun the update command.  Surface a concise
                    # error message pointing the user to the terminal.  The
                    # optional latest.log only records the command and return
                    # code; it does not include full stdout/stderr.  Be
                    # explicit to avoid misleading users.
                    err_msg = (
                        f"container update failed in '{container_name}'; see terminal output for details "
                        "(latest.log only records the command and return code)"
                    )
                    container_result = {"ok": False, "error": err_msg}
                    results["containers"][container_name] = container_result
            except MjaError as exc:
                results["containers"][container_name] = {"ok": False, "error": str(exc)}

    return results