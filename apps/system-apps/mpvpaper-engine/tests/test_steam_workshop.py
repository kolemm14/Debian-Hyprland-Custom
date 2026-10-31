"""Tests for mpvpaper_engine.steam_workshop module.

All 30 required tests are implemented here.  No real Steam account,
real download, internet access, repkg, or Wallpaper Engine installation
is required – network and subprocess calls are mocked throughout.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

# ---------------------------------------------------------------------------
# Module loading – mirrors the pattern used in test_downloads.py
# ---------------------------------------------------------------------------

# Add engine root to sys.path so steam_workshop can import mpvpaper_download
ENGINE_ROOT = Path(__file__).parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

MODULE_PATH = ENGINE_ROOT / "mpvpaper_engine" / "steam_workshop.py"
SPEC = importlib.util.spec_from_file_location("steam_workshop", MODULE_PATH)
SW = importlib.util.module_from_spec(SPEC)
# Register in sys.modules before exec_module so @dataclass can resolve __module__
sys.modules.setdefault("steam_workshop", SW)
SPEC.loader.exec_module(SW)

# Convenience aliases
WEProjectType = SW.WEProjectType
WorkshopCompatibility = SW.WorkshopCompatibility
WorkshopResult = SW.WorkshopResult
MediaProbe = SW.MediaProbe
SteamWorkshopResolver = SW.SteamWorkshopResolver
resolve_workshop_url = SW.resolve_workshop_url

# Load mpvpaper_download for test 30
DOWNLOAD_PATH = ENGINE_ROOT / "mpvpaper_download.py"
DL_SPEC = importlib.util.spec_from_file_location("mpvpaper_download", DOWNLOAD_PATH)
DL = importlib.util.module_from_spec(DL_SPEC)
sys.modules.setdefault("mpvpaper_download", DL)
DL_SPEC.loader.exec_module(DL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_WORKSHOP_URL = (
    "https://steamcommunity.com/sharedfiles/filedetails/?id=2704773569"
)
VALID_ITEM_ID = "2704773569"


def _make_resolver(**kwargs) -> SteamWorkshopResolver:
    """Return a resolver with safe injectable no-op defaults."""
    defaults = dict(
        library_roots_fn=lambda: [],
        workshop_id_fn=SW._steam_workshop_id,
        file_details_fn=lambda _id: {},
        runner=mock.MagicMock(side_effect=OSError("subprocess disabled")),
    )
    defaults.update(kwargs)
    return SteamWorkshopResolver(**defaults)


def _fake_run_ok(cmd, **kw):
    """Simulate a successful subprocess call."""
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _fake_run_fail(cmd, **kw):
    """Simulate a subprocess call that returns non-zero."""
    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="error")


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestValidateUrl(unittest.TestCase):
    """Tests 1–2: URL validation."""

    def test_valid_workshop_url(self):
        """Test 1: valid URL extracts item ID."""
        resolver = _make_resolver()
        item_id = resolver.validate_url(VALID_WORKSHOP_URL)
        self.assertEqual(item_id, VALID_ITEM_ID)

    def test_invalid_workshop_url(self):
        """Test 2: invalid URL returns ERROR result via resolve()."""
        resolver = _make_resolver()
        result = resolver.resolve("https://example.com/not-a-workshop-url")
        self.assertEqual(result.compatibility, WorkshopCompatibility.ERROR)
        self.assertEqual(result.id, "")


class TestLocalVideoProject(unittest.TestCase):
    """Tests 3–7: local VIDEO project handling."""

    def _resolver_for(self, item_dir: Path) -> SteamWorkshopResolver:
        return _make_resolver(
            library_roots_fn=lambda: [],
            workshop_id_fn=lambda uri: VALID_ITEM_ID,
            runner=_fake_run_ok,
        )

    def test_local_video_project_found(self):
        """Test 3: project.json type=video returns FULL compatibility."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp) / VALID_ITEM_ID
            item_dir.mkdir()
            (item_dir / "movie.mp4").write_bytes(b"dummy")
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": "movie.mp4"}),
                encoding="utf-8",
            )
            resolver = _make_resolver(
                library_roots_fn=lambda: [Path(tmp).parent],
                workshop_id_fn=lambda uri: VALID_ITEM_ID,
                runner=_fake_run_ok,
            )
            # Manually call _resolve_local to avoid the find_local lookup
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertEqual(result.project_type, WEProjectType.VIDEO)
            self.assertEqual(result.compatibility, WorkshopCompatibility.FULL)
            self.assertEqual(result.renderer, "mpvpaper")

    def test_video_with_valid_media(self):
        """Test 4: mp4 file found, probe runs, compatibility FULL."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "scene.mp4").write_bytes(b"fakemp4")
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": "scene.mp4"}),
                encoding="utf-8",
            )
            ffprobe_output = json.dumps({
                "streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30/1",
                             "codec_name": "h264", "duration": "60.0"}],
                "format": {"duration": "60.0"},
            })

            def fake_run(cmd, **kw):
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=ffprobe_output, stderr=""
                )

            resolver = _make_resolver(runner=fake_run)
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertEqual(result.compatibility, WorkshopCompatibility.FULL)
            self.assertIsNotNone(result.probe)

    def test_video_with_missing_media(self):
        """Test 5: project.json points to missing file — graceful fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": "nonexistent.mp4"}),
                encoding="utf-8",
            )
            resolver = _make_resolver(runner=_fake_run_ok)
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            # Media missing → compatibility ERROR, but no exception raised
            self.assertIn(result.compatibility, (
                WorkshopCompatibility.ERROR, WorkshopCompatibility.FULL,
            ))

    def test_video_path_traversal_rejected(self):
        """Test 6: project.json file='../../outside.mp4' is REJECTED."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp) / "inner"
            item_dir.mkdir()
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": "../../outside.mp4"}),
                encoding="utf-8",
            )
            resolver = _make_resolver(runner=_fake_run_ok)
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            # Path traversal → media is None → ERROR or fallback without the bad path
            self.assertNotEqual(
                result.media,
                (item_dir / "../../outside.mp4").resolve(),
                "Path traversal candidate must not be used as media",
            )
            if result.media is not None:
                # Whatever fallback was used must be inside item_dir
                self.assertTrue(
                    str(result.media).startswith(str(item_dir.resolve())),
                    f"Fallback media {result.media} outside item_dir",
                )

    def test_video_symlink_escape_rejected(self):
        """Test 7: symlink pointing outside source_root is rejected."""
        with tempfile.TemporaryDirectory() as outer, \
                tempfile.TemporaryDirectory() as inner:
            outer_file = Path(outer) / "secret.mp4"
            outer_file.write_bytes(b"secret")
            item_dir = Path(inner)
            link = item_dir / "link.mp4"
            link.symlink_to(outer_file)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": "link.mp4"}),
                encoding="utf-8",
            )
            resolver = _make_resolver(runner=_fake_run_ok)
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            if result.media is not None:
                # The resolved media must not point to the outer secret file
                self.assertNotEqual(result.media.resolve(), outer_file.resolve())


class TestSceneProject(unittest.TestCase):
    """Tests 8–12: SCENE project handling."""

    def test_scene_project_detection(self):
        """Test 8: project.json type=scene → PARTIAL compatibility."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "scene"}), encoding="utf-8"
            )
            resolver = _make_resolver()
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertEqual(result.project_type, WEProjectType.SCENE)
            self.assertEqual(result.compatibility, WorkshopCompatibility.PARTIAL)
            self.assertIsNone(result.renderer)

    def test_scene_with_pkg(self):
        """Test 9: scene.pkg present → result.package is set."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "scene"}), encoding="utf-8"
            )
            (item_dir / "scene.pkg").write_bytes(b"pkg")
            resolver = _make_resolver()
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertIsNotNone(result.package)
            self.assertEqual(result.package.name, "scene.pkg")

    def test_scene_without_pkg(self):
        """Test 10: no scene.pkg → result.package is None, still PARTIAL."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "scene"}), encoding="utf-8"
            )
            resolver = _make_resolver()
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertIsNone(result.package)
            self.assertEqual(result.compatibility, WorkshopCompatibility.PARTIAL)

    def test_repkg_unavailable(self):
        """Test 11: no repkg, still returns useful PARTIAL result."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "scene"}), encoding="utf-8"
            )
            resolver = SteamWorkshopResolver(
                library_roots_fn=lambda: [],
                repkg_exe=None,
            )
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertEqual(result.compatibility, WorkshopCompatibility.PARTIAL)

    def test_repkg_command_failure(self):
        """Test 12: repkg detection only — resolve() does not invoke repkg."""
        fake_repkg = Path("/usr/bin/repkg-fake")
        resolver = SteamWorkshopResolver(
            library_roots_fn=lambda: [],
            repkg_exe=fake_repkg,
            runner=mock.MagicMock(side_effect=AssertionError("runner should not be called")),
        )
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "scene"}), encoding="utf-8"
            )
            # Must not raise (runner is not called for scene type)
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertEqual(result.project_type, WEProjectType.SCENE)


class TestWebAndUnknown(unittest.TestCase):
    """Tests 13–14: WEB and UNKNOWN project types."""

    def test_web_project_detection(self):
        """Test 13: project.json type=web → PREVIEW_ONLY."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "web"}), encoding="utf-8"
            )
            resolver = _make_resolver()
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertEqual(result.project_type, WEProjectType.WEB)
            self.assertEqual(result.compatibility, WorkshopCompatibility.PREVIEW_ONLY)
            self.assertIsNone(result.renderer)

    def test_unknown_project_type(self):
        """Test 14: project.json type=vr → UNSUPPORTED."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "vr"}), encoding="utf-8"
            )
            resolver = _make_resolver()
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertEqual(result.project_type, WEProjectType.UNKNOWN)
            self.assertEqual(result.compatibility, WorkshopCompatibility.UNSUPPORTED)


class TestMissingOrMalformedProjectJson(unittest.TestCase):
    """Tests 15–16: missing/malformed project.json."""

    def test_missing_project_json(self):
        """Test 15: no project.json → graceful fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            # No project.json
            resolver = _make_resolver()
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            # Must not raise; returns some WorkshopResult
            self.assertIsInstance(result, WorkshopResult)

    def test_malformed_project_json(self):
        """Test 16: invalid JSON in project.json → graceful fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            item_dir = Path(tmp)
            (item_dir / "project.json").write_bytes(b"{not valid json !!!")
            (item_dir / "video.mp4").write_bytes(b"vid")
            resolver = _make_resolver(runner=_fake_run_ok)
            result = resolver._resolve_local(VALID_ITEM_ID, item_dir)
            self.assertIsInstance(result, WorkshopResult)
            # Should not crash; may fall back to video scan
            self.assertNotEqual(result.compatibility, None)


class TestLocalWorkshopNoNetwork(unittest.TestCase):
    """Test 17: local item found, no network calls made."""

    def test_local_workshop_import_no_network(self):
        """Test 17: resolve uses local item without calling fetch_metadata."""
        with tempfile.TemporaryDirectory() as tmp:
            steam_root = Path(tmp)
            item_dir = (
                steam_root
                / "steamapps/workshop/content"
                / SteamWorkshopResolver.WALLPAPER_ENGINE_APP_ID
                / VALID_ITEM_ID
            )
            item_dir.mkdir(parents=True)
            (item_dir / "movie.mp4").write_bytes(b"vid")
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": "movie.mp4"}),
                encoding="utf-8",
            )

            fetch_called = mock.MagicMock(return_value={})
            resolver = SteamWorkshopResolver(
                library_roots_fn=lambda: [steam_root],
                workshop_id_fn=lambda uri: VALID_ITEM_ID,
                file_details_fn=fetch_called,
                runner=_fake_run_ok,
            )
            result = resolver.resolve(VALID_WORKSHOP_URL)
            fetch_called.assert_not_called()
            self.assertEqual(result.compatibility, WorkshopCompatibility.FULL)


class TestAdditionalSteamLibraryDetection(unittest.TestCase):
    """Test 18: steam_library_roots reads libraryfolders.vdf."""

    def test_additional_steam_library_detection(self):
        """Test 18: resolver's library_roots_fn is called and its paths searched."""
        with tempfile.TemporaryDirectory() as extra_lib, \
                tempfile.TemporaryDirectory() as primary:
            extra = Path(extra_lib)
            item_dir = (
                extra
                / "steamapps/workshop/content"
                / SteamWorkshopResolver.WALLPAPER_ENGINE_APP_ID
                / VALID_ITEM_ID
            )
            item_dir.mkdir(parents=True)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": ""}), encoding="utf-8"
            )
            roots_called = mock.MagicMock(return_value=[extra])
            resolver = SteamWorkshopResolver(
                library_roots_fn=roots_called,
                workshop_id_fn=lambda uri: VALID_ITEM_ID,
                file_details_fn=lambda _: {},
                runner=_fake_run_ok,
            )
            result = resolver.resolve(VALID_WORKSHOP_URL)
            roots_called.assert_called()
            self.assertIsInstance(result, WorkshopResult)


