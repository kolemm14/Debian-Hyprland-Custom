"""Dynamic ASS desktop HUD rendered by MPV over the wallpaper."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import threading
import math
from copy import deepcopy
from typing import Any

from .hud_positioning import Rect, resolve_position


@dataclass(frozen=True, slots=True)
class HudSettings:
    enabled: bool = False
    x: float = 0.18
    y: float = 0.30
    scale: float = 1.0
    opacity: float = 1.0
    username: str = "ムハメト・ケベ"
    greeting: bool = True
    day: bool = True
    time: bool = True
    date: bool = True
    japanese: bool = True
    decorative_lines: bool = True
    color_mode: str = "system"
    custom_colors: dict[str, str] | None = None
    anchor: str = "center"
    safe_margin: int = 24
    snap: bool = True
    avoid_layers: bool = True
    model: str = "classic"
    use_24h: bool = False
    date_format: str = "text"


HUD_MODELS = {
    "classic": "Cyber / Japonais",
    "mond": "Rain Clock — Mond",
    "summit": "Rain Clock — Summit",
    "meenimal": "Rain Clock — Meenimal",
    "madara": "Madara compact (Anurati)",
}


def settings_from_config(data: Any) -> HudSettings:
    source = data if isinstance(data, dict) else {}
    position = source.get("position") if isinstance(source.get("position"), dict) else {}
    elements = source.get("elements") if isinstance(source.get("elements"), dict) else {}
    colors = source.get("colors") if isinstance(source.get("colors"), dict) else {}
    def number(value, default, low, high):
        try:
            value = float(value)
            return max(low, min(high, value)) if math.isfinite(value) else default
        except (TypeError, ValueError, OverflowError):
            return default
    return HudSettings(
        enabled=source.get("enabled") is True,
        x=number(position.get("x"), 0.18, 0, 1),
        y=number(position.get("y"), 0.30, 0, 1),
        scale=number(source.get("scale"), 1.0, 0.5, 2.0),
        opacity=number(source.get("opacity"), 1.0, 0, 1),
        username=str(source.get("username", "ムハメト・ケベ"))[:80],
        color_mode=colors.get("mode") if isinstance(colors.get("mode"), str) and colors.get("mode") in {"wallpaper", "system", "custom"}
        else "system",
        custom_colors=(
            {key: value for key, value in colors["custom"].items()
             if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value)}
            if isinstance(colors.get("custom"), dict) else {}
        ),
        anchor=source.get("anchor") if isinstance(source.get("anchor"), str) and source.get("anchor") in {
            "top-left", "top", "top-right", "left", "center", "right",
            "bottom-left", "bottom", "bottom-right",
        } else "center",
        safe_margin=int(number(source.get("safe_margin"), 24, 0, 200)),
        snap=source.get("snap") is not False,
        avoid_layers=source.get("avoid_layers") is not False,
        model=(source.get("model") if source.get("model") in HUD_MODELS else "classic"),
        use_24h=source.get("use_24h") is True,
        date_format=source.get("date_format") if source.get("date_format") in {
            "text", "numeric",
        } else "text",
        **{name: elements.get(name, True) is not False for name in (
            "greeting", "day", "time", "date", "japanese", "decorative_lines",
        )},
    )


def merge_hud(base, patch):
    """Merge a partial edit without dropping other screens or nested colors."""
    result = deepcopy(base) if isinstance(base, dict) else {}
    for key, value in (patch.items() if isinstance(patch, dict) else ()):
        result[key] = (merge_hud(result.get(key), value)
                       if isinstance(value, dict) else deepcopy(value))
    return result


def effective_hud(config, output, preview=None):
    result = deepcopy(config) if isinstance(config, dict) else {}
    outputs = result.pop("outputs", {})
    if isinstance(outputs, dict):
        result = merge_hud(result, outputs.get(output))
    return merge_hud(result, preview)


def preview_settings(config, output, previews):
    """Global drafts retain the same per-monitor precedence as an applied edit."""
    base = merge_hud(config, previews.get("*"))
    return effective_hud(base, output, previews.get(output))


def normalized_hud(data):
    """Use the same finite, bounded values for storage, controls and rendering."""
    result = deepcopy(data) if isinstance(data, dict) else {}
    settings = settings_from_config(result)
    result.update(enabled=settings.enabled, position={"x": settings.x, "y": settings.y},
                  scale=settings.scale, opacity=settings.opacity,
                  username=settings.username, anchor=settings.anchor,
                  safe_margin=settings.safe_margin, snap=settings.snap,
                  avoid_layers=settings.avoid_layers, model=settings.model,
                  use_24h=settings.use_24h, date_format=settings.date_format)
    result["elements"] = {name: getattr(settings, name) for name in (
        "greeting", "day", "time", "date", "japanese", "decorative_lines")}
    result["colors"] = {"mode": settings.color_mode, "custom": settings.custom_colors}
    if "outputs" in result:
        outputs = result["outputs"]
        result["outputs"] = {}
        if isinstance(outputs, dict):
            for name, override in outputs.items():
                if isinstance(override, dict):
                    clean = normalized_hud({key: value for key, value in override.items()
                                            if key != "outputs"})
                    result["outputs"][name] = {key: clean[key] for key in override if key in clean}
    return result


def _ass_color(value: str, fallback: str, alpha: int = 0) -> str:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", value if isinstance(value, str) else "")
    if not match:
        value = fallback
    red, green, blue = (value[index:index + 2] for index in (1, 3, 5))
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def _palette(path: Path) -> dict[str, str]:
    values = {"text": "#FFFFFF", "muted": "#CCCCCC", "accent": "#FF5577", "lines": "#CCCCCC"}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(
                r"@define-color\s+(text|muted|accent|lines)\s+(#[0-9a-fA-F]{6});", line,
            )
            if match:
                values[match.group(1)] = match.group(2)
    except OSError:
        pass
    return values


def font_status() -> dict[str, bool]:
    """Report optional font availability without making rendering depend on it."""
    if shutil.which("fc-match") is None:
        return {
            "Noto Sans": True, "Noto Sans CJK JP": True,
            "Anurati": True, "Poppins": True, "Electroharmonix": True,
            "Outfit": True, "Google Sans": True,
            "Gilroy-Bold": True, "Gilroy-SemiBold": True,
        }
    result = {}
    for family in (
        "Noto Sans", "Noto Sans CJK JP", "Anurati", "Poppins",
        "Electroharmonix", "Outfit", "Google Sans",
        "Gilroy-Bold", "Gilroy-SemiBold",
    ):
        try:
            probe = subprocess.run(
                ["fc-match", "-f", "%{family}", family],
                capture_output=True, text=True, timeout=2, check=False,
            )
            result[family] = probe.returncode == 0 and family.casefold() in probe.stdout.casefold()
        except (OSError, subprocess.TimeoutExpired):
            result[family] = False
    return result


def make_ass(
    width: int,
    height: int,
    settings: HudSettings,
    palette: dict[str, str],
    now: datetime | None = None,
) -> str:
    now = now or datetime.now().astimezone()
    greetings = ((5, 12, "GOOD MORNING", "おはよう"), (12, 18, "GOOD AFTERNOON", "こんにちは"))
    greeting_en, greeting_jp = "GOOD EVENING", "こんばんは"
    for start, end, english, japanese in greetings:
        if start <= now.hour < end:
            greeting_en, greeting_jp = english, japanese
            break
    x, y = int(width * settings.x), int(height * settings.y)
    alpha = max(0, min(255, round((1 - settings.opacity) * 255)))
    primary = _ass_color(palette["text"], "#FFFFFF", alpha)
    secondary = _ass_color(palette["muted"], "#CCCCCC", alpha)
    accent = _ass_color(palette["accent"], "#FF5577", alpha)
    lines = _ass_color(palette.get("lines", palette["muted"]), "#CCCCCC", alpha)
    sizes = {
        "normal": round(42 * settings.scale),
        "greeting": round(58 * settings.scale),
        "day": round(56 * settings.scale),
        "japanese": round(28 * settings.scale),
        "username": round(22 * settings.scale),
        "lines": round(38 * settings.scale),
    }
    gap = lambda value: round(value * settings.scale)
    events = []
    months = (
        "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
        "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
    )
    weekdays = (
        "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
        "FRIDAY", "SATURDAY", "SUNDAY",
    )
    month = months[now.month - 1]
    weekday = weekdays[now.weekday()]
    short_day = weekday[:3]
    clock = now.strftime("%H:%M" if settings.use_24h else "%I:%M %p")
    text_date = (
        f"{now.day:02d}.{now.month:02d}.{now.year}"
        if settings.date_format == "numeric"
        else f"{now.day:02d} {month[:3]} {now.year}"
    )
    if settings.model == "mond":
        if settings.day:
            events.append(("MondDay", f"{{\\pos({x},{y - gap(45)})}}{weekday}"))
        if settings.date:
            events.append(("MondMeta", f"{{\\pos({x},{y + gap(42)})}}{text_date}"))
        if settings.time:
            events.append(("MondMeta", f"{{\\pos({x},{y + gap(82)})}}- {clock} -"))
    elif settings.model == "summit":
        summit_date = (
            f"{now.day:02d}.{now.month:02d}.{now.year}"
            if settings.date_format == "numeric"
            else f"{now.day:02d} {month}"
        )
        if settings.decorative_lines:
            events.extend((
                ("SummitLine", f"{{\\pos({x},{y - gap(220)})}}│"),
                ("SummitLine", f"{{\\pos({x},{y + gap(208)})}}│"),
            ))
        if settings.greeting:
            events.extend((
                ("SummitGreeting", f"{{\\pos({x},{y - gap(130)})}}GOOD"),
                ("SummitGreeting", f"{{\\pos({x},{y - gap(102)})}}{greeting_en.removeprefix('GOOD ')}"),
            ))
        if settings.day:
            events.append(("SummitDay", f"{{\\pos({x},{y - gap(18)})}}{short_day}"))
        if settings.date:
            events.append(("SummitMeta", f"{{\\pos({x},{y + gap(76)})}}{summit_date}"))
        if settings.time:
            events.append(("SummitMeta", f"{{\\pos({x},{y + gap(112)})}}{clock}"))
    elif settings.model == "meenimal":
        if settings.time:
            events.extend((
                ("MeenimalNumber", f"{{\\pos({x},{y - gap(112)})}}{now:%H}"),
                ("MeenimalNumber", f"{{\\pos({x},{y + gap(20)})}}{now:%M}"),
            ))
        if settings.day:
            events.append(("MeenimalDay", f"{{\\pos({x},{y + gap(148)})}}{weekday}"))
        if settings.date:
            events.append(("MeenimalDate", f"{{\\pos({x},{y + gap(177)})}}{month} {now.day}"))
    elif settings.model == "madara":
        compact_date = (
            f"{now.day:02d}.{now.month:02d}.{now.year}"
            if settings.date_format == "numeric"
            else f"{now.day:02d} {month}"
        )
        if settings.greeting:
            events.append(("CompactGreeting", f"{{\\pos({x},{y - gap(70)})}}{greeting_en}"))
        if settings.day:
            events.append(("CompactDay", f"{{\\pos({x},{y})}}{short_day}"))
        if settings.date:
            events.append(("CompactMeta", f"{{\\pos({x},{y + gap(62)})}}{compact_date}"))
        if settings.time:
            events.append(("CompactMeta", f"{{\\pos({x},{y + gap(94)})}}{clock}"))
    elif settings.model == "classic" and settings.decorative_lines:
        events.extend((
            ("Lines", f"{{\\pos({x},{y - gap(150)})}}│"),
            ("Lines", f"{{\\pos({x},{y - gap(105)})}}│"),
        ))
    if settings.model == "classic" and settings.greeting:
        events.append(("Greeting", f"{{\\pos({x},{y})}}{greeting_en}"))
    if settings.model == "classic" and settings.day:
        events.append(("Anurati", f"{{\\pos({x},{y + gap(70)})}}{now.strftime('%a').upper()}"))
    if settings.model == "classic" and settings.time:
        events.append(("Normal", f"{{\\pos({x},{y + gap(125)})}}{now.strftime('%H:%M')}"))
    if settings.model == "classic" and settings.date:
        events.append(("Normal", f"{{\\pos({x},{y + gap(175)})}}{now.strftime('%d')}"))
    if settings.model == "classic" and settings.japanese:
        events.append(("Japanese", f"{{\\pos({x},{y + gap(225)})}}{greeting_jp}"))
    if settings.model == "classic" and settings.username:
        events.append(("Username", f"{{\\pos({x},{y + gap(265)})}}{settings.username}"))
    if settings.model == "classic" and settings.decorative_lines:
        events.extend((
            ("Lines", f"{{\\pos({x},{y + gap(325)})}}│"),
            ("Lines", f"{{\\pos({x},{y + gap(370)})}}│"),
        ))
    event_text = "\n".join(
        f"Dialogue: 0,0:00:00.00,9:59:59.00,{style},,0,0,0,,{text}"
        for style, text in events
    )
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Normal,Noto Sans,{sizes["normal"]},{primary},{primary},&H00000000,&H00000000,0,0,0,0,100,100,5,0,1,0,0,5,0,0,0,1
Style: Greeting,Noto Sans,{sizes["greeting"]},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,5,0,1,0,0,5,0,0,0,1
Style: Anurati,Anurati,{sizes["day"]},{primary},{primary},&H00000000,&H00000000,0,0,0,0,100,100,8,0,1,0,0,5,0,0,0,1
Style: Japanese,Noto Sans CJK JP,{sizes["japanese"]},{accent},{accent},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,5,0,0,0,1
Style: Username,Noto Sans CJK JP,{sizes["username"]},{secondary},{secondary},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,5,0,0,0,1
Style: Lines,Noto Sans,{sizes["lines"]},{lines},{lines},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: MondDay,Anurati,{round(86 * settings.scale)},{primary},{primary},&H00000000,&H00000000,0,0,0,0,100,100,20,0,1,0,0,5,0,0,0,1
Style: MondMeta,Poppins,{round(23 * settings.scale)},{primary},{primary},&H00000000,&H00000000,0,0,0,0,100,100,4,0,1,0,0,5,0,0,0,1
Style: SummitGreeting,Outfit,{round(17 * settings.scale)},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,0,0,5,0,0,0,1
Style: SummitDay,Electroharmonix,{round(115 * settings.scale)},{primary},{primary},&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,0,0,5,0,0,0,1
Style: SummitMeta,Outfit,{round(18 * settings.scale)},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,0,0,5,0,0,0,1
Style: SummitLine,Outfit,{round(58 * settings.scale)},{lines},{lines},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: MeenimalNumber,Google Sans,{round(156 * settings.scale)},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,-5,0,1,0,0,5,0,0,0,1
Style: MeenimalDay,Gilroy-Bold,{round(17 * settings.scale)},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,0,0,5,0,0,0,1
Style: MeenimalDate,Gilroy-SemiBold,{round(16 * settings.scale)},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,0,0,5,0,0,0,1
Style: CompactGreeting,Poppins,{round(16 * settings.scale)},{secondary},{secondary},&H00000000,&H00000000,1,0,0,0,100,100,4,0,1,0,1,5,0,0,0,1
Style: CompactDay,Anurati,{round(68 * settings.scale)},{primary},{primary},&H00000000,&H00000000,0,0,0,0,100,100,6,0,1,0,2,5,0,0,0,1
Style: CompactMeta,Poppins,{round(14 * settings.scale)},{primary},{primary},&H00000000,&H00000000,1,0,0,0,100,100,3,0,1,0,1,5,0,0,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
{event_text}
"""


