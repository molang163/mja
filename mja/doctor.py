from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import MjaError
from .models import StateFile, SourceKind, InstallStatus, ExportStatus
from .runtime import detect_container_runtime, which
from .install import DEFAULT_CONTAINER_NAME, find_desktop_files, find_bin_candidates, list_installed_files_in_container, container_run, distrobox_exists, sh_quote
from .state import StateStore


@dataclass(slots=True)
class Check:
    """Represents the result of a single health check.

    The ``name`` identifies the check, ``ok`` indicates whether the
    underlying requirement is satisfied, and ``detail`` contains a
    human‑readable description or error message.  When a check is not
    applicable in the current context (for example, container checks on
    a system that has never used the AUR container), the ``skipped``
    flag should be set to ``True``.  Skipped checks do not count as
    failures and are reported distinctly in both human and JSON output.
    """
    name: str
    ok: bool
    detail: str
    skipped: bool = False


def run_doctor(*, fix: bool = False, state_store: StateStore | None = None) -> dict[str, Any]:
    """Run a series of diagnostic checks and return a report.

    The doctor command verifies the presence of required host tools,
    inspects the state file for corruption, and optionally probes the
    AUR container environment. Container checks are performed only when
    there is evidence that a container is actually in use (i.e. when
    the state file records one or more containers or packages from the
    AUR). On a completely fresh installation with no recorded
    container usage, these checks are marked as skipped and do not
    influence the overall ``ok`` status.
    """
    state_store = state_store or StateStore()

    # Base checks for required host tools and container runtime
    checks: list[Check] = [
        check_binary("python", "python interpreter"),
        check_binary("pacman", "repo database / verification"),
        check_binary("pamac", "host repo install path"),
        check_binary("distrobox", "container orchestration"),
        check_runtime(),
    ]

    state_dir = state_store.directory
    state_file = state_store.path
    state_dir_exists = state_dir.exists()
    state_file_exists = state_file.exists()
    state_status = "missing"
    backup_path: str | None = None
    current_state: StateFile | None = None

    # Load the state file to determine its status. If corrupted the
    # caller can request a fix; otherwise propagate errors.
    try:
        current_state = state_store.load()
        state_status = "ok" if state_file_exists else "missing"
    except MjaError as exc:
        if exc.code != "E040 STATE_CORRUPTED":
            raise
        state_status = "corrupted"
        if fix:
            state_store.ensure_directory()
            backup_path = backup_corrupted_state(state_file)
            state_store.save(StateFile())
            state_status = "rebuilt"
            state_dir_exists = state_dir.exists()
            state_file_exists = state_file.exists()
            current_state = state_store.load()

    # If the state file was entirely missing and fix is requested, create it
    if fix and state_status == "missing":
        state_store.ensure_directory()
        if not state_file.exists():
            state_store.save(StateFile())
            state_status = "created"
        state_dir_exists = state_dir.exists()
        state_file_exists = state_file.exists()
        current_state = state_store.load()

    # Determine whether any container checks should be performed. We only
    # probe the default container when the state records at least one
    # container or at least one package whose source is AUR_CONTAINER.
    needs_container_checks = False
    if current_state:
        if current_state.containers:
            needs_container_checks = True
        else:
            # fall back to package records
            for pkg in current_state.packages.values():
                if pkg.source == SourceKind.AUR_CONTAINER.value:
                    needs_container_checks = True
                    break

    # Extended checks: container existence, ability to enter, paru presence,
    # and validation of recorded containers. These are wrapped in a try/except
    # to avoid aborting the doctor command on unexpected failures.
    try:
        if needs_container_checks:
            # Check whether the default container exists
            exists = False
            try:
                exists = distrobox_exists(DEFAULT_CONTAINER_NAME)
            except Exception:
                exists = False
            checks.append(Check("container-exists", exists, f"{DEFAULT_CONTAINER_NAME} exists", skipped=False))
            # Check whether we can enter the container
            enter_ok = False
            if exists:
                try:
                    res = container_run(DEFAULT_CONTAINER_NAME, "true", check=False)
                    enter_ok = res.returncode == 0
                except Exception:
                    enter_ok = False
            checks.append(Check("container-enter", enter_ok, f"enter {DEFAULT_CONTAINER_NAME}", skipped=False))
            # Check for paru inside container
            paru_ok = False
            if exists:
                try:
                    res = container_run(DEFAULT_CONTAINER_NAME, "command -v paru", check=False)
                    paru_ok = res.returncode == 0
                except Exception:
                    paru_ok = False
            checks.append(Check("container-paru", paru_ok, f"paru in {DEFAULT_CONTAINER_NAME}", skipped=False))
            # Validate that all containers recorded in state exist
            for cname in current_state.containers.keys():
                ok = False
                try:
                    ok = distrobox_exists(cname)
                except Exception:
                    ok = False
                checks.append(Check(f"record-container-{cname}", ok, f"recorded container {cname} exists", skipped=False))
        else:
            # If no container is expected, mark checks as skipped so the overall
            # ok status remains unaffected and report that container checks were
            # not applicable.  Setting ``skipped=True`` ensures the JSON
            # output includes an explicit flag.
            checks.append(Check("container-exists", True, "no AUR container configured", skipped=True))
            checks.append(Check("container-enter", True, "no AUR container configured", skipped=True))
            checks.append(Check("container-paru", True, "no AUR container configured", skipped=True))
        # Validate that exported files recorded in state exist on host. Only
        # perform this check for AUR container packages that are currently
        # installed and have an export_status indicating that artifacts should
        # exist. Removed packages or those where the user never requested an
        # export are skipped. This avoids misleading reports about "exported
        # artifacts present" on removed or never exported packages (see issue
        # v0.3‑doctor‑skip).
        if current_state:
            desktop_base = Path.home() / ".local/share/applications"
            bin_base = Path.home() / ".local/bin"
            for pkg_name, record in current_state.packages.items():
                if record.source != SourceKind.AUR_CONTAINER.value:
                    continue
                # Skip packages that are not installed
                if record.install_status != InstallStatus.INSTALLED.value:
                    continue
                # If the export status explicitly indicates missing artifacts,
                # report this as a problem and skip further checks for this
                # package.  When state rebuild encounters exportable
                # artifacts in the container but none exported on the host,
                # it marks the export_status as EXPORT_MISSING.
                if record.export_status == ExportStatus.EXPORT_MISSING.value:
                    checks.append(Check(f"export-{pkg_name}", False, "missing host export artifacts"))
                    continue

                # Only check when export_status expects artifacts to exist
                if record.export_status not in {
                    ExportStatus.DESKTOP_EXPORTED.value,
                    ExportStatus.BIN_EXPORTED.value,
                }:
                    continue
                missing: list[str] = []
                cname = record.container or DEFAULT_CONTAINER_NAME
                # Depending on export_status, only verify the corresponding type
                # of exported artifact. When desktop_exported, ignore binary
                # wrappers; when bin_exported, ignore desktop entries.
                if record.export_status == ExportStatus.DESKTOP_EXPORTED.value:
                    exported_desktop = False
                    # Check desktop entries: handle both unprefixed and
                    # container-prefixed names
                    for path_str in record.desktop_entries:
                        try:
                            basename = Path(path_str).name
                            candidate_names = [basename, f"{cname}-{basename}"]
                            found = any((desktop_base / candidate).exists() for candidate in candidate_names)
                            if found:
                                exported_desktop = True
                            else:
                                missing.append(f"desktop:{basename}")
                        except Exception:
                            missing.append(f"desktop:{path_str}")
                    # Determine check outcome for desktop exports only
                    if exported_desktop and not missing:
                        checks.append(Check(f"export-{pkg_name}", True, "exported artifacts present"))
                    else:
                        detail = f"missing: {', '.join(missing)}" if missing else "no exported artifacts found"
                        checks.append(Check(f"export-{pkg_name}", False, detail))
                elif record.export_status == ExportStatus.BIN_EXPORTED.value:
                    exported_bin = False
                    # Check binary wrappers only (no prefix for binaries)
                    for path_str in record.binaries:
                        try:
                            basename = Path(path_str).name
                            if (bin_base / basename).exists():
                                exported_bin = True
                            else:
                                missing.append(f"bin:{basename}")
                        except Exception:
                            missing.append(f"bin:{path_str}")
                    # Determine check outcome for bin exports only
                    if exported_bin and not missing:
                        checks.append(Check(f"export-{pkg_name}", True, "exported artifacts present"))
                    else:
                        detail = f"missing: {', '.join(missing)}" if missing else "no exported artifacts found"
                        checks.append(Check(f"export-{pkg_name}", False, detail))
    except Exception:
        # Do not break the doctor output if any of the extended checks fail
        pass

    return {
        "checks": [asdict(check) for check in checks],
        "state_dir": {"path": str(state_dir), "exists": state_dir_exists},
        "state_file": {
            "path": str(state_file),
            "exists": state_file_exists,
            "status": state_status,
            "backup_path": backup_path,
        },
        "fix_applied": fix,
        "ok": all(check.ok for check in checks) and state_status in {"ok", "created", "rebuilt", "missing"},
    }


