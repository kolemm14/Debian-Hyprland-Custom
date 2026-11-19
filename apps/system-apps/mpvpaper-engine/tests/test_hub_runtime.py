"""Private loopback runtime helpers for the embedded Hub module."""
import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mpvpaper_engine.hub_runtime import (
    available_loopback_port, hub_embedded_url, locate_hub_directory,
    production_hub_command,
)


class HubRuntimeTests(unittest.TestCase):
    def test_embedded_url_is_loopback_and_starts_in_engine_mode(self):
        self.assertEqual(hub_embedded_url(52341), "http://127.0.0.1:52341/?embedded=engine")
        for port in (0, -1, 65536, "5173"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                hub_embedded_url(port)

    def test_port_picker_returns_valid_ephemeral_port(self):
        port = available_loopback_port()
        self.assertGreaterEqual(port, 1)
        self.assertLessEqual(port, 65535)

    def test_locator_requires_a_complete_hub_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = root / "app"
            package = engine / "mpvpaper_engine"
            package.mkdir(parents=True)
            hub = engine / "hub"
            (hub / "scripts").mkdir(parents=True)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / "scripts" / "run-framework.mjs").write_text("", encoding="utf-8")
            self.assertEqual(locate_hub_directory(package / "gui.py", root / "home"), hub)
            (hub / "scripts" / "run-framework.mjs").unlink()
            self.assertIsNone(locate_hub_directory(package / "gui.py", root / "home"))

    def test_production_command_is_loopback_only_and_uses_prebuilt_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "scripts/local-hub-server.mjs",
                "scripts/sites-env.mjs",
                "node_modules/wrangler/bin/wrangler.js",
                "dist/server/wrangler.json",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("", encoding="utf-8")
            command = production_hub_command(root, "/usr/bin/node", 52341, root / "state")
            self.assertIn("52341", command)
            self.assertIn("local-hub-server.mjs", command[1])
            self.assertNotIn("scripts/run-framework.mjs", command)
            with self.assertRaises(ValueError):
                production_hub_command(root, "/usr/bin/node", 0, root / "state")


if __name__ == "__main__":
    unittest.main()
