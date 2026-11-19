"""Downloads selected Discover pages into the local wallpaper library."""

from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
import re
import subprocess
import locale
import threading
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from mpvpaper_download import (
    DownloadOutcome,
    IMAGE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
    adapt_image_to_height,
    detect_hardware_profile,
    downloader_diagnostics,
    adapt_video_to_height,
    media_dimensions,
    force_steam_workshop_download,
    requested_height,
    steam_workshop_id,
    youtube_download_command,
)


MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_MEDIA_BYTES = 8 * 1024 * 1024 * 1024


class DownloadCancelled(Exception):
    """Raised after a user cancels a streamed media download."""

_CATEGORY_TRANSLATIONS = {
    "anime": {"fr": "Anime", "en": "Anime"},
    "games": {"fr": "Jeux", "en": "Games"},
    "nature": {"fr": "Nature", "en": "Nature"},
    "city": {"fr": "Ville", "en": "City"},
    "space": {"fr": "Espace", "en": "Space"},
}


def localized_category_directory(category: str, language: str | None = None) -> str:
    """Map catalog labels to a safe folder name in the user's active language."""
    language = (language or _system_language()).split("_")[0].split("-")[0].lower()
    language = "fr" if language == "fr" else "en"
    token = re.sub(r"[^a-z]", "", str(category).casefold().translate(
        str.maketrans("éèêëàâäîïôöùûüç", "eeeeaaaiioouuuc")
    ))
    canonical = {
        "anime": "anime", "jeux": "games", "games": "games", "game": "games",
        "nature": "nature", "ville": "city", "city": "city", "urban": "city",
        "espace": "space", "space": "space",
    }.get(token)
    if canonical is None:
        canonical = "games" if token in {"gaming", "videogames"} else None
    if canonical is None:
        canonical = "nature" if token in {"paysage", "landscape"} else None
    if canonical is None:
        return "Autres" if language == "fr" else "Other"
    return _CATEGORY_TRANSLATIONS[canonical][language]


def _system_language() -> str:
    for value in (os.environ.get("LC_ALL"), os.environ.get("LC_MESSAGES"),
                  os.environ.get("LANGUAGE"), os.environ.get("LANG")):
        if value:
            return value.split(":", 1)[0].split(".", 1)[0].split("@", 1)[0]
    try:
        return locale.getlocale()[0] or "en"
    except (ValueError, TypeError):
        return "en"


class _MediaLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.preferred_links: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        candidates = []
        preferred = False
        if tag == "a":
            candidates.append(values.get("href", ""))
        elif tag == "meta":
            key = (values.get("property") or values.get("name") or "").casefold()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
                candidates.append(values.get("content", ""))
                preferred = True
        elif tag == "link":
            rel = {item.casefold() for item in values.get("rel", "").split()}
            if "preload" in rel and values.get("as", "").casefold() == "image":
                candidates.append(values.get("href", ""))
                preferred = True
        elif tag in {"img", "source", "video"}:
            candidates.extend((values.get("src", ""), values.get("data-src", "")))
            candidates.extend(
                value.strip().split(" ", 1)[0]
                for value in values.get("srcset", "").split(",") if value.strip()
            )
        for value in candidates:
            path = urlparse(value).path.casefold()
            if "/dl/" in path or Path(path).suffix in MEDIA_EXTENSIONS:
                (self.preferred_links if preferred else self.links).append(value)


