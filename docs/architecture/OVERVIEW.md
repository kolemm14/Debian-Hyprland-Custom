# Architecture overview

## Reference architecture

- `apps/system-apps`: independent end-user applications (MirrorBridge, MPVpaper Engine, PeriphX).
- `apps/system-tools`: system management tools (Custom Manager).
- `apps/waybars`: the three Deblestia Waybar variants.
- `apps/desktop-shells`: Caelestia V2, Nova Shell and Aurora.
- `core`: registry, updater, transaction/rollback and system detection.
- `shared`: genuinely reusable Python, shell, Hyprland and Waybar assets.
- `installer`, `manifests`, `profiles`, `resources`, `scripts`, `compat`, `tests`, `docs`: lifecycle, metadata, assets, automation, compatibility, validation and documentation.

## Current audited baseline

The migration branch was forked from the existing architecture-migration work. The audited tree contains 359 tracked files at the time this document was generated. Main legacy groups include `config/` (191 files), `installer/` (38), `manager/` (43), `core/` (12), `docs/` (18), `tests/` (7), `manifests/` (2) and `profiles/` (4). See [MIGRATION_MAP.md](MIGRATION_MAP.md) for the file-by-file path inventory.

## Design constraints

1. Keep core independent of application GUI implementations.
2. Preserve existing CLI commands and installer entry points through explicit compatibility adapters.
3. Keep application-specific tests with their application until the shared test layout is deliberately adopted.
4. Keep updater source/destination semantics stable; manifests are executable migration contracts, not passive documentation.
5. Never infer a safe move from directory names alone. Split mixed directories only after their files and consumers are audited.
6. Avoid resolving repository paths from the caller's current working directory.

## Migration state

MirrorBridge, MPVpaper Engine and PeriphX have canonical copies under `apps/system-apps/`; Custom Manager has a canonical copy under `apps/system-tools/custom-manager/`. Deblestia Bar, Nova Lite and Nova 2 have variant-specific configs/styles under `apps/waybars/`, with reusable modules and scripts under `shared/waybar/`. Caelestia V2 and Nova Shell now have canonical application assets under `apps/desktop-shells/`; reusable Hyprland includes and scripts are copied under `shared/hyprland/`. The Caelestia V2, Nova Shell and Nova 2 installers prefer canonical shell/shared paths with legacy fallbacks. All legacy source trees remain intentionally. MirrorBridge's installer prefers its canonical source and falls back to the legacy sparse-checkout path. MPVpaper's main installer similarly resolves canonical then legacy; its easy installer supports either tree. MPVpaper and PeriphX updater manifest globs now target their canonical paths. PeriphX's installer resolves canonical then legacy source trees. Custom Manager's C resolver and update launcher prefer the canonical paths while preserving legacy fallbacks. The Waybar installer now copies shared assets from `shared/waybar/` and the selected variant from its canonical app directory, retaining the legacy shared directory as fallback. These are compatibility transitions, not completed removal of legacy sources.
