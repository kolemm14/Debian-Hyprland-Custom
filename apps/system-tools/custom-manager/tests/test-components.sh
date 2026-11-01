#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="$ROOT/data/components.ini"

grep -q '^\[component:core\]$' "$FILE"
grep -q '^\[component:mpvpaper-engine\]$' "$FILE"
grep -q '^\[component:aurora\]$' "$FILE"
grep -q '^\[component:mirrorbridge\]$' "$FILE"
grep -q '^\[component:nova-shell\]$' "$FILE"
grep -q '^required=true$' "$FILE"

# No test suite from MPVpaper Engine is an install target of the Manager.
if grep -q 'mpvpaper-engine/tests' "$FILE"; then
  echo 'FAIL: tests MPVpaper ne doivent pas être installés par le Manager'
  exit 1
fi

echo "PASS components manifest"
