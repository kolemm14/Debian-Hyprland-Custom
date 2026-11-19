"""Asynchronous Task Manager for MPVpaper Engine.

Handles background media optimization tasks (FFmpeg / Image conversion)
with thread safety, real progress reporting, clean cancellation,
disk space pre-checks, temporary file isolation, and strict preservation
of original files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable
import uuid

from .ipc import RPCError
from .media_optimizer import (
    MediaMetadata,
    VideoOptimizationConfig,
    ImageOptimizationConfig,
    probe_media,
    estimate_video_optimization,
    estimate_image_optimization,
    build_ffmpeg_video_command,
    RESOLUTIONS,
    VIDEO_FPS,
    VIDEO_CODECS,
    IMAGE_FORMATS,
    DEFAULT_INITIAL_RESOLUTION,
    DEFAULT_INITIAL_MAX_MB,
    OptimizationError,
)
from .paths import EnginePaths


@dataclass
class TaskRecord:
    task_id: str
    task_type: str
    state: str  # queued, running, completed, failed, cancelled
    progress: float  # 0.0 to 1.0
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    bytes_downloaded: int = 0
    total_bytes: int = 0
    phase: str = "En attente"
    # Private execution handles (not exposed to JSON API)
    _process: subprocess.Popen | None = None
    _temp_file: Path | None = None
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _cancel_callback: Callable[[], None] | None = field(default=None, repr=False)
    _uncancellable: bool = field(default=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "type": self.task_type,
            "state": self.state,
            "progress": round(self.progress, 3),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "bytes_downloaded": self.bytes_downloaded,
            "total_bytes": self.total_bytes,
            "phase": self.phase,
        }


class TaskManager:
    def __init__(self, paths: EnginePaths, max_workers: int = 2):
        self.paths = paths
        self.max_workers = max_workers
        self.tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_workers)

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self.tasks.values())
        records.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in records[:limit]]

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self.tasks.get(task_id)
        if not task:
            raise RPCError("task_not_found", f"Tâche inconnue : {task_id}")
        return task.to_dict()

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                raise RPCError("task_not_found", f"Tâche inconnue : {task_id}")

            if task.state in {"completed", "failed", "cancelled"}:
                return task.to_dict()
            if task._uncancellable:
                return task.to_dict()

            task.state = "cancelled"
            task.phase = "Annulation…"
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task._cancel_event.set()
            process = task._process
            temp_file = task._temp_file
            cancel_callback = task._cancel_callback

        # Terminate subprocess outside the main lock
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
            except OSError:
                pass

        if cancel_callback is not None:
            try:
                cancel_callback()
            except OSError:
                pass

        # Clean up temp file
        if temp_file is not None and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass

        return task.to_dict()

    def start_background(self, task_type: str,
                         worker: Callable[[TaskRecord], dict[str, Any]]) -> dict[str, str]:
        """Run a cancellable Engine job without holding the RPC request open."""
        task_id = uuid.uuid4().hex[:12]
        task = TaskRecord(
            task_id=task_id,
            task_type=task_type,
            state="queued",
            progress=0.0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self.tasks[task_id] = task
        thread = threading.Thread(
            target=self._run_background,
            args=(task, worker),
            name=f"task-{task_type}-{task_id}",
            daemon=True,
        )
        thread.start()
        return {"task_id": task_id, "state": task.state}

    def _run_background(self, task: TaskRecord,
                        worker: Callable[[TaskRecord], dict[str, Any]]) -> None:
        with self._semaphore:
            with self._lock:
                if task.state == "cancelled":
                    return
                task.state = "running"
                task.phase = "Démarrage…"
                task.started_at = datetime.now(timezone.utc).isoformat()
            try:
                result = worker(task)
                with self._lock:
                    if task.state == "cancelled":
                        return
                    task.state = "completed"
                    task.phase = "Terminé"
                    task.progress = 1.0
                    task.completed_at = datetime.now(timezone.utc).isoformat()
                    task.result = result
                    task._cancel_callback = None
            except Exception as error:
                with self._lock:
                    if task.state == "cancelled" or task._cancel_event.is_set():
                        task.state = "cancelled"
                        task.completed_at = task.completed_at or datetime.now(timezone.utc).isoformat()
                    else:
                        task.state = "failed"
                        task.phase = "Échec"
                        task.completed_at = datetime.now(timezone.utc).isoformat()
                        task.error = {"code": "task_failed", "message": str(error)}
                    task._cancel_callback = None

    def update_download_progress(self, task_id: str, downloaded: int, total: int) -> None:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task or task.state not in {"queued", "running"}:
                return
            task.bytes_downloaded = max(0, int(downloaded))
            task.total_bytes = max(0, int(total))
            if task.total_bytes:
                task.progress = min(0.99, task.bytes_downloaded / task.total_bytes)

    def set_phase(self, task_id: str, phase: str) -> None:
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.state in {"queued", "running"}:
                task.phase = str(phase)[:120]

    def set_cancel_callback(self, task_id: str, callback: Callable[[], None]) -> None:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            if task._cancel_event.is_set():
                call_now = True
            else:
                task._cancel_callback = callback
                call_now = False
        if call_now:
            callback()

    def begin_commit(self, task_id: str) -> bool:
        """Prevent cancellation once a completed download enters library import."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task or task.state == "cancelled" or task._cancel_event.is_set():
                return False
            task._uncancellable = True
            task._cancel_callback = None
            return True

    def estimate(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = params.get("file_path")
        if not file_path or not isinstance(file_path, str):
            raise RPCError("invalid_params", "file_path obligatoire")

        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise RPCError("file_not_found", f"Fichier source inexistant : {file_path}")
        if not os.access(path, os.R_OK):
            raise RPCError("permission_denied", f"Lecture impossible pour : {file_path}")

        meta = probe_media(str(path))
        media_type = params.get("media_type") or meta.media_type

        if media_type == "image":
            img_cfg = ImageOptimizationConfig(
                resolution=params.get("resolution", DEFAULT_INITIAL_RESOLUTION),
                format=params.get("format", "webp"),
                compression=params.get("compression", "medium"),
                target_max_mb=float(params.get("target_max_mb", DEFAULT_INITIAL_MAX_MB)),
                preserve_original=True,
            )
            est = estimate_image_optimization(meta, img_cfg)
        else:
            vid_cfg = VideoOptimizationConfig(
                resolution=params.get("resolution", DEFAULT_INITIAL_RESOLUTION),
                fps=str(params.get("fps", "original")),
                codec=params.get("codec", "h264"),
                compression=params.get("compression", "medium"),
                target_max_mb=float(params.get("target_max_mb", DEFAULT_INITIAL_MAX_MB)),
                preserve_original=True,
            )
            est = estimate_video_optimization(meta, vid_cfg)

        return {
            "file_path": str(path),
            "media_type": media_type,
            "metadata": {
                "width": meta.width,
                "height": meta.height,
                "size_mb": round(meta.size_bytes / (1024 * 1024), 2),
                "duration": meta.duration_seconds,
                "fps": meta.fps,
                "codec": meta.codec,
            },
            "estimate": est,
        }

    def start_optimize(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = params.get("file_path")
        if not file_path or not isinstance(file_path, str):
            raise RPCError("invalid_params", "file_path obligatoire")

        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise RPCError("file_not_found", f"Fichier source inexistant : {file_path}")
        if not os.access(path, os.R_OK):
            raise RPCError("permission_denied", f"Lecture impossible pour : {file_path}")

        # Estimation & validation
        est_result = self.estimate(params)
        est = est_result["estimate"]
        confirmed_lossy = bool(params.get("confirmed_lossy", False))

        if est.get("requires_lossy_confirmation") and not confirmed_lossy:
            raise RPCError(
                "confirmation_required",
                "Cette optimisation entraîne une modification avec perte de qualité et requiert une confirmation explicite.",
            )

        # Check disk space
        try:
            stat_vfs = shutil.disk_usage(path.parent)
            needed_bytes = int(est.get("estimated_size_mb", 150) * 1024 * 1024 * 2)
            if stat_vfs.free < needed_bytes:
                raise RPCError(
                    "insufficient_disk_space",
                    f"Espace disque insuffisant sur {path.parent} : requis {needed_bytes // (1024*1024)} Mo, disponible {stat_vfs.free // (1024*1024)} Mo",
                )
        except OSError as err:
            raise RPCError("disk_check_failed", f"Vérification de l'espace disque impossible : {err}")

        # Unique task id
        task_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        # Output path (NEVER overwrite original)
        output_dir = path.parent
        stem = path.stem
        ext = params.get("format", "mp4" if est_result["media_type"] == "video" else "webp").lstrip(".")
        output_file = output_dir / f"{stem}_optimized.{ext}"
        counter = 1
        while output_file.exists() or output_file == path:
            output_file = output_dir / f"{stem}_optimized_{counter}.{ext}"
            counter += 1

        record = TaskRecord(
            task_id=task_id,
            task_type="media_optimize",
            state="queued",
            progress=0.0,
            created_at=now,
        )

        with self._lock:
            self.tasks[task_id] = record

        # Dispatch background worker thread
        thread = threading.Thread(
            target=self._run_optimize_worker,
            args=(record, path, output_file, est_result["media_type"], params, est),
            name=f"task-opt-{task_id}",
            daemon=True,
        )
        thread.start()

        return {"task_id": task_id, "state": "queued", "output_path": str(output_file)}

    def _run_optimize_worker(
        self,
        task: TaskRecord,
        input_path: Path,
        output_path: Path,
        media_type: str,
        params: dict[str, Any],
        est: dict[str, Any],
    ) -> None:
        with self._semaphore:
            with self._lock:
                if task.state == "cancelled":
                    return
                task.state = "running"
                task.started_at = datetime.now(timezone.utc).isoformat()

            self.paths.temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self.paths.temp_dir / f"opt_{task.task_id}_{output_path.name}.tmp"
            task._temp_file = temp_file

            try:
                if media_type == "image":
                    self._execute_image_optimization(task, input_path, temp_file, params)
                else:
                    self._execute_video_optimization(task, input_path, temp_file, params, est)

                if task.state == "cancelled":
                    if temp_file.exists():
                        temp_file.unlink()
                    return

                # Verify result
                if not temp_file.exists() or temp_file.stat().st_size == 0:
                    raise OptimizationError("Le fichier produit est vide ou manquant.")

                # Atomic move to final destination
                shutil.move(str(temp_file), str(output_path))

                final_size_mb = round(output_path.stat().st_size / (1024 * 1024), 2)
                with self._lock:
                    task.state = "completed"
                    task.progress = 1.0
                    task.completed_at = datetime.now(timezone.utc).isoformat()
                    task.result = {
                        "input_path": str(input_path),
                        "output_path": str(output_path),
                        "final_size_mb": final_size_mb,
                        "saved_size_mb": max(0.0, round(input_path.stat().st_size / (1024 * 1024) - final_size_mb, 2)),
                    }

            except Exception as error:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass
                with self._lock:
                    if task.state != "cancelled":
                        task.state = "failed"
                        task.completed_at = datetime.now(timezone.utc).isoformat()
                        task.error = {"code": "optimization_error", "message": str(error)}

    def _execute_image_optimization(
        self, task: TaskRecord, input_path: Path, temp_file: Path, params: dict[str, Any]
    ) -> None:
        fmt = params.get("format", "webp").lower()
        quality_map = {"weak": 92, "medium": 80, "strong": 65}
        quality = quality_map.get(params.get("compression", "medium"), 80)
        res = RESOLUTIONS.get(params.get("resolution", DEFAULT_INITIAL_RESOLUTION))

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            cmd = ["ffmpeg", "-y", "-i", str(input_path)]
            if res:
                cmd.extend(["-vf", f"scale={res[0]}:{res[1]}:force_original_aspect_ratio=decrease"])
            if fmt == "webp":
                cmd.extend(["-c:v", "libwebp", "-quality", str(quality)])
            elif fmt == "jpeg":
                cmd.extend(["-q:v", str(int((100 - quality) / 3))])
            cmd.append(str(temp_file))

            task.progress = 0.3
            res_p = subprocess.run(cmd, capture_output=True, text=True, check=False)
            task.progress = 0.9
            if res_p.returncode != 0:
                raise OptimizationError(f"Échec conversion FFmpeg image : {res_p.stderr.strip()[:200]}")
        else:
            # Fallback to PIL if ffmpeg not in path
            from PIL import Image
            with Image.open(input_path) as img:
                if res:
                    img.thumbnail(res)
                img.save(temp_file, format=fmt.upper(), quality=quality)
            task.progress = 0.9

    def _execute_video_optimization(
        self,
        task: TaskRecord,
        input_path: Path,
        temp_file: Path,
        params: dict[str, Any],
        est: dict[str, Any],
    ) -> None:
        cfg = VideoOptimizationConfig(
            resolution=params.get("resolution", DEFAULT_INITIAL_RESOLUTION),
            fps=str(params.get("fps", "original")),
            codec=params.get("codec", "h264"),
            compression=params.get("compression", "medium"),
            target_max_mb=float(params.get("target_max_mb", DEFAULT_INITIAL_MAX_MB)),
            preserve_original=True,
        )

        base_cmd = build_ffmpeg_video_command(str(input_path), str(temp_file), cfg)
        # Add real progress reporting
        # insert progress flags after -i <input>
        idx = base_cmd.index(str(input_path)) + 1
        cmd = base_cmd[:idx] + ["-progress", "pipe:1", "-nostats"] + base_cmd[idx:]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        task._process = proc

        total_duration = est.get("metadata", {}).get("duration") or 30.0

        # Read progress output lines
        if proc.stdout:
            for line in proc.stdout:
                if task.state == "cancelled":
                    break
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        curr_sec = us / 1_000_000.0
                        ratio = min(0.98, curr_sec / max(1.0, total_duration))
                        task.progress = ratio
                    except (ValueError, IndexError):
                        pass

        stderr_output = ""
        if proc.stderr:
            stderr_output = proc.stderr.read()

        ret = proc.wait()
        if task.state == "cancelled":
            return

        if ret != 0:
            raise OptimizationError(f"Erreur FFmpeg ({ret}) : {stderr_output.strip()[-300:]}")