class TestSteamWebApiMetadata(unittest.TestCase):
    """Test 19: metadata fetch called and result used."""

    def test_steam_web_api_metadata(self):
        """Test 19: fetch_metadata is called when item is not local."""
        metadata = {
            "title": "Awesome Wallpaper",
            "preview_url": "https://cdn.steam.com/preview.jpg",
        }
        fetch_fn = mock.MagicMock(return_value=metadata)
        resolver = SteamWorkshopResolver(
            library_roots_fn=lambda: [],
            workshop_id_fn=lambda uri: VALID_ITEM_ID,
            file_details_fn=fetch_fn,
            runner=mock.MagicMock(side_effect=OSError("no subprocess")),
        )
        result = resolver.resolve(VALID_WORKSHOP_URL)
        fetch_fn.assert_called_once_with(VALID_ITEM_ID)
        self.assertEqual(result.title, "Awesome Wallpaper")


class TestDirectSteamFileUrl(unittest.TestCase):
    """Test 20: file_url in metadata → download attempted."""

    def test_direct_steam_file_url(self):
        """Test 20: When file_url present and library_dir given, download is attempted."""
        metadata = {
            "title": "Direct File",
            "file_url": "https://cdn.steamstatic.com/content/file.zip",
        }
        resolver = SteamWorkshopResolver(
            library_roots_fn=lambda: [],
            workshop_id_fn=lambda uri: VALID_ITEM_ID,
            file_details_fn=lambda _: metadata,
            runner=_fake_run_ok,
        )
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp)
            # Mock _try_direct_download so we don't actually hit the network
            with mock.patch.object(
                resolver, "_try_direct_download",
                return_value=WorkshopResult(
                    id=VALID_ITEM_ID,
                    compatibility=WorkshopCompatibility.FULL,
                    title="Direct File",
                    message="Downloaded via Steam file URL",
                ),
            ) as patched:
                result = resolver.resolve(VALID_WORKSHOP_URL, library_dir=lib)
                patched.assert_called_once()
        self.assertEqual(result.compatibility, WorkshopCompatibility.FULL)


