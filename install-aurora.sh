#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=core/setup.sh
source "$repo_dir/core/setup.sh"
aurora_cli="$repo_dir/apps/desktop-shells/aurora/aurora"
aurora_profile="$repo_dir/apps/desktop-shells/aurora/profile.py"
[ -x "$aurora_cli" ] || aurora_cli="$repo_dir/bin/aurora"
[ -f "$aurora_profile" ] || aurora_profile="$repo_dir/core/aurora/profile.py"

case "${1:-install}" in
    check)
        # Check base dependencies (Python 3 is required for our profile manager)
        command -v python3 >/dev/null || exit 1
        ;;
    install)
        # Link CLI
        mkdir -p "$HOME/.local/bin"
        ln -sf "$aurora_cli" "$HOME/.local/bin/aurora"
        
        # Setup config dir
        aurora_dir="$HOME/.config/aurora"
        mkdir -p "$aurora_dir/hypr/profiles"
        mkdir -p "$aurora_dir/waybar"
        mkdir -p "$aurora_dir/rofi"
        
        # Init profile matching system (lite, balanced, ultra)
        target_profile="balanced"
        # shellcheck disable=SC2154 # Initialized by the sourced core/setup.sh.
        if [ -n "${DEBLESTIA_PROFILE:-}" ]; then
            case "${DEBLESTIA_PROFILE,,}" in
                lite|legacy) target_profile="lite" ;;
                full) target_profile="ultra" ;;
                *) target_profile="balanced" ;;
            esac
        elif [ -f "$deblestia_state_dir/profile" ]; then
            installed_profile="$(cat "$deblestia_state_dir/profile" 2>/dev/null || true)"
            case "${installed_profile,,}" in
                lite|legacy) target_profile="lite" ;;
                full) target_profile="ultra" ;;
                *) target_profile="balanced" ;;
            esac
        fi
        python3 "$aurora_profile" set "$target_profile"
        
        # Create the main aurora.conf file to be sourced
        cat > "$aurora_dir/hypr/aurora.conf" << 'EOL'
# Aurora Hyprland Core Configuration
# This file should be sourced from ~/.config/hypr/hyprland.conf
source = ~/.config/aurora/hypr/profiles/active.conf
EOL

        # Warn user how to source it
        echo "Aurora Core installed successfully."
        echo "Please add the following line to your ~/.config/hypr/hyprland.conf if not already present:"
        echo "source = ~/.config/aurora/hypr/aurora.conf"
        
        deblestia_record_component aurora-core
        source "$repo_dir/core/updater/record.sh"
        deblestia_update_record aurora-core
        ;;
    launch)
        ;;
    status)
        "$aurora_cli" status
        ;;
    restore)
        # Remove symlink and config
        rm -f "$HOME/.local/bin/aurora"
        rm -rf "$HOME/.config/aurora"
        source "$repo_dir/core/updater/record.sh"
        deblestia_update_record aurora-core forget
        ;;
    *)
        echo "Usage: $0 {check|install|launch|status|restore}"
        exit 1
        ;;
esac
