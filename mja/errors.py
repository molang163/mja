from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MjaError(Exception):
    code: str
    message: str
    details: Any | None = None

    def __str__(self) -> str:
        if self.details is None:
            return f"{self.code}: {self.message}"
        return f"{self.code}: {self.message} ({self.details})"
