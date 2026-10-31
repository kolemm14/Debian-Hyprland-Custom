# Architecture migration plan

## Goal

Move the repository toward a modular layout while preserving current installation workflows, user configurations, update behavior, and compatibility with existing sparse-checkout instructions.

## Safety rules

- Work only on `refactor/architecture-migration`; do not commit migration work directly to `main`.
- Inspect each source group and its references before moving it.
- Keep legacy installer entry points working until their replacements have been tested.
- Update path references in installers, manifests, documentation, tests, and sparse-checkout examples together.
- Do not remove old paths until compatibility checks and CI pass.
- Preserve updater repository/path migration behavior unless a dedicated change is reviewed.

## Target layout

```text
apps/
  system-apps/       # MirrorBridge, MPVpaper Engine, PeriphX
  system-tools/      # Custom Manager
  waybars/           # Deblestia bars
  desktop-shells/    # Caelestia, Nova Shell, Aurora
core/                # registry, updater, transactions, system integration
shared/              # reusable Python, shell, Hyprland, Waybar components
installer/
manifests/
profiles/
resources/
scripts/
compat/
tests/
docs/
```

## Current-to-target mapping (provisional)

| Existing location | Intended canonical location | Notes |
| --- | --- | --- |
| `config/mirrorbridge/` | `apps/system-apps/mirrorbridge/` | Rust project; update `install-mirrorbridge.sh` and sparse-checkout examples together. |
| `config/mpvpaper-engine/` | `apps/system-apps/mpvpaper-engine/` | Python modules, tools, services and tests; update installer, docs and test references together. |
| `config/v3/` PeriphX content | `apps/system-apps/periphx/` | Inspect exact ownership and references before splitting/moving any files. |
| `manager/` | `apps/system-tools/custom-manager/` | Inspect launchers, packaging and install references first. |
| `config/waybar/` and Deblestia bar variants | `apps/waybars/` | Preserve variant-specific configs and shared assets. |
| `config/caelestia/`, `config/nova-shell/`, `config/v2/`, `config/v3/` shell content | `apps/desktop-shells/` | These directories may contain mixed responsibilities; inventory before moving. |
| reusable scripts/configuration | `shared/` | Extract only after dependency and call-site analysis. |
| root installer scripts | `compat/` or thin root wrappers | Keep established commands functional during migration. |

This mapping is a planning guide, not permission to move a mixed directory wholesale. In particular, `config/v3/` must be audited because it may contain both application and shell components.

## Staged execution

1. Establish this plan and path/compatibility checks.
2. Inventory one application group at a time, including imports, shell `source` statements, relative paths, packaging files, workflows, manifests, README snippets, sparse-checkout instructions, and updater logic.
3. Migrate one low-coupling group at a time, retaining compatibility wrappers where practical.
4. Run relevant Python tests, Rust checks, shell syntax checks, and path checks for each group.
5. Update documentation only after the new paths and legacy entry points have been verified.
6. Review the complete diff and CI results before proposing a pull request; merge only after review.

## Verification checklist

- [ ] All legacy installer entry points still exist or have explicit compatibility replacements.
- [ ] All referenced source directories exist at the expected migration stage.
- [ ] Sparse-checkout instructions include every required path.
- [ ] Manifests and package definitions point to valid paths.
- [ ] Python and Rust tests pass for the migrated group.
- [ ] Shell scripts pass syntax checks.
- [ ] Updater and rollback behavior remain intact.
- [ ] No user data or existing configuration is deleted as part of a move.
