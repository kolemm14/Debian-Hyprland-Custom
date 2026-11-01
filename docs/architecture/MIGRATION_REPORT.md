# Migration report

## Status

**PARTIALLY COMPLETED — application groups, shared assets, core system, updater, transaction engine and the registry reader have canonical paths. The registry data remains in `manifests/components.tsv`; installer reorganization and full runtime validation remain outstanding.**

## Branch and baseline

- Working branch: `refactor/repository-reorganization`.
- Base: existing `refactor/architecture-migration` work.
- Original main baseline recorded earlier: `57d81a05b8b13596f90c844dd33fbe128e31bfac`.
- The migration branch includes the prior plan, compatibility test, CI workflow, MirrorBridge canonical copy, MPVpaper Engine canonical copy (111 files), PeriphX canonical copy (16 files) and Custom Manager canonical copy (43 files), 26 Waybar files split between three variants and shared resources, plus 25 desktop-shell/Hyprland assets and 2 Aurora assets.

## Completed in this phase

- Staged the four system-management modules under `core/system/`: hardware detection, compatibility evaluation, localization and setup orchestration. Kept `core/hardware.py`, `core/compatibility.py`, `core/i18n.sh` and `core/setup.sh` as compatibility wrappers; the Python wrappers re-export the original import APIs as well as CLI behavior.
- Migrated updater implementation files to `core/updater/` and the transaction engine to `core/transactions/transaction.py`. Old `core/update/*` paths are relative symlinks, and the updater CLI/installers now use canonical paths. Updater tests were adapted to run against the new package layout.
- Extracted the shell component-registry reader to `core/registry/components.sh`; the TSV data remains in `manifests/components.tsv` and is not yet a separate registry package.

- Created the dedicated repository-reorganization branch without changing `main`.
- Generated `MIGRATION_MAP.md` as a 359-file inventory snapshot at its recorded
	baseline; the current branch has 602 tracked files and the map needs refresh
	before it can serve as an exhaustive final inventory.
- Documented architecture overview, target directory rules, high-level dependency graph and compatibility policy.
- Confirmed critical coupling between source directories, installers, manifests, updater, sparse-checkout instructions and tests.

## Validation executed

- Command: `python -m unittest discover -s tests -p 'test_architecture_migration_paths.py' -v`
- Result: 8 tests, 8 passed, 0 failed on GitHub Actions (Ubuntu runner, Python 3.15.1; run `41242557648`).
- Expanded CI run `41242923297` passed: 8 migration path tests, 4 MPVpaper path tests, Python bytecode compilation, Bash syntax validation, updater-manifest JSON validation, and the full MPVpaper suite (406 tests, 406 passed). The CI environment installs GTK/Adwaita/WebKit/Pango-Cairo and yt-dlp dependencies and supplies a harmless `mpvpaper` stub for service unit tests; no real desktop runtime is launched.
- Scope: repository path compatibility only. This does not validate Python application behavior, Bash installation flows, C/Rust builds, GUI runtime behavior, update transactions or rollback.

## Additional local validation

The following checks were executed in the isolated worktree on the current
continuation; they are local results, not GitHub Actions results:

- Architecture migration path suite: 27 tests passed after moving the existing
	Custom Manager assertions into the discoverable test class.
- MPVpaper path tests: 4 passed; MPVpaper unit suite: 406 passed using the same
	harmless `mpvpaper` test executable as CI.
- Repository regression suite: 83 passed (including the Aurora tests); the
	dedicated Aurora suite also passed all 3 tests.
- MirrorBridge Rust suite: 3 passed; PeriphX daemon Rust suite: 16 passed.
- Custom Manager compiled successfully and its full `make test` target passed.
	An earlier PTY assertion had counted delayed bytes from the initial frame as
	an idle redraw; the helper now drains that startup paint before checking
	idleness. The PTY suite passed three consecutive runs and the full clean/build/
	test target passed after this change. Hosted CI for the resulting commit is
	still required.
- The installer plan integration test exceeded its previous fixed 10-second
	timeout during real hardware probing (18.2 seconds in an isolated run). Its
	timeout is now 30 seconds; the focused test and full repository suite passed.
