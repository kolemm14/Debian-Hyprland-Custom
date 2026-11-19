"""Localized category-folder and Hub URI validation tests."""
import sys
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mpvpaper_engine.discovery_download import localized_category_directory
from mpvpaper_engine.discovery_download import DiscoveryDownloader
from mpvpaper_engine.hub_import import (
    download_external_wallpaper, import_hub_wallpaper, open_hub_wallpaper,
)


class HubDownloadTests(unittest.TestCase):
    def test_categories_follow_supported_system_languages(self):
        self.assertEqual(localized_category_directory("Nature", "fr_FR.UTF-8"), "Nature")
        self.assertEqual(localized_category_directory("Jeux", "fr_FR"), "Jeux")
        self.assertEqual(localized_category_directory("Jeux", "en_US"), "Games")
        self.assertEqual(localized_category_directory("Ville", "en_GB"), "City")
        self.assertEqual(localized_category_directory("Espace", "fr"), "Espace")
        self.assertEqual(localized_category_directory("unknown", "fr"), "Autres")
        self.assertEqual(localized_category_directory("unknown", "en"), "Other")

    def test_rejects_non_hub_uri_without_network(self):
        with self.assertRaises(ValueError):
            import_hub_wallpaper("https://example.com/video.mp4")

    def test_rejects_path_traversal_category_folder(self):
        self.assertEqual(localized_category_directory("../../home/private", "en"), "Other")

    def test_engine_download_creates_localized_category_directory(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                self.close()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Live"
            downloader = DiscoveryDownloader(root)
            with mock.patch.object(downloader, "profile", return_value=object()), \
                    mock.patch("mpvpaper_engine.discovery_download.urlopen",
                               return_value=Response(b"media")), \
                    mock.patch("mpvpaper_engine.discovery_download.adapt_video_to_height",
                               side_effect=lambda path, _height: path), \
                    mock.patch("mpvpaper_engine.discovery_download.media_dimensions",
                               return_value=(640, 360)):
                result = downloader.download(
                    "https://motionbgs.com/wallpaper.mp4", "Aurora", 1080,
                    category="Nature", language="fr_FR",
                )
            self.assertEqual(result.path, root / "Nature" / "Aurora.mp4")
            self.assertEqual(result.path.read_bytes(), b"media")

    def test_direct_hub_video_uses_registered_video_type_and_quality_adaptation(self):
        class Response(io.BytesIO):
            headers = {"Content-Type": "video/mp4", "Content-Length": "5"}
            def __enter__(self): return self
            def __exit__(self, *_args): self.close()
            def geturl(self): return "https://cdn.livelywallpaper.app/wallpapers/aurora/download.mp4"
        with tempfile.TemporaryDirectory() as directory:
            downloader = DiscoveryDownloader(Path(directory) / "Live")
            with mock.patch.object(downloader, "profile", return_value=object()), \
                    mock.patch("mpvpaper_engine.discovery_download.build_opener", return_value=SimpleNamespace(open=mock.Mock(return_value=Response(b"video")))), \
                    mock.patch("mpvpaper_engine.discovery_download.adapt_video_to_height", side_effect=lambda path, _height: path) as adapt, \
                    mock.patch("mpvpaper_engine.discovery_download.media_dimensions", return_value=(640, 360)):
                result = downloader.download(
                    "https://cdn.livelywallpaper.app/wallpapers/aurora/download.mp4",
                    "Aurora", 720, category="Nature",
                    trusted_redirect_hosts={"cdn.livelywallpaper.app"},
                    media_suffix_hint=".mp4", trusted_media_types=("video/",),
                )
            self.assertEqual(result.path, Path(directory) / "Live" / "Nature" / "Aurora.mp4")
            self.assertEqual(result.path.read_bytes(), b"video")
            adapt.assert_called_once_with(result.path, 720)

    def test_engine_download_refuses_category_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Live"
            outside = Path(directory) / "outside"
            root.mkdir(); outside.mkdir()
            (root / "Nature").symlink_to(outside, target_is_directory=True)
            downloader = DiscoveryDownloader(root)
            with self.assertRaises(ValueError):
                downloader.download("https://motionbgs.com/video.mp4", "Aurora",
                                    1080, category="Nature", language="en")
            self.assertEqual(list(outside.iterdir()), [])

    @mock.patch("mpvpaper_engine.hub_import.DiscoveryDownloader")
    @mock.patch("mpvpaper_engine.hub_import._fetch_manifest")
    def test_hub_import_passes_category_to_engine_downloader(self, fetch, downloader):
        fetch.return_value = {
            "schema_version": 1, "mpvpaper_id": "motionbgs:test",
            "automatic_apply": False, "title": "Aurora", "category": "Nature",
            "source": {"url": "https://motionbgs.com/aurora"},
            "media": {"url": "https://motionbgs.com/dl/aurora.mp4"},
        }
        downloader.return_value.download.return_value = SimpleNamespace(
            path=None, message="mocked download"
        )
        import_hub_wallpaper("mpvp://download/motionbgs:test")
        downloader.assert_called_once()
        downloader.return_value.download.assert_called_once_with(
            "https://motionbgs.com/dl/aurora.mp4", "Aurora", category="Nature"
        )

    @mock.patch("mpvpaper_engine.hub_import.DiscoveryDownloader")
    @mock.patch("mpvpaper_engine.hub_import._fetch_manifest")
    def test_hub_manifest_cannot_send_engine_to_unapproved_media_host(self, fetch, downloader):
        fetch.return_value = {
            "schema_version": 1, "mpvpaper_id": "motionbgs:test",
            "automatic_apply": False, "title": "Aurora", "category": "Nature",
            "source": {"url": "https://motionbgs.com/aurora"},
            "media": {"url": "https://attacker.invalid/private.mp4"},
        }
        with self.assertRaises(ValueError):
            import_hub_wallpaper("mpvp://download/motionbgs:test")
        downloader.assert_not_called()

    @mock.patch("mpvpaper_engine.hub_import.DiscoveryDownloader")
    def test_external_wallpaper_download_uses_engine_downloader_with_registered_host(self, downloader):
        downloader.return_value.download.return_value = SimpleNamespace(path=None, message="test")
        result = download_external_wallpaper(
            "Wallhaven", "https://w.wallhaven.cc/full/ab/wallhaven-abcdef.jpg",
            "Night city", "Ville",
        )
        self.assertEqual(result.message, "test")
        downloader.return_value.download.assert_called_once_with(
            "https://w.wallhaven.cc/full/ab/wallhaven-abcdef.jpg", "Night city",
            category="Ville", trusted_redirect_hosts={"w.wallhaven.cc"},
        )

    @mock.patch("mpvpaper_engine.hub_import.DiscoveryDownloader")
    def test_curated_direct_video_sources_are_allowlisted_for_cancellable_import(self, downloader):
        downloader.return_value.download.return_value = SimpleNamespace(path=None, message="test")
        sources = (
            ("LivelyWallpaper.app", "https://cdn.livelywallpaper.app/wallpapers/aurora/download.mp4", {"cdn.livelywallpaper.app"}),
            ("MotionBGS", "https://motionbgs.com/dl/4k/7739/", {"motionbgs.com"}),
        )
        for source, url, hosts in sources:
            with self.subTest(source=source):
                download_external_wallpaper(source, url, "Aurora", "Nature")
                self.assertEqual(downloader.return_value.download.call_args.kwargs, {
                    "category": "Nature",
                    "trusted_redirect_hosts": hosts,
                    "media_suffix_hint": ".mp4",
                    "trusted_media_types": ("video/",),
                })

    @mock.patch("mpvpaper_engine.hub_import.DiscoveryDownloader")
    def test_direct_video_import_rejects_unapproved_hosts_and_paths(self, downloader):
        for source, url in (
            ("LivelyWallpaper.app", "https://cdn.livelywallpaper.app/wallpapers/aurora/private.mp4"),
            ("MotionBGS", "https://motionbgs.com/dl/8k/7739/"),
            ("MotionBGS", "https://evil.test/dl/4k/7739/"),
        ):
            with self.subTest(source=source, url=url), self.assertRaises(ValueError):
                download_external_wallpaper(source, url, "Aurora", "Nature")
        downloader.assert_not_called()

    @mock.patch("mpvpaper_engine.hub_import.DiscoveryDownloader")
    def test_external_download_forwards_progress_and_cancellation_hooks(self, downloader):
        import threading

        event = threading.Event()
        progress = mock.Mock()
        phase = mock.Mock()
        cancel = mock.Mock()
        downloader.return_value.download.return_value = SimpleNamespace(path=None, message="cancelled")
        download_external_wallpaper(
            "Wallhaven", "https://w.wallhaven.cc/full/ab/wallhaven-abcdef.jpg",
            "Night city", "Ville", cancel_event=event,
            progress_callback=progress, phase_callback=phase, cancel_callback=cancel,
        )
        kwargs = downloader.return_value.download.call_args.kwargs
        self.assertIs(kwargs["cancel_event"], event)
        self.assertIs(kwargs["progress_callback"], progress)
        self.assertIs(kwargs["phase_callback"], phase)
        self.assertIs(kwargs["cancel_callback"], cancel)

    @mock.patch("mpvpaper_engine.hub_import.DiscoveryDownloader")
    def test_external_download_rejects_unknown_providers_and_malformed_paths(self, downloader):
        for source, url in (
            ("Wallhaven", "https://127.0.0.1/private.jpg"),
            ("NASA Images", "https://images-assets.nasa.gov/image/PIA/a.jpg?redirect=x"),
            ("Unknown", "https://example.com/image.jpg"),
            ("NASA Images", "http://images-assets.nasa.gov/image/PIA/a.jpg"),
        ):
            with self.subTest(source=source, url=url), self.assertRaises(ValueError):
                download_external_wallpaper(source, url, "Wall", "Nature")
        downloader.assert_not_called()


    def test_open_hub_wallpaper_accepts_only_safe_item_links(self):
        self.assertTrue(open_hub_wallpaper("mpvp://open/space-zimmer").endswith("/?wallpaper=space-zimmer"))
        for uri in ("mpvp://open/../etc", "mpvp://open/ok?next=x", "https://example.com/"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                open_hub_wallpaper(uri)

if __name__ == "__main__":
    unittest.main()
