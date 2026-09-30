# Debian Custom Manager

Native control center for Debian-Hyprland-Custom.

## Why C + GTK3

The project targets older PCs as well as modern Debian/Hyprland systems. The Manager therefore avoids Electron/WebView and does not add a Python runtime dependency. GTK3/GLib provides a mature native interface with a small memory footprint and fast startup.

## Responsibilities

The Manager:

- displays the state of components;
- explains each component in simple language;
- runs update checks and dry-runs;
- delegates installation, update, rollback and repair to existing scripts;
- shows basic dependency status;
- keeps command output in a log view.

It does **not** absorb MPVpaper Engine, Aurora, Nova, MirrorBridge or Pericored.

## Build

```bash
sudo apt install build-essential pkg-config libgtk-3-dev
cd manager
make
make test
./build/debian-custom-manager
```

When run from inside the repository, it automatically finds the Git root. You can also set:

```bash
DHC_REPO_ROOT=/path/to/Debian-Hyprland-Custom ./build/debian-custom-manager
```

## Install for the current user

```bash
cd manager
./scripts/install.sh
```

This installs only the Manager under `~/.local`. It does not modify the desktop components.

## Uninstall the Manager

```bash
cd manager
./scripts/uninstall.sh
```

This removes only the Manager.

## Diagnostic CLI

No graphical session is required for the component diagnostic:

```bash
./build/debian-custom-manager --version
./build/debian-custom-manager --diagnose
```
