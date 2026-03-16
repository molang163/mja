from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .errors import MjaError
from .models import (
    ContainerRecord,
    ExportMode,
    ExportStatus,
    InstallPlan,
    InstallStatus,
    PackageRecord,
    ResolveSource,
    SourceKind,
    now_iso,
)
from .runtime import command_failure_details, detect_container_runtime, require_binary, run
from .search import aur_exact, aur_info, aur_search, repo_exact, repo_search
from .state import StateStore

DEFAULT_CONTAINER_NAME = "mja-arch"
DEFAULT_ARCH_IMAGE = "docker.io/library/archlinux:latest"
DEFAULT_EXPORT_PATH = str(Path.home() / ".local" / "bin")


def install(
    name: str,
    *,
    source: ResolveSource = ResolveSource.AUTO,
    export: ExportMode = ExportMode.AUTO,
    selected_bin: str | None = None,
    dry_run: bool = False,
    state_store: StateStore | None = None,
) -> dict[str, Any]:
    state_store = state_store or StateStore()

    ensure_base_ready()
    if source in (ResolveSource.AUTO, ResolveSource.REPO):
        require_binary("pacman", "E001 PACMAN_NOT_FOUND")

    plan = resolve_package(name, source=source)
    # If the resolved plan targets the host repository but the user did not
    # explicitly disable exports, demote AUTO to NONE. Repository installs
    # never support exporting artifacts.  This prevents E041 errors when
    # ``--source repo`` is used without overriding ``--export`` on the CLI.
    if plan.kind == SourceKind.HOST_REPO and export == ExportMode.AUTO:
        export = ExportMode.NONE
    if dry_run:
        return {
            "dry_run": True,
            "plan": plan.to_dict(),
            "export": export.value,
            "selected_bin": selected_bin,
        }

    if plan.kind == SourceKind.HOST_REPO:
        ensure_repo_ready()
        if export != ExportMode.NONE:
            raise MjaError(
                "E041 REPO_EXPORT_UNSUPPORTED",
                "repo installs do not support export; use --export none",
                {"source": plan.kind.value, "export": export.value},
            )
        return _install_repo(plan, export=export, state_store=state_store)

    ensure_container_prereqs()
    return _install_aur_container(
        plan,
        export=export,
        selected_bin=selected_bin,
        state_store=state_store,
    )


def ensure_base_ready() -> None:
    return None


def ensure_repo_ready() -> None:
    require_binary("pacman", "E001 PACMAN_NOT_FOUND")
    require_binary("pamac", "E001 PAMAC_NOT_FOUND")


def ensure_container_prereqs() -> None:
    require_binary("distrobox", "E002 DISTROBOX_NOT_FOUND")
    runtime = detect_container_runtime()
    if not runtime:
        raise MjaError("E003 CONTAINER_RUNTIME_NOT_FOUND", "neither podman nor docker was found")


def resolve_package(name: str, *, source: ResolveSource) -> InstallPlan:
    if source == ResolveSource.REPO:
        repo = repo_exact(name)
        if not repo:
            _raise_not_found_with_candidates(name, check_repo=True, check_aur=False)
        return InstallPlan(
            kind=SourceKind.HOST_REPO,
            requested_name=name,
            resolved_name=repo.name,
            display_name=repo.name,
            repo=repo.repo,
        )

    if source == ResolveSource.AUR:
        aur = aur_exact(name)
        if not aur:
            _raise_not_found_with_candidates(name, check_repo=False, check_aur=True)
        return InstallPlan(
            kind=SourceKind.AUR_CONTAINER,
            requested_name=name,
            resolved_name=aur.name,
            display_name=aur.name,
            container=DEFAULT_CONTAINER_NAME,
            aur_meta=aur_info(aur.name)["results"][0],
        )

    repo = repo_exact(name)
    if repo:
        return InstallPlan(
            kind=SourceKind.HOST_REPO,
            requested_name=name,
            resolved_name=repo.name,
            display_name=repo.name,
            repo=repo.repo,
        )

    aur = aur_exact(name)
    if aur:
        return InstallPlan(
            kind=SourceKind.AUR_CONTAINER,
            requested_name=name,
            resolved_name=aur.name,
            display_name=aur.name,
            container=DEFAULT_CONTAINER_NAME,
            aur_meta=aur_info(aur.name)["results"][0],
        )

    _raise_not_found_with_candidates(name, check_repo=True, check_aur=True)
    raise AssertionError("unreachable")