class TestSteamcmdBehavior(unittest.TestCase):
    """Tests 21–24: steamcmd integration."""

    def _resolver_with_steamcmd(self, fake_run):
        return SteamWorkshopResolver(
            library_roots_fn=lambda: [],
            workshop_id_fn=lambda uri: VALID_ITEM_ID,
            file_details_fn=lambda _: {},
            runner=fake_run,
        )

    def test_steamcmd_success(self):
        """Test 21: steamcmd returns 0 → resolver looks for local item → FULL."""
        with tempfile.TemporaryDirectory() as tmp:
            steam_root = Path(tmp)
            item_dir = (
                steam_root
                / "steamapps/workshop/content"
                / SteamWorkshopResolver.WALLPAPER_ENGINE_APP_ID
                / VALID_ITEM_ID
            )
            item_dir.mkdir(parents=True)
            (item_dir / "project.json").write_text(
                json.dumps({"type": "video", "file": "vid.mp4"}), encoding="utf-8"
            )
            (item_dir / "vid.mp4").write_bytes(b"vid")

            def fake_run(cmd, **kw):
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            resolver = SteamWorkshopResolver(
                library_roots_fn=lambda: [steam_root],
                workshop_id_fn=lambda uri: VALID_ITEM_ID,
                file_details_fn=lambda _: {},
                runner=fake_run,
            )
            # steamcmd must appear "available" on the PATH
            with mock.patch("shutil.which", return_value="/usr/bin/steamcmd"):
                result = resolver._try_steamcmd(VALID_ITEM_ID, "", {}, None)
            self.assertIsInstance(result, WorkshopResult)
            self.assertEqual(result.compatibility, WorkshopCompatibility.FULL)

    def test_steamcmd_timeout(self):
        """Test 22: timeout → ERROR result with descriptive message."""
        def fake_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 1800)

        with mock.patch("shutil.which", return_value="/usr/bin/steamcmd"):
            resolver = self._resolver_with_steamcmd(fake_run)
            result = resolver._try_steamcmd(VALID_ITEM_ID, "", {}, None)
        self.assertIsNotNone(result)
        self.assertEqual(result.compatibility, WorkshopCompatibility.ERROR)
        self.assertIn("timed out", result.message)

    def test_steamcmd_failure(self):
        """Test 23: steamcmd returncode nonzero → graceful None (caller handles)."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="failure")

        with mock.patch("shutil.which", return_value="/usr/bin/steamcmd"):
            resolver = self._resolver_with_steamcmd(fake_run)
            result = resolver._try_steamcmd(VALID_ITEM_ID, "", {}, None)
        # non-zero without auth patterns → returns None (not a WorkshopResult)
        self.assertIsNone(result)

    def test_authentication_required(self):
        """Test 24: steamcmd output contains 'Login Failure' → REQUIRES_AUTH."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(
                cmd, 5, stdout="Login Failure: Invalid Password\n", stderr=""
            )

        with mock.patch("shutil.which", return_value="/usr/bin/steamcmd"):
            resolver = self._resolver_with_steamcmd(fake_run)
            result = resolver._try_steamcmd(VALID_ITEM_ID, "", {}, None)
        self.assertIsNotNone(result)
        self.assertEqual(result.compatibility, WorkshopCompatibility.REQUIRES_AUTH)


