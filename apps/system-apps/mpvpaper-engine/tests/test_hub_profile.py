"""Hub contract tests with the Engine's actual SQLite schema, without GTK."""
import ast
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mpvpaper_engine.hub_profile import TOKEN_ALIASES, build_profile, hub_url
from mpvpaper_engine.paths import EnginePaths

# Reuse the production schema without importing media probing dependencies.
tree = ast.parse((ROOT / "mpvpaper_engine/library.py").read_text())
SCHEMA = next(ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and any(
                  isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets))


class HubProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = EnginePaths.from_environment({}, home=Path(self.temp.name), uid=123)

    def database(self):
        self.paths.data_home.mkdir(parents=True)
        db = sqlite3.connect(self.paths.library_db)
        db.executescript(SCHEMA)
        self.addCleanup(db.close)
        return db

    def add(self, db, title, favorite=0, usage=0, missing=0):
        row = db.execute("""INSERT INTO wallpapers
            (path,title,type,file_size,mtime_ns,fingerprint,date_added,favorite,usage_count,missing)
            VALUES (?,?, 'video',0,0,'fixture','2026-01-01',?,?,?)""",
            ("/home/private-person/secret-" + title + ".mp4", title, favorite, usage, missing))
        db.commit()
        return row.lastrowid

    def test_no_library_does_not_create_one(self):
        self.assertEqual(build_profile(self.paths)["preferences"], [])
        self.assertFalse(self.paths.data_home.exists())

    def test_favorites_and_usage_weight_but_paths_do_not_leave(self):
        db = self.database()
        self.add(db, "forest")
        self.add(db, "anime", favorite=1)
        self.add(db, "space", usage=31)
        before = self.paths.library_db.read_bytes()
        profile = build_profile(self.paths)
        weights = {p["tag"]:p["weight"] for p in profile["preferences"]}
        self.assertGreater(weights["anime"], weights["nature"])
        self.assertGreater(weights["espace"], weights["nature"])
        self.assertEqual(before, self.paths.library_db.read_bytes())
        text = json.dumps(profile)
        for private in ["private-person", "/home", "secret-", "usage_count", "path", "title"]:
            self.assertNotIn(private, text)
        self.assertEqual(set(profile), {"version", "source", "preferences"})

    def test_tags_are_recognized_locally_but_unknowns_and_missing_are_omitted(self):
        db = self.database()
        ident = self.add(db, "personal-document")
        self.add(db, "snowy", favorite=1, missing=1)
        db.execute("INSERT INTO tags(id,name) VALUES (1,'Nature'),(2,'private-employer')")
        db.execute("INSERT INTO wallpaper_tags(wallpaper_id,tag_id) VALUES (?,1),(?,2)", (ident,ident))
        db.commit()
        self.assertEqual(build_profile(self.paths)["preferences"], [{"tag":"nature","weight":1.0}])

    def test_no_known_theme_returns_general_profile(self):
        db = self.database(); self.add(db, "my-secret-project")
        self.assertEqual(build_profile(self.paths)["preferences"], [])

    def test_bounded_vocabulary_and_weights(self):
        db = self.database(); self.add(db, " ".join(TOKEN_ALIASES), favorite=1, usage=100000000)
        preferences = build_profile(self.paths)["preferences"]
        self.assertLessEqual(len(preferences), 16)
        self.assertTrue(all(p["tag"] in TOKEN_ALIASES and 0.01 <= p["weight"] <= 1 for p in preferences))
        self.assertLess(len(json.dumps(build_profile(self.paths))), 4096)

    def test_url_profile_is_fragment_only_and_round_trips(self):
        profile = {"version":1,"source":"mpvpaper-engine","preferences":[{"tag":"your name","weight":1}]}
        parts = urlsplit(hub_url(profile))
        self.assertEqual(parts.scheme, "https"); self.assertEqual(parts.query, "")
        self.assertEqual(json.loads(unquote(parts.fragment.removeprefix("mpvp_profile="))), profile)

    def test_incompatible_database_is_clear_error(self):
        self.paths.data_home.mkdir(parents=True)
        with sqlite3.connect(self.paths.library_db):
            pass
        with self.assertRaisesRegex(ValueError, "bibliothèque Engine"):
            build_profile(self.paths)

    def test_cli_exports_actual_library_without_service(self):
        db = self.database(); self.add(db, "Mountain Lake", favorite=1, usage=31)
        environment = {**os.environ, "XDG_DATA_HOME": str(self.paths.data_home.parent)}
        result = subprocess.run([sys.executable, str(ROOT / "mpvpaper-enginectl.py"), "hub", "--json"],
                                env=environment, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), build_profile(self.paths))

    def test_cli_empty_profile_without_creating_library(self):
        environment = {**os.environ, "XDG_DATA_HOME": str(self.paths.data_home.parent)}
        result = subprocess.run([sys.executable, str(ROOT / "mpvpaper-enginectl.py"), "hub", "--json"],
                                env=environment, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["preferences"], [])
        self.assertFalse(self.paths.data_home.exists())


if __name__ == "__main__":
    unittest.main()
