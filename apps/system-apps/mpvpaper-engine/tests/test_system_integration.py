import unittest
from pathlib import Path
from mpvpaper_engine.system_integration import (
    detect_environment,
    HyprlandAdapter,
    GnomeAdapter,
    KdeAdapter,
    UnsupportedAdapter,
    get_adapter,
    UnsupportedEnvironmentError,
)


class TestSystemIntegration(unittest.TestCase):
    def test_detect_hyprland(self):
        info = detect_environment(
            environ={"XDG_CURRENT_DESKTOP": "Hyprland", "HYPRLAND_INSTANCE_SIGNATURE": "dummy"},
            which=lambda cmd: "/usr/bin/" + cmd if cmd in {"hyprlock", "hypridle"} else None,
        )
        self.assertEqual(info.desktop, "Hyprland")
        self.assertTrue(info.lock_supported)
        self.assertTrue(info.screensaver_supported)
        self.assertEqual(info.detected_lock_tool, "hyprlock")
        self.assertEqual(info.detected_idle_tool, "hypridle")

    def test_detect_gnome(self):
        info = detect_environment(
            environ={"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"},
            which=lambda cmd: "/usr/bin/" + cmd if cmd == "gsettings" else None,
        )
        self.assertEqual(info.desktop, "GNOME")
        self.assertTrue(info.lock_supported)
        self.assertTrue(info.screensaver_supported)

    def test_detect_kde(self):
        info = detect_environment(
            environ={"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland"},
            which=lambda cmd: "/usr/bin/" + cmd if cmd == "kwriteconfig6" else None,
        )
        self.assertEqual(info.desktop, "KDE Plasma")
        self.assertTrue(info.lock_supported)

    def test_hyprland_adapter_preview(self):
        adapter = HyprlandAdapter()
        # Use an existing file like this test file
        test_file = str(Path(__file__).resolve())
        preview = adapter.apply_lockscreen(test_file, preview_only=True)
        self.assertTrue(preview["ok"])
        self.assertTrue(preview["preview_only"])
        self.assertIn("hyprlock", preview["generated_config"])
        self.assertEqual(preview["adapter"], "Hyprland")

        idle_prev = adapter.apply_screensaver(test_file, idle_delay_seconds=180, preview_only=True)
        self.assertTrue(idle_prev["ok"])
        self.assertIn("timeout = 180", idle_prev["generated_config"])

    def test_unsupported_adapter(self):
        adapter = UnsupportedAdapter("XFCE")
        caps = adapter.get_capabilities()
        self.assertFalse(caps["lockscreen"]["supported"])
        self.assertFalse(caps["screensaver"]["supported"])
        with self.assertRaises(UnsupportedEnvironmentError):
            adapter.apply_lockscreen("/any/path")
        with self.assertRaises(UnsupportedEnvironmentError):
            adapter.apply_screensaver("/any/path")


if __name__ == "__main__":
    unittest.main()
