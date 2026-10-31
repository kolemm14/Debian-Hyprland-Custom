# Migration report

## Status

**PARTIALLY COMPLETED — MirrorBridge and MPVpaper canonical copies are staged; full migration and runtime validation remain outstanding.**

## Branch and baseline

- Working branch: `refactor/repository-reorganization`.
- Base: existing `refactor/architecture-migration` work.
- Original main baseline recorded earlier: `57d81a05b8b13596f90c844dd33fbe128e31bfac`.
- The migration branch includes the prior plan, compatibility test, CI workflow, MirrorBridge canonical copy, MPVpaper Engine canonical copy (111 files), PeriphX canonical copy (16 files) and Custom Manager canonical copy (43 files), 26 Waybar files split between three variants and shared resources, plus 25 desktop-shell/Hyprland assets and 2 Aurora assets.

## Completed in this phase

- Created the dedicated repository-reorganization branch without changing `main`.
- Generated `MIGRATION_MAP.md` with 359 tracked file paths and proposed destinations.
- Documented architecture overview, target directory rules, high-level dependency graph and compatibility policy.
- Confirmed critical coupling between source directories, installers, manifests, updater, sparse-checkout instructions and tests.

## Validation executed

- Command: `python -m unittest discover -s tests -p 'test_architecture_migration_paths.py' -v`
- Result: 8 tests, 8 passed, 0 failed on GitHub Actions (Ubuntu runner, Python 3.15.1; run `41242557648`).
- Expanded CI run `41242923297` passed: 8 migration path tests, 4 MPVpaper path tests, Python bytecode compilation, Bash syntax validation, updater-manifest JSON validation, and the full MPVpaper suite (406 tests, 406 passed). The CI environment installs GTK/Adwaita/WebKit/Pango-Cairo and yt-dlp dependencies and supplies a harmless `mpvpaper` stub for service unit tests; no real desktop runtime is launched.
- Scope: repository path compatibility only. This does not validate Python application behavior, Bash installation flows, C/Rust builds, GUI runtime behavior, update transactions or rollback.

## Not yet completed

- MirrorBridge and MPVpaper Engine canonical copies exist; their legacy source trees remain intentionally.
- MPVpaper's primary installer and easy installer now prefer/accept the canonical source while retaining legacy sparse-checkout support.
- MPVpaper updater manifest source globs, contributor test discovery, README sparse-checkout instructions, updater docs and Custom Manager detail path now point to the canonical source.
- PeriphX's 16-file canonical copy is present; `install-v3.sh`, updater rules, README sparse-checkout instructions, roadmap and PeriphX test paths now resolve to the canonical path with legacy fallback in the installer.
- Custom Manager's C resolver now prefers canonical component data and falls back to the legacy manager path; update actions resolve the canonical wrapper first. Its install and update scripts calculate the repository root from the deeper canonical location.
- Deblestia Bar, Nova Lite and Nova 2 configuration/style files are staged in their variant-specific application folders; reusable modules, scripts and resources are staged under `shared/waybar/`. `install-nova2.sh` prefers these canonical locations and retains the old `config/waybar` source as a shared-assets fallback.
- Aurora CLI and profile manager, Caelestia V2 and Nova Shell assets are staged under `apps/desktop-shells/`; the Aurora installer prefers the colocated CLI/profile with fallback to `bin/aurora` and `core/aurora/profile.py`. shared Hyprland includes, scripts and user scripts are staged under `shared/hyprland/`. Their installers (plus Nova 2) now prefer canonical paths and fall back to legacy `config/` paths. The original source trees remain untouched. README sparse-checkout commands for Nova 2, Nova Shell and Caelestia V2 now include the canonical application/shared directories.
- **Updater manifest migration remains outstanding and is a release blocker:** `manifests/update-files.json` still contains legacy `config/waybar`, `config/hypr`, `config/caelestia`, `config/nova-shell`, `bin/aurora` and `config/mirrorbridge` source rules. These must be reconciled component-by-component before relying on canonical sources for in-place updates.
- Core subpackage migration (`registry`, `updater`, `transactions`, `system`), installer framework reorganization, service packaging and complete internal-reference migration remain outstanding.
- No local Python, Bash, C, Rust or desktop integration test suite has been executed in this environment.
- GitHub Actions path-compatibility workflow passed on commit `e34cbb25834597b6634ecdc596b1515938591a15` (run `41242224199`). The workflow executed 6 path-compatibility tests; all 6 passed.

## Next safe sequence

0. CI run `41244048874` passed all configured repository path tests (13), MPVpaper path tests (4), PeriphX Python tests (20), PeriphX Rust tests (16), Custom Manager build/tests, and MPVpaper unit tests (406).

0. CI run `41243513041` passed the MPVpaper, PeriphX and Custom Manager suites; the Waybar path and shell checks are queued for the next CI run.

1. Finish MirrorBridge validation and reconcile its duplicate legacy/canonical source.
2. Run the MPVpaper-specific CI checks; then plan removal or conversion of the duplicate legacy tree only after all sparse-checkout consumers are migrated.
3. Keep the legacy trees for MirrorBridge, MPVpaper, PeriphX and Custom Manager until all old sparse-checkout and installed updater cases are validated; then plan compatibility cleanup.
4. Audit Aurora and the updater/core package; then complete component manifests, sparse-checkout documentation and GUI/system integration tests before legacy cleanup.
5. Move core modules only as complete packages and validate rollback/update behavior.
6. Finish central path resolution, docs, CI and full regression matrix.

## Validation honesty

A source file copied to a new directory is not evidence that the component works from the new location. A queued or in-progress CI run is not a passing test. The migration remains incomplete until all critical suites execute successfully.
