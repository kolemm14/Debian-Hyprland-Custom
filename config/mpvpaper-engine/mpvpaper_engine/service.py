"""Minimal MPVpaper Engine session service for state and read-only IPC."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import signal
import socket
import threading
import time
from typing import Any, Callable

from .config import EngineConfig, load_config, validate_output_name
from .ipc import EngineServer, PROTOCOL_VERSION, RPCError
from .logging import configure_logging
from .models import PerformanceMode, PlaybackState, PlaybackStatus
from .paths import EnginePaths
from .playback import PlaybackController, PlaybackError
from .playback import mpv_socket_candidates
from .state import EngineState, STATE_VERSION, StateStore, playback_state_to_dict
from .theme_sync import ThemeSync
from .systemd import SystemdError
from .runtimes.runtime_manager import RuntimeManager
from .runtimes.mpv_runtime import MpvRuntime


ENGINE_VERSION = "2.0-d3"
LOGGER = logging.getLogger(__name__)


def initial_state_from_config(config: EngineConfig) -> EngineState:
    outputs = {}
    for output, profile in config.outputs.items():
        if output == "*":
            # Wildcard is a user intent, never a running physical output.
            continue
        wallpaper = profile.get("wallpaper")
        performance = profile.get("performance_profile", PerformanceMode.AUTO.value)
        try:
            performance_mode = PerformanceMode(performance)
        except (TypeError, ValueError):
            performance_mode = PerformanceMode.AUTO
        outputs[output] = PlaybackState(
            output=output,
            status=PlaybackStatus.STOPPED,
            path=Path(wallpaper) if isinstance(wallpaper, str) and wallpaper else None,
            position=None,
            duration=None,
            volume=profile.get("volume") if isinstance(profile.get("volume"), int) else None,
            muted=profile.get("muted") if isinstance(profile.get("muted"), bool) else None,
            speed=(
                profile.get("speed")
                if isinstance(profile.get("speed"), (int, float)) else None
            ),
            performance_profile=performance_mode,
            color_profile=(
                profile["color_profile"]
                if isinstance(profile.get("color_profile"), str) else "Original"
            ),
            service_pid=os.getpid(),
        )
    return EngineState(
        mode=config.mode,
        service_status="starting",
        outputs=outputs,
        last_error=config.load_error,
    )


class EngineService:
    def __init__(
        self,
        paths: EnginePaths | None = None,
        config_loader: Callable[[EnginePaths], EngineConfig] = load_config,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.config = config_loader(self.paths)
        self.state = StateStore(self.paths, initial_state_from_config(self.config))
        self.playback = PlaybackController(self.config, self.paths, self.state)
        self.runtimes = RuntimeManager(mpv=MpvRuntime(self.playback), systemd=self.playback.systemd,
                                       config=self.config, paths=self.paths, persist=True)
        self._monitor_thread = None
        self._theme_lock = threading.Lock()
        self._theme_pending = None
        self._theme_thread = None
        self.theme_sync = ThemeSync(self.paths)
        self.server = EngineServer(self._methods(), self.paths)
        self._stop_event = threading.Event()
        self._started = False
        self._hud_thread: threading.Thread | None = None

    def _methods(self):
        return {
            "runtime_diagnose": self._runtime_diagnose,
            "runtime_status": self._runtime_status,
            "runtime_restore": self._runtime_restore,
            "apply_all": self._apply_all,
            "ping": self._ping,
            "get_state": self._get_state,
            "get_output_state": self._get_output_state,
            "list_outputs": self._list_outputs,
            "get_version": self._get_version,
            "play": self._play,
            "stop": self._stop,
            "pause": self._pause,
            "resume": self._resume,
            "toggle_pause": self._toggle_pause,
            "restart": self._restart,
            "seek": self._seek,
            "seek_relative": self._seek_relative,
            "set_volume": self._set_volume,
            "set_mute": self._set_mute,
            "set_speed": self._set_speed,
            "set_loop": self._set_loop,
            "set_fit": self._set_fit,
            "set_color": self._set_color,
            "set_performance_profile": self._set_performance_profile,
            "get_playback_state": self._get_playback_state,
            "configure_hud": self._configure_hud,
            "refresh_hud": self._refresh_hud,
            "preview_hud": self._preview_hud,
            "clear_hud_preview": self._clear_hud_preview,
        }

    def _configure_hud(self, params):
        if set(params) != {"settings"} or not isinstance(params["settings"], dict):
            raise RPCError("invalid_params", "HUD settings must be an object")
        settings = params["settings"]
        self._invoke(self.playback.configure_hud, settings)
        self.config.ui["hud"] = settings
        live = self.playback.refresh_hud("*")
        return {"configured": True, "live": live}

    def _refresh_hud(self, params):
        output = self._output(params)
        return {"refreshed": self._invoke(self.playback.refresh_hud, output)}

    def _preview_hud(self, params):
        output = self._output(params, "settings")
        if not isinstance(params["settings"], dict):
            raise RPCError("invalid_params", "HUD settings must be an object")
        return self._invoke(self.playback.preview_hud, output, params["settings"])

    def _clear_hud_preview(self, params):
        output = self._output(params)
        return self._invoke(self.playback.clear_hud_preview, output)

    @staticmethod
    def _require_empty(params: dict[str, Any]) -> None:
        if params:
            raise RPCError("invalid_params", "This method does not accept parameters")

    def _ping(self, params: dict[str, Any]) -> dict[str, bool]:
        self._require_empty(params)
        return {"pong": True}

    def _get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_empty(params)
        result = self.state.as_dict()
        result["runtimes"] = {output: self.runtimes.status(output) for output in list(self.runtimes.records)}
        return result

    def _get_output_state(self, params: dict[str, Any]) -> dict[str, Any]:
        if set(params) != {"output"} or not validate_output_name(params.get("output")):
            raise RPCError("invalid_params", "A valid output name is required")
        output = params["output"]
        if output in self.runtimes.records:
            self._sync_runtime_state(output)
        current = self.state.snapshot().outputs.get(output)
        if current is None:
            raise RPCError("output_not_found", f"Output is not configured: {output}")
        return {"output": output, **playback_state_to_dict(current)}

    def _list_outputs(self, params: dict[str, Any]) -> list[str]:
        self._require_empty(params)
        return sorted(self.state.snapshot().outputs)

    def _get_version(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_empty(params)
        return {
            "engine": ENGINE_VERSION,
            "protocol": PROTOCOL_VERSION,
            "state": STATE_VERSION,
        }

    @staticmethod
    def _output(params: dict[str, Any], *extra: str) -> str:
        if set(params) != {"output", *extra} or not validate_output_name(params.get("output")):
            raise RPCError("invalid_params", "Invalid playback parameters")
        return params["output"]

    @staticmethod
    def _invoke(operation, *args):
        try:
            return operation(*args)
        except (ValueError, RuntimeError, OSError) as error:
            raise RPCError("playback_error", str(error)) from error

    def _play(self, params):
        params = dict(params)
        options = params.pop("options", None)
        if options is not None and not isinstance(options, dict):
            raise RPCError("invalid_params", "options must be an object")
        output = self._output(params, "wallpaper")
        if not isinstance(params["wallpaper"], str) or not params["wallpaper"]:
            raise RPCError("invalid_params", "wallpaper must be a non-empty path")
        strategy = self._invoke(lambda: self.runtimes.apply(output, Path(params["wallpaper"]), options=options))
        for target in (strategy if isinstance(strategy, dict) else [output]):
            if target in self.runtimes.records:
                self._sync_runtime_state(target)
        self._schedule_theme(output)
        return {"strategy": strategy, "persisted": True, "theme_sync_managed": True,
                **({"outputs": strategy} if isinstance(strategy, dict) else {})}

    def _stop(self, params):
        output = self._output(params)
        result = self._invoke(self.runtimes.stop, output)
        for target in (list(self.state.snapshot().outputs) if output == "*" else [output]):
            if target in self.state.snapshot().outputs:
                self.state.update_output(target, status=PlaybackStatus.STOPPED)
        return {"stopped": True, "outputs": result}

    def _pause(self, params):
        output = self._output(params)
        self._require_mpv(output)
        self._invoke(self.playback.pause, output)
        return {"paused": True}

    def _resume(self, params):
        output = self._output(params)
        self._require_mpv(output)
        self._invoke(self.playback.resume, output)
        return {"paused": False}

    def _toggle_pause(self, params):
        output = self._output(params)
        self._require_mpv(output)
        return {"paused": self._invoke(self.playback.toggle_pause, output)}

    def _restart(self, params):
        output = self._output(params)
        if output == "*":
            return self._invoke(self.runtimes.apply_all)
        intent = self.config.outputs.get(output, {})
        if not intent.get("wallpaper"):
            raise RPCError("playback_error", "No saved wallpaper for this output")
        self.runtimes.stop(output, remember=False)
        self.runtimes.apply(output, intent["wallpaper"], options=intent.get("runtime_options"))
        return {"restarted": True}

    def _require_mpv(self, output):
        if self.config.outputs.get(output, {}).get("runtime") == "linux-wallpaperengine":
            raise RPCError("unsupported_operation", "This control is available for MPV media only")

    def _seek(self, params):
        output = self._output(params, "seconds")
        self._require_mpv(output)
        self._invoke(self.playback.seek, output, params["seconds"])
        return {"position": float(params["seconds"])}

    def _seek_relative(self, params):
        output = self._output(params, "delta")
        self._require_mpv(output)
        self._invoke(self.playback.seek_relative, output, params["delta"])
        return {"delta": float(params["delta"])}

    def _set_volume(self, params):
        output = self._output(params, "volume")
        self._require_mpv(output)
        return {"volume": self._invoke(self.playback.set_volume, output, params["volume"])}

    def _set_mute(self, params):
        output = self._output(params, "muted")
        self._require_mpv(output)
        self._invoke(self.playback.set_mute, output, params["muted"])
        return {"muted": params["muted"]}

    def _set_speed(self, params):
        output = self._output(params, "speed")
        self._require_mpv(output)
        return {"speed": self._invoke(self.playback.set_speed, output, params["speed"])}

    def _set_loop(self, params):
        output = self._output(params, "enabled")
        self._require_mpv(output)
        self._invoke(self.playback.set_loop, output, params["enabled"])
        return {"loop": params["enabled"]}

    def _set_fit(self, params):
        output = self._output(params, "mode")
        self._require_mpv(output)
        self._invoke(self.playback.set_fit, output, params["mode"])
        return {"fit": params["mode"]}

    def _set_color(self, params):
        output = self._output(params, "color")
        self._require_mpv(output)
        self._invoke(self.playback.set_color, output, params["color"])
        return {"color": params["color"].get("name", "Custom")}

    def _set_performance_profile(self, params):
        output = self._output(params, "profile")
        self._require_mpv(output)
        profile = self._invoke(
            self.playback.set_performance_profile, output, params["profile"]
        )
        return {"profile": profile}

    def _get_playback_state(self, params):
        output = self._output(params)
        self._require_mpv(output)
        current = self._invoke(self.playback.get_state, output)
        return {"output": output, **playback_state_to_dict(current)}

    def start(self) -> None:
        if self._started:
            raise RuntimeError("Engine service is already started")
        self.server.start()
        try:
            self.state.set_service_status("running", self.config.load_error)
            self._restore_configured_wallpapers()
            self._reconcile_running_outputs()
            self._schedule_theme("*")
        except Exception:
            self.server.shutdown()
            raise
        self._started = True
        try:
            self.playback.start_hud()
        except OSError:
            LOGGER.warning("Desktop HUD could not start", exc_info=True)
        self._hud_thread = threading.Thread(
            target=self._hud_loop, name="mpvpaper-hud", daemon=True
        )
        self._hud_thread.start()
        self._monitor_thread = threading.Thread(target=self._monitor_events, name="mpvpaper-monitors", daemon=True)
        self._monitor_thread.start()

    def _schedule_theme(self, output):
        # One global desktop palette: selected output, or focused screen at restore.
        mode = load_config(self.paths).theme_sync.get("mode", "off")
        if mode == "off":
            return
        if output == "*":
            from .monitors import detect_monitors, MonitorError
            try:
                monitors = detect_monitors()
            except MonitorError as error:
                LOGGER.warning("Theme monitor discovery: %s", error)
                return
            output = next((m.name for m in monitors if m.focused), monitors[0].name if monitors else "")
        record = self.runtimes.records.get(output, {})
        if record.get("project_type") not in {"video", "image"}:
            return
        with self._theme_lock:
            self._theme_pending = (Path(record["wallpaper"]), mode)
            if self._theme_thread is None or not self._theme_thread.is_alive():
                self._theme_thread = threading.Thread(target=self._theme_worker, name="wallpaper-palette", daemon=True)
                self._theme_thread.start()

    def _theme_worker(self):
        while not self._stop_event.is_set():
            with self._theme_lock:
                job, self._theme_pending = self._theme_pending, None
                if job is None:
                    self._theme_thread = None
                    return
            try:
                result = self.theme_sync.apply(job[0], mode=job[1])
                LOGGER.info("Desktop palette: %s (%s)", result.reason, result.integrations)
            except (OSError, ValueError, RuntimeError) as error:
                LOGGER.warning("Desktop palette failed: %s", error)

    def _sync_runtime_state(self, output):
        runtime = self.runtimes.status(output)
        status = {"active": PlaybackStatus.PLAYING, "activating": PlaybackStatus.LOADING,
                  "failed": PlaybackStatus.ERROR}.get(runtime["state"], PlaybackStatus.STOPPED)
        self.state.update_output(output, path=Path(runtime["wallpaper"]), status=status,
                                 last_error=runtime.get("reason"))

    def _runtime_diagnose(self, params):
        if set(params) != {"wallpaper"} or not isinstance(params["wallpaper"], str):
            raise RPCError("invalid_params", "wallpaper path required")
        return self.runtimes.diagnose(params["wallpaper"])

    def _runtime_status(self, params):
        return self._invoke(self.runtimes.status, self._output(params))

    def _runtime_restore(self, params):
        self._require_empty(params)
        return self._invoke(self.runtimes.restore)

    def _apply_all(self, params):
        self._require_empty(params)
        return self._invoke(self.runtimes.apply_all)

    def _restore_configured_wallpapers(self):
        try:
            return self.runtimes.restore()
        except (RuntimeError, OSError, ValueError) as error:
            LOGGER.warning("Runtime restore unavailable: %s", error)
            return {"error": str(error)}

    def _monitor_events(self):
        signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        if not signature:
            return
        path = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "hypr" / signature / ".socket2.sock"
        while not self._stop_event.is_set():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(1)
                    client.connect(str(path))
                    pending = b""
                    while not self._stop_event.is_set():
                        try:
                            data = client.recv(8192)
                        except socket.timeout:
                            continue
                        if not data:
                            break
                        pending += data
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            if line.startswith((b"monitoradded", b"monitorremoved", b"configreloaded")):
                                result = self.runtimes.reconcile()
                                if any(not v.get("ok", False) for v in result.values()):
                                    LOGGER.warning("Monitor reconciliation: %s", result)
            except (OSError, RuntimeError, ValueError) as error:
                LOGGER.warning("Monitor events unavailable: %s", error)
            self._stop_event.wait(5)

    def _hud_loop(self):
        while not self._stop_event.wait(self._seconds_to_next_minute()):
            try:
                self.playback.refresh_hud("*")
            except Exception:
                LOGGER.debug("HUD refresh failed", exc_info=True)

    @staticmethod
    def _seconds_to_next_minute() -> float:
        now = time.time()
        return max(0.1, 60.0 - (now % 60.0))

    def _reconcile_running_outputs(self) -> None:
        """Reconstruct state once when wallpapers predate the Engine service."""
        for output in self.config.outputs:
            if output == "*":
                continue
            if not any(path.is_socket() for path in mpv_socket_candidates(self.paths, output)):
                continue
            try:
                self.playback.get_state(output)
            except PlaybackError as error:
                LOGGER.warning("Unable to reconstruct %s playback state: %s", output, error)

    def shutdown(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=6)
        self._monitor_thread = None
        if self._hud_thread is not None:
            self._hud_thread.join(timeout=5)
        self._hud_thread = None
        self.playback.stop_hud()
        try:
            self.server.shutdown()
        finally:
            self.state.set_service_status("stopped", self.config.load_error)
            self._started = False

    def run_forever(self) -> None:
        self.start()
        try:
            self._stop_event.wait()
        finally:
            self.shutdown()

    def request_shutdown(self, _signum=None, _frame=None) -> None:
        self._stop_event.set()


def run_session_service(paths: EnginePaths | None = None) -> None:
    service = EngineService(paths)
    previous = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, service.request_shutdown)
    try:
        service.run_forever()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main() -> int:
    configure_logging()
    try:
        run_session_service()
    except Exception as error:
        LOGGER.error("Engine session service failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
