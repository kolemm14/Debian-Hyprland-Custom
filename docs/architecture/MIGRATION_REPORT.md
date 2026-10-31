# Migration report

## Status

**PARTIALLY COMPLETED — audit and migration scaffolding only.**

## Branch and baseline

- Working branch: `refactor/repository-reorganization`.
- Base: existing `refactor/architecture-migration` work.
- Original main baseline recorded earlier: `57d81a05b8b13596f90c844dd33fbe128e31bfac`.
- The migration branch includes the prior plan, compatibility test, CI workflow and MirrorBridge canonical copy.

## Completed in this phase

- Created the dedicated repository-reorganization branch without changing `main`.
- Generated `MIGRATION_MAP.md` with 359 tracked file paths and proposed destinations.
- Documented architecture overview, target directory rules, high-level dependency graph and compatibility policy.
- Confirmed critical coupling between source directories, installers, manifests, updater, sparse-checkout instructions and tests.

## Validation executed

- Command: `python -m unittest discover -s tests -p 'test_architecture_migration_paths.py' -v`
- Result: 6 tests, 6 passed, 0 failed (GitHub Actions, Ubuntu runner, Python 3.15.1).
- Scope: repository path compatibility only. This does not validate Python application behavior, Bash installation flows, C/Rust builds, GUI runtime behavior, update transactions or rollback.

## Not yet completed

- No broad directory moves have been performed.
- MirrorBridge's old source directory remains; its canonical copy is not yet a complete migration.
- The other application groups have not been moved.
- Manifest, updater, installer, service, packaging and all internal references have not yet been migrated.
- No local Python, Bash, C, Rust or desktop integration test suite has been executed in this environment.
- GitHub Actions path-compatibility workflow passed on commit `e34cbb25834597b6634ecdc596b1515938591a15` (run `41242224199`). The workflow executed 6 path-compatibility tests; all 6 passed.

## Next safe sequence

1. Finish MirrorBridge validation and reconcile its duplicate legacy/canonical source.
2. Migrate MPVpaper Engine only after atomically updating all updater manifest globs, sparse-checkout docs, tests and install scripts.
3. Migrate PeriphX with its Rust daemon and service as one unit.
4. Migrate Custom Manager, Waybar variants and desktop shells in dependency-aware groups.
5. Move core modules only as complete packages and validate rollback/update behavior.
6. Finish central path resolution, docs, CI and full regression matrix.

## Validation honesty

A source file copied to a new directory is not evidence that the component works from the new location. A queued or in-progress CI run is not a passing test. The migration remains incomplete until all critical suites execute successfully.
