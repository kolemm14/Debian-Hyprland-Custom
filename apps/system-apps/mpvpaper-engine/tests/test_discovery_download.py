from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.discovery_download import DownloadCancelled, DiscoveryDownloader  # noqa: E402


class DiscoveryDownloadTests(unittest.TestCase):
    def test_wallpapercave_wallpaper_page_resolves_og_image_and_preload(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'''<html><head>
                  <meta property="og:image" content="https://wallpapercave.com/wp/wp11941670.jpg">
                  <link rel="preload" as="image" href="/wp/wp11941670.jpg">
                </head><body><img src="/w200/wp7310062.png"></body></html>'''

        downloader = DiscoveryDownloader(Path("/tmp/mpvpaper-discovery-test"))
        with mock.patch("mpvpaper_engine.discovery_download.urlopen", return_value=Response()):
            media_uri = downloader._page_media("https://wallpapercave.com/w/wp11941670", 1080)
        self.assertEqual(media_uri, "https://wallpapercave.com/wp/wp11941670.jpg")

    def test_direct_download_cancellation_removes_partial_file(self):
        class Response:
            headers = {"Content-Length": "8"}

            def __init__(self):
                self.closed = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

            def read(self, _size):
                return b"payload!"

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = Response()
            event = threading.Event()
            cancel_callback = []
            downloader = DiscoveryDownloader(root)
            with mock.patch("mpvpaper_engine.discovery_download.urlopen", return_value=response):
                with self.assertRaises(DownloadCancelled):
                    downloader._direct(
                        "https://example.test/wallpaper.jpg", "wallpaper", ".jpg",
                        cancel_event=event,
                        progress_callback=lambda _downloaded, _total: event.set(),
                        cancel_callback=cancel_callback.append,
                    )
            self.assertTrue(response.closed)
            self.assertEqual(cancel_callback, [response.close])
            self.assertEqual(list(root.iterdir()), [])

    def test_direct_video_download_applies_selected_height(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "wallpaper.mp4"
            video.write_bytes(b"source")
            downloader = DiscoveryDownloader(root)
            with mock.patch.object(downloader, "profile", return_value=object()), \
                    mock.patch.object(downloader, "_direct", return_value=video), \
                    mock.patch("mpvpaper_engine.discovery_download.adapt_video_to_height",
                               return_value=video) as adapt, \
                    mock.patch("mpvpaper_engine.discovery_download.media_dimensions",
                               return_value=(640, 360)):
                result = downloader.download("https://example.test/wallpaper.mp4", "wallpaper", 360)
            adapt.assert_called_once_with(video, 360)
            self.assertEqual(result.path, video)
            self.assertIn("360p", result.message)

    def test_direct_download_fails_instead_of_claiming_unverified_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "wallpaper.mp4"
            video.write_bytes(b"source")
            downloader = DiscoveryDownloader(root)
            with mock.patch.object(downloader, "profile", return_value=object()), \
                    mock.patch.object(downloader, "_direct", return_value=video), \
                    mock.patch("mpvpaper_engine.discovery_download.adapt_video_to_height",
                               return_value=video), \
                    mock.patch("mpvpaper_engine.discovery_download.media_dimensions",
                               return_value=(1920, 1080)):
                result = downloader.download("https://example.test/wallpaper.mp4", "wallpaper", 360)
            self.assertIsNone(result.path)
            self.assertEqual(result.source, "quality")

    def test_ytdlp_output_is_checked_against_requested_height(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"over-height")
            downloader = DiscoveryDownloader(Path(directory))
            with mock.patch("mpvpaper_engine.discovery_download.youtube_download_command",
                            return_value=["yt-dlp"]), \
                    mock.patch("mpvpaper_engine.discovery_download.subprocess.run",
                               return_value=subprocess.CompletedProcess(
                                   ["yt-dlp"], 0, stdout=f"{video}\n", stderr="")), \
                    mock.patch("mpvpaper_engine.discovery_download.media_dimensions",
                               return_value=(1920, 1080)):
                result = downloader._yt_dlp("https://youtube.test/video", "video", 720)
            self.assertIsNone(result.path)
            self.assertEqual(result.source, "quality")
            self.assertFalse(video.exists())

    def test_youtube_uses_the_original_known_working_strategy(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch("shutil.which", return_value="/bin/yt-dlp"), \
                mock.patch("subprocess.run", return_value=subprocess.CompletedProcess(
                    [], 1, stdout="", stderr="test failure"
                )) as run:
            downloader = DiscoveryDownloader(Path(directory))
            downloader._yt_dlp(
                "https://www.youtube.com/watch?v=MtJTIuCKzLc", "Video", 1080
            )
        command = run.call_args.args[0]
        self.assertNotIn("--ignore-config", command)
        self.assertNotIn("--extractor-args", command)
        self.assertIn("bv*[height<=1080]+ba/b[height<=1080]", command)


if __name__ == "__main__":
    unittest.main()
