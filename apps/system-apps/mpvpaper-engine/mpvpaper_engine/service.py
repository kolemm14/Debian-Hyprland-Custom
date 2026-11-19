"""Minimal MPVpaper Engine session service for state and read-only IPC."""

from __future__ import annotations

import http.server
import json
import logging
import os
from pathlib import Path
import signal
import socket
import threading
import time
from typing import Any, Callable

from .config import EngineConfig, load_config, save_config, validate_output_name
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
from .task_manager import TaskManager
from .library import Library, LibraryError
from .playlists import PlaylistManager
from .recommendations import RecommendationEngine


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


class _LoopbackHTTPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.startswith("/media?"):
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            target = query.get("path", [None])[0]
            if not target:
                self.send_response(400)
                self.end_headers()
                return
            # Strict security checks: reject relative paths, traversal tokens, and disallowed extensions
            if not os.path.isabs(target) or ".." in Path(target).parts:
                self.send_response(403)
                self.end_headers()
                return
            real_target = os.path.realpath(target)
            allowed_roots = [
                str(Path.home().resolve()),
                "/tmp",
                os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
            ]
            if not any(real_target.startswith(root.rstrip("/") + "/") or real_target == root for root in allowed_roots):
                self.send_response(403)
                self.end_headers()
                return
            ext = os.path.splitext(real_target)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"):
                self.send_response(403)
                self.end_headers()
                return
            if not os.path.isfile(real_target):
                self.send_response(404)
                self.end_headers()
                return
            try:
                with open(real_target, "rb") as f:
                    content = f.read()
                mime = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext[1:]}"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.end_headers()
                self.wfile.write(content)
            except Exception:
                self.send_response(500)
                self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/rpc":
            self.send_response(404)
            self.end_headers()
            return
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 1024 * 1024:
            self.send_response(413)
            self.end_headers()
            return
        body = self.rfile.read(content_len)
        try:
            req = json.loads(body.decode("utf-8"))
            if not isinstance(req, dict):
                raise ValueError("JSON object expected")
            if "id" not in req:
                req["id"] = 1
            resp = self.server.engine_server.handle_request(req)  # type: ignore[attr-defined]
        except Exception as e:
            resp = {"id": 1, "ok": False, "error": {"code": "invalid_request", "message": str(e)}}
        data = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


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
        self.task_manager = TaskManager(self.paths)
        self.library = Library(self.paths)
        self.playlist_manager = PlaylistManager(self.library)
        self.recommendation_engine = RecommendationEngine(self.paths)
        self.server = EngineServer(self._methods(), self.paths)
        self._stop_event = threading.Event()
        self._started = False
        self._hud_thread: threading.Thread | None = None
        self._http_port = int(os.environ.get("MPVPAPER_ENGINE_PORT", "48199"))
        self._http_server: http.server.ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None

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
            "save_playback_settings": self._save_playback_settings,
            "refresh_hud": self._refresh_hud,
            "preview_hud": self._preview_hud,
            "clear_hud_preview": self._clear_hud_preview,
            "engine.status": self._engine_status,
            "engine_status": self._engine_status,
            "engine.capabilities": self._engine_capabilities,
            "engine_capabilities": self._engine_capabilities,
            "media.estimate": self._media_estimate,
            "media_estimate": self._media_estimate,
            "media.optimize": self._media_optimize,
            "media_optimize": self._media_optimize,
            "task.status": self._task_status,
            "task_status": self._task_status,
            "task.cancel": self._task_cancel,
            "task_cancel": self._task_cancel,
            "task.list": self._task_list,
            "task_list": self._task_list,
            "library.list": self._library_list,
            "library_list": self._library_list,
            "library.scan": self._library_scan,
            "library_scan": self._library_scan,
            "library.set_favorite": self._library_set_favorite,
            "library_set_favorite": self._library_set_favorite,
            "library.import": self._library_import,
            "library_import": self._library_import,
            "library.delete": self._library_delete,
            "library_delete": self._library_delete,
            "hub.import": self._hub_import,
            "hub_import": self._hub_import,
            "hub.v1.download": self._hub_v1_download,
            "hub.v1.download.start": self._hub_v1_download_start,
            "hub.v1.apply": self._hub_v1_apply,
            "playlists.list": self._playlists_list,
            "playlists_list": self._playlists_list,
            "playlists.create": self._playlists_create,
            "playlists_create": self._playlists_create,
            "playlists.delete": self._playlists_delete,
            "playlists_delete": self._playlists_delete,
            "recommendations.list": self._recommendations_list,
            "recommendations_list": self._recommendations_list,
        }

    def _save_playback_settings(self, params):
        import math
        output = self._output(params, "settings")
        settings = params["settings"]
        if output == "*" or not isinstance(settings, dict) or not settings:
            raise RPCError("invalid_params", "Concrete output and settings required")
        allowed = {"volume", "muted", "speed", "loop", "performance_profile"}
        if set(settings) - allowed:
            raise RPCError("invalid_params", "Unknown playback setting")
        for key, value in settings.items():
            if key in {"muted", "loop"}:
                valid = type(value) is bool
            elif key == "performance_profile":
                valid = isinstance(value, str) and value in {"auto", "eco", "balanced", "performance", "ultra", "quality"}
            else:
                low, high = (0, 100) if key == "volume" else (.1, 5)
                valid = type(value) in {int, float} and math.isfinite(value) and low <= value <= high
            if not valid:
                raise RPCError("invalid_params", f"Invalid {key}")
        candidate = load_config(self.paths)
        if candidate.load_error:
            raise RPCError("config_error", candidate.load_error)
        candidate.outputs[output] = {**candidate.outputs.get(output, {}), **settings}
        save_config(candidate, self.paths)
        self.config.outputs[output] = dict(candidate.outputs[output])
        return {"saved": True, "output": output, "settings": settings}

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

    def _engine_status(self, params: dict[str, Any]) -> dict[str, Any]:
        state = self.state.as_dict()
        with self.task_manager._lock:
            active_count = len([t for t in self.task_manager.tasks.values() if t.state in {"queued", "running"}])
        return {
            "service_status": state.get("service_status", "running"),
            "pid": os.getpid(),
            "version": PROTOCOL_VERSION,
            "engine_version": ENGINE_VERSION,
            "outputs": state.get("outputs", {}),
            "active_tasks_count": active_count,
        }

    def _engine_capabilities(self, params: dict[str, Any]) -> dict[str, Any]:
        import shutil
        from .media_optimizer import RESOLUTIONS, VIDEO_FPS, VIDEO_CODECS, IMAGE_FORMATS
        from .system_integration import detect_environment
        sys_info = detect_environment()
        return {
            "version": PROTOCOL_VERSION,
            "engine_version": ENGINE_VERSION,
            "media_optimizer": {
                "ffmpeg_available": bool(shutil.which("ffmpeg")),
                "ffprobe_available": bool(shutil.which("ffprobe")),
                "video_resolutions": list(RESOLUTIONS.keys()),
                "video_fps": list(VIDEO_FPS.keys()),
                "video_codecs": VIDEO_CODECS,
                "image_formats": IMAGE_FORMATS,
                "default_initial_resolution": "720p",
                "default_initial_max_mb": 150.0,
                "preserve_original_required": True,
            },
            "system_integration": {
                "desktop": sys_info.desktop,
                "session_type": sys_info.session_type,
                "lock_supported": sys_info.lock_supported,
                "screensaver_supported": sys_info.screensaver_supported,
                "detected_lock_tool": sys_info.detected_lock_tool,
                "detected_idle_tool": sys_info.detected_idle_tool,
            },
            "runtimes": ["mpv", "lwe_scene"],
        }

    def _media_estimate(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.task_manager.estimate(params)

    def _media_optimize(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.task_manager.start_optimize(params)

    def _task_status(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id") or params.get("id")
        if not task_id or not isinstance(task_id, str):
            raise RPCError("invalid_params", "task_id obligatoire")
        return self.task_manager.get_task(task_id)

    def _task_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id") or params.get("id")
        if not task_id or not isinstance(task_id, str):
            raise RPCError("invalid_params", "task_id obligatoire")
        return self.task_manager.cancel_task(task_id)

    def _task_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        limit = int(params.get("limit", 20)) if isinstance(params.get("limit"), (int, float)) else 20
        return self.task_manager.list_tasks(limit=limit)

    def _default_library_roots(self) -> list[Path]:
        candidates = [
            Path.home() / "Pictures" / "Wallpapers",
            Path.home() / "Pictures" / "wallpapers",
            Path.home() / "Videos" / "Wallpapers",
            Path.home() / "Videos" / "wallpapers",
            self.paths.data_home / "wallpapers",
        ]
        return [p for p in candidates if p.exists()] or [Path.home() / "Pictures" / "Wallpapers"]

    @staticmethod
    def _wallpaper_to_dict(w: Any) -> dict[str, Any]:
        if w is None:
            return {}
        return {
            "id": getattr(w, "id", None),
            "path": str(w.path) if getattr(w, "path", None) else "",
            "title": getattr(w, "title", ""),
            "type": w.media_type.value if hasattr(getattr(w, "media_type", None), "value") else str(getattr(w, "media_type", "") or ""),
            "duration": getattr(w, "duration", None),
            "width": getattr(w, "width", None),
            "height": getattr(w, "height", None),
            "fps": getattr(w, "fps", None),
            "video_codec": getattr(w, "video_codec", None),
            "audio_codec": getattr(w, "audio_codec", None),
            "bitrate": getattr(w, "bitrate", None),
            "file_size": getattr(w, "file_size", 0),
            "thumbnail_path": str(w.thumbnail_path) if getattr(w, "thumbnail_path", None) else None,
            "source": getattr(w, "source", "local"),
            "source_url": getattr(w, "source_url", None),
            "favorite": bool(getattr(w, "favorite", False)),
            "date_added": (
                w.date_added.isoformat()
                if hasattr(getattr(w, "date_added", None), "isoformat") and w.date_added
                else str(getattr(w, "date_added", "") or "")
            ),
            "missing": bool(getattr(w, "missing", False)),
        }

    def _library_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        media_type = params.get("media_type")
        favorites_only = bool(params.get("favorites_only", False))
        query = params.get("query", "")
        limit = int(params.get("limit", 1000))
        if query:
            items = self.library.search(query, media_type=media_type, favorites_only=favorites_only, limit=limit)
        else:
            items = self.library.list(media_type=media_type, favorites_only=favorites_only, limit=limit)
        return [self._wallpaper_to_dict(w) for w in items]

    def _library_scan(self, params: dict[str, Any]) -> dict[str, Any]:
        roots = params.get("roots")
        if roots and isinstance(roots, list):
            root_paths = [Path(r) for r in roots]
        else:
            root_paths = self._default_library_roots()
        return self.library.scan(root_paths)

    def _library_set_favorite(self, params: dict[str, Any]) -> dict[str, Any]:
        wallpaper_id = params.get("id") or params.get("wallpaper_id")
        if wallpaper_id is None:
            raise RPCError("invalid_params", "wallpaper id required")
        favorite = bool(params.get("favorite", True))
        try:
            wallpaper = self.library.set_favorite(int(wallpaper_id), favorite)
            return self._wallpaper_to_dict(wallpaper)
        except KeyError:
            raise RPCError("not_found", f"Wallpaper introuvable : {wallpaper_id}")

    def _library_import(self, params: dict[str, Any]) -> dict[str, Any]:
        path = params.get("path")
        if not path or not isinstance(path, str):
            raise RPCError("invalid_params", "path required")
        p = Path(path).expanduser().resolve()
        if p.is_dir() and (p / "project.json").is_file():
            wp = self.library.import_project(p)
        elif p.is_file():
            wp = self.library.import_file(p, source=params.get("source", "local"))
        else:
            raise RPCError("invalid_params", f"Fichier ou projet introuvable : {path}")
        return self._wallpaper_to_dict(wp)

    def _library_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        wallpaper_id = params.get("id") or params.get("wallpaper_id")
        if wallpaper_id is None:
            raise RPCError("invalid_params", "wallpaper id required")
        roots = self._default_library_roots()
        protected = [
            Path(p["wallpaper"])
            for p in self.config.outputs.values()
            if isinstance(p, dict) and p.get("wallpaper")
        ]
        try:
            self.library.delete_to_trash(int(wallpaper_id), library_roots=roots, protected_paths=protected)
            return {"deleted": True, "id": int(wallpaper_id)}
        except Exception as e:
            raise RPCError("delete_error", str(e))

    def _hub_import(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not uri or not isinstance(uri, str):
            raise RPCError("invalid_params", "uri required")
        from .hub_import import import_hub_wallpaper
        outcome = import_hub_wallpaper(uri)
        return {"path": str(outcome.path) if outcome.path else None, "message": outcome.message}

    def _hub_v1_download(self, params: dict[str, Any]) -> dict[str, Any]:
        required = {"source", "media_url", "title", "category"}
        if set(params) != required or any(not isinstance(params.get(key), str) for key in required):
            raise RPCError("invalid_params", "Contrat hub.v1.download invalide")
        from .hub_import import download_external_wallpaper
        outcome = download_external_wallpaper(
            params["source"], params["media_url"], params["title"], params["category"]
        )
        if outcome.path is None or not outcome.path.is_file():
            raise RPCError("download_failed", outcome.message)
        try:
            wallpaper = self.library.import_file(outcome.path, source="hub")
        except (OSError, ValueError, LibraryError) as error:
            raise RPCError("library_import_failed", f"Le fichier téléchargé n’a pas pu être indexé : {error}") from error
        return {"wallpaper": self._wallpaper_to_dict(wallpaper), "message": outcome.message}

    def _hub_v1_download_start(self, params: dict[str, Any]) -> dict[str, Any]:
        required = {"source", "media_url", "title", "category"}
        if set(params) != required or any(not isinstance(params.get(key), str) for key in required):
            raise RPCError("invalid_params", "Contrat hub.v1.download.start invalide")

        def worker(task):
            from .hub_import import download_external_wallpaper

            outcome = download_external_wallpaper(
                params["source"], params["media_url"], params["title"], params["category"],
                cancel_event=task._cancel_event,
                progress_callback=lambda downloaded, total: self.task_manager.update_download_progress(
                    task.task_id, downloaded, total
                ),
                phase_callback=lambda phase: self.task_manager.set_phase(task.task_id, phase),
                cancel_callback=lambda callback: self.task_manager.set_cancel_callback(
                    task.task_id, callback
                ),
            )
            if task._cancel_event.is_set():
                if outcome.path:
                    outcome.path.unlink(missing_ok=True)
                return {}
            if outcome.path is None or not outcome.path.is_file():
                raise RPCError("download_failed", outcome.message)
            if not self.task_manager.begin_commit(task.task_id):
                outcome.path.unlink(missing_ok=True)
                return {}
            self.task_manager.set_phase(task.task_id, "Ajout à la bibliothèque Engine…")
            try:
                wallpaper = self.library.import_file(outcome.path, source="hub")
            except (OSError, ValueError, LibraryError) as error:
                raise RPCError("library_import_failed", f"Le fichier téléchargé n’a pas pu être indexé : {error}") from error
            return {"wallpaper": self._wallpaper_to_dict(wallpaper), "message": outcome.message}

        return self.task_manager.start_background("hub_download", worker)

    def _hub_v1_apply(self, params: dict[str, Any]) -> dict[str, Any]:
        if set(params) != {"wallpaper_id", "output"}:
            raise RPCError("invalid_params", "Contrat hub.v1.apply invalide")
        wallpaper_id = params.get("wallpaper_id")
        output = params.get("output")
        if not isinstance(wallpaper_id, int) or isinstance(wallpaper_id, bool) or not validate_output_name(output):
            raise RPCError("invalid_params", "Wallpaper ou écran invalide")
        wallpaper = self.library.get(wallpaper_id)
        if wallpaper is None or wallpaper.missing:
            raise RPCError("not_found", "Wallpaper absent de la bibliothèque locale")
        result = self._play({"output": output, "wallpaper": str(wallpaper.path)})
        return {"wallpaper_id": wallpaper_id, **result}

    def _playlists_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        playlists = self.playlist_manager.list()
        res = []
        for p in playlists:
            items = self.playlist_manager.items(p.id)
            res.append({
                "id": p.id,
                "name": p.name,
                "mode": p.mode.value,
                "interval_seconds": p.interval_seconds,
                "items": [self._wallpaper_to_dict(w) for w in items],
            })
        return res

    def _playlists_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "").strip()
        if not name:
            raise RPCError("invalid_params", "playlist name required")
        mode = params.get("mode", "sequential")
        if mode not in ("sequential", "shuffle", "smart"):
            mode = "sequential"
        interval = params.get("interval_seconds")
        if interval is not None and interval not in (300, 600, 1800, 3600, 7200):
            interval = None
        try:
            pl = self.playlist_manager.create(name, mode=mode, interval_seconds=interval)
        except Exception as e:
            raise RPCError("invalid_params", str(e))
        return {
            "id": pl.id,
            "name": pl.name,
            "mode": pl.mode.value,
            "interval_seconds": pl.interval_seconds,
            "items": [],
        }

    def _playlists_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        playlist_id = params.get("id") or params.get("playlist_id")
        if playlist_id is None:
            raise RPCError("invalid_params", "playlist id required")
        try:
            self.playlist_manager.delete(int(playlist_id))
            return {"deleted": True, "id": int(playlist_id)}
        except KeyError:
            raise RPCError("not_found", f"Playlist introuvable : {playlist_id}")

    def _recommendations_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        limit = int(params.get("limit", 16))
        try:
            recs = self.recommendation_engine.recommend(limit=limit)
            return [{
                "uri": r.uri,
                "title": r.title,
                "source": r.source,
                "tags": list(r.tags),
                "rating": r.rating,
                "confidence": r.confidence,
                "external_views": r.external_views,
                "external_likes": r.external_likes,
                "thumbnail": str(r.thumbnail) if r.thumbnail else None,
            } for r in recs]
        except Exception as e:
            return []

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
        profile = self.config.outputs.get(output, {})
        return {
            "output": output,
            "loop": bool(profile.get("loop", True)),
            **playback_state_to_dict(current),
        }

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
            if self.playback.systemd.unit_status("*") == "active":
                self._invoke(self.playback.restart, "*")
                return {"restarted": True}
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
        enabled = params["enabled"]
        self._invoke(self.playback.set_loop, output, enabled)
        self.config.outputs.setdefault(output, {})["loop"] = enabled
        return {"loop": enabled}

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
        try:
            self._http_server = http.server.ThreadingHTTPServer(("127.0.0.1", self._http_port), _LoopbackHTTPHandler)
            self._http_server.engine_server = self.server  # type: ignore[attr-defined]
            self._http_thread = threading.Thread(target=self._http_server.serve_forever, name="mpvpaper-http-bridge", daemon=True)
            self._http_thread.start()
        except OSError as e:
            LOGGER.warning("Could not start loopback HTTP bridge on port %d: %s", self._http_port, e)
            self._http_server = None
            self._http_thread = None

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
            except Exception as error:
                # This worker runs after playback starts; a bad optional theme
                # adapter must never terminate the Engine service.
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
        if self._http_server is not None:
            try:
                self._http_server.shutdown()
            except Exception:
                pass
            self._http_server = None
        self._http_thread = None
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
