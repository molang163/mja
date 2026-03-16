from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class InstallStatus(StrEnum):
    PLANNED = "planned"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    REMOVING = "removing"
    REMOVED = "removed"


class ExportStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    DESKTOP_EXPORTED = "desktop_exported"
    BIN_EXPORTED = "bin_exported"
    NONE_AVAILABLE = "none_available"
    FAILED = "failed"

    # Exportable content exists in the package but the host-side export is missing.  This
    # status is set by ``state rebuild`` when the package contains desktop entries or
    # binary candidates but no corresponding exported artifact can be found on the
    # host.  It allows tooling and UIs to distinguish between "nothing to export"
    # (``none_available``) and "export has gone missing".
    EXPORT_MISSING = "export_missing"


class SourceKind(StrEnum):
    HOST_REPO = "host-repo"
    AUR_CONTAINER = "aur-container"


class ExportMode(StrEnum):
    AUTO = "auto"
    DESKTOP = "desktop"
    BIN = "bin"
    NONE = "none"


class ResolveSource(StrEnum):
    AUTO = "auto"
    REPO = "repo"
    AUR = "aur"


@dataclass(slots=True)
class SearchResult:
    source: str
    name: str
    version: str = ""
    description: str = ""
    repo: str | None = None
    exact: bool = False
    popularity: float | None = None
    votes: int | None = None
    package_base: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ContainerRecord:
    status: str
    runtime: str
    aur_helper: str = "paru"
    last_update: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContainerRecord":
        return cls(**payload)


@dataclass(slots=True)
class PackageRecord:
    source: str
    container: str | None
    install_status: str
    export_status: str
    export_mode: str
    desktop_entries: list[str] = field(default_factory=list)
    binaries: list[str] = field(default_factory=list)
    requested_at: str = field(default_factory=now_iso)
    installed_at: str | None = None
    updated_at: str = field(default_factory=now_iso)
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PackageRecord":
        return cls(**payload)


@dataclass(slots=True)
class StateFile:
    version: int = 2
    containers: dict[str, ContainerRecord] = field(default_factory=dict)
    packages: dict[str, PackageRecord] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "containers": {k: v.to_dict() for k, v in self.containers.items()},
            "packages": {k: v.to_dict() for k, v in self.packages.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StateFile":
        containers = {
            name: ContainerRecord.from_dict(item)
            for name, item in payload.get("containers", {}).items()
        }
        packages = {
            name: PackageRecord.from_dict(item)
            for name, item in payload.get("packages", {}).items()
        }
        return cls(
            version=payload.get("version", 2),
            containers=containers,
            packages=packages,
        )


@dataclass(slots=True)
class InstallPlan:
    kind: SourceKind
    requested_name: str
    resolved_name: str
    display_name: str | None = None
    repo: str | None = None
    container: str | None = None
    aur_meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "requested_name": self.requested_name,
            "resolved_name": self.resolved_name,
            "display_name": self.display_name or self.resolved_name,
            "repo": self.repo,
            "container": self.container,
            "aur_meta": self.aur_meta,
        }
