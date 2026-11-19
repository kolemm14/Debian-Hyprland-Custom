#!/usr/bin/env bash
# Run the Hub dev server against the user's normal Engine service.
set -euo pipefail

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
ENGINE_DIR="$(realpath "$SCRIPT_DIR/..")"
HUB_DIR="$ENGINE_DIR/hub"

command -v python3 >/dev/null || { echo "python3 est requis." >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js >= 22.13 est requis." >&2; exit 1; }
systemctl --user is-active --quiet mpvpaper-engine.service || {
  echo "Démarrez d'abord le moteur : systemctl --user start mpvpaper-engine.service" >&2
  exit 1
}

SOCKET_PATH="$(PYTHONPATH="$ENGINE_DIR" python3 -c \
  'from mpvpaper_engine.paths import EnginePaths; print(EnginePaths.from_environment().engine_socket)')"
[[ -S "$SOCKET_PATH" ]] || { echo "Socket Engine absente : $SOCKET_PATH" >&2; exit 1; }

if [[ ! -d "$HUB_DIR/node_modules" ]]; then
  bash "$HUB_DIR/scripts/install-pnpm.sh"
fi

cd "$HUB_DIR"
exec pnpm dev
