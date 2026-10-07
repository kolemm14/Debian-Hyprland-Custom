# Backend contract

The Custom Manager is an orchestrator. It must not reimplement the updater.

## Update backend

The current stable contract is deliberately small:

- `./update.sh --check` — read-only update check.
- `./update.sh --dry-run` — read-only simulation.
- `./update.sh` — apply the update interactively.
- `./update.sh --rollback` — rollback interactively.

`--check` and `--dry-run` are captured by the GUI. Apply/rollback run in an external terminal so sudo/password prompts remain usable.

A future `--json` mode may replace human-output parsing, but it is not required by v0.1.

## Components

`data/components.ini` is presentation/orchestration metadata only. Each component remains responsible for its own runtime and installer.

Detection keys:

- `detect_any`: installed when at least one listed path exists.
- `detect_all`: all listed paths must exist.
- `detect_command`: command must exist in `PATH`.
- `service`: if installation is detected but the user service is inactive, state becomes `À vérifier`.

Supported variables in paths: `$HOME`, `$REPO`.

## Manager self-refresh

The GUI launches `manager/scripts/update-wrapper.sh` for apply/rollback. The wrapper first delegates the real project transition to `update.sh`. Only after a successful transition does it rebuild/test/reinstall the Manager binary. It does not copy project files or decide update contents.