def _raise_not_found_with_candidates(name: str, *, check_repo: bool, check_aur: bool) -> None:
    candidates: dict[str, list[str]] = {"repo": [], "aur": []}
    if check_repo:
        candidates["repo"] = [item.name for item in repo_search(name)[:10]]
    if check_aur:
        candidates["aur"] = [item.name for item in aur_search(name)[:10]]

    if any(candidates.values()):
        raise MjaError(
            "E013 AMBIGUOUS_MATCH",
            f"no exact match for '{name}', refusing auto install",
            candidates,
        )
    raise MjaError("E012 PACKAGE_NOT_FOUND", f"package not found: {name}")


def _install_repo(
    plan: InstallPlan,
    *,
    export: ExportMode,
    state_store: StateStore,
) -> dict[str, Any]:
    requested_at = now_iso()
    record = PackageRecord(
        source=SourceKind.HOST_REPO.value,
        container=None,
        install_status=InstallStatus.INSTALLING.value,
        export_status=ExportStatus.NOT_REQUESTED.value,
        export_mode=export.value,
        requested_at=requested_at,
        installed_at=None,
        updated_at=requested_at,
    )
    state_store.upsert_package(plan.resolved_name, record)

    try:
        run(["pamac", "install", plan.resolved_name], capture=False)
        verify_host_install(plan.resolved_name)
    except MjaError as exc:
        record.install_status = InstallStatus.FAILED.value
        record.last_error = str(exc)
        state_store.upsert_package(plan.resolved_name, record)
        raise MjaError("E020 HOST_INSTALL_FAILED", "host repo install failed", str(exc)) from exc

    record.install_status = InstallStatus.INSTALLED.value
    record.export_status = ExportStatus.NOT_REQUESTED.value
    record.installed_at = now_iso()
    record.last_error = None
    state_store.upsert_package(plan.resolved_name, record)
    return {
        "package": plan.resolved_name,
        "source": plan.kind.value,
        "install_status": record.install_status,
        "export_status": record.export_status,
    }


def _install_aur_container(
    plan: InstallPlan,
    *,
    export: ExportMode,
    selected_bin: str | None,
    state_store: StateStore,
) -> dict[str, Any]:
    container_name = plan.container or DEFAULT_CONTAINER_NAME
    requested_at = now_iso()
    record = PackageRecord(
        source=SourceKind.AUR_CONTAINER.value,
        container=container_name,
        install_status=InstallStatus.INSTALLING.value,
        export_status=ExportStatus.PENDING.value if export != ExportMode.NONE else ExportStatus.NOT_REQUESTED.value,
        export_mode=export.value,
        requested_at=requested_at,
        installed_at=None,
        updated_at=requested_at,
    )
    state_store.upsert_package(plan.resolved_name, record)

    try:
        ensure_container_exists(container_name, state_store=state_store)
        ensure_paru_ready(container_name, state_store=state_store)
        container_install(container_name, plan.resolved_name)
        verify_container_install(container_name, plan.resolved_name)
    except MjaError as exc:
        record.install_status = InstallStatus.FAILED.value
        if record.export_status == ExportStatus.PENDING.value:
            record.export_status = ExportStatus.FAILED.value
        record.last_error = str(exc)
        state_store.upsert_package(plan.resolved_name, record)
        raise

    record.install_status = InstallStatus.INSTALLED.value
    record.installed_at = now_iso()
    record.last_error = None
    state_store.upsert_package(plan.resolved_name, record)

    try:
        files = list_installed_files_in_container(container_name, plan.resolved_name)
        desktop_files = find_desktop_files(files)
        bin_candidates = find_bin_candidates(files)
        record.desktop_entries = desktop_files
        record.binaries = bin_candidates

        export_status = maybe_export(
            container_name,
            export=export,
            desktop_files=desktop_files,
            bin_candidates=bin_candidates,
            selected_bin=selected_bin,
        )
        record.export_status = export_status.value
        record.last_error = None
    except MjaError as exc:
        record.export_status = ExportStatus.FAILED.value
        record.last_error = str(exc)
        state_store.upsert_package(plan.resolved_name, record)
        raise

    state_store.upsert_package(plan.resolved_name, record)
    return {
        "package": plan.resolved_name,
        "source": plan.kind.value,
        "container": container_name,
        "install_status": record.install_status,
        "export_status": record.export_status,
        "desktop_entries": record.desktop_entries,
        "binaries": record.binaries,
    }


def verify_host_install(name: str) -> None:
    result = run(["pacman", "-Q", name], check=False)
    if result.returncode != 0:
        raise MjaError("E024 VERIFY_INSTALL_FAILED", f"host package not installed after install: {name}")


