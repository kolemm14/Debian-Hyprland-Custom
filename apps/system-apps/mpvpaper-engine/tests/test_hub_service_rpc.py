"""Unit and integration tests for Hub RPC methods exposed by EngineService."""
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))

from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.service import EngineService
from mpvpaper_engine.ipc import RPCError


def make_paths(temp_dir: str) -> EnginePaths:
    root = Path(temp_dir)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class HubServiceRPCTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.paths = make_paths(self.temp_dir.name)
        self.paths.config_home.mkdir(parents=True, exist_ok=True)
        self.paths.data_home.mkdir(parents=True, exist_ok=True)
        self.paths.config_file.write_text("outputs: {}\n", encoding="utf-8")
        self.service = EngineService(self.paths)

    def tearDown(self):
        self.service.shutdown()
        self.temp_dir.cleanup()

    def test_library_list_empty(self):
        result = self.service._library_list({})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_library_scan_and_favorite(self):
        # Create a mock image file
        wp_dir = Path(self.temp_dir.name) / "wallpapers"
        wp_dir.mkdir(parents=True)
        img = wp_dir / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        # Scan
        scan_res = self.service._library_scan({"roots": [str(wp_dir)]})
        self.assertIn("imported", scan_res)
        self.assertEqual(scan_res["imported"], 1)

        # List
        items = self.service._library_list({})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "test")
        self.assertEqual(items[0]["favorite"], False)

        # Set favorite
        fav_res = self.service._library_set_favorite({"id": items[0]["id"], "favorite": True})
        self.assertEqual(fav_res["favorite"], True)

        # Check list with favorites_only
        fav_items = self.service._library_list({"favorites_only": True})
        self.assertEqual(len(fav_items), 1)

    def test_playlists_rpc(self):
        # Create playlist
        pl = self.service._playlists_create({"name": "Chill", "mode": "sequential", "interval_seconds": 300})
        self.assertEqual(pl["name"], "Chill")
        self.assertEqual(pl["mode"], "sequential")

        # List playlists
        pls = self.service._playlists_list({})
        self.assertEqual(len(pls), 1)
        self.assertEqual(pls[0]["name"], "Chill")

        # Delete playlist
        del_res = self.service._playlists_delete({"id": pl["id"]})
        self.assertTrue(del_res["deleted"])
        self.assertEqual(len(self.service._playlists_list({})), 0)

    def test_recommendations_list_safe_fallback(self):
        recs = self.service._recommendations_list({"limit": 5})
        self.assertIsInstance(recs, list)

    def test_versioned_hub_download_and_apply_contract(self):
        methods = self.service._methods()
        self.assertIn("hub.v1.download", methods)
        self.assertIn("hub.v1.apply", methods)
        with self.assertRaises(RPCError):
            self.service._hub_v1_download({"source": "unknown"})

        root = Path(self.temp_dir.name) / "registered-wallpapers"
        root.mkdir()
        image = root / "hub-image.png"
        image.write_bytes(bytes([137]) + b"PNG\r\n\x1a\n" + bytes(64))
        self.service._library_scan({"roots": [str(root)]})
        wallpaper = self.service.library.get_by_path(image)
        with mock.patch.object(self.service, "_play", return_value={"strategy": "mock"}) as play:
            applied = self.service._hub_v1_apply({
                "wallpaper_id": wallpaper.id, "output": "*",
            })
        self.assertEqual(applied["wallpaper_id"], wallpaper.id)
        play.assert_called_once_with({"output": "*", "wallpaper": str(image)})

    def test_hub_download_indexes_only_the_downloaded_file(self):
        downloaded = Path(self.temp_dir.name) / "downloaded.png"
        downloaded.write_bytes(b"image")
        item = SimpleNamespace(id=7, path=downloaded, title="Downloaded", media_type="image")
        with mock.patch("mpvpaper_engine.hub_import.download_external_wallpaper",
                        return_value=SimpleNamespace(path=downloaded, message="ok")), \
                mock.patch.object(self.service.library, "import_file", return_value=item) as import_file, \
                mock.patch.object(self.service.library, "scan") as scan:
            result = self.service._hub_v1_download({
                "source": "Wallhaven", "media_url": "https://w.wallhaven.cc/file.jpg",
                "title": "Downloaded", "category": "Nature",
            })
        self.assertEqual(result["wallpaper"]["id"], 7)
        import_file.assert_called_once_with(downloaded, source="hub")
        scan.assert_not_called()

    def test_hub_download_start_can_report_progress_and_be_cancelled(self):
        entered = threading.Event()

        def blocked_download(source, media_url, title, category, *, cancel_event,
                             progress_callback, phase_callback, cancel_callback):
            progress_callback(256, 1024)
            phase_callback("Adaptation de la qualité vidéo…")
            entered.set()
            cancel_event.wait(1)
            raise RuntimeError("cancelled by user")

        with mock.patch("mpvpaper_engine.hub_import.download_external_wallpaper",
                        side_effect=blocked_download):
            started = self.service._hub_v1_download_start({
                "source": "Wallhaven", "media_url": "https://w.wallhaven.cc/file.jpg",
                "title": "Downloaded", "category": "Nature",
            })
            self.assertTrue(entered.wait(1))
            status = self.service._task_status({"task_id": started["task_id"]})
            self.assertEqual(status["bytes_downloaded"], 256)
            self.assertEqual(status["total_bytes"], 1024)
            self.assertEqual(status["phase"], "Adaptation de la qualité vidéo…")
            cancelled = self.service._task_cancel({"task_id": started["task_id"]})
            self.assertEqual(cancelled["state"], "cancelled")

    def test_unexpected_theme_adapter_error_is_contained_after_playback(self):
        self.service._theme_pending = (Path(self.temp_dir.name) / "wall.mp4", "on_apply")
        with mock.patch.object(self.service.theme_sync, "apply",
                               side_effect=TypeError("bad optional adapter")):
            self.service._theme_worker()
        self.assertIsNone(self.service._theme_pending)