def backup_corrupted_state(path: Path) -> str | None:
    if not path.exists():
        return None
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    path.replace(backup)
    return str(backup)


def format_doctor(report: dict[str, Any]) -> str:
    lines = []
    for check in report["checks"]:
        # Display a distinct marker for skipped checks.  When a check
        # reports ``skipped`` the requirement was not applicable for the
        # current system (for example, container checks on a fresh
        # installation).  Otherwise show OK or MISSING based on the
        # underlying ``ok`` flag.
        if check.get("skipped"):
            marker = "SKIPPED"
        else:
            marker = "OK" if check["ok"] else "MISSING"
        lines.append(f"[{marker}] {check['name']}: {check['detail']}")
    lines.append(
        f"[{'OK' if report['state_dir']['exists'] else 'MISSING'}] state_dir: {report['state_dir']['path']}"
    )

    state_file = report["state_file"]
    if state_file["status"] in {"ok", "created", "rebuilt"}:
        marker = "OK"
    elif state_file["status"] == "corrupted":
        marker = "CORRUPT"
    else:
        marker = "MISSING"
    lines.append(f"[{marker}] state_file: {state_file['path']} ({state_file['status']})")
    if state_file.get("backup_path"):
        lines.append(f"[INFO] state_backup: {state_file['backup_path']}")
    return "\n".join(lines)


def check_binary(binary: str, purpose: str) -> Check:
    path = which(binary)
    if path:
        return Check(binary, True, f"{purpose} -> {path}")
    return Check(binary, False, purpose)


def check_runtime() -> Check:
    runtime = detect_container_runtime()
    if runtime:
        return Check("container-runtime", True, runtime)
    return Check("container-runtime", False, "neither podman nor docker found")