def ensure_container_exists(container_name: str, *, state_store: StateStore) -> None:
    require_binary("distrobox", "E002 DISTROBOX_NOT_FOUND")
    runtime = detect_container_runtime()
    if not runtime:
        raise MjaError("E003 CONTAINER_RUNTIME_NOT_FOUND", "neither podman nor docker was found")

    if not distrobox_exists(container_name):
        create_cmd = [
            "distrobox",
            "create",
            "--name",
            container_name,
            "--image",
            DEFAULT_ARCH_IMAGE,
            "--yes",
            "--additional-packages",
            "sudo git base-devel",
        ]
        result = run(create_cmd, check=False, capture=False)
        if result.returncode != 0:
            raise MjaError(
                "E021 CONTAINER_CREATE_FAILED",
                "failed to create distrobox container",
                command_failure_details(result),
            )

    state = state_store.load()
    state.containers[container_name] = state.containers.get(container_name) or ContainerRecord(
        status="ready",
        runtime=runtime,
    )
    state_store.save(state)


# Require that a distrobox container already exists without implicitly creating it.
#
# This helper mirrors :func:`ensure_container_exists` but will raise an
# error instead of creating a new container. It is intended for commands
# that operate on existing state (e.g. remove, repair, update) where
# automatic side effects are undesirable.
def require_container_exists(container_name: str, *, state_store: StateStore) -> None:
    require_binary("distrobox", "E002 DISTROBOX_NOT_FOUND")
    runtime = detect_container_runtime()
    if not runtime:
        raise MjaError("E003 CONTAINER_RUNTIME_NOT_FOUND", "neither podman nor docker was found")

    if not distrobox_exists(container_name):
        # Do not create the container here; surface a dedicated error instead.
        raise MjaError(
            "E061 CONTAINER_NOT_FOUND",
            f"distrobox container not found: {container_name}",
        )

    # Update the runtime on an existing record if one exists; do not create a new record
    state = state_store.load()
    if container_name in state.containers:
        state.containers[container_name].runtime = runtime
        state_store.save(state)


def require_paru_ready(container_name: str, *, state_store: StateStore) -> None:
    """Ensure that paru is installed in the given container without bootstrapping it.

    This function checks whether the specified container exists and has the
    ``paru`` command available.  If the container is missing or ``paru`` is not
    installed, a descriptive :class:`MjaError` is raised.  Unlike
    :func:`ensure_paru_ready`, this helper does not attempt to create the
    container or bootstrap the AUR helper, avoiding unintended side effects
    during maintenance operations.
    """
    # First verify the container exists
    require_container_exists(container_name, state_store=state_store)
    # Probe for paru inside the container
    probe = container_run(container_name, "command -v paru", check=False)
    if probe.returncode != 0:
        raise MjaError(
            "E062 PARU_NOT_READY",
            f"paru is not available in container: {container_name}",
        )


def distrobox_exists(container_name: str) -> bool:
    result = run(["distrobox", "list", "--no-color"], check=False)
    if result.returncode != 0:
        raise MjaError(
            "E021 CONTAINER_CREATE_FAILED",
            "failed to list distrobox containers",
            command_failure_details(result),
        )

    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            continue
        if parts[1].upper() == "NAME":
            continue
        if parts[1] == container_name:
            return True
    return False


def ensure_paru_ready(container_name: str, *, state_store: StateStore) -> None:
    probe = container_run(container_name, "command -v paru", check=False)
    if probe.returncode == 0:
        return

    ensure_container_build_tooling(container_name)

    bootstrap_cmd = r"""
set -euo pipefail
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
cd "$workdir"
git clone https://aur.archlinux.org/paru.git
cd paru
makepkg -si --noconfirm
""".strip()
    bootstrap = container_run(container_name, bootstrap_cmd, check=False, capture=False)
    if bootstrap.returncode != 0:
        raise MjaError(
            "E022 PARU_BOOTSTRAP_FAILED",
            "failed to bootstrap paru",
            command_failure_details(bootstrap),
        )

    state = state_store.load()
    if container_name in state.containers:
        state.containers[container_name].aur_helper = "paru"
        state.containers[container_name].last_update = now_iso()
        state_store.save(state)


def ensure_container_build_tooling(container_name: str) -> None:
    install_base_cmd = "pacman -Syu --noconfirm --needed base-devel git sudo"
    root_result = container_run(container_name, install_base_cmd, root=True, check=False, capture=False)
    if root_result.returncode != 0:
        raise MjaError(
            "E022 PARU_BOOTSTRAP_FAILED",
            "failed to install base build tooling",
            command_failure_details(root_result),
        )


def container_install(container_name: str, package_name: str) -> None:
    cmd = f"paru -S --noconfirm --needed {sh_quote(package_name)}"
    result = container_run(container_name, cmd, check=False, capture=False)
    if result.returncode != 0:
        raise MjaError(
            "E023 CONTAINER_INSTALL_FAILED",
            f"failed to install AUR package: {package_name}",
            command_failure_details(result),
        )


