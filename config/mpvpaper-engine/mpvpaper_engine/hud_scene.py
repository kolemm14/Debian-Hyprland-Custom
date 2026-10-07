"""Shared desktop/editor layout in logical screen pixels, independent of MPV."""

from datetime import datetime
import re

from .hud import settings_from_config
from .hud_positioning import Rect, safe_area


ANCHORS = {
    "top-left": (0, 0), "top": (.5, 0), "top-right": (1, 0),
    "left": (0, .5), "center": (.5, .5), "right": (1, .5),
    "bottom-left": (0, 1), "bottom": (.5, 1), "bottom-right": (1, 1),
}
PALETTE = {"text": "#FFFFFF", "muted": "#CCCCCC", "accent": "#FF5577", "lines": "#CCCCCC"}
ENGLISH_MONTHS = (
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
)
ENGLISH_MONTHS_SHORT = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)
ENGLISH_WEEKDAYS = (
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
    "FRIDAY", "SATURDAY", "SUNDAY",
)
MODEL_SIZE = {
    "classic": (620, 560),
    "mond": (620, 300),
    "summit": (440, 520),
    "meenimal": (440, 460),
    "madara": (440, 320),
}


def logical_screen(monitor):
    scale = monitor.scale if monitor.scale and monitor.scale > 0 else 1
    width, height = monitor.width, monitor.height
    if getattr(monitor, "transform", 0) in (1, 3, 5, 7):
        width, height = height, width
    return Rect(monitor.x or 0, monitor.y or 0,
                width / scale, height / scale)


def geometry(data, screen, panels=()):
    settings = settings_from_config(data)
    base_width, base_height = MODEL_SIZE[settings.model]
    width, height = base_width * settings.scale, base_height * settings.scale
    ax, ay = ANCHORS[settings.anchor]
    area = (safe_area(screen, list(panels), settings.safe_margin)
            if settings.avoid_layers else screen)
    x = screen.x + settings.x * screen.width - ax * width
    y = screen.y + settings.y * screen.height - ay * height
    requested = (x, y)
    # Keep requested scale intact even when the widget exceeds the available area.
    if settings.avoid_layers:
        x = max(area.x, min(x, area.right - width))
        y = max(area.y, min(y, area.bottom - height))
    snapped = False
    if settings.snap:
        for axis, value, start, end, size in (
            (0, x, area.x, area.right, width),
            (1, y, area.y, area.bottom, height),
        ):
            candidates = (start, (start + end - size) / 2, end - size)
            nearest = min(candidates, key=lambda candidate: abs(candidate - value))
            if abs(nearest - value) <= 8:
                snapped |= nearest != value
                if axis == 0:
                    x = nearest
                else:
                    y = nearest
    return {
        "rect": Rect(x, y, width, height), "safe_area": area,
        "resolved": {"x": (x + ax * width - screen.x) / screen.width,
                     "y": (y + ay * height - screen.y) / screen.height},
        "collision": settings.avoid_layers and requested != (x, y),
        "snapped": snapped,
        "limited": width > area.width or height > area.height,
    }


def colors(data, system=None):
    settings = settings_from_config(data)
    palette = {**PALETTE, **(system or {})}
    if settings.color_mode == "custom":
        aliases = {"primary": "text", "secondary": "muted", "line": "lines"}
        for key, value in (settings.custom_colors or {}).items():
            if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                palette[aliases.get(key, key)] = value
    return palette


