"""Baseline path checks for the staged repository architecture migration.

Run from the repository root with:
    python3 -m unittest tests/test_architecture_migration_paths.py

These checks intentionally validate the legacy layout first. They protect
existing install entry points while each application is migrated separately.
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
            "config/mpvpaper-engine",
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
