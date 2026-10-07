#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$MANAGER_DIR/.." && pwd)"
SKIP_BUILD=0

if [[ "${1:-}" == "--skip-build" ]]; then
  SKIP_BUILD=1
fi

need=(gcc make pkg-config)
missing=()
for cmd in "${need[@]}"; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done

if ! pkg-config --exists gtk+-3.0 gio-2.0 glib-2.0 2>/dev/null; then
  missing+=("libgtk-3-dev")
fi

if ((${#missing[@]})); then
  printf 'Dépendances de compilation manquantes : %s\n' "${missing[*]}"
  printf 'Sur Debian : sudo apt install build-essential pkg-config libgtk-3-dev\n'
  exit 2
fi

if (( ! SKIP_BUILD )); then
  make -C "$MANAGER_DIR" clean all test
fi

BIN_SRC="$MANAGER_DIR/build/debian-custom-manager"
[[ -x "$BIN_SRC" ]] || { echo "Binaire absent : $BIN_SRC" >&2; exit 3; }

BIN_DIR="${HOME}/.local/bin"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/debian-custom-manager"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/debian-custom-manager"
mkdir -p "$BIN_DIR" "$DATA_DIR" "$APP_DIR" "$CFG_DIR"

install -m 0755 "$BIN_SRC" "$BIN_DIR/debian-custom-manager"
install -m 0644 "$MANAGER_DIR/data/components.ini" "$DATA_DIR/components.ini"
install -m 0644 "$MANAGER_DIR/data/debian-custom-manager.desktop" "$APP_DIR/debian-custom-manager.desktop"

cat > "$CFG_DIR/config.ini" <<CFG
[manager]
repo_root=$REPO_ROOT
CFG

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

printf 'Debian Custom Manager installé.\n'
printf 'Commande : %s/debian-custom-manager\n' "$BIN_DIR"
printf 'Dépôt associé : %s\n' "$REPO_ROOT"
