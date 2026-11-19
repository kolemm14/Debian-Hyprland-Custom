import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "mpvpaper_download.py"
SPEC = importlib.util.spec_from_file_location("mpvpaper_download", MODULE_PATH)
DOWNLOADS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOWNLOADS)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class DownloadPolicyTests(unittest.TestCase):
    def test_integrated_1080p_machine_stays_at_native_resolution(self):
        profile = DOWNLOADS.choose_hardware_profile(
            [1080, 1080], 16 * 1024 * 1024, "Intel UHD Graphics 620"
        )
        self.assertEqual(profile.target_height, 1080)
        self.assertEqual(profile.display_height, 1080)

    def test_powerful_machine_caps_download_at_4k(self):
        profile = DOWNLOADS.choose_hardware_profile(
            [4320], 32 * 1024 * 1024, "NVIDIA GeForce RTX 4090"
        )
        self.assertEqual(profile.target_height, 2160)

    def test_4k_integrated_machine_is_capped(self):
        profile = DOWNLOADS.choose_hardware_profile(
            [2160], 8 * 1024 * 1024, "Intel UHD Graphics 620"
        )
        self.assertEqual(profile.target_height, 720)

    def test_workshop_id_validation(self):
        self.assertEqual(
            DOWNLOADS.steam_workshop_id(
                "https://steamcommunity.com/sharedfiles/filedetails/?id=2704773569"
            ),
            "2704773569",
        )
        self.assertEqual(DOWNLOADS.steam_workshop_id("https://example.com/?id=1"), "")

    def test_youtube_command_has_resume_and_bounded_retries(self):
        with mock.patch.object(DOWNLOADS, "PRIVATE_PYTHON", Path("/missing")), \
                mock.patch.object(DOWNLOADS, "LOCAL_YTDLP", Path("/bin/yt-dlp")), \
                mock.patch.object(DOWNLOADS, "LOCAL_DENO", Path("/missing-deno")):
            command = DOWNLOADS.youtube_download_command(
                "https://youtube.test/watch?v=1", "/tmp/video.%(ext)s", 1080
            )
        self.assertIn("--continue", command)
        self.assertEqual(command[command.index("--concurrent-fragments") + 1], "8")
        self.assertEqual(command[command.index("--buffer-size") + 1], "1M")
        self.assertEqual(command[command.index("--retries") + 1], "10")
        self.assertEqual(command[command.index("--fragment-retries") + 1], "10")
        self.assertNotIn("--cookies-from-browser", command)

    def test_download_profile_prefers_codec_before_source_fallback(self):
        with mock.patch.object(DOWNLOADS, "PRIVATE_PYTHON", Path("/missing")), \
                mock.patch.object(DOWNLOADS, "LOCAL_YTDLP", Path("/bin/yt-dlp")), \
                mock.patch.object(DOWNLOADS, "LOCAL_DENO", Path("/missing-deno")):
            command = DOWNLOADS.youtube_download_command(
                "https://youtube.test/watch?v=1", "/tmp/video.%(ext)s", 2160,
                preferred_codecs=("av01", "hev1", "not-allowed"),
            )
        selector = command[command.index("-f") + 1]
        self.assertLess(selector.index("vcodec^=av01"), selector.index("vcodec^=hev1"))
        self.assertNotIn("not-allowed", selector)
        self.assertTrue(selector.endswith("b[height<=2160]"))

    def test_youtube_command_enables_available_node_js_runtime(self):
        with mock.patch.object(DOWNLOADS, "PRIVATE_PYTHON", Path("/missing")), \
                mock.patch.object(DOWNLOADS, "LOCAL_YTDLP", Path("/bin/yt-dlp")), \
                mock.patch.object(DOWNLOADS, "LOCAL_DENO", Path("/missing-deno")), \
                mock.patch.object(DOWNLOADS.shutil, "which", return_value="/usr/bin/node"):
            command = DOWNLOADS.youtube_download_command(
                "https://youtube.test/watch?v=1", "/tmp/video.%(ext)s", 360
            )
        index = command.index("--js-runtimes")
        self.assertEqual(command[index + 1], "node:/usr/bin/node")

    def test_video_height_adaptation_replaces_source_only_after_verified_transcode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wallpaper.mp4"
            source.write_bytes(b"original")

            def runner(command, **_kwargs):
                if command[0] == "ffprobe":
                    height = 1080 if command[-1] == str(source) else 360
                    payload = json.dumps({"streams": [{"width": 640, "height": height}]})
                    return subprocess.CompletedProcess(command, 0, payload, "")
                Path(command[-1]).write_bytes(b"transcoded")
                return subprocess.CompletedProcess(command, 0, "", "")

            result = DOWNLOADS.adapt_video_to_height(source, 360, runner=runner)

            self.assertEqual(result, source)
            self.assertEqual(source.read_bytes(), b"transcoded")

    def test_video_height_adaptation_keeps_source_when_transcode_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wallpaper.mp4"
            source.write_bytes(b"original")

            def runner(command, **_kwargs):
                if command[0] == "ffprobe":
                    return subprocess.CompletedProcess(
                        command, 0, '{"streams":[{"width":1920,"height":1080}]}', ""
                    )
                return subprocess.CompletedProcess(command, 1, "", "ffmpeg failed")

            result = DOWNLOADS.adapt_video_to_height(source, 360, runner=runner)

            self.assertEqual(result, source)
            self.assertEqual(source.read_bytes(), b"original")

    def test_firefox_cookies_are_explicit_fallback_only(self):
        with mock.patch.object(DOWNLOADS, "PRIVATE_PYTHON", Path("/missing")), \
                mock.patch.object(DOWNLOADS, "LOCAL_YTDLP", Path("/bin/yt-dlp")), \
                mock.patch.object(DOWNLOADS, "LOCAL_DENO", Path("/missing-deno")):
            command = DOWNLOADS.youtube_download_command(
                "https://youtube.test/watch?v=1", "/tmp/video.%(ext)s", 1080,
                firefox=True,
            )
        index = command.index("--cookies-from-browser")
        self.assertEqual(command[index + 1], "firefox")

    def test_steam_details_uses_official_endpoint(self):
        payload = {"response": {"publishedfiledetails": [{
            "publishedfileid": "42", "title": "Test", "preview_url": "https://cdn/x.jpg"
        }]}}

        def opener(request, timeout):
            self.assertEqual(timeout, 20)
            self.assertIn(b"publishedfileids%5B0%5D=42", request.data)
            return FakeResponse(json.dumps(payload).encode())

        self.assertEqual(DOWNLOADS.steam_file_details("42", opener)["title"], "Test")

    def test_local_video_project_is_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root / "item"
            library = root / "library"
            item.mkdir()
            (item / "movie.mp4").write_bytes(b"video")
            (item / "project.json").write_text('{"file":"movie.mp4"}', encoding="utf-8")
            result = DOWNLOADS.import_workshop_item(item, library, "42", "Night City")
            self.assertTrue(result.is_file())
            self.assertIn("Steam-42", result.name)

    def test_local_workshop_import_does_not_require_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root / "item"
            item.mkdir()
            (item / "movie.mp4").write_bytes(b"video")
            with mock.patch.object(DOWNLOADS, "find_workshop_item", return_value=item), \
                    mock.patch.object(DOWNLOADS, "steam_file_details") as details:
                result = DOWNLOADS.force_steam_workshop_download(
                    "https://steamcommunity.com/sharedfiles/filedetails/?id=42",
                    root / "library", 1080,
                )
            details.assert_not_called()
            self.assertEqual(result.source, "local")

    def test_reimport_refreshes_changed_media_with_same_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root / "item"
            item.mkdir()
            media = item / "movie.mp4"
            media.write_bytes(b"old video")
            imported = DOWNLOADS.import_workshop_item(item, root / "library", "42")
            media.write_bytes(b"new video")
            DOWNLOADS.import_workshop_item(item, root / "library", "42")
            self.assertEqual(imported.read_bytes(), b"new video")

    def test_preview_is_never_imported_when_workshop_media_is_not_exportable(self):
        details = {
            "publishedfileid": "42", "title": "Scene", "file_url": "",
            "preview_url": "https://cdn.example/preview.jpg",
        }
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(DOWNLOADS, "find_workshop_item", return_value=None), \
                mock.patch.object(DOWNLOADS, "steam_file_details", return_value=details), \
                mock.patch.object(DOWNLOADS.shutil, "which", return_value=None), \
                mock.patch.object(DOWNLOADS, "media_dimensions", return_value=(1920, 1080)), \
                mock.patch.object(DOWNLOADS, "_download") as download:
            result = DOWNLOADS.force_steam_workshop_download(
                "https://steamcommunity.com/sharedfiles/filedetails/?id=42",
                Path(directory), 2160,
            )
        self.assertIsNone(result.path)
        download.assert_not_called()
        self.assertEqual(result.source, "preview")
        self.assertIn("aperçu", result.message)

    def test_tiny_steam_thumbnail_is_rejected(self):
        details = {
            "publishedfileid": "42", "title": "Scene", "file_url": "",
            "preview_url": "https://cdn.example/preview.gif",
        }
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(DOWNLOADS, "find_workshop_item", return_value=None), \
                mock.patch.object(DOWNLOADS, "steam_file_details", return_value=details), \
                mock.patch.object(DOWNLOADS.shutil, "which", return_value=None), \
                mock.patch.object(DOWNLOADS, "media_dimensions", return_value=(224, 224)), \
                mock.patch.object(DOWNLOADS, "_download") as download:
            result = DOWNLOADS.force_steam_workshop_download(
                "https://steamcommunity.com/sharedfiles/filedetails/?id=42",
                Path(directory), 1080,
            )
        download.assert_not_called()
        self.assertIsNone(result.path)
        self.assertIn("aperçu", result.message)


if __name__ == "__main__":
    unittest.main()