class DiscoveryDownloader:
    def __init__(self, library_dir: Path):
        self.library_dir = Path(library_dir)

    def profile(self):
        return detect_hardware_profile()

    def diagnostics(self):
        return {**downloader_diagnostics(), "profile": self.profile()}

    def download(self, uri: str, title: str, selected_height: int = 0,
                 *, firefox=False, category: str | None = None,
                 language: str | None = None,
                 trusted_redirect_hosts: set[str] | None = None,
                 media_suffix_hint: str | None = None,
                 trusted_media_types: tuple[str, ...] = ("image/",),
                 preferred_codecs: tuple[str, ...] = (),
                 cancel_event: threading.Event | None = None,
                 progress_callback: Callable[[int, int], None] | None = None,
                 phase_callback: Callable[[str], None] | None = None,
                 cancel_callback: Callable[[Callable[[], None]], None] | None = None) -> DownloadOutcome:
        library_dir = self.library_dir
        if category:
            base_dir = library_dir.resolve()
            category_dir = base_dir / localized_category_directory(category, language)
            library_dir = category_dir.resolve()
            if not library_dir.is_relative_to(base_dir):
                raise ValueError("le dossier de catégorie sort de la bibliothèque Engine")
        library_dir.mkdir(parents=True, exist_ok=True)
        profile = self.profile()
        height = requested_height(selected_height, profile)
        if steam_workshop_id(uri):
            return force_steam_workshop_download(uri, library_dir, height)
        if phase_callback:
            phase_callback("Préparation de la source…")
        media_uri = uri if media_suffix_hint else self._page_media(uri, height)
        suffix = (media_suffix_hint or Path(urlparse(media_uri).path).suffix).casefold()
        if suffix in MEDIA_EXTENSIONS:
            try:
                path = self._direct(media_uri, title, suffix, library_dir,
                                    trusted_redirect_hosts=trusted_redirect_hosts,
                                    trusted_media_types=trusted_media_types,
                                    cancel_event=cancel_event,
                                    progress_callback=progress_callback,
                                    phase_callback=phase_callback,
                                    cancel_callback=cancel_callback)
            except DownloadCancelled as error:
                return DownloadOutcome(None, str(error), "cancelled")
            if suffix in IMAGE_EXTENSIONS:
                if phase_callback:
                    phase_callback("Adaptation de la résolution de l’image…")
                path = adapt_image_to_height(path, height)
            elif suffix in VIDEO_EXTENSIONS:
                if phase_callback:
                    phase_callback("Adaptation de la qualité vidéo…")
                path = adapt_video_to_height(path, height)
            if suffix in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                if phase_callback:
                    phase_callback("Vérification de la qualité…")
                if cancel_event and cancel_event.is_set():
                    return DownloadOutcome(None, "Téléchargement annulé", "cancelled")
                _width, actual_height = media_dimensions(path)
                if actual_height <= 0 or actual_height > height:
                    return DownloadOutcome(
                        None,
                        f"La limite {height}p n’a pas pu être vérifiée ou appliquée; le fichier source a été conservé.",
                        "quality",
                    )
            return DownloadOutcome(path, f"Média téléchargé · cible {height}p", "direct")
        return self._yt_dlp(media_uri, title, height, firefox=firefox,
                            library_dir=library_dir,
                            preferred_codecs=preferred_codecs)

    def _page_media(self, uri: str, target_height: int) -> str:
        if Path(urlparse(uri).path).suffix.casefold() in MEDIA_EXTENSIONS:
            return uri
        try:
            request = Request(uri, headers={"User-Agent": "Mozilla/5.0 MPVpaperEngine/2"})
            with urlopen(request, timeout=20) as response:
                contents = response.read(MAX_PAGE_BYTES + 1)
            if len(contents) > MAX_PAGE_BYTES:
                return uri
            parser = _MediaLinks()
            parser.feed(contents.decode("utf-8", "replace"))
            candidates = parser.preferred_links or parser.links
            links = {urljoin(uri, link) for link in candidates}
            if links:
                return max(links, key=lambda link: self._link_rank(link, target_height))
        except (OSError, ValueError):
            pass
        return uri

    @staticmethod
    def _link_rank(uri: str, target_height: int):
        lowered = uri.casefold()
        resolution = 0
        for token, height in (("8k", 4320), ("4k", 2160), ("1440", 1440),
                              ("1080", 1080), ("720", 720)):
            if token in lowered:
                resolution = height
                break
        within_target = resolution <= target_height
        is_video = Path(urlparse(uri).path).suffix.casefold() in VIDEO_EXTENSIONS
        return within_target, resolution if within_target else -resolution, is_video

    def _direct(self, uri: str, title: str, suffix: str,
                library_dir: Path | None = None,
                *, trusted_redirect_hosts: set[str] | None = None,
                trusted_media_types: tuple[str, ...] = ("image/",),
                cancel_event: threading.Event | None = None,
                progress_callback: Callable[[int, int], None] | None = None,
                phase_callback: Callable[[str], None] | None = None,
                cancel_callback: Callable[[Callable[[], None]], None] | None = None) -> Path:
        library_dir = Path(library_dir or self.library_dir)
        library_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", title).strip(" ._")[:150]
        stem = stem or "wallpaper"
        destination = library_dir / f"{stem}{suffix}"
        counter = 2
        while destination.exists():
            destination = library_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        partial = destination.with_name(f".{destination.name}.part")
        request = Request(uri, headers={
            "User-Agent": "Mozilla/5.0 MPVpaperEngine/2",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        })
        opener = None
        if trusted_redirect_hosts is not None:
            allowed_hosts = {host.lower() for host in trusted_redirect_hosts}

            class SameHostRedirects(HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    from urllib.parse import urlsplit
                    redirect = urlsplit(newurl)
                    if redirect.scheme != "https" or (redirect.hostname or "").lower() not in allowed_hosts:
                        raise ValueError("redirection externe refusée")
                    return super().redirect_request(req, fp, code, msg, headers, newurl)

            opener = build_opener(SameHostRedirects())
        total = 0
        try:
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Téléchargement annulé")
            if phase_callback:
                phase_callback("Téléchargement depuis la source…")
            response_context = opener.open(request, timeout=20) if opener else urlopen(request, timeout=20)
            with response_context as response, partial.open("wb") as stream:
                if cancel_callback:
                    cancel_callback(response.close)
                if trusted_redirect_hosts is not None:
                    from urllib.parse import urlsplit
                    final = urlsplit(response.geturl())
                    if final.scheme != "https" or (final.hostname or "").lower() not in allowed_hosts:
                        raise ValueError("redirection externe refusée")
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if not any(content_type.startswith(prefix) for prefix in trusted_media_types):
                        raise ValueError("la source n’a pas renvoyé un média du type attendu")
                try:
                    response_headers = getattr(response, "headers", {})
                    expected_size = int(response_headers.get("Content-Length", "0"))
                except ValueError:
                    expected_size = 0
                if progress_callback:
                    progress_callback(0, expected_size)
                while True:
                    if cancel_event and cancel_event.is_set():
                        raise DownloadCancelled("Téléchargement annulé")
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_MEDIA_BYTES:
                        raise ValueError("média distant trop volumineux")
                    stream.write(block)
                    if progress_callback:
                        progress_callback(total, expected_size)
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Téléchargement annulé")
            os.replace(partial, destination)
        except Exception as error:
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Téléchargement annulé") from error
            raise
        finally:
            partial.unlink(missing_ok=True)
        return destination

    def _yt_dlp(self, uri: str, title: str, height: int,
                *, firefox=False, library_dir: Path | None = None,
                preferred_codecs: tuple[str, ...] = ()) -> DownloadOutcome:
        library_dir = Path(library_dir or self.library_dir)
        library_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", title).strip(" ._")[:150]
        try:
            command = youtube_download_command(
                uri, library_dir / f"{stem or '%(title).150B'}.%(ext)s",
                height, firefox=firefox,
                preferred_codecs=preferred_codecs,
            )
        except FileNotFoundError as error:
            return DownloadOutcome(None, str(error), "yt-dlp")
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=1800, check=False)
        except subprocess.TimeoutExpired:
            return DownloadOutcome(None, "téléchargement interrompu après 30 minutes", "yt-dlp")
        except OSError as error:
            return DownloadOutcome(None, str(error), "yt-dlp")
        paths = [Path(line) for line in result.stdout.splitlines() if line.strip()]
        path = paths[-1] if result.returncode == 0 and paths else None
        if path is not None and path.is_file():
            _width, actual_height = media_dimensions(path)
            if actual_height <= 0 or actual_height > height:
                path.unlink(missing_ok=True)
                return DownloadOutcome(
                    None,
                    f"yt-dlp n’a pas respecté la limite de résolution {height}p; téléchargement refusé.",
                    "quality",
                )
            return DownloadOutcome(path, f"Vidéo téléchargée · cible {height}p", "yt-dlp")
        detail = result.stderr.strip().splitlines()
        message = "\n".join(detail[-8:]) if detail else "aucun média détecté"
        lowered = message.casefold()
        source = "authentication-required" if any(token in lowered for token in (
            "sign in", "not a bot", "cookies", "http error 403", "page needs to be reloaded",
        )) else "yt-dlp"
        return DownloadOutcome(None, message, source)
