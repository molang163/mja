from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import MjaError
from .models import PackageRecord, StateFile, now_iso

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "mja"
DEFAULT_STATE_FILE = DEFAULT_STATE_DIR / "state.json"


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_STATE_FILE

    @property
    def directory(self) -> Path:
        return self.path.parent

    def ensure_directory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self) -> StateFile:
        if not self.path.exists():
            return StateFile()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return StateFile.from_dict(payload)
        except Exception as exc:
            raise MjaError(
                "E040 STATE_CORRUPTED",
                "state file is invalid or unreadable",
                str(self.path),
            ) from exc

    def save(self, state: StateFile) -> None:
        self.ensure_directory()
        raw = json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        fd, tmp_name = tempfile.mkstemp(dir=str(self.directory), prefix=".state.", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(raw)
            os.replace(tmp_name, self.path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

    def upsert_package(self, name: str, record: PackageRecord) -> None:
        state = self.load()
        record.updated_at = now_iso()
        state.packages[name] = record
        self.save(state)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
