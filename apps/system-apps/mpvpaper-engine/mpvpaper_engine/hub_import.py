"""Handle MPVpaper Hub links received through the mpvp:// URI scheme."""
from __future__ import annotations

import json
from pathlib import Path
import re
import threading
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from mpvpaper_download import DownloadOutcome

from .discovery_download import DiscoveryDownloader
from .library import Library

DEFAULT_LIBRARY_ROOTS = (
    Path.home() / "Pictures" / "Wallpapers" / "Live",
    Path.home() / "Pictures" / "wallpapers",
)

HUB_ORIGIN = "https://mpvpaper-hub.kebemouhamet08.chatgpt.site"
MAX_MANIFEST_BYTES = 64 * 1024


def _allowed_https_url(value: object, hosts: set[str]) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("URL absente ou invalide dans la fiche Hub")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("La fiche Hub contient une URL non sécurisée")
    if not any(host == allowed or host.endswith("." + allowed) for allowed in hosts):
        raise ValueError("La fiche Hub pointe vers une source non autorisée")
    return value


def _fetch_manifest(wallpaper_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9:-]{0,180}", wallpaper_id):
        raise ValueError("Identifiant de fond invalide")
    request = Request(
        f"{HUB_ORIGIN}/api/manifest?id={wallpaper_id}",
        headers={"Accept": "application/json", "User-Agent": "MPVpaperEngine/2"},
    )
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("Le Hub n’a pas fourni la fiche du fond")
        if urlsplit(response.geturl()).hostname != "mpvpaper-hub.kebemouhamet08.chatgpt.site":
            raise ValueError("La fiche Hub a été redirigée vers un autre domaine")
        payload = response.read(MAX_MANIFEST_BYTES + 1)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("La fiche Hub est trop volumineuse")
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Version de fiche Hub incompatible")
    if data.get("mpvpaper_id") != wallpaper_id or data.get("automatic_apply") is not False:
        raise ValueError("La fiche Hub ne correspond pas au fond demandé")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("Titre de fond absent")
    return data


def import_hub_wallpaper(uri: str) -> DownloadOutcome:
    """Fetch and import one Hub item into its localized category directory."""
    parsed = urlsplit(uri)
    if parsed.scheme != "mpvp" or parsed.netloc != "download" or parsed.query or parsed.fragment:
        raise ValueError("Lien MPVpaper Hub invalide")
    wallpaper_id = parsed.path.lstrip("/")
    if "/" in wallpaper_id:
        raise ValueError("Lien MPVpaper Hub invalide")
    item = _fetch_manifest(wallpaper_id)
    source = item.get("source")
    media = item.get("media")
    if not isinstance(source, dict) or not isinstance(media, dict):
        raise ValueError("Fiche Hub incomplète")
    source_url = _allowed_https_url(source.get("url"), {
        "motionbgs.com", "livelywallpaper.app", "mylivewallpapers.com",
        "moewalls.com", "wallsflow.com", "backiee.com", "vsthemes.org",
        "steamcommunity.com",
    })
    media_url = media.get("url")
    uri_to_download = source_url
    if media_url:
        uri_to_download = _allowed_https_url(media_url, {
            "motionbgs.com", "cdn.livelywallpaper.app", "mylivewallpapers.com",
            "moewalls.com", "wallsflow.com",
        })
    category = item.get("category")
    if not isinstance(category, str) or len(category) > 80:
        category = "Autres"
    downloader = DiscoveryDownloader(DEFAULT_LIBRARY_ROOTS[0])
    outcome = downloader.download(uri_to_download, item["title"], category=category)
    if outcome.path is not None and outcome.path.is_file():
        Library().scan(DEFAULT_LIBRARY_ROOTS)
    return outcome


def download_external_wallpaper(source: object, media_url: object,
                                title: object, category: object, *,
                                cancel_event: threading.Event | None = None,
                                progress_callback: Callable[[int, int], None] | None = None,
                                phase_callback: Callable[[str], None] | None = None,
                                cancel_callback: Callable[[Callable[[], None]], None] | None = None) -> DownloadOutcome:
    """Import a public image from a registered API source into Engine storage."""
    media_suffix_hint = None
    trusted_media_types = ("image/",)
    if source == "Wallhaven":
        hosts = {"w.wallhaven.cc"}
        path_pattern = r"/full/[a-z0-9]{2}/wallhaven-[a-z0-9]{6}\.(?:jpg|jpeg|png|webp)"
    elif source == "NASA Images":
        hosts = {"images-assets.nasa.gov"}
        path_pattern = r"/image/[a-zA-Z0-9_-]{1,100}/[a-zA-Z0-9._-]{1,180}\.(?:jpg|jpeg|png|webp)"
    elif source == "LivelyWallpaper.app":
        hosts = {"cdn.livelywallpaper.app"}
        path_pattern = r"/wallpapers/[a-z0-9-]{1,120}/download\.mp4"
        media_suffix_hint = ".mp4"
        trusted_media_types = ("video/",)
    elif source == "MotionBGS":
        hosts = {"motionbgs.com"}
        path_pattern = r"/dl/4k/[0-9]{1,12}/"
        media_suffix_hint = ".mp4"
        trusted_media_types = ("video/",)
    else:
        raise ValueError("Source externe non enregistrée pour le téléchargement Engine")
    if not isinstance(title, str) or not title.strip() or len(title) > 240:
        raise ValueError("Titre de wallpaper invalide")
    media = _allowed_https_url(media_url, hosts)
    parsed = urlsplit(media)
    if not re.fullmatch(path_pattern, parsed.path, flags=re.IGNORECASE) or parsed.query or parsed.fragment:
        raise ValueError("Adresse média externe non autorisée")
    if not isinstance(category, str) or len(category) > 80:
        category = "Autres"
    downloader = DiscoveryDownloader(DEFAULT_LIBRARY_ROOTS[0])
    options = {"trusted_redirect_hosts": hosts}
    if media_suffix_hint:
        options["media_suffix_hint"] = media_suffix_hint
        options["trusted_media_types"] = trusted_media_types
    if any(value is not None for value in (cancel_event, progress_callback, phase_callback, cancel_callback)):
        options.update({
            "cancel_event": cancel_event,
            "progress_callback": progress_callback,
            "phase_callback": phase_callback,
            "cancel_callback": cancel_callback,
        })
    result = downloader.download(media, title.strip(), category=category, **options)
    return result


def open_hub_wallpaper(uri: str) -> str:
    """Return the trusted Hub page for an item; the embedded view opens it."""
    parsed = urlsplit(uri)
    if parsed.scheme != "mpvp" or parsed.netloc != "open" or parsed.query or parsed.fragment:
        raise ValueError("Lien MPVpaper Hub invalide")
    wallpaper_id = parsed.path.lstrip("/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9:-]{0,180}", wallpaper_id):
        raise ValueError("Identifiant de fond invalide")
    return f"{HUB_ORIGIN}/?wallpaper={wallpaper_id}"
