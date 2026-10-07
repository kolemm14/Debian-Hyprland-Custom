#!/usr/bin/env bash
# Called only after an existing installer has completed its file operations.
deblestia_update_record() {
    local update_root
    update_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    if ! git -C "$update_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        printf '%s\n' 'Installation sans clone Git : suivi des mises à jour indisponible.' >&2
        return 0
    fi
    PYTHONDONTWRITEBYTECODE=1 python3 "$update_root/core/update/main.py" "--${2:-record}-component" "$1"
}