- Selected workflow Bash syntax, Python compilation, manifest JSON validation,
	canonical/legacy CLI help and `git diff --check` passed.
- GitHub Actions for commit `6500f5e` was successful. The two immediately prior
	failed workflow runs failed at the Custom Manager job; public log download
	returned HTTP 403, so their detailed hosted-run output could not be verified.
	The local reruns above do not establish the result for a future commit.

## Not yet completed

- MirrorBridge and MPVpaper Engine canonical copies exist; their legacy source trees remain intentionally.
- MPVpaper's primary installer and easy installer now prefer/accept the canonical source while retaining legacy sparse-checkout support.
- MPVpaper updater manifest source globs, contributor test discovery, README sparse-checkout instructions, updater docs and Custom Manager detail path now point to the canonical source.
- PeriphX's 16-file canonical copy is present; `install-v3.sh`, updater rules, README sparse-checkout instructions, roadmap and PeriphX test paths now resolve to the canonical path with legacy fallback in the installer.
- Custom Manager's C resolver now prefers canonical component data and falls back to the legacy manager path; update actions resolve the canonical wrapper first. Its install and update scripts calculate the repository root from the deeper canonical location.
- Deblestia Bar, Nova Lite and Nova 2 configuration/style files are staged in their variant-specific application folders; reusable modules, scripts and resources are staged under `shared/waybar/`. `install-nova2.sh` prefers these canonical locations and retains the old `config/waybar` source as a shared-assets fallback.
- Aurora CLI and profile manager, Caelestia V2 and Nova Shell assets are staged under `apps/desktop-shells/`; the Aurora installer prefers the colocated CLI/profile with fallback to `bin/aurora` and `core/aurora/profile.py`. shared Hyprland includes, scripts and user scripts are staged under `shared/hyprland/`. Their installers (plus Nova 2) now prefer canonical paths and fall back to legacy `config/` paths. The original source trees remain untouched. README sparse-checkout commands for Nova 2, Nova Shell and Caelestia V2 now include the canonical application/shared directories.
- Updater manifest sources are now aligned with the staged canonical paths: MirrorBridge, PeriphX, MPVpaper, Aurora, Caelestia V2, Nova Shell, all three Waybar variants and shared Hyprland/Waybar resources. The migration test now checks every exact updater source, each glob's source directory, Rust build manifests and Nova patch files. The remaining updater work is to migrate rules alongside components not yet moved (especially core/installer and other legacy components), not to fix these staged groups.
- `core/system`, `core/updater`, `core/transactions` and the registry reader now have canonical implementations. The shell reader is `core/registry/components.sh`; registry data remains in `manifests/components.tsv`, with no separate typed registry API yet. Installer framework reorganization, service packaging and complete internal-reference migration remain outstanding. CI runs the repository-level regression suite against the canonical core packages.
- No local Debian desktop installation, live Hyprland/Waybar runtime, end-to-end install/update/rollback or GUI integration test has been executed. GitHub Actions provides isolated source-level Python, Bash, C and Rust validation only.
- GitHub Actions path-compatibility workflow passed on commit `e34cbb25834597b6634ecdc596b1515938591a15` (run `41242224199`). The workflow executed 6 path-compatibility tests; all 6 passed.

## Next safe sequence

1. Finish the remaining installer/core integration and update the historical
	migration map from the current branch tree.
2. Keep the legacy trees for MirrorBridge, MPVpaper, PeriphX and Custom Manager
	until old sparse-checkout and already-installed updater cases are validated;
	do not remove them as part of this staged migration.
3. Define any future registry data/API migration separately from the extracted
	shell reader and test its compatibility contract before changing consumers.
4. Run end-to-end install, update and rollback checks on a Debian/Hyprland host;
	no live desktop or GUI integration test has been executed in this work.
5. After committing and pushing only to the migration branch, wait for the
	workflow on that exact commit to finish before release handoff.

## Validation honesty

A source file copied to a new directory is not evidence that the component works from the new location. A queued or in-progress CI run is not a passing test. The migration remains incomplete until all critical suites execute successfully.
