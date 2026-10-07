#!/bin/bash
json_mode=0
new_args=()
for arg in "$@"; do
    case "$arg" in
        --json) json_mode=1 ;;
        *) new_args+=("$arg") ;;
    esac
done
set -- "${new_args[@]}"
echo "json_mode=$json_mode"
echo "args=$*"
