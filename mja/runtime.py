from __future__ import annotations

import json
from pathlib import Path
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable

from .errors import MjaError


@dataclass(slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    captured: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def which(binary: str) -> str | None:
    return shutil.which(binary)


def require_binary(binary: str, code: str) -> str:
    path = which(binary)
    if not path:
        raise MjaError(code, f"required binary not found: {binary}")
    return path


def detect_container_runtime() -> str | None:
    for binary in ("podman", "docker"):
        if which(binary):
            return binary
    return None


def shell_join(args: Iterable[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def command_failure_details(result: CommandResult) -> dict[str, Any]:
    details: dict[str, Any] = {
        "command": shell_join(result.args),
        "returncode": result.returncode,
        "captured": result.captured,
    }
    if result.stdout:
        details["stdout"] = result.stdout
    if result.stderr:
        details["stderr"] = result.stderr
    if not result.captured:
        details["note"] = "command output was streamed to the terminal and was not captured"
    return details


def run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> CommandResult:
    proc = subprocess.run(
        args,
        text=True,
        capture_output=capture,
        env={**os.environ, **(env or {})},
        cwd=cwd,
    )
    stdout = proc.stdout if capture and proc.stdout is not None else ""
    stderr = proc.stderr if capture and proc.stderr is not None else ""
    result = CommandResult(
        args=args,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        captured=capture,
    )
    # If output was not captured, append a simple entry to the log file. This
    # helps the user diagnose failures on long-running commands. The log
    # includes a timestamp, the invoked command and its return code. It is
    # intentionally minimal to avoid unexpected disk usage.
    if not capture:
        try:
            from datetime import datetime
            # Construct the path ~/.local/state/mja/logs/latest.log
            base = Path.home() / ".local" / "state" / "mja" / "logs"
            base.mkdir(parents=True, exist_ok=True)
            log_file = base / "latest.log"
            with log_file.open("a", encoding="utf-8") as fh:
                timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
                fh.write(f"{timestamp} :: {shell_join(args)} :: returncode={proc.returncode}\n")
        except Exception:
            # Logging failure should not block the primary operation
            pass
    if check and proc.returncode != 0:
        raise MjaError(
            "E999 COMMAND_FAILED",
            f"command failed: {shell_join(args)}",
            command_failure_details(result),
        )
    return result


def run_json(args: list[str]) -> Any:
    result = run(args)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MjaError("E011 AUR_RPC_BAD_RESPONSE", "invalid JSON response", result.stdout) from exc
