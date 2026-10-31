# Compatibility policy

## Stable interfaces

- Preserve root installer commands and their argument behavior until replacements are tested on fresh and existing installations.
- Preserve installed XDG destinations, desktop entry IDs, systemd unit names, CLI executable names, state files and backup/rollback behavior.
- Preserve updater manifest semantics and component IDs.
- Preserve old sparse-checkout recipes until all documented installation paths have been updated and validated.

## Migration adapters

Use explicit path resolution with this precedence: canonical repository path, legacy repository path, then a clear actionable error. Never silently use a different component or follow an ambiguous symlink.

Legacy source directories may remain as copies during a staged migration. They must be marked as compatibility snapshots and must not diverge silently; add checks that compare canonical and legacy trees or convert the legacy location to a tested forwarding adapter when all consumers can handle it.

## High-risk compatibility areas

- MPVpaper Engine: 111 files, Python package, tests, launchers, user services, desktop entry, updater manifest globs and multiple install scripts.
- PeriphX: Python UI/CLI plus Rust `pericored`, systemd service, manifest and user state.
- Waybar variants: configs/styles plus shared scripts and Hyprland includes.
- Desktop shells: shell-specific config, patches, launchers and shared Hyprland snippets.
- Core updater: update manifest, file inventory, transaction and rollback.
- Custom Manager: C code, compiled object artifacts, Makefile, data files, scripts and its own repository root resolver.

## Safety rules

Do not run real system install/uninstall operations as part of repository validation. Use static checks and isolated temporary fixtures. Keep user data and installed configurations untouched.
