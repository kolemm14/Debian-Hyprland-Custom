"""Small systemd-user abstraction preserving the current transient units."""

from __future__ import annotations

from pathlib import Path
import re
import hashlib
import shutil
import subprocess
from typing import Callable

from .config import validate_output_name


UNIT_PREFIX = "mpvpaper-engine-wallpaper"
COMMAND_TIMEOUT = 8.0


class SystemdError(RuntimeError):
    pass


def unit_for_output(output: str) -> str:
    if not validate_output_name(output):
        raise ValueError("invalid output name")
    suffix = "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)
    return f"{UNIT_PREFIX}-{suffix}.service"


def runtime_description(runtime, wallpaper):
    identity = str(Path(wallpaper).expanduser().resolve()).encode()
    return f"mpvpaper-engine:{runtime}:{hashlib.sha256(identity).hexdigest()}"


def _default_runner(command, **options):
    return subprocess.run(command, **options)


class SystemdManager:
    def __init__(self, runner: Callable = _default_runner):
        self._runner = runner

    def _run(self, command, *, check=False):
        try:
            result = self._runner(
                command, capture_output=True, text=True,
                timeout=COMMAND_TIMEOUT, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SystemdError(str(error)) from error
        if check and result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "systemd command failed"
            raise SystemdError(message)
        return result

    def start_output(
        self,
        output: str,
        wallpaper: Path,
        mpv_options: str,
        *,
        auto_pause: bool = True,
    ) -> None:
        if not validate_output_name(output):
            raise ValueError("invalid output name")
        wallpaper = Path(wallpaper).expanduser()
        if not wallpaper.is_file():
            raise ValueError(f"wallpaper does not exist: {wallpaper}")
        executable = shutil.which("mpvpaper")
        if executable is None:
            raise SystemdError("mpvpaper is not installed")
        if output != "*":
            # A previous wildcard unit must not retain ownership of the desktop.
            self.stop_output("*")
        command = [
            "systemd-run", "--user", "--quiet",
            f"--unit={unit_for_output(output)}", "--property=Type=exec",
            f"--description={runtime_description("mpvpaper", wallpaper)}", executable,
        ]
        if auto_pause:
            command.extend(["--auto-pause", "--auto-mode", "full"])
        command.extend(["--mpv-options", mpv_options, output, str(wallpaper)])
        self._run(command, check=True)

    def stop_output(self, output: str) -> None:
        self._run(["systemctl", "--user", "stop", unit_for_output(output)], check=False)

    def restart_output(self, output: str) -> None:
        self._run(["systemctl", "--user", "restart", unit_for_output(output)], check=True)

    def unit_status(self, output: str) -> str:
        result = self._run([
            "systemctl", "--user", "is-active", unit_for_output(output),
        ])
        status = result.stdout.strip()
        if status in {"active", "activating", "deactivating", "failed", "inactive"}:
            return status
        return "unknown"

    def details(self, output):
        result = self._run(["systemctl", "--user", "show", unit_for_output(output),
                            "--property=ActiveState,SubState,MainPID,ExecMainStatus,Description,LoadState"])
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        return {"state": values.get("ActiveState", "unknown"),
                "substate": values.get("SubState", "unknown"),
                "process": int(values.get("MainPID", "0") or 0),
                "exit_code": int(values.get("ExecMainStatus", "0") or 0),
                "description": values.get("Description", ""),
                "load_state": values.get("LoadState", "not-found")}

    def stop_checked(self, output):
        if self.details(output)["load_state"] == "not-found":
            return
        self._run(["systemctl", "--user", "stop", unit_for_output(output)], check=True)
        self._run(["systemctl", "--user", "reset-failed", unit_for_output(output)])
