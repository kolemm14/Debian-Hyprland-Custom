"""Bounded wallpaper palette analysis and failure-isolated theme integrations."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import colorsys
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import Callable

from .metadata import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .paths import EnginePaths
from .waybar_theme import write_panel_colors


THEME_SYNC_MODES = {"off", "on_apply", "always"}
SAMPLE_SIZE = 32
DEFAULT_FRAMES = 4
ECO_FRAMES = 2
MAX_DECODE_BYTES = SAMPLE_SIZE * SAMPLE_SIZE * 3 * DEFAULT_FRAMES


@dataclass(frozen=True, slots=True)
class Palette:
    colors: tuple[str, ...]
    foreground: str
    background: str
    source: str
    frames: int


@dataclass(frozen=True, slots=True)
class ThemeSyncResult:
    applied: bool
    palette: Palette | None
    integrations: dict[str, str]
    reason: str


class ThemeSyncError(RuntimeError):
    pass


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _luminance(color: str) -> float:
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def palette_from_rgb(data: bytes, source: Path, frames: int) -> Palette:
    if len(data) < 3:
        raise ThemeSyncError("no decoded pixels")
    histogram = Counter()
    usable = len(data) - len(data) % 3
    for red, green, blue in zip(data[:usable:3], data[1:usable:3], data[2:usable:3]):
        # Five bits per channel suppress codec noise while preserving useful accents.
        color = (red >> 3 << 3, green >> 3 << 3, blue >> 3 << 3)
        histogram[color] += 1
    # Keep distinct hues, including less common accents, instead of eight near-black bins.
    candidates = histogram.most_common(128)
    def score(entry):
        rgb, count = entry
        _, saturation, value = colorsys.rgb_to_hsv(*(v / 255 for v in rgb))
        return count ** 0.5 * (0.15 + saturation) * (0.2 + value)
    chosen = []
    for rgb, _count in sorted(candidates, key=score, reverse=True):
        if all(sum((a - b) ** 2 for a, b in zip(rgb, other)) >= 48 ** 2 for other in chosen):
            chosen.append(rgb)
        if len(chosen) == 8:
            break
    def hex_color(rgb):
        return "#" + "".join(f"{round(v):02x}" for v in rgb)
    ranked = [hex_color(rgb) for rgb in chosen]
    dominant = candidates[0][0]
    # Tint a dark surface from the dominant color; retain wallpaper hue.
    factor = min(1, 32 / max(1, max(dominant)))
    background = hex_color(tuple(v * factor for v in dominant))
    foreground = max(ranked, key=_luminance)
    if _luminance(foreground) - _luminance(background) < 160:
        base = tuple(int(foreground[i:i + 2], 16) for i in (1, 3, 5))
        foreground = hex_color(tuple(v * 0.2 + 255 * 0.8 for v in base))
    accents = [(rgb, count) for rgb, count in candidates
               if colorsys.rgb_to_hsv(*(v / 255 for v in rgb))[1] > .22
               and max(rgb) > 56 and count >= max(2, usable / 3 * .003)]
    accent = max(accents, key=score)[0] if accents else chosen[0]
    hue, light, saturation = colorsys.rgb_to_hls(*(v / 255 for v in accent))
    ranked[0] = hex_color(tuple(v * 255 for v in colorsys.hls_to_rgb(
        hue, max(0.6, min(0.75, light)), saturation)))
    return Palette(tuple(ranked), foreground, background, str(source), frames)


def _has_video_stream(source: Path, runner: Callable) -> bool:
    try:
        result = runner(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(source)],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = result.stdout.decode(errors="replace") if isinstance(result.stdout, bytes) else result.stdout
    return result.returncode == 0 and output.strip() == "video"


def extract_palette(
    source: Path,
    *,
    frames: int = DEFAULT_FRAMES,
    runner: Callable = subprocess.run,
) -> Palette:
    source = Path(source).expanduser().resolve()
    suffix = source.suffix.casefold()
    if not source.is_file():
        raise ValueError("wallpaper is missing or unsupported")
    if suffix not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS and not _has_video_stream(source, runner):
        raise ValueError("wallpaper is missing or unsupported")
    count = 1 if suffix in IMAGE_EXTENSIONS else max(1, min(int(frames), DEFAULT_FRAMES))
    command = ["ffmpeg", "-v", "error", "-i", str(source)]
    if count > 1:
        command.extend(["-vf", f"fps=1/8,scale={SAMPLE_SIZE}:{SAMPLE_SIZE}"])
    else:
        command.extend(["-vf", f"scale={SAMPLE_SIZE}:{SAMPLE_SIZE}"])
    command.extend(["-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    try:
        timeout = 60 if count > 1 else 15
        result = runner(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ThemeSyncError(str(error)) from error
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace") if isinstance(result.stderr, bytes) else result.stderr
        raise ThemeSyncError((message or "ffmpeg palette extraction failed").strip())
    data = bytes(result.stdout[:MAX_DECODE_BYTES])
    frame_bytes = SAMPLE_SIZE * SAMPLE_SIZE * 3
    decoded_frames = max(1, min(count, len(data) // frame_bytes))
    return palette_from_rgb(data, source, decoded_frames)


class ThemeSync:
    def __init__(
        self,
        paths: EnginePaths | None = None,
        *,
        extractor: Callable = extract_palette,
        runner: Callable = subprocess.run,
        clock: Callable = time.monotonic,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.extractor = extractor
        self.runner = runner
        self.clock = clock
        self.state_file = self.paths.palette_dir / "theme-sync-state.json"
        self.palette_file = self.paths.palette_dir / "current.json"
        self._lock = threading.Lock()
        self._active = False
        self._last_key = None

    def apply(self, source: Path, *, mode="on_apply", profile="balanced", force=False) -> ThemeSyncResult:
        if mode not in THEME_SYNC_MODES:
            raise ValueError("invalid theme sync mode")
        if mode == "off":
            return ThemeSyncResult(False, None, {}, "theme sync is off")
        source = Path(source).expanduser().resolve()
        key = self._key(source)
        with self._lock:
            if self._active:
                return ThemeSyncResult(False, None, {}, "theme sync already active")
            if not force and (key == self._last_key or key == self._stored_key()):
                return ThemeSyncResult(False, None, {}, "wallpaper already synchronized")
            self._active = True
        try:
            frames = ECO_FRAMES if profile == "eco" else DEFAULT_FRAMES
            palette = self.extractor(source, frames=frames)
            _atomic_json(self.palette_file, asdict(palette))
            wallust = self._run_wallust(source, palette)
            waybar = self._update_waybar(palette)
            integrations = {
                "waybar": waybar,
                "nova": self._notify_nova(),
                "wallust": wallust,
                "desktop": self._update_desktop(),
            }
            _atomic_json(self.state_file, {
                "key": key, "source": str(source), "updated_monotonic": self.clock(),
            })
            self._last_key = key
            return ThemeSyncResult(True, palette, integrations, "palette applied")
        finally:
            with self._lock:
                self._active = False

    def _run(self, command) -> str:
        try:
            result = self.runner(
                command, capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return f"failed: {error}"
        return "ok" if result.returncode == 0 else f"failed: {(result.stderr or '').strip()}"

    def _signal_waybar(self):
        return self._run(["pkill", "-SIGUSR2", "-x", "waybar"])

    def _update_waybar(self, palette: Palette) -> str:
        waybar_dir = self.paths.config_home.parent / "waybar"
        changed = write_panel_colors(
            waybar_dir,
            palette={
                "accent": palette.colors[0] if palette.colors else palette.foreground,
                "foreground": palette.foreground,
                "background": palette.background,
                "muted": "#" + "".join(f"{round(int(palette.foreground[i:i+2], 16) * .7 + int(palette.background[i:i+2], 16) * .3):02x}" for i in (1, 3, 5)),
            },
        )
        signal = self._signal_waybar() if changed else "unchanged"
        return f"updated; {signal}" if changed else signal

    def _update_desktop(self):
        script = self.paths.config_home.parent / "hypr/UserScripts/DeblestiaSystemThemeSync.sh"
        if not script.is_file():
            return "unavailable: desktop theme sync script is missing"
        return self._run(["bash", str(script), "--no-waybar-reload"])

    def _notify_nova(self):
        return self._run(["qs", "ipc", "call", "wallpaper", "paletteChanged"])

    def _run_wallust(self, source, palette=None):
        if palette is None:
            return self._run(["wallust", "run", "--quiet", str(source)])
        # Wallust accepts images, not MP4. Feed the same sampled colors as Waybar.
        colors = palette.colors or (palette.background, palette.foreground)
        row = b"".join(bytes.fromhex(color.lstrip("#")) * 32 for color in colors)
        self.paths.palette_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".ppm", dir=self.paths.palette_dir) as sample:
            sample.write(f"P6\n{len(colors) * 32} 32\n255\n".encode() + row * 32)
            sample.flush()
            return self._run(["wallust", "run", "--quiet", "--backend", "full",
                              "--colorspace", "lchansi", "--fallback-generator",
                              "interpolate", "--skip-sequences", sample.name])

    @staticmethod
    def _key(source):
        try:
            info = source.stat()
            value = f"desktop-v3:{source}:{info.st_size}:{info.st_mtime_ns}"
        except OSError:
            value = str(source)
        return hashlib.sha256(value.encode()).hexdigest()

    def _stored_key(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data.get("key") if isinstance(data, dict) else None