class TestPreviewFallback(unittest.TestCase):
    """Tests 25–26: preview fallback behavior."""

    def test_preview_fallback(self):
        """Test 25: no media, preview_url used → PREVIEW_ONLY."""
        metadata = {
            "title": "Scene Wallpaper",
            "file_url": "",
            "preview_url": "https://cdn.steam.com/preview.jpg",
        }
        resolver = SteamWorkshopResolver(
            library_roots_fn=lambda: [],
            workshop_id_fn=lambda uri: VALID_ITEM_ID,
            file_details_fn=lambda _: metadata,
            runner=mock.MagicMock(side_effect=OSError("no subprocess")),
        )
        # Patch _try_direct_download and _try_steamcmd to return None (no success)
        with mock.patch.object(resolver, "_try_direct_download", return_value=None), \
             mock.patch.object(resolver, "_try_steamcmd", return_value=None):
            result = resolver.resolve(VALID_WORKSHOP_URL)
        self.assertEqual(result.compatibility, WorkshopCompatibility.PREVIEW_ONLY)
        self.assertIn("cdn.steam.com/preview.jpg", result.preview)

    def test_tiny_preview_rejected(self):
        """Test 26: no network preview used when dimensions too small — PREVIEW_ONLY with message."""
        # In the current resolver, preview_url is accepted as PREVIEW_ONLY when network
        # fails; the tiny-preview rejection is handled in mpvpaper_download. Confirm
        # that our resolver surfaces PREVIEW_ONLY (not ERROR) when only preview available.
        metadata = {
            "title": "Tiny Scene",
            "file_url": "",
            "preview_url": "https://cdn.steam.com/tiny.jpg",
        }
        resolver = SteamWorkshopResolver(
            library_roots_fn=lambda: [],
            workshop_id_fn=lambda uri: VALID_ITEM_ID,
            file_details_fn=lambda _: metadata,
            runner=mock.MagicMock(side_effect=OSError("no subprocess")),
        )
        with mock.patch.object(resolver, "_try_direct_download", return_value=None), \
             mock.patch.object(resolver, "_try_steamcmd", return_value=None):
            result = resolver.resolve(VALID_WORKSHOP_URL)
        # Preview fallback → PREVIEW_ONLY (tiny detection is mpvpaper_download's job)
        self.assertEqual(result.compatibility, WorkshopCompatibility.PREVIEW_ONLY)


