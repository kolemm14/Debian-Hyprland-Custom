#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=core/setup.sh
source "$repo_dir/core/setup.sh"

case "${1:-install}" in
    check)
        # Check base dependencies (Python 3 is required for our profile manager)
        command -v python3 >/dev/null || exit 1
        ;;
    install)
        # Link CLI
        mkdir -p "$HOME/.local/bin"
        ln -sf "$repo_dir/bin/aurora" "$HOME/.local/bin/aurora"
        
        # Setup config dir
        aurora_dir="$HOME/.config/aurora"
        mkdir -p "$aurora_dir/hypr/profiles"
        mkdir -p "$aurora_dir/waybar"
        mkdir -p "$aurora_dir/rofi"
        
        # Init profile matching system (lite, balanced, ultra)
        target_profile="balanced"
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
        python3 "$repo_dir/core/aurora/profile.py" set "$target_profile"
        
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
        source "$repo_dir/core/update/record.sh"
        deblestia_update_record aurora-core
        ;;
    launch)
        ;;
    status)
        "$repo_dir/bin/aurora" status
        ;;
    restore)
        # Remove symlink and config
        rm -f "$HOME/.local/bin/aurora"
        rm -rf "$HOME/.config/aurora"
        source "$repo_dir/core/update/record.sh"
        deblestia_update_record aurora-core forget
        ;;
    *)
        echo "Usage: $0 {check|install|launch|status|restore}"
        exit 1
        ;;
esac
