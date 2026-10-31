# Migration report

## Status

**PARTIALLY COMPLETED — MirrorBridge and MPVpaper canonical copies are staged; full migration and runtime validation remain outstanding.**

## Branch and baseline

- Working branch: `refactor/repository-reorganization`.
- Base: existing `refactor/architecture-migration` work.
- Original main baseline recorded earlier: `57d81a05b8b13596f90c844dd33fbe128e31bfac`.
- The migration branch includes the prior plan, compatibility test, CI workflow, MirrorBridge canonical copy and MPVpaper Engine canonical copy (111 files).

## Completed in this phase

- Created the dedicated repository-reorganization branch without changing `main`.
- Generated `MIGRATION_MAP.md` with 359 tracked file paths and proposed destinations.
- Documented architecture overview, target directory rules, high-level dependency graph and compatibility policy.
- Confirmed critical coupling between source directories, installers, manifests, updater, sparse-checkout instructions and tests.

## Validation executed

- Command: `python -m unittest discover -s tests -p 'test_architecture_migration_paths.py' -v`
- Result: 8 tests, 8 passed, 0 failed on GitHub Actions (Ubuntu runner, Python 3.15.1; run `41242557648`).
- A broader CI job now additionally runs MPVpaper's path tests, Python bytecode compilation, Bash syntax checks and JSON validation; its result is tracked separately.
- Scope: repository path compatibility only. This does not validate Python application behavior, Bash installation flows, C/Rust builds, GUI runtime behavior, update transactions or rollback.

## Not yet completed

- MirrorBridge and MPVpaper Engine canonical copies exist; their legacy source trees remain intentionally.
- MPVpaper's primary installer and easy installer now prefer/accept the canonical source while retaining legacy sparse-checkout support.
- MPVpaper updater manifest source globs, contributor test discovery, README sparse-checkout instructions, updater docs and Custom Manager detail path now point to the canonical source.
- PeriphX, Custom Manager source, Waybar variants and desktop shells have not been migrated.
- Core, updater package, installer framework, service packaging and complete internal-reference migration remain outstanding.
- No local Python, Bash, C, Rust or desktop integration test suite has been executed in this environment.
- GitHub Actions path-compatibility workflow passed on commit `e34cbb25834597b6634ecdc596b1515938591a15` (run `41242224199`). The workflow executed 6 path-compatibility tests; all 6 passed.

## Next safe sequence

0. Confirm the expanded CI checks on the MPVpaper canonical copy before treating this group as validated.

0. Confirm the expanded CI checks on the MPVpaper canonical copy before treating this group as validated.

1. Finish MirrorBridge validation and reconcile its duplicate legacy/canonical source.
2. Run the MPVpaper-specific CI checks; then plan removal or conversion of the duplicate legacy tree only after all sparse-checkout consumers are migrated.
3. Migrate PeriphX with its Rust daemon and service as one unit.
4. Migrate Custom Manager, Waybar variants and desktop shells in dependency-aware groups.
5. Move core modules only as complete packages and validate rollback/update behavior.
6. Finish central path resolution, docs, CI and full regression matrix.

## Validation honesty

A source file copied to a new directory is not evidence that the component works from the new location. A queued or in-progress CI run is not a passing test. The migration remains incomplete until all critical suites execute successfully.
