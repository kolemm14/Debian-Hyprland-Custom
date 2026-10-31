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
            "apps/system-apps/periphx",
            "config/waybar",
            "config/caelestia",
            "config/nova-shell",
            "manager",
            "apps/system-tools/custom-manager",
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


    def test_canonical_periphx_sources_and_manifest_exist(self):
        import json
        app = ROOT / "apps/system-apps/periphx"
        self.assertTrue((app / "device-center.py").is_file())
        self.assertTrue((app / "periphx.py").is_file())
        self.assertTrue((app / "pericored/Cargo.toml").is_file())
        self.assertTrue((app / "tests/test_periphx_cli.py").is_file())
        manifest = json.loads((ROOT / "manifests/update-files.json").read_text(encoding="utf-8"))
        rules = [rule for rule in manifest["rules"] if rule.get("component") == "periphx"]
        self.assertTrue(rules, "PeriphX updater rules are missing")
        self.assertTrue(all(rule["source"].startswith("apps/system-apps/periphx/") for rule in rules))

    def test_periphx_installer_supports_canonical_and_legacy_paths(self):
        installer = (ROOT / "install-v3.sh").read_text(encoding="utf-8")
        self.assertIn("apps/system-apps/periphx", installer)
        self.assertIn("config/v3", installer)


    def test_custom_manager_canonical_files_and_legacy_fallback_exist(self):
        app = ROOT / "apps/system-tools/custom-manager"
        self.assertTrue((app / "Makefile").is_file())
        self.assertTrue((app / "src/paths.c").is_file())
        self.assertTrue((app / "data/components.ini").is_file())
        self.assertTrue((app / "scripts/update-wrapper.sh").is_file())
        paths_source = (app / "src/paths.c").read_text(encoding="utf-8")
        self.assertIn('"apps", "system-tools", "custom-manager"', paths_source)
        self.assertIn('"manager", "data", "components.ini"', paths_source)
        cli_source = (app / "src/cli.c").read_text(encoding="utf-8")
        self.assertIn('"apps", "system-tools", "custom-manager", "scripts", "update-wrapper.sh"', cli_source)


    def test_canonical_waybar_variants_and_shared_resources_exist(self):
        variants = {
            "deblestia-bar": ("[Deblestia] Bar", "[Deblestia] Bar.css"),
            "deblestia-nova-lite": ("[Deblestia] Nova", "[Deblestia] Nova.css"),
            "deblestia-nova-2": ("[Deblestia] Nova 2", "[Deblestia] Nova 2.css"),
        }
        for name, (config, style) in variants.items():
            app = ROOT / "apps/waybars" / name
            with self.subTest(variant=name):
                self.assertTrue((app / "configs" / config).is_file())
                self.assertTrue((app / "styles" / style).is_file())
        shared = ROOT / "shared/waybar"
        for relative in (
            "Modules", "ModulesCustom", "ModulesWorkspaces",
            "deblestia-waybar-switch.sh", "deblestia-focus.py",
            "media-panel.py", "panel-colors.css", "icons/hyprdebian-cli.svg",
        ):
            with self.subTest(shared=relative):
                self.assertTrue((shared / relative).exists(), f"Missing shared Waybar asset: {relative}")

    def test_waybar_installer_prefers_canonical_variants_and_keeps_legacy_fallback(self):
        installer = (ROOT / "install-nova2.sh").read_text(encoding="utf-8")
        self.assertIn("apps/waybars/deblestia-bar", installer)
        self.assertIn("apps/waybars/deblestia-nova-lite", installer)
        self.assertIn("apps/waybars/deblestia-nova-2", installer)
        self.assertIn("shared/waybar", installer)
        self.assertIn('config/waybar', installer)


    def test_desktop_shell_installers_prefer_canonical_paths_with_legacy_fallback(self):
        caelestia = (ROOT / "install-v2.sh").read_text(encoding="utf-8")
        nova = (ROOT / "install-nova-shell.sh").read_text(encoding="utf-8")
        for source in ("apps/desktop-shells/caelestia-v2", "config/caelestia",
                       "shared/hyprland", "config/hypr"):
            with self.subTest(installer="caelestia", source=source):
                self.assertIn(source, caelestia)
        for source in ("apps/desktop-shells/nova-shell", "config/nova-shell",
                       "config/hypr"):
            with self.subTest(installer="nova", source=source):
                self.assertIn(source, nova)


    def test_canonical_desktop_shell_assets_and_shared_hyprland_paths_exist(self):
        caelestia = ROOT / "apps/desktop-shells/caelestia-v2"
        for relative in ("shell.json", "hyprland/caelestia-v2.conf",
                         "scripts/caelestia-v2-launch.sh",
                         "scripts/caelestia-v2-lock.sh",
                         "scripts/caelestia-v2-display-profile.sh"):
            with self.subTest(caelestia=relative):
                self.assertTrue((caelestia / relative).is_file())
        nova = ROOT / "apps/desktop-shells/nova-shell"
        for relative in ("config/debian-config.json", "patches/qt68-compat.patch",
                         "patches/mpvpaper-integration.patch",
                         "patches/hyprland-ipc-compat.patch",
                         "hyprland/deblestia-nova-shell.conf",
                         "scripts/deblestia-nova-shell-launch.sh",
                         "scripts/deblestia-nova-lock.sh"):
            with self.subTest(nova=relative):
                self.assertTrue((nova / relative).is_file())
        for relative in ("deblestia-input.conf", "deblestia-workspaces.conf",
                         "deblestia-ui.conf", "scripts/desktop-shell-mode.sh",
                         "UserScripts/WaybarWallpaperSync.sh"):
            with self.subTest(shared=relative):
                self.assertTrue((ROOT / "shared/hyprland" / relative).is_file())

    def test_desktop_shell_installers_prefer_canonical_paths_with_legacy_fallback(self):
        caelestia = (ROOT / "install-v2.sh").read_text(encoding="utf-8")
        nova = (ROOT / "install-nova-shell.sh").read_text(encoding="utf-8")
        waybar = (ROOT / "install-nova2.sh").read_text(encoding="utf-8")
        for source in ("apps/desktop-shells/caelestia-v2", "config/caelestia",
                       "shared/hyprland", "config/hypr"):
            with self.subTest(installer="caelestia", source=source):
                self.assertIn(source, caelestia)
        for source in ("apps/desktop-shells/nova-shell", "config/nova-shell",
                       "shared/hyprland", "config/hypr"):
            with self.subTest(installer="nova", source=source):
                self.assertIn(source, nova)
        self.assertIn("shared/hyprland", waybar)
        self.assertIn("config/hypr", waybar)


    def test_canonical_aurora_assets_and_legacy_installer_fallback_exist(self):
        app = ROOT / "apps/desktop-shells/aurora"
        self.assertTrue((app / "aurora").is_file())
        self.assertTrue((app / "profile.py").is_file())
        cli = (app / "aurora").read_text(encoding="utf-8")
        self.assertIn('profile_script="$app_dir/profile.py"', cli)
        installer = (ROOT / "install-aurora.sh").read_text(encoding="utf-8")
        self.assertIn("apps/desktop-shells/aurora/aurora", installer)
        self.assertIn("apps/desktop-shells/aurora/profile.py", installer)
        self.assertIn('"$repo_dir/bin/aurora"', installer)
        self.assertIn('"$repo_dir/core/aurora/profile.py"', installer)


    def test_readme_sparse_checkout_instructions_use_canonical_shell_paths(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for path in ("apps/waybars/deblestia-nova-2", "shared/waybar",
                     "apps/desktop-shells/nova-shell",
                     "apps/desktop-shells/caelestia-v2", "shared/hyprland"):
            with self.subTest(path=path):
                self.assertIn(path, readme)


    def test_shell_and_aurora_updater_manifest_sources_resolve(self):
        import json
        manifest = json.loads((ROOT / "manifests/update-files.json").read_text(encoding="utf-8"))
        components = {"deblestia-shell", "deblestia-nova", "aurora-core"}
        rules = [rule for rule in manifest["rules"] if rule.get("component") in components]
        self.assertTrue(rules)
        for rule in rules:
            source = rule["source"]
            if not any(char in source for char in "*?["):
                with self.subTest(component=rule["component"], source=source):
                    self.assertTrue((ROOT / source).is_file(), f"Updater source missing: {source}")
        for patch_set in manifest.get("patch_sets", []):
            if patch_set.get("component") == "deblestia-nova":
                for patch in patch_set["patches"]:
                    with self.subTest(patch=patch):
                        self.assertTrue((ROOT / patch).is_file(), f"Updater patch missing: {patch}")
        aurora = next(rule for rule in rules if rule.get("component") == "aurora-core")
        self.assertEqual(aurora["link"], "repo:apps/desktop-shells/aurora/aurora")


    def test_all_updater_manifest_sources_and_build_directories_resolve(self):
        import json
        manifest = json.loads((ROOT / "manifests/update-files.json").read_text(encoding="utf-8"))
        for rule in manifest["rules"]:
            source = rule["source"]
            wildcard = min((source.find(char) for char in "*?[" if char in source), default=-1)
            if wildcard >= 0:
                prefix = source[:wildcard].rstrip("/")
                candidate = ROOT / prefix
                if not candidate.exists():
                    candidate = candidate.parent
                with self.subTest(component=rule["component"], source=source):
                    self.assertTrue(candidate.exists(), f"Updater glob has no source directory: {source}")
            else:
                with self.subTest(component=rule["component"], source=source):
                    self.assertTrue((ROOT / source).is_file(), f"Updater source missing: {source}")
            if rule.get("build"):
                with self.subTest(component=rule["component"], build=rule["build"]):
                    self.assertTrue((ROOT / rule["build"] / "Cargo.toml").is_file())
        for patch_set in manifest.get("patch_sets", []):
            for patch in patch_set["patches"]:
                with self.subTest(component=patch_set["component"], patch=patch):
                    self.assertTrue((ROOT / patch).is_file())

    def test_waybar_updater_rules_use_variant_and_shared_canonical_sources(self):
        import json
        manifest = json.loads((ROOT / "manifests/update-files.json").read_text(encoding="utf-8"))
        expected = {
            "deblestia-bar": "apps/waybars/deblestia-bar/",
            "deblestia-nova-lite": "apps/waybars/deblestia-nova-lite/",
            "nova2": "apps/waybars/deblestia-nova-2/",
        }
        for component, prefix in expected.items():
            sources = [r["source"] for r in manifest["rules"] if r.get("component") == component]
            with self.subTest(component=component):
                self.assertIn("shared/waybar/**/*", sources)
                self.assertIn(prefix + "**/*", sources)
                self.assertFalse(any(s == "config/waybar/**/*" for s in sources))

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

    def test_mirrorbridge_installer_and_updater_prefer_canonical_app(self):
        import json
        installer = (ROOT / "install-mirrorbridge.sh").read_text(encoding="utf-8")
        self.assertIn("apps/system-apps/mirrorbridge", installer)
        self.assertIn("config/mirrorbridge", installer)
        manifest = json.loads((ROOT / "manifests/update-files.json").read_text(encoding="utf-8"))
        rules = [rule for rule in manifest["rules"] if rule.get("component") == "mirrorbridge"]
        self.assertTrue(rules)
        self.assertTrue(all(rule["source"].startswith("apps/system-apps/mirrorbridge/") for rule in rules))
        cargo_rule = next(rule for rule in rules if rule["source"].endswith("Cargo.toml"))
        self.assertEqual(cargo_rule["build"], "apps/system-apps/mirrorbridge")

    def test_primary_installers_reference_existing_source_paths(self):
        checks = {
            "install-mirrorbridge.sh": ("apps/system-apps/mirrorbridge", "config/mirrorbridge"),
            "install-mpvpaper-engine.sh": ("apps/system-apps/mpvpaper-engine", "config/mpvpaper-engine"),
            "install-periphx.sh": ("apps/system-apps/periphx", "config/v3"),
            "install-v2.sh": ("apps/desktop-shells/caelestia-v2", "config/caelestia"),
            "install-nova-shell.sh": ("apps/desktop-shells/nova-shell", "config/nova-shell"),
            "install-aurora.sh": ("apps/desktop-shells/aurora", "core/aurora"),
        }
        for installer, source_paths in checks.items():
            with self.subTest(installer=installer):
                content = (ROOT / installer).read_text(encoding="utf-8")
                for source_path in source_paths:
                    with self.subTest(source=source_path):
                        self.assertIn(source_path, content)
                        self.assertTrue((ROOT / source_path).is_dir())


if __name__ == "__main__":
    unittest.main()
