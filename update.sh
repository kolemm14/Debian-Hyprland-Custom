#!/usr/bin/env bash
# Incremental installation-aware updater; Python is already required by Setup.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$repo_dir/core/updater/main.py" ] || [ ! -f "$repo_dir/core/transactions/transaction.py" ]; then
    printf '%s\n' 'Updater absent du checkout partiel. Ajoutez : git sparse-checkout add core/updater core/transactions manifests' >&2
    exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$repo_dir/core/updater/main.py" "$@"
