"""On-demand, read-only preference summary for MPVpaper Hub.

No service, media scan, network request, or database write occurs here.
Only a fixed public vocabulary and normalized weights leave the machine.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import unicodedata
from urllib.parse import quote

from .paths import EnginePaths

HUB_URL = "https://mpvpaper-hub.kebemouhamet08.chatgpt.site"
TOKEN_ALIASES = {
    "anime": ("anime", "manga", "naruto", "goku", "dragon ball", "your name", "kiminonawa", "kimetsu", "demon slayer"),
    "jeux": ("jeux", "game", "gaming", "genshin", "elden ring", "honkai", "zelda", "minecraft", "cyberpunk 2077"),
    "nature": ("nature", "landscape", "paysage", "mountain", "mountains", "lake", "forest", "fjord", "waterfall", "beach", "river", "aurora", "northern lights", "montagne", "foret", "plage"),
    "ville": ("ville", "city", "tokyo", "street", "urban", "ville", "cyberpunk"),
    "espace": ("espace", "space", "galaxy", "galaxie", "nebula", "planet", "cosmos"),
    "paysage": ("paysage", "landscape", "mountain", "mountains", "valley", "fjord", "lake", "waterfall"),
    "calme": ("calme", "calm", "peaceful", "relax", "zen"),
    "ciel": ("ciel", "sky", "skies", "cloud", "clouds"),
    "your name": ("your name", "kiminonawa", "kimi no na wa"),
    "cyberpunk": ("cyberpunk",), "pluie": ("pluie", "rain", "rainy"),
    "foret": ("foret", "forest"), "montagne": ("montagne", "mountain", "mountains"),
    "mer": ("mer", "sea", "ocean", "beach", "plage"),
    "neige": ("neige", "snow", "snowy", "winter"),
    "fantasy": ("fantasy", "fantastique", "dragon", "magic"),
}


def _tokens(text: str) -> set[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                    if not unicodedata.combining(c))
    plain = " " + re.sub(r"[^a-z0-9]+", " ", plain) + " "
    return {tag for tag, aliases in TOKEN_ALIASES.items()
            if any(" " + alias + " " in plain for alias in aliases)}


def build_profile(paths: EnginePaths | None = None) -> dict:
    paths = paths or EnginePaths.from_environment()
    profile = {"version": 1, "source": "mpvpaper-engine", "preferences": []}
    if not paths.library_db.is_file():
        return profile
    # mode=ro: no initialization, migration, scan, or accidental new database.
    connection = None
    try:
        connection = sqlite3.connect(paths.library_db.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute("""
            SELECT substr(w.title,1,512), w.favorite, w.usage_count,
                   substr(group_concat(t.name,' '),1,1024)
            FROM (SELECT id,title,favorite,usage_count FROM wallpapers
                  WHERE missing=0 ORDER BY favorite DESC,usage_count DESC,id DESC LIMIT 1000) w
            LEFT JOIN wallpaper_tags wt ON wt.wallpaper_id=w.id
            LEFT JOIN tags t ON t.id=wt.tag_id
            GROUP BY w.id
        """).fetchall()
    except sqlite3.Error as error:
        raise ValueError("La bibliothèque Engine ne permet pas de lire les préférences.") from error
    finally:
        if connection is not None:
            connection.close()
    scores: dict[str, float] = {}
    for title, favorite, usage_count, tags in rows:
        # One library vote, favorite bonus, bounded weight for prior uses.
        usage = max(0, min(int(usage_count or 0), 1000000))
        weight = 1 + (4 if favorite else 0) + min(5, math.log2(1 + usage))
        for tag in _tokens((title or "") + " " + (tags or "")):
            scores[tag] = scores.get(tag, 0) + weight
    maximum = max(scores.values(), default=1)
    profile["preferences"] = [
        {"tag": tag, "weight": max(0.01, round(score / maximum, 3))}
        for tag, score in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    return profile


def hub_url(profile: dict) -> str:
    payload = json.dumps(profile, ensure_ascii=True, separators=(",", ":"))
    return HUB_URL + "#mpvp_profile=" + quote(payload, safe="")