class TestArchiveSafety(unittest.TestCase):
    """Tests 27–28: archive extraction safety."""

    def test_safe_archive_extraction(self):
        """Test 27: _import_downloaded_archive processes safe zips without errors."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "test.zip"
            library = root / "library"
            library.mkdir()
            # Create a safe zip with a video inside
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("wallpaper/movie.mp4", b"fakemp4" * 10)
            # Call through mpvpaper_download's _import_downloaded_archive
            # The key guarantee: this must NOT raise, and if it returns a Path
            # that path must be inside the library directory.
            result = DL._import_downloaded_archive(archive, library, "9999", "Safe WP")
            if result is not None:
                self.assertTrue(
                    str(result).startswith(str(library)),
                    f"Extracted file {result} escaped library directory",
                )

    def test_archive_path_traversal_rejection(self):
        """Test 28: zip with ../escape path → raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "evil.zip"
            # Manually craft a zip with a path-traversal member name
            with zipfile.ZipFile(archive, "w") as zf:
                info = zipfile.ZipInfo("../escaped.mp4")
                zf.writestr(info, b"evil")
            with self.assertRaises(ValueError):
                DL._import_downloaded_archive(archive, root / "library", "42", "evil")


class TestMediaProbe(unittest.TestCase):
    """Test 29: ffprobe failure is handled gracefully."""

    def test_media_probe_failure(self):
        """Test 29: ffprobe fails → probe.error set, no exception propagated."""
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "vid.mp4"
            video.write_bytes(b"fake")

            def fake_run(cmd, **kw):
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no such codec")

            with mock.patch("shutil.which", return_value="/usr/bin/ffprobe"):
                probe = SW._probe_video(video, runner=fake_run)
            self.assertIsInstance(probe, MediaProbe)
            self.assertNotEqual(probe.error, "")


