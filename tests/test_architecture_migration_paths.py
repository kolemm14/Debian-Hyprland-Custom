"""Baseline path checks for the staged repository architecture migration.

Run from the repository root with:
    python3 -m unittest tests/test_architecture_migration_paths.py

These checks validate canonical application paths and preserve legacy
entry points during the staged migration.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LegacyPathCompatibilityTests(unittest.TestCase):
    def test_legacy_installers_are_preserved(self):
        expected = (
            "install-mirrorbridge.sh",
            "install-mpvpaper-engine.sh",
            "install-periphx.sh",
            "install-deblestia-bar.sh",
            "install-aurora.sh",
            "install.sh",
        )
        for relative in expected:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file(), f"Missing legacy entry point: {relative}")

    def test_application_source_directories_exist_before_migration(self):
        expected = (
            "config/mirrorbridge",
            "apps/system-apps/mirrorbridge",
            "config/mpvpaper-engine",
            "apps/system-apps/mpvpaper-engine",
            "config/v3",
            "config/waybar",
            "config/caelestia",
            "config/nova-shell",
            "manager",
            "core/update",
            "manifests",
        )
        for relative in expected:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_dir(), f"Missing legacy source directory: {relative}")


    def test_canonical_mpvpaper_application_and_manifest_paths_exist(self):
        import json
        app = ROOT / "apps/system-apps/mpvpaper-engine"
        self.assertTrue((app / "mpvpaper-engine.py").is_file())
        self.assertTrue((app / "mpvpaper_engine/paths.py").is_file())
        self.assertTrue((app / "tests/test_paths.py").is_file())
        manifest = json.loads((ROOT / "manifests/update-files.json").read_text(encoding="utf-8"))
        rules = [rule for rule in manifest["rules"] if rule.get("component") == "mpvpaper-engine"]
        self.assertTrue(rules, "MPVpaper updater rules are missing")
        self.assertTrue(all(rule["source"].startswith("apps/system-apps/mpvpaper-engine/") for rule in rules))

    def test_mpvpaper_installers_support_canonical_and_legacy_paths(self):
        installer = (ROOT / "install-mpvpaper-engine.sh").read_text(encoding="utf-8")
        easy = (ROOT / "install-mpvpaper-engine-easy.sh").read_text(encoding="utf-8")
        self.assertIn("apps/system-apps/mpvpaper-engine", installer)
        self.assertIn("config/mpvpaper-engine", installer)
        self.assertIn("apps/system-apps/mpvpaper-engine", easy)
        self.assertIn("config/mpvpaper-engine", easy)

    def test_migration_plan_documents_compatibility_requirements(self):
        plan = ROOT / "docs" / "ARCHITECTURE-MIGRATION.md"
        self.assertTrue(plan.is_file(), "Migration plan is missing")
        content = plan.read_text(encoding="utf-8")
        for phrase in (
            "compatibility wrappers",
            "sparse-checkout",
            "Updater and rollback behavior",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), content.lower())

    def test_canonical_mirrorbridge_manifest_exists(self):
        self.assertTrue((ROOT / "apps/system-apps/mirrorbridge/Cargo.toml").is_file())
        self.assertTrue((ROOT / "apps/system-apps/mirrorbridge/src/main.rs").is_file())

    def test_readme_uses_canonical_mirrorbridge_sparse_checkout_path(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("git sparse-checkout set apps/system-apps/mirrorbridge core/update manifests", readme)

    def test_primary_installers_reference_existing_source_paths(self):
        checks = {
            "install-mirrorbridge.sh": 'config/mirrorbridge',
            "install-mpvpaper-engine.sh": 'config/mpvpaper-engine',
        }
        for installer, source_path in checks.items():
            with self.subTest(installer=installer):
                content = (ROOT / installer).read_text(encoding="utf-8")
                self.assertIn(source_path, content)
                self.assertTrue((ROOT / source_path).is_dir())


if __name__ == "__main__":
    unittest.main()
