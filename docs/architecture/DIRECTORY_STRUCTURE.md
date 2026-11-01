# Directory structure

## Target tree

```text
apps/
  system-apps/
    mirrorbridge/
    mpvpaper-engine/
    periphx/
  system-tools/
    custom-manager/
  waybars/
    deblestia-bar/
    deblestia-nova-lite/
    deblestia-nova-2/
  desktop-shells/
    caelestia-v2/
    nova-shell/
    aurora/
core/
  registry/
  updater/
  transactions/
  system/
shared/
  python/
  shell/
  hyprland/
  waybar/
installer/
manifests/
profiles/
resources/
scripts/
compat/
tests/
docs/
```

## Placement rules

- Put a component's code, private resources, packaging and tests together unless an external contract requires a stable shared location.
- Shared modules must have at least two real consumers and a stable interface.
- Keep desktop-shell-specific Hyprland snippets with the shell unless multiple shells genuinely share them.
- Split `config/waybar` by variant only after mapping shared scripts, modules, styles and config includes.
- Split `config/v3` into PeriphX only after confirming every file belongs to PeriphX.
- Keep root-level historical commands as compatibility entry points until all callers and user documentation are migrated.
- Do not move generated object files (`.o`) as application source; inspect whether they are tracked build artifacts and remove only in a separate, justified cleanup after build reproducibility is verified.

## Current tree decisions

- The current tracked-path inventory is maintained in `MIGRATION_MAP.md`. At
  the previous audit contained 602 tracked paths. The current continuation
  adds one installer CI workflow, bringing the branch to 603 tracked paths;
  the inventory rules and a regression test ensure every tracked path has one disposition.
- The root shell commands remain stable public entry points. Several are still
  invoked by `manifests/components.tsv`, other root scripts, README examples,
  and sparse-checkout flows. Convert them to wrappers only as an individually
  tested migration unit that preserves argument forwarding, exit status,
  executable mode, working-directory independence, and old sparse-checkout
  behavior.
- `config/`, `manager/`, `bin/aurora`, and `core/update/` remain compatibility
  sources/aliases while installed checkouts and installers still depend on
  those paths. Their presence is deliberate, not proof that the migration is
  complete.
- `core/registry/components.sh` reads `manifests/components.tsv`. The reader
  currently has one importing module; keep this small interface rather than
  introduce another registry API until a second real consumer needs a shared
  contract. `manifests/update-files.json` continues to describe per-file update
  ownership independently.
- `installer/` is the separate Rust GUI project, not the canonical home of the
  currently dispatched shell installer implementations. Its GUI/core flow is
  not considered production-validated by repository path tests; see
  `MIGRATION_REPORT.md` for current test and lint results.
- The target diagram's `resources/`, `scripts/`, and `compat/` directories are
  not created just to satisfy names. Existing reusable assets are app-local or
  under `shared/`; root commands remain public contracts; and `fixes/` patches
  are consumed at their current location.
