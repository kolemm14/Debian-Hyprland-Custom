from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.theme_sync import (  # noqa: E402
    Palette, ThemeSync, extract_palette, palette_from_rgb,
)


def paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class ThemeSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = paths(self.temp.name)
        self.media = Path(self.temp.name) / "wall.mp4"
        self.media.write_bytes(b"video")

    def tearDown(self):
        self.temp.cleanup()

    def test_palette_quantizes_and_selects_contrast(self):
        palette = palette_from_rgb(bytes([0, 0, 0, 255, 255, 255] * 4), self.media, 1)
        self.assertEqual(palette.background, "#000000")
        self.assertEqual(palette.foreground, "#f8f8f8")

    def test_palette_keeps_colored_accent_among_dark_pixels(self):
        data = bytes([8, 8, 8] * 800 + [16, 16, 16] * 100 + [32, 160, 224] * 100)
        palette = palette_from_rgb(data, self.media, 1)
        red, green, blue = (int(palette.colors[0][i:i+2], 16) for i in (1, 3, 5))
        self.assertGreater(blue, red + 60)
        self.assertGreater(green, red)
        self.assertGreater(min(int(palette.foreground[i:i+2], 16) for i in (1, 3, 5)), 160)

    def test_monochrome_wallpaper_gets_readable_text(self):
        palette = palette_from_rgb(bytes([96, 96, 96] * 100), self.media, 1)
        self.assertNotEqual(palette.foreground, palette.background)
        self.assertGreater(int(palette.foreground[1:3], 16), 200)
        self.assertLessEqual(int(palette.background[1:3], 16), 32)

    def test_extract_uses_one_frame_for_image_and_bounds_video_to_four(self):
        image = Path(self.temp.name) / "still.png"
        image.write_bytes(b"image")
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, b"\0\0\0" * 1024, b""))
        self.assertEqual(extract_palette(image, frames=4, runner=runner).frames, 1)
        self.assertIn("1", runner.call_args.args[0])
        extract_palette(self.media, frames=99, runner=runner)
        self.assertIn("4", runner.call_args.args[0])

    def test_extract_accepts_extensionless_video_wallpaper(self):
        current = Path(self.temp.name) / ".wallpaper_current"
        current.write_bytes(b"video")
        runner = mock.Mock(side_effect=[
            subprocess.CompletedProcess([], 0, "video\n", ""),
            subprocess.CompletedProcess([], 0, b"\0\0\0" * 4096, b""),
        ])

        palette = extract_palette(current, runner=runner)

        self.assertEqual(palette.frames, 4)
        self.assertEqual(runner.call_count, 2)

    def test_off_mode_has_no_side_effect(self):
        sync = ThemeSync(self.paths, extractor=mock.Mock(), runner=mock.Mock())
        self.assertFalse(sync.apply(self.media, mode="off").applied)
        sync.extractor.assert_not_called()

    def test_integrations_are_failure_isolated_and_state_is_written(self):
        palette = Palette(("#101010", "#eeeeee"), "#eeeeee", "#101010", str(self.media), 4)
        runner = mock.Mock(side_effect=[
            subprocess.CompletedProcess([], 1, "", "no wallust"),
            OSError("no waybar"),
            subprocess.CompletedProcess([], 0, "", ""),
        ])
        result = ThemeSync(
            self.paths, extractor=lambda _source, frames: palette, runner=runner
        ).apply(self.media)
        self.assertTrue(result.applied)
        self.assertTrue(result.integrations["wallust"].startswith("failed:"))
        self.assertIn("failed:", result.integrations["waybar"])
        self.assertEqual(result.integrations["nova"], "ok")
        self.assertTrue(self.paths.palette_dir.joinpath("current.json").is_file())

    def test_waybar_file_is_updated_before_reload(self):
        palette = Palette(("#204060", "#d0d0d0"), "#d0d0d0", "#101010", str(self.media), 4)
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        result = ThemeSync(
            self.paths, extractor=lambda _source, frames: palette, runner=runner
        ).apply(self.media)
        self.assertTrue(result.applied)
        panel = self.paths.config_home.parent / "waybar" / "panel-colors.css"
        self.assertIn("@define-color accent #204060;", panel.read_text())
        calls = [call.args[0][0] for call in runner.call_args_list]
        self.assertEqual(calls, ["wallust", "pkill", "qs"])

    def test_same_wallpaper_is_guarded_across_instances(self):
        palette = Palette(("#000000",), "#000000", "#000000", str(self.media), 2)
        first = ThemeSync(self.paths, extractor=lambda _source, frames: palette,
                          runner=lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""))
        self.assertTrue(first.apply(self.media, profile="eco").applied)
        second = ThemeSync(self.paths, extractor=mock.Mock(), runner=mock.Mock())
        result = second.apply(self.media)
        self.assertFalse(result.applied)
        second.extractor.assert_not_called()

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            ThemeSync(self.paths).apply(self.media, mode="sometimes")

    def test_desktop_sync_and_real_waybar_reload(self):
        script = self.paths.config_home.parent / "hypr/UserScripts/DeblestiaSystemThemeSync.sh"
        script.parent.mkdir(parents=True)
        script.write_text("#!/bin/sh\n")
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        palette = Palette(("#204060",), "#eeeeee", "#101010", str(self.media), 4)
        sync = ThemeSync(self.paths, extractor=lambda *a, **kw: palette, runner=runner)
        result = sync.apply(self.media)
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertIn(["pkill", "-SIGUSR2", "-x", "waybar"], commands)
        self.assertIn(["bash", str(script), "--no-waybar-reload"], commands)
        self.assertEqual(result.integrations["desktop"], "ok")
        self.assertTrue(sync.apply(self.media, force=True).applied)

    def test_wallust_receives_sampled_image_instead_of_video(self):
        palette = Palette(("#204060", "#8090a0"), "#eeeeee", "#101010", str(self.media), 4)
        files = []
        def runner(command, **kwargs):
            if command[0] == "wallust":
                sample = Path(command[-1]); files.append(sample)
                self.assertEqual(sample.suffix, ".ppm")
                self.assertTrue(sample.read_bytes().startswith(b"P6\n64 32\n255\n"))
            return subprocess.CompletedProcess(command, 0, "", "")
        ThemeSync(self.paths, extractor=lambda *a, **kw: palette, runner=runner).apply(self.media)
        self.assertEqual(len(files), 1)
        self.assertFalse(files[0].exists())


if __name__ == "__main__":
    unittest.main()
