from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))
from mpvpaper_engine.steam_local import installed_project, parse_manifest
from mpvpaper_download import steam_library_roots


class SteamLocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workshop = self.root / 'steamapps/workshop'
        self.project = self.workshop / 'content/431960/123'
        self.project.mkdir(parents=True)
        self.manifest = self.workshop / 'appworkshop_431960.acf'
        self.write_manifest()
        self.write_project('video', 'movie.mp4')

    def write_manifest(self, installed='42', latest='42'):
        self.manifest.write_text('"AppWorkshop" { "appid" "431960" '
            '"WorkshopItemsInstalled" { "123" { "manifest" "' + installed + '" } } '
            '"WorkshopItemDetails" { "123" { "latest_manifest" "' + latest + '" } } }')

    def write_project(self, kind, entry):
        (self.project / entry).write_bytes(b'original')
        (self.project / 'project.json').write_text(json.dumps({'type':kind,'file':entry,'preview':'preview.jpg'}))
        (self.project / 'preview.jpg').write_bytes(b'preview')

    def test_video_uses_original_media(self):
        item = installed_project('https://steamcommunity.com/sharedfiles/filedetails/?id=123', [self.root])
        self.assertEqual(item.media, self.project / 'movie.mp4')
        self.assertEqual(item.kind, 'video')

    def test_scene_and_web_preserve_directory(self):
        for kind, entry in [('scene','scene.pkg'),('web','index.html')]:
            self.write_project(kind, entry)
            item = installed_project('123', [self.root])
            self.assertEqual(item.path, self.project)
            self.assertIsNone(item.media)
            self.assertEqual(item.kind, kind)

    def test_missing_manifest_does_not_import_visible_files(self):
        self.manifest.unlink()
        self.assertIsNone(installed_project('123', [self.root]))

    def test_pending_update_is_not_imported(self):
        self.write_manifest(latest='43')
        self.assertIsNone(installed_project('123', [self.root]))

    def test_download_in_progress_is_not_imported(self):
        (self.workshop / 'downloads/431960/123').mkdir(parents=True)
        self.assertIsNone(installed_project('123', [self.root]))

    def test_preview_and_missing_entry_are_rejected(self):
        for entry in ['preview.jpg', 'absent.mp4']:
            (self.project / 'project.json').write_text(json.dumps({'type':'image','file':entry,'preview':'preview.jpg'}))
            self.assertIsNone(installed_project('123', [self.root]))

    def test_truncated_manifest_is_not_ready(self):
        self.manifest.write_text('"AppWorkshop" { "WorkshopItemsInstalled" {')
        self.assertIsNone(installed_project('123', [self.root]))
        with self.assertRaises(ValueError):
            parse_manifest('"key"')

    def test_invalid_uri(self):
        with self.assertRaises(ValueError):
            installed_project('https://example.com/?id=123', [self.root])

    def test_flatpak_and_external_library_discovery(self):
        root = self.root / '.var/app/com.valvesoftware.Steam/.local/share/Steam'
        (root / 'steamapps').mkdir(parents=True)
        external = self.root / 'External Library'; external.mkdir()
        (root / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "' + str(external) + '" } }')
        roots = steam_library_roots(self.root)
        self.assertIn(root, roots)
        self.assertIn(external, roots)


if __name__ == '__main__':
    unittest.main()
