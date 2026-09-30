"""Steam Workshop resolver for MPVpaper Engine.

Resolves Steam Workshop items (Wallpaper Engine) to playable media,
structured results, and compatibility information.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

try:
    from mpvpaper_download import (
        WALLPAPER_ENGINE_APP_ID as _WE_APP_ID,
        steam_workshop_id as _steam_workshop_id,
        steam_file_details as _steam_file_details,
        steam_library_roots as _steam_library_roots,
        find_workshop_item as _find_workshop_item,
    )
except ImportError:
    # Fallback stubs when imported as part of the package without the script
    import re
    from urllib.parse import urlparse

    _WE_APP_ID = "431960"

    def _steam_workshop_id(uri: str) -> str:  # type: ignore[misc]
        try:
            parsed = urlparse(uri)
        except ValueError:
            return ""
        if parsed.hostname not in {"steamcommunity.com", "www.steamcommunity.com"}:
            return ""
        match = re.search(r"(?:^|&)id=([1-9]\d*)(?:&|$)", parsed.query)
        return match.group(1) if match else ""

    def _steam_file_details(item_id: str, opener=None) -> dict:  # type: ignore[misc]
        return {}

    def _steam_library_roots(home=None) -> list:  # type: ignore[misc]
        return []

    def _find_workshop_item(item_id: str, roots=None) -> Path | None:  # type: ignore[misc]
        return None


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StringEnum(str, Enum):
    """Enum whose members serialize naturally as string values."""


class WEProjectType(StringEnum):
    VIDEO = "video"
    IMAGE = "image"
    SCENE = "scene"
    WEB = "web"
    UNKNOWN = "unknown"


class WorkshopCompatibility(StringEnum):
    FULL = "full"
    PARTIAL = "partial"
    PREVIEW_ONLY = "preview_only"
    UNSUPPORTED = "unsupported"
    REQUIRES_AUTH = "requires_auth"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MediaProbe:
    path: Path
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0
    codec: str = ""
    has_audio: bool = False
    file_size: int = 0
    error: str = ""


@dataclass
class WorkshopResult:
    id: str
    provider: str = "steam-workshop"
    project_type: WEProjectType = WEProjectType.UNKNOWN
    compatibility: WorkshopCompatibility = WorkshopCompatibility.ERROR
    title: str = ""
    media: Path | None = None
    preview: str = ""
    source_dir: Path | None = None
    package: Path | None = None   # scene.pkg
    renderer: str | None = None   # 'mpvpaper' for VIDEO, None otherwise
    message: str = ""
    probe: MediaProbe | None = None
    raw_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict for future Hub API communication."""
        return {
            "id": self.id,
            "provider": self.provider,
            "type": self.project_type.value,
            "compatibility": self.compatibility.value,
            "title": self.title,
            "media": str(self.media) if self.media else None,
            "preview": self.preview,
            "source_dir": str(self.source_dir) if self.source_dir else None,
            "package": str(self.package) if self.package else None,
            "renderer": self.renderer,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp"}

# Auth-failure patterns emitted by steamcmd
_AUTH_REQUIRED_PATTERNS = (
    "login failure",
    "two-factor",
    "not logged on",
    "requires a purchase",
    "invalid password",
)


def _detect_repkg() -> Path | None:
    """Locate the repkg executable, if installed."""
    exe = shutil.which("repkg")
    if exe:
        return Path(exe)
    return None


def _safe_candidate(source_root: Path, relative_file: str) -> Path | None:
    """
    Resolve ``relative_file`` relative to ``source_root`` and apply path-
    traversal and symlink-escape guards.

    Returns the resolved ``Path`` when safe, ``None`` otherwise.
    """
    try:
        candidate = (source_root / relative_file).resolve()
    except (OSError, ValueError):
        return None

    # Reject paths that escape source_root
    root_str = str(source_root)
    cand_str = str(candidate)
    if not (cand_str.startswith(root_str + os.sep) or candidate == source_root):
        return None

    # Reject symlinks that point outside source_root
    if candidate.is_symlink():
        try:
            real = candidate.resolve()
        except OSError:
            return None
        if not str(real).startswith(root_str):
            return None

    return candidate


def _probe_video(path: Path, runner=subprocess.run) -> MediaProbe:
    """Run ffprobe on *path* and return a :class:`MediaProbe`.

    Probe failure is non-fatal; ``probe.error`` will be set instead.
    """
    probe = MediaProbe(path=path)
    try:
        probe.file_size = path.stat().st_size
    except OSError:
        pass

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        probe.error = "ffprobe not found"
        return probe

    try:
        result = runner(
            [
                ffprobe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,codec_name,duration"
                ":stream_tags=",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        probe.error = str(exc)
        return probe

    if result.returncode != 0:
        probe.error = result.stderr.strip() or "ffprobe error"
        return probe

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        probe.error = f"ffprobe JSON parse error: {exc}"
        return probe

    streams = data.get("streams", [{}])
    video_stream = streams[0] if streams else {}
    probe.width = int(video_stream.get("width", 0) or 0)
    probe.height = int(video_stream.get("height", 0) or 0)
    probe.codec = str(video_stream.get("codec_name", "") or "")

    fps_raw = video_stream.get("r_frame_rate", "0/1")
    try:
        num, den = (int(x) for x in str(fps_raw).split("/"))
        probe.fps = num / den if den else 0.0
    except (ValueError, ZeroDivisionError):
        probe.fps = 0.0

    # duration: prefer format-level, fall back to stream-level
    fmt_dur = data.get("format", {}).get("duration", "")
    stream_dur = video_stream.get("duration", "")
    for raw_dur in (fmt_dur, stream_dur):
        try:
            probe.duration = float(raw_dur)
            break
        except (TypeError, ValueError):
            continue

    # audio streams detection
    try:
        audio_result = runner(
            [
                ffprobe,
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        audio_data = json.loads(audio_result.stdout)
        probe.has_audio = bool(audio_data.get("streams"))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass

    return probe


def _find_best_media(item_dir: Path, preview: str = "") -> tuple[Path | None, str]:
    """
    Scan *item_dir* for video/image files when project.json is absent/broken.

    Returns ``(path, kind)`` where kind is ``"video"``, ``"image"``, or ``""``.
    """
    videos: list[Path] = []
    images: list[Path] = []
    for p in item_dir.rglob("*"):
        if not p.is_file() or _safe_candidate(item_dir, str(p.relative_to(item_dir))) is None:
            continue
        if p.stem.casefold().startswith(("preview", "thumbnail", "thumb")):
            continue
        if preview and p.resolve() == (item_dir / preview).resolve():
            continue
        suffix = p.suffix.casefold()
        if suffix in _VIDEO_EXTENSIONS:
            videos.append(p)
        elif suffix in _IMAGE_EXTENSIONS:
            images.append(p)
    if videos:
        return max(videos, key=lambda p: p.stat().st_size), "video"
    if images:
        return max(images, key=lambda p: p.stat().st_size), "image"
    return None, ""


# ---------------------------------------------------------------------------
# SteamWorkshopResolver
# ---------------------------------------------------------------------------

class SteamWorkshopResolver:
    """Resolve Steam Workshop items to playable media for MPVpaper Engine."""

    WALLPAPER_ENGINE_APP_ID = _WE_APP_ID

    def __init__(
        self,
        *,
        library_roots_fn=None,
        workshop_id_fn=None,
        file_details_fn=None,
        runner=subprocess.run,
        repkg_exe: Path | None = None,
    ):
        self._library_roots_fn = library_roots_fn or _steam_library_roots
        self._workshop_id_fn = workshop_id_fn or _steam_workshop_id
        self._file_details_fn = file_details_fn or _steam_file_details
        self._runner = runner
        self._repkg_exe = repkg_exe if repkg_exe is not None else _detect_repkg()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_url(self, uri: str) -> str:
        """Return the Workshop item ID if *uri* is a valid Workshop URL, else ``''``."""
        # Accept bare numeric IDs directly
        if uri.strip().isascii() and uri.strip().isdigit() and int(uri.strip()) > 0:
            return uri.strip()
        return self._workshop_id_fn(uri)

    def find_local(self, item_id: str) -> Path | None:
        """Return the local Workshop item directory if installed, else ``None``."""
        roots = self._library_roots_fn()
        for root in roots:
            candidate = (
                Path(root)
                / "steamapps/workshop/content"
                / self.WALLPAPER_ENGINE_APP_ID
                / item_id
            )
            if candidate.is_dir():
                return candidate
        return None

    def fetch_metadata(self, item_id: str) -> dict:
        """Fetch public Steam Workshop metadata.  Returns ``{}`` on failure."""
        try:
            return self._file_details_fn(item_id)
        except Exception:  # noqa: BLE001 – intentional broad catch for network errors
            return {}

    def resolve(self, uri_or_id: str, *, library_dir: Path | None = None) -> WorkshopResult:
        """Main entrypoint: resolve a Workshop URL or bare item ID to a :class:`WorkshopResult`."""
        item_id = self.validate_url(uri_or_id)
        if not item_id:
            return WorkshopResult(
                id="",
                compatibility=WorkshopCompatibility.ERROR,
                message="Invalid Steam Workshop URL or item ID",
            )

        # 1. Check local installation first
        item_dir = self.find_local(item_id)
        if item_dir is not None:
            return self._resolve_local(item_id, item_dir)

        # 2. Not local — try network paths
        return self._resolve_remote(item_id, library_dir=library_dir)

    # ------------------------------------------------------------------
    # Local resolution
    # ------------------------------------------------------------------

    def _resolve_local(self, item_id: str, item_dir: Path) -> WorkshopResult:
        source_root = item_dir.resolve()
        project_path = source_root / "project.json"

        if not project_path.is_file():
            return self._resolve_without_project_json(item_id, source_root)

        try:
            project = json.loads(project_path.read_text(encoding="utf-8"))
            if not isinstance(project, dict):
                raise ValueError("project.json must be an object")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result = self._resolve_without_project_json(item_id, source_root)
            result.message = f"project.json parse error ({exc}); {result.message}"
            return result

        raw_type = str(project.get("type", "") or "").strip().casefold()
        if not raw_type:
            suffix = Path(str(project.get("file", ""))).suffix.casefold()
            raw_type = "video" if suffix in _VIDEO_EXTENSIONS else "image" if suffix in _IMAGE_EXTENSIONS else "unknown"
            project["type"] = raw_type
        project_type = _parse_project_type(raw_type)
        title = str(project.get("title", "") or "")
        preview = str(project.get("preview", "") or "")
        relative_file = str(project.get("file", "") or "")

        if project_type in {WEProjectType.VIDEO, WEProjectType.IMAGE}:
            return self._resolve_media(
                item_id, source_root, relative_file, title, preview, project
            )
        if project_type == WEProjectType.SCENE:
            return self._resolve_scene(item_id, source_root, title, preview, project)
        if project_type == WEProjectType.WEB:
            return self._resolve_web(item_id, source_root, title, preview, project)

        # UNKNOWN type
        return WorkshopResult(
            id=item_id,
            project_type=WEProjectType.UNKNOWN,
            compatibility=WorkshopCompatibility.UNSUPPORTED,
            title=title,
            preview=preview,
            source_dir=source_root,
            message="Unknown or unsupported Wallpaper Engine project type",
            raw_metadata=project,
        )

    def _resolve_media(
        self,
        item_id: str,
        source_root: Path,
        relative_file: str,
        title: str,
        preview: str,
        project: dict,
    ) -> WorkshopResult:
        media_path: Path | None = None
        message = ""

        if relative_file:
            candidate = _safe_candidate(source_root, relative_file)
            if candidate is None:
                message = "Path traversal attempt in project.json file field — rejected"
            elif not candidate.is_file():
                message = f"Media file listed in project.json not found: {relative_file}"
            elif candidate.suffix.casefold() not in (
                _IMAGE_EXTENSIONS if project.get("type", "").casefold() == "image" else _VIDEO_EXTENSIONS
            ):
                message = "Referenced file is not media of the declared type"
            elif preview and candidate == (source_root / preview).resolve():
                message = "Referenced media is the project preview — rejected"
            else:
                media_path = candidate

        if media_path is None and not message:
            # Fallback: scan for any video file
            media_path, kind = _find_best_media(source_root, preview)
            if kind != str(project.get("type", "video")).casefold():
                media_path = None

        probe: MediaProbe | None = None
        if media_path is not None:
            probe = _probe_video(media_path, runner=self._runner)

        compat = (
            WorkshopCompatibility.FULL
            if media_path is not None
            else WorkshopCompatibility.ERROR
        )
        if not message and media_path is None:
            message = "No playable media of the declared type found in Workshop item"

        return WorkshopResult(
            id=item_id,
            project_type=_parse_project_type(str(project.get("type", "video")).casefold()),
            compatibility=compat,
            title=title,
            media=media_path,
            preview=preview,
            source_dir=source_root,
            renderer="mpvpaper" if media_path is not None else None,
            message=message,
            probe=probe,
            raw_metadata=project,
        )

    def _resolve_scene(
        self,
        item_id: str,
        source_root: Path,
        title: str,
        preview: str,
        project: dict,
    ) -> WorkshopResult:
        # Locate scene.pkg safely
        package: Path | None = None
        pkg_candidate = _safe_candidate(source_root, "scene.pkg")
        if pkg_candidate is not None and pkg_candidate.is_file():
            package = pkg_candidate

        repkg_note = ""
        if self._repkg_exe is not None:
            repkg_note = f" (repkg available at {self._repkg_exe}; extraction not performed here)"

        return WorkshopResult(
            id=item_id,
            project_type=WEProjectType.SCENE,
            compatibility=WorkshopCompatibility.PARTIAL,
            title=title,
            preview=preview,
            source_dir=source_root,
            package=package,
            renderer=None,
            message=f"Scene project: not natively rendered by mpvpaper{repkg_note}",
            raw_metadata=project,
        )

    def _resolve_web(
        self,
        item_id: str,
        source_root: Path,
        title: str,
        preview: str,
        project: dict,
    ) -> WorkshopResult:
        return WorkshopResult(
            id=item_id,
            project_type=WEProjectType.WEB,
            compatibility=WorkshopCompatibility.PREVIEW_ONLY,
            title=title,
            preview=preview,
            source_dir=source_root,
            renderer=None,
            message="Web wallpaper: HTML/JS not supported by native mpvpaper renderer",
            raw_metadata=project,
        )

    def _resolve_without_project_json(
        self, item_id: str, source_root: Path
    ) -> WorkshopResult:
        media_path, kind = _find_best_media(source_root)
        if kind == "video":
            probe = _probe_video(media_path, runner=self._runner)  # type: ignore[arg-type]
            return WorkshopResult(
                id=item_id,
                project_type=WEProjectType.VIDEO,
                compatibility=WorkshopCompatibility.FULL,
                source_dir=source_root,
                media=media_path,
                renderer="mpvpaper",
                message="No project.json; best-effort video detected",
                probe=probe,
            )
        if kind == "image":
            return WorkshopResult(
                id=item_id,
                project_type=WEProjectType.IMAGE,
                compatibility=WorkshopCompatibility.FULL,
                renderer="mpvpaper",
                source_dir=source_root,
                media=media_path,
                message="No project.json; only image files found",
            )
        return WorkshopResult(
            id=item_id,
            compatibility=WorkshopCompatibility.ERROR,
            source_dir=source_root,
            message="No project.json and no playable media found in Workshop item",
        )

    # ------------------------------------------------------------------
    # Remote resolution
    # ------------------------------------------------------------------

    def _resolve_remote(
        self, item_id: str, *, library_dir: Path | None
    ) -> WorkshopResult:
        metadata = self.fetch_metadata(item_id)
        title = str(metadata.get("title", "") or "")
        preview_url = str(metadata.get("preview_url", "") or "")
        file_url = str(metadata.get("file_url", "") or "")

        # Try direct file_url download
        if file_url and file_url != preview_url and file_url.startswith("https://"):
            result = self._try_direct_download(item_id, file_url, title, metadata, library_dir)
            if result is not None:
                return result

        # Try steamcmd anonymous
        steamcmd_result = self._try_steamcmd(item_id, title, metadata, library_dir)
        if steamcmd_result is not None:
            return steamcmd_result

        # Preview fallback
        if preview_url and preview_url.startswith("https://"):
            return WorkshopResult(
                id=item_id,
                project_type=WEProjectType.UNKNOWN,
                compatibility=WorkshopCompatibility.PREVIEW_ONLY,
                title=title,
                preview=preview_url,
                message="Only preview image available; full content requires Steam/steamcmd",
                raw_metadata=metadata,
            )

        return WorkshopResult(
            id=item_id,
            compatibility=WorkshopCompatibility.ERROR,
            title=title,
            message=(
                "Steam does not expose importable media. "
                "Install steamcmd or subscribe in Steam."
            ),
            raw_metadata=metadata,
        )

    def _try_direct_download(
        self,
        item_id: str,
        file_url: str,
        title: str,
        metadata: dict,
        library_dir: Path | None,
    ) -> WorkshopResult | None:
        """Attempt to download via the Steam file_url. Returns result or None."""
        if library_dir is None:
            return None
        try:
            from mpvpaper_download import _download, _import_downloaded_archive, _safe_title
        except ImportError:
            return None

        safe_title = _safe_title(title, f"Steam Workshop {item_id}")
        from urllib.parse import urlparse as _urlparse
        suffix = Path(_urlparse(file_url).path).suffix.casefold()
        destination = library_dir / f"{safe_title} [Steam-{item_id}-file]{suffix or '.bin'}"
        try:
            _download(file_url, destination, 8 * 1024 * 1024 * 1024)
        except (OSError, ValueError):
            destination.unlink(missing_ok=True)
            return None

        if destination.suffix.casefold() not in _VIDEO_EXTENSIONS | _IMAGE_EXTENSIONS:
            try:
                imported = _import_downloaded_archive(destination, library_dir, item_id, title)
            except (OSError, ValueError):
                imported = None
            destination.unlink(missing_ok=True)
            if imported is None:
                return None
            destination = imported
        kind = WEProjectType.VIDEO if destination.suffix.casefold() in _VIDEO_EXTENSIONS else WEProjectType.IMAGE
        probe = _probe_video(destination, runner=self._runner)
        if probe.error or not probe.width or not probe.height:
            destination.unlink(missing_ok=True)
            return None
        return WorkshopResult(
            id=item_id, project_type=kind,
            compatibility=WorkshopCompatibility.FULL, title=title,
            media=destination, renderer="mpvpaper", probe=probe,
            message="Downloaded via Steam file URL", raw_metadata=metadata,
        )

    def _try_steamcmd(
        self,
        item_id: str,
        title: str,
        metadata: dict,
        library_dir: Path | None,
    ) -> WorkshopResult | None:
        """Attempt steamcmd anonymous download. Returns result or None on hard failure."""
        steamcmd = shutil.which("steamcmd")
        if not steamcmd:
            return None

        command = [
            steamcmd,
            "+login", "anonymous",
            "+workshop_download_item",
            self.WALLPAPER_ENGINE_APP_ID,
            item_id,
            "validate",
            "+quit",
        ]
        try:
            result = self._runner(
                command,
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return WorkshopResult(
                id=item_id,
                compatibility=WorkshopCompatibility.ERROR,
                title=title,
                message="steamcmd download timed out after 1800 seconds",
                raw_metadata=metadata,
            )
        except OSError:
            return None

        output_lower = result.stdout.casefold() + result.stderr.casefold()
        if any(pat in output_lower for pat in _AUTH_REQUIRED_PATTERNS):
            return WorkshopResult(
                id=item_id,
                compatibility=WorkshopCompatibility.REQUIRES_AUTH,
                title=title,
                message="Steam authentication required to download this item",
                raw_metadata=metadata,
            )

        if result.returncode != 0:
            return None

        # After steamcmd success, look for locally installed item
        local = self.find_local(item_id)
        if local:
            return self._resolve_local(item_id, local)

        return None


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _parse_project_type(raw: str) -> WEProjectType:
    try:
        return WEProjectType(raw)
    except ValueError:
        return WEProjectType.UNKNOWN


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------

def resolve_workshop_url(
    uri: str, *, library_dir: Path | None = None
) -> WorkshopResult:
    """Convenience wrapper for one-shot resolution."""
    return SteamWorkshopResolver().resolve(uri, library_dir=library_dir)