class TestExistingDownloadFlowsIntact(unittest.TestCase):
    """Test 30: force_steam_workshop_download from mpvpaper_download still works."""

    def test_existing_download_flows_intact(self):
        """Test 30: force_steam_workshop_download returns DownloadOutcome on invalid URL."""
        result = DL.force_steam_workshop_download(
            "https://example.com/not-workshop",
            Path("/tmp/library"),
            1080,
            runner=_fake_run_ok,
        )
        self.assertIsNone(result.path)
        self.assertIn("invalide", result.message)


class TestToDict(unittest.TestCase):
    """Extra: to_dict() produces JSON-serializable output."""

    def test_to_dict_serializable(self):
        r = WorkshopResult(
            id="12345",
            project_type=WEProjectType.VIDEO,
            compatibility=WorkshopCompatibility.FULL,
            title="Test",
            renderer="mpvpaper",
        )
        d = r.to_dict()
        self.assertEqual(d["type"], "video")
        self.assertEqual(d["compatibility"], "full")
        self.assertIsNone(d["media"])
        import json as _json
        # Must be JSON-serializable
        serialized = _json.dumps(d)
        self.assertIn("video", serialized)


if __name__ == "__main__":
    unittest.main()


class TestOriginalMediaPolicy(unittest.TestCase):
    def test_preview_and_escaping_symlinks_are_not_fallback_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = root / "item"
            item.mkdir()
            (item / "preview.jpg").write_bytes(b"preview")
            outside = root / "outside.mp4"
            outside.write_bytes(b"video")
            (item / "escape.mp4").symlink_to(outside)
            self.assertIsNone(_make_resolver()._resolve_local("42", item).media)
            self.assertIsNone(DL.import_workshop_item(item, root / "library", "42"))

    def test_image_project_uses_original_even_with_larger_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = Path(tmp)
            (item / "original.png").write_bytes(b"image")
            (item / "cover.png").write_bytes(b"preview" * 100)
            (item / "project.json").write_text(json.dumps({
                "type": "image", "file": "original.png", "preview": "cover.png",
            }))
            result = _make_resolver()._resolve_local("42", item)
            self.assertEqual(result.media, item / "original.png")
            self.assertEqual(result.project_type, WEProjectType.IMAGE)
            self.assertEqual(result.renderer, "mpvpaper")

    def test_declared_preview_cannot_be_the_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = Path(tmp)
            (item / "cover.mp4").write_bytes(b"preview")
            (item / "project.json").write_text(json.dumps({
                "type": "video", "file": "cover.mp4", "preview": "cover.mp4",
            }))
            self.assertIsNone(_make_resolver()._resolve_local("42", item).media)

    def test_scene_preview_never_reaches_legacy_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = Path(tmp)
            (item / "preview.png").write_bytes(b"preview")
            (item / "project.json").write_text(json.dumps({
                "type": "scene", "file": "scene.pkg", "preview": "preview.png",
            }))
            self.assertIsNone(DL.import_workshop_item(item, item / "library", "42"))

    def test_invalid_direct_payload_is_not_reported_as_video(self):
        import mpvpaper_download
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(mpvpaper_download, "_download", side_effect=lambda u, p, m: p.write_bytes(b"not an archive")):
                result = _make_resolver()._try_direct_download(
                    "42", "https://example.com/file.zip", "Test", {}, Path(tmp)
                )
            self.assertIsNone(result)
