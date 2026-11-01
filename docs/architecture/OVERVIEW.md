# Architecture overview

## Reference architecture

- `apps/system-apps`: independent end-user applications (MirrorBridge, MPVpaper Engine, PeriphX).
- `apps/system-tools`: system management tools (Custom Manager).
- `apps/waybars`: the three Deblestia Waybar variants.
- `apps/desktop-shells`: Caelestia V2, Nova Shell and Aurora.
- `core/system`: hardware detection, compatibility evaluation, localization and setup orchestration; legacy `core/*.py` and `core/*.sh` entry points preserve their APIs.
- `core/updater`: updater orchestration, file ownership, install state, patch handling and recording. `core/transactions` owns the durable transaction journal and rollback engine. Legacy `core/update/*` paths are retained as relative symlinks.
- `shared`: genuinely reusable Python, shell, Hyprland and Waybar assets.
- `installer`, `manifests`, `profiles`, `resources`, `scripts`, `compat`, `tests`, `docs`: lifecycle, metadata, assets, automation, compatibility, validation and documentation.

## Current audited baseline

The migration branch was forked from the existing architecture-migration work.
The current audited tree contains 602 tracked files: root 29, `.github` 2,
`apps` 201, `bin` 1, `config` 191, `core` 25, `docs` 24, `fixes` 2,
`installer` 38, `manager` 43, `manifests` 2, `profiles` 4, `shared` 33 and
`tests` 7. The totals include tracked Custom Manager `.o` files under both
canonical and legacy trees; the detailed, executable path-family inventory is
in [MIGRATION_MAP.md](MIGRATION_MAP.md).

## Design constraints

1. Keep core independent of application GUI implementations.
2. Preserve existing CLI commands and installer entry points through explicit compatibility adapters.
3. Keep application-specific tests with their application until the shared test layout is deliberately adopted.
4. Keep updater source/destination semantics stable; manifests are executable migration contracts, not passive documentation.
5. Never infer a safe move from directory names alone. Split mixed directories only after their files and consumers are audited.
6. Avoid resolving repository paths from the caller's current working directory.

## Migration state

MirrorBridge, MPVpaper Engine and PeriphX have canonical copies under `apps/system-apps/`; Custom Manager has a canonical copy under `apps/system-tools/custom-manager/`. Deblestia Bar, Nova Lite and Nova 2 have variant-specific configs/styles under `apps/waybars/`, with reusable modules and scripts under `shared/waybar/`. Aurora, Caelestia V2 and Nova Shell now have canonical application assets under `apps/desktop-shells/`; reusable Hyprland includes and scripts are copied under `shared/hyprland/`. The Aurora, Caelestia V2, Nova Shell and Nova 2 installers prefer canonical shell/shared paths with legacy fallbacks. All legacy source trees remain intentionally. MirrorBridge's installer prefers its canonical source and falls back to the legacy sparse-checkout path. MPVpaper's main installer similarly resolves canonical then legacy; its easy installer supports either tree. MPVpaper and PeriphX updater manifest globs now target their canonical paths. PeriphX's installer resolves canonical then legacy source trees. Custom Manager's C resolver and update launcher prefer the canonical paths while preserving legacy fallbacks. The Waybar installer now copies shared assets from `shared/waybar/` and the selected variant from its canonical app directory, retaining the legacy shared directory as fallback. These are compatibility transitions, not completed removal of legacy sources.
