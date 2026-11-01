#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$MANAGER_DIR/../../.." && pwd)"

cd "$REPO_ROOT"

case "${1:-}" in
  "")
    ./update.sh
    ;;
  --rollback)
    ./update.sh --rollback
    ;;
  *)
    echo "Usage: $0 [--rollback]" >&2
    exit 2
    ;;
esac

# update.sh owns the project update. This wrapper only refreshes the GUI binary
# afterwards so its installed executable matches the checked-out Manager source.
if [[ -f "$MANAGER_DIR/Makefile" && -x "$MANAGER_DIR/scripts/install.sh" ]]; then
  echo
  echo "Actualisation de Debian Custom Manager…"
  make -C "$MANAGER_DIR" clean all test
  "$MANAGER_DIR/scripts/install.sh" --skip-build
  echo "Debian Custom Manager actualisé."
else
  echo "Le Manager n'existe plus dans cette version du dépôt ; aucune réinstallation effectuée."
fi
