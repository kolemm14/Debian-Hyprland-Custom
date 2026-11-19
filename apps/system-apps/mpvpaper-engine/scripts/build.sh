#!/usr/bin/env bash

# Build script for MPVpaper Hub production bundle
# -------------------------------------------------------------

set -e

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
ENGINE_DIR="$(realpath "$SCRIPT_DIR/..")"
HUB_DIR="$ENGINE_DIR/hub"

echo "=== Construction de MPVpaper Hub ==="
cd "$HUB_DIR"

if [ ! -d node_modules ]; then
  echo "Installation reproductible des dépendances Hub…"
  bash scripts/install-pnpm.sh
fi

echo "Compilation de MPVpaper Hub..."
pnpm build

echo "=== Construction terminée avec succès ==="