def verify_container_install(container_name: str, package_name: str) -> None:
    result = container_run(container_name, f"pacman -Q {sh_quote(package_name)}", check=False)
    if result.returncode != 0:
        raise MjaError("E024 VERIFY_INSTALL_FAILED", f"container package not installed after install: {package_name}")


def list_installed_files_in_container(container_name: str, package_name: str) -> list[str]:
    result = container_run(container_name, f"pacman -Qlq {sh_quote(package_name)}", check=False)
    if result.returncode != 0:
        raise MjaError("E024 VERIFY_INSTALL_FAILED", f"could not inspect installed files for {package_name}", result.stderr.strip())
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def find_desktop_files(files: list[str]) -> list[str]:
    prefixes = ("/usr/share/applications/", "/usr/local/share/applications/")
    return sorted(
        file for file in files
        if file.endswith(".desktop") and file.startswith(prefixes)
    )


def find_bin_candidates(files: list[str]) -> list[str]:
    prefixes = ("/usr/bin/", "/usr/local/bin/")
    candidates: list[str] = []
    for file in files:
        if file.endswith("/"):
            continue
        if file.startswith(prefixes):
            candidates.append(file)
    return sorted(set(candidates))


def maybe_export(
    container_name: str,
    *,
    export: ExportMode,
    desktop_files: list[str],
    bin_candidates: list[str],
    selected_bin: str | None,
) -> ExportStatus:
    # When the user explicitly selects none we bypass all export logic.
    if export == ExportMode.NONE:
        return ExportStatus.NOT_REQUESTED

    # Desktop export (including auto mode) prefers desktop files. In auto
    # mode, if no desktop files exist, attempt to fall back to a binary
    # wrapper if one is available.  This mirrors the behaviour of
    # ``repair export --mode auto``, aligning install‑time and repair
    # semantics.
    if export in (ExportMode.AUTO, ExportMode.DESKTOP):
        if desktop_files:
            export_desktop_files(container_name, desktop_files)
            return ExportStatus.DESKTOP_EXPORTED
        if export == ExportMode.DESKTOP:
            raise MjaError("E030 NO_DESKTOP_FILES", "desktop export requested, but no desktop files were installed")
        # AUTO mode and no desktop files: fall back to exporting a binary
        if bin_candidates:
            target = choose_binary(bin_candidates, selected_bin)
            export_binary(container_name, target)
            return ExportStatus.BIN_EXPORTED
        return ExportStatus.NONE_AVAILABLE

    # Binary export explicitly requests a wrapper script.  This will raise
    # if no candidates exist or the selection is ambiguous.
    if export == ExportMode.BIN:
        target = choose_binary(bin_candidates, selected_bin)
        export_binary(container_name, target)
        return ExportStatus.BIN_EXPORTED

    raise MjaError("E099 INVALID_EXPORT_MODE", f"unsupported export mode: {export}")


def choose_binary(bin_candidates: list[str], selected_bin: str | None) -> str:
    if not bin_candidates:
        raise MjaError("E031 NO_BIN_CANDIDATE", "no binary candidates found for --export bin")

    if selected_bin:
        for candidate in bin_candidates:
            path = PurePosixPath(candidate)
            if candidate == selected_bin or path.name == selected_bin:
                return candidate
        raise MjaError("E033 REQUESTED_BIN_NOT_FOUND", f"requested binary not found in package payload: {selected_bin}", bin_candidates)

    if len(bin_candidates) == 1:
        return bin_candidates[0]

    raise MjaError("E032 MULTIPLE_BIN_CANDIDATES", "multiple binary candidates found, use --bin", bin_candidates)


def export_desktop_files(container_name: str, desktop_files: list[str]) -> None:
    for desktop_file in desktop_files:
        result = container_run(
            container_name,
            f"distrobox-export --app {sh_quote(desktop_file)}",
            check=False,
        )
        if result.returncode != 0:
            raise MjaError(
                "E034 EXPORT_APP_FAILED",
                f"failed to export desktop file: {desktop_file}",
                command_failure_details(result),
            )


def export_binary(container_name: str, target: str) -> None:
    result = container_run(
        container_name,
        f"distrobox-export --bin {sh_quote(target)} --export-path {sh_quote(DEFAULT_EXPORT_PATH)}",
        check=False,
    )
    if result.returncode != 0:
        raise MjaError(
            "E035 EXPORT_BIN_FAILED",
            f"failed to export binary: {target}",
            command_failure_details(result),
        )


def container_run(
    container_name: str,
    command: str,
    *,
    root: bool = False,
    check: bool = True,
    capture: bool = True,
):
    args = ["distrobox", "enter", "--name", container_name, "--no-tty"]
    if root:
        args.insert(2, "--root")
    args += ["--", "bash", "-lc", command]
    return run(args, check=check, capture=capture)


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