class HudManager:
    def __init__(self, cache_home: Path, config_home: Path):
        self.directory = Path(cache_home) / "hud"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.palette_file = Path(config_home).parent / "waybar" / "panel-colors.css"
        self.settings = HudSettings()
        self._config: dict[str, Any] = {}
        self._lock = threading.Lock()

    def configure(self, data: Any) -> None:
        self._config = dict(data) if isinstance(data, dict) else {}
        self.settings = settings_from_config(self._config)

    def settings_for_output(self, output: str, override: dict[str, Any] | None = None) -> HudSettings:
        return settings_from_config(effective_hud(self._config, output, override))

    def path(self, output: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "-", output)
        return self.directory / f"hud-{safe or 'all'}.ass"

    def render(
        self,
        output: str,
        width: int | None = None,
        height: int | None = None,
        monitor: Rect | None = None,
        safe_area_rect: Rect | None = None,
        palette: dict[str, str] | None = None,
        settings_override: dict[str, Any] | None = None,
    ) -> Path | None:
        settings = self.settings_for_output(output, settings_override)
        if not settings.enabled:
            return None
        width = width or 1920
        height = height or 1080
        if monitor is not None and safe_area_rect is not None and settings.avoid_layers:
            x, y = resolve_position(
                settings.x, settings.y, monitor,
                (260 * settings.scale, 420 * settings.scale),
                safe_area_rect, snap=settings.snap,
            )
            settings = replace(settings, x=max(0.05, min(0.95, x)),
                               y=max(0.10, min(0.90, y)))
        target = self.path(output)
        colors = palette or _palette(self.palette_file)
        if settings.color_mode == "custom":
            custom = settings.custom_colors or {}
            aliases = {
                "primary": "text", "secondary": "muted",
                "line": "lines",
            }
            normalized = {
                aliases.get(key, key): value for key, value in custom.items()
            }
            colors = {**colors, **normalized}
        content = make_ass(width, height, settings, colors)
        temporary = target.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(target)
        return target
