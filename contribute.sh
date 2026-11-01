#!/usr/bin/env bash

set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=core/i18n.sh
source "$repo_dir/core/i18n.sh"
case "${1:-menu}" in
    report|hardware-report) python3 "$repo_dir/core/hardware.py" --json ;;
    test)
        PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$repo_dir/tests"
        if [ -d "$repo_dir/apps/system-apps/mpvpaper-engine/tests" ]; then
            PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$repo_dir/apps/system-apps/mpvpaper-engine/tests"
        elif [ -d "$repo_dir/config/mpvpaper-engine/tests" ]; then
            PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$repo_dir/config/mpvpaper-engine/tests"
        fi
        ;;
    menu)
        deblestia_t contribution_help; printf '\n'
        ;;
    *) printf 'Usage : %s [menu|report|test]\n' "$0" >&2; exit 2 ;;
esac
