# Architecture — Debian Custom Manager

## Goal

Provide one lightweight control center without turning the project into one monolithic application.

```text
Debian Custom Manager (C + GTK3)
        |
        +-- component registry (components.ini)
        +-- state detection
        +-- dependency view
        +-- logs
        +-- safe command runner
        |
        +--> update.sh
        +--> install-*.sh
        +--> component-specific uninstall/repair scripts when available
        |
        +--> MPVpaper Engine   (independent)
        +--> Aurora Desktop    (independent)
        +--> Nova Shell        (independent)
        +--> MirrorBridge      (independent)
        +--> Pericored         (independent)
```

## Layers

### `paths.c`
Finds the Debian-Hyprland-Custom checkout and resolves `$HOME` / `$REPO` paths.

Lookup order:

1. `DHC_REPO_ROOT` environment variable;
2. `~/.config/debian-custom-apps/system-tools/custom-manager/config.ini`;
3. current Git worktree;
4. `~/Debian-Hyprland-Custom`.

### `component.c`
Loads `data/components.ini` and computes component state. The registry contains presentation and detection metadata, not component implementation code.

### `runner.c`
Two execution modes:

- captured/read-only operations for `--check` and `--dry-run`;
- interactive terminal operations for install/update/rollback, preserving sudo prompts.

No update algorithm is duplicated here.

### `ui.c`
GTK3 interface with five views:

- Accueil;
- Composants;
- Dépendances;
- Journaux;
- À propos.

## Safety rules

- Never run the whole GUI as root.
- Never overwrite user configuration itself; that remains updater responsibility.
- Never execute arbitrary commands coming from writable user input.
- Component scripts are repository-relative entries from the trusted registry.
- Required components cannot be uninstalled from the GUI.
- Optional uninstall buttons appear only when an explicit uninstall script is registered.
- Apply/rollback operations stay interactive.

## Future stable backend

A future updater can expose JSON, for example:

```text
./update.sh --check --json
./update.sh --dry-run --json
```

The Manager should then consume that structured output while preserving the same updater ownership boundary.
