#!/usr/bin/env bash
set -euo pipefail

BIN="${HOME}/.local/bin/debian-custom-manager"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/debian-custom-manager"
APP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/debian-custom-manager.desktop"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/debian-custom-manager"

rm -f -- "$BIN" "$APP"
rm -rf -- "$DATA_DIR" "$CFG_DIR"
echo "Debian Custom Manager supprimé. Le dépôt Debian-Hyprland-Custom et ses composants n’ont pas été touchés."