def entries(data, now=None):
    settings = settings_from_config(data)
    now = now or datetime.now().astimezone()
    english, japanese = ("GOOD MORNING", "おはよう") if 5 <= now.hour < 12 else (
        ("GOOD AFTERNOON", "こんにちは") if 12 <= now.hour < 18 else ("GOOD EVENING", "こんばんは"))
    weekday = ENGLISH_WEEKDAYS[now.weekday()]
    short_day = weekday[:3]
    month = ENGLISH_MONTHS[now.month - 1]
    date = (
        f"{now.day:02d}.{now.month:02d}.{now.year}"
        if settings.date_format == "numeric"
        else f"{now.day:02d} {ENGLISH_MONTHS_SHORT[now.month - 1]} {now.year}"
    )
    time = now.strftime("%H:%M" if settings.use_24h else "%I:%M %p")
    if settings.model == "mond":
        rows = [
            (settings.day, weekday, 86, -45, "Anurati", "text", 20),
            (settings.date, date, 23, 42, "Poppins", "text", 4),
            (settings.time, f"- {time} -", 23, 82, "Poppins", "text", 4),
        ]
    elif settings.model == "summit":
        greeting_word = english.removeprefix("GOOD ")
        summit_date = (
            f"{now.day:02d}.{now.month:02d}.{now.year}"
            if settings.date_format == "numeric"
            else f"{now.day:02d} {month}"
        )
        rows = [
            (settings.decorative_lines, "│", 58, -220, "Outfit", "lines", 0),
            (settings.greeting, "GOOD", 17, -130, "Outfit ExtraBold", "text", 1),
            (settings.greeting, greeting_word, 17, -102, "Outfit ExtraBold", "text", 1),
            (settings.day, short_day, 115, -18, "Electroharmonix", "text", 1),
            (settings.date, summit_date, 18, 76, "Outfit ExtraBold", "text", 1),
            (settings.time, time, 18, 112, "Outfit ExtraBold", "text", 1),
            (settings.decorative_lines, "│", 58, 208, "Outfit", "lines", 0),
        ]
    elif settings.model == "meenimal":
        rows = [
            (settings.time, now.strftime("%H"), 156, -112, "Google Sans Bold", "text", -5),
            (settings.time, now.strftime("%M"), 156, 20, "Google Sans Bold", "text", -5),
            (settings.day, weekday, 17, 148, "Gilroy-Bold", "text", 1),
            (settings.date, f"{month} {now.day}", 16, 177, "Gilroy-SemiBold", "text", 1),
        ]
    elif settings.model == "madara":
        compact_date = (
            f"{now.day:02d}.{now.month:02d}.{now.year}"
            if settings.date_format == "numeric"
            else f"{now.day:02d} {month}"
        )
        rows = [
            (settings.greeting, english, 16, -70, "Poppins Bold", "muted", 4),
            (settings.day, short_day, 68, 0, "Anurati", "text", 6),
            (settings.date, compact_date, 14, 62, "Poppins Bold", "text", 3),
            (settings.time, time, 14, 94, "Poppins Bold", "text", 3),
        ]
    else:
        rows = [
            (settings.greeting, english, 58, -110, "Noto Sans Bold", "text", 0),
            (settings.day, now.strftime("%a").upper(), 56, -40, "Anurati", "text", 0),
            (settings.time, now.strftime("%H:%M"), 42, 15, "Noto Sans", "text", 0),
            (settings.date, now.strftime("%d"), 42, 65, "Noto Sans", "text", 0),
            (settings.japanese, japanese, 28, 115, "Noto Sans CJK JP", "accent", 0),
            (bool(settings.username), settings.username, 22, 155,
             "Noto Sans CJK JP", "muted", 0),
        ]
        if settings.decorative_lines:
            rows.extend((True, "│", 38, offset, "Noto Sans", "lines", 0)
                        for offset in (-260, -215, 215, 260))
    return [row[1:] for row in rows if row[0]]


def draw(context, data, rect, palette=None):
    """The same Pango renderer is used by GTK3 desktop and GTK4 editor."""
    import gi
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    settings = settings_from_config(data)
    if not settings.enabled:
        return
    palette = colors(data, palette)
    for text, size, offset, family, color, spacing in entries(data):
        layout = PangoCairo.create_layout(context)
        PangoCairo.context_set_resolution(layout.get_context(), 96)
        font = Pango.FontDescription(family)
        font.set_absolute_size(size * settings.scale * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_width(round(rect.width * Pango.SCALE))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_single_paragraph_mode(True)
        layout.set_text(text, -1)
        if spacing:
            attributes = Pango.AttrList()
            attributes.insert(Pango.attr_letter_spacing_new(
                round(spacing * settings.scale * Pango.SCALE)
            ))
            layout.set_attributes(attributes)
        _, height = layout.get_pixel_size()
        value = palette[color]
        rgb = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        context.set_source_rgba(*rgb, settings.opacity)
        context.move_to(rect.x, rect.y + rect.height / 2 + offset * settings.scale - height / 2)
        PangoCairo.show_layout(context, layout)
