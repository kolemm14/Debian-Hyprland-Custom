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
