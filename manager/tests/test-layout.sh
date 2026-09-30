#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
required=(
  Makefile
  src/main.c src/ui.c src/ui.h src/paths.c src/paths.h
  src/component.c src/component.h src/runner.c src/runner.h
  data/components.ini data/debian-custom-manager.desktop
  scripts/install.sh scripts/uninstall.sh scripts/update-wrapper.sh
)
for file in "${required[@]}"; do
  [[ -s "$ROOT/$file" ]] || { echo "FAIL: $file absent/vide"; exit 1; }
done
[[ -x "$ROOT/scripts/install.sh" ]]
[[ -x "$ROOT/scripts/uninstall.sh" ]]
[[ -x "$ROOT/scripts/update-wrapper.sh" ]]
echo "PASS layout"
