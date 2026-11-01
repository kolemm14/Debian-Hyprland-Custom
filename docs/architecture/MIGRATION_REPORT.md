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
- The old file-by-file table remains a 359-file historical snapshot. Added a
	current 602-path family inventory and a regression classifier that fails if a
	tracked path is unclassified or a family count drifts.
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

- Architecture migration path suite: 29 tests passed. It now classifies all 602
	tracked paths, proves updater source globs match files, checks component-ID
	alignment (including documented updater-only Nova 2), and exercises recovery
	from a legacy sparse checkout whose core/update symlinks lack targets.
- MPVpaper path tests: 4 passed; MPVpaper unit suite: 406 passed using the same
	harmless `mpvpaper` test executable as CI.
- Repository regression suite: 85 passed (including the Aurora tests); the
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
- All tracked shell scripts passed `bash -n` and ShellCheck. Python compilation,
	updater-manifest JSON validation, canonical/legacy CLI help, systemd unit
	verification, and `git diff --check` also passed.
- Before this continuation, the full `make -C installer check` was not
	clean: strict Clippy reported unused placeholder page and state models because
	the GTK binary only displayed a static welcome page. In this continuation,
	those unused prototype models were removed, the remaining language/dry-run
	state was made explicit in the UI, and the UI now labels itself as
	informational rather than a working installation flow. A dedicated
	`.github/workflows/installer-check.yml` workflow now runs formatting, strict
	Clippy, workspace tests and release compilation on this branch and on relevant
	pull requests. These checks have **not yet been observed passing** for the
	current branch commit; source edits and workflow creation alone are not proof
	of a successful build. Treat the GUI as experimental until a tested
	installation flow is integrated and exercised.
- ShellCheck-driven edits only clarify the best-effort command guards and
	sourced-variable contracts; canonical and legacy Hyprland scripts remain
	behaviorally aligned.
- Latest remote CI observed at the start of this continuation passed for commit
	`6aa30d3` (run `41325674233`, job `path-compatibility`). The additional
	inventory, ShellCheck, and helper-test changes are committed locally as
	`d788aee`, but are not pushed; hosted CI for that commit is therefore not yet
	available. Local success does not establish its hosted result.

## Not yet completed

- MirrorBridge and MPVpaper Engine canonical copies exist; their legacy source trees remain intentionally.
- MPVpaper's primary installer and easy installer now prefer/accept the canonical source while retaining legacy sparse-checkout support.
- MPVpaper updater manifest source globs, contributor test discovery, README sparse-checkout instructions, updater docs and Custom Manager detail path now point to the canonical source.
- PeriphX's 16-file canonical copy is present; `install-v3.sh`, updater rules, README sparse-checkout instructions, roadmap and PeriphX test paths now resolve to the canonical path with legacy fallback in the installer.
- Custom Manager's C resolver now prefers canonical component data and falls back to the legacy manager path; update actions resolve the canonical wrapper first. Its install and update scripts calculate the repository root from the deeper canonical location.
- Deblestia Bar, Nova Lite and Nova 2 configuration/style files are staged in their variant-specific application folders; reusable modules, scripts and resources are staged under `shared/waybar/`. `install-nova2.sh` prefers these canonical locations and retains the old `config/waybar` source as a shared-assets fallback.
- Aurora CLI and profile manager, Caelestia V2 and Nova Shell assets are staged under `apps/desktop-shells/`; the Aurora installer prefers the colocated CLI/profile with fallback to `bin/aurora` and `core/aurora/profile.py`. shared Hyprland includes, scripts and user scripts are staged under `shared/hyprland/`. Their installers (plus Nova 2) now prefer canonical paths and fall back to legacy `config/` paths. The original source trees remain untouched. README sparse-checkout commands for Nova 2, Nova Shell and Caelestia V2 now include the canonical application/shared directories.
- Updater manifest sources are now aligned with the staged canonical paths: MirrorBridge, PeriphX, MPVpaper, Aurora, Caelestia V2, Nova Shell, all three Waybar variants and shared Hyprland/Waybar resources. The migration test now expands every source glob, checks all Rust build manifests and Nova patch files, and verifies component IDs. Remaining updater work is limited to rules for components whose implementations and installation contracts have not yet been migrated; the already staged groups should not be reworked.
- `core/system`, `core/updater`, `core/transactions` and the registry reader now have canonical implementations. The shell reader is `core/registry/components.sh`; registry data remains in `manifests/components.tsv`, with no separate typed registry API yet. Installer framework reorganization, service packaging and complete internal-reference migration remain outstanding. CI runs the repository-level regression suite against the canonical core packages.
- The Rust helper's input validation and JSON action decoding now have local
	unit coverage. The GTK installer remains an informational prototype, not a
	working installation workflow. The unused placeholder page, hardware,
	compatibility and profile state models have been retired rather than presented
	as implemented functionality. The minimal state still consumed by the
	prototype (language and dry-run selection) is retained and displayed. A full
	GUI installation workflow remains a separate implementation and validation task.
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
