#!/usr/bin/env bash

set -Eeuo pipefail

REPO_URL="https://github.com/kolemm14/Debian-Hyprland-Custom.git"
TARGET_DIR="${MPVPAPER_ENGINE_REPO:-$HOME/mpvpaper-engine}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/mpvpaper-engine-installer"
LANGUAGE="auto"
ACTION="install"
NON_INTERACTIVE=0

if [ -t 1 ]; then
    BOLD='\033[1m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    RED='\033[31m'
    BLUE='\033[34m'
    RESET='\033[0m'
else
    BOLD='' GREEN='' YELLOW='' RED='' BLUE='' RESET=''
fi

usage() {
    cat <<'EOF'
MPVpaper Engine — Easy Installer

Usage:
  ./install-mpvpaper-engine-easy.sh
  ./install-mpvpaper-engine-easy.sh --check
  ./install-mpvpaper-engine-easy.sh --install
  ./install-mpvpaper-engine-easy.sh --lang fr
  ./install-mpvpaper-engine-easy.sh --lang en
  ./install-mpvpaper-engine-easy.sh --non-interactive

Options:
  --check             Vérifie seulement la machine
  --install           Lance l'installation guidée
  --lang fr|en        Langue
  --non-interactive   Pas de questions interactives
  -h, --help          Affiche cette aide
EOF
}

while (($#)); do
    case "$1" in
        --check)
            ACTION="check"
            ;;
        --install)
            ACTION="install"
            ;;
        --lang)
            LANGUAGE="${2:-}"
            shift
            ;;
        --lang=*)
            LANGUAGE="${1#*=}"
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Option inconnue : %s\n' "$1" >&2
            usage
            exit 2
            ;;
    esac
    shift
done

if [ "$LANGUAGE" = auto ]; then
    case "${LANG:-fr}" in
        en*) LANGUAGE=en ;;
        *)   LANGUAGE=fr ;;
    esac
fi

if [[ "$LANGUAGE" != fr && "$LANGUAGE" != en ]]; then
    printf 'Language must be fr or en.\n' >&2
    exit 2
fi

say() {
    printf '%b\n' "$*"
}

step() {
    say ""
    say "${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    say "${BLUE}${BOLD}$*${RESET}"
    say "${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
}

ok() {
    say "${GREEN}[ OK ]${RESET} $*"
}

warn() {
    say "${YELLOW}[ OPTIONAL / WARNING ]${RESET} $*"
}

missing() {
    say "${RED}[ MISSING ]${RESET} $*"
}

die() {
    say "${RED}[ ERROR ]${RESET} $*" >&2
    exit 1
}

confirm() {
    [ "$NON_INTERACTIVE" = 1 ] && return 0

    local answer
    read -r -p "$1 [y/N] " answer

    case "$answer" in
        y|Y|yes|YES|o|O|oui|OUI)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

run_root() {
    if [ "$EUID" -eq 0 ]; then
        "$@"
        return
    fi

    if command -v sudo >/dev/null 2>&1; then
        sudo "$@"
        return
    fi

    if command -v su >/dev/null 2>&1; then
        local command_string=""
        printf -v command_string '%q ' "$@"

        say ""
        if [ "$LANGUAGE" = fr ]; then
            say "${YELLOW}sudo n'est pas installé.${RESET}"
            say "Le mot de passe ROOT va être demandé uniquement pour cette opération."
        else
            say "${YELLOW}sudo is not installed.${RESET}"
            say "The ROOT password will be requested only for this operation."
        fi

        su -c "$command_string"
        return
    fi

    die "Impossible d'obtenir les privilèges administrateur."
}

check_command() {
    local command_name="$1"
    local description="$2"

    if command -v "$command_name" >/dev/null 2>&1; then
        ok "$command_name — $description"
        return 0
    fi

    missing "$command_name — $description"
    return 1
}

check_os() {
    step "1/8 — System check"

    [ -r /etc/os-release ] || die "/etc/os-release introuvable."

    # shellcheck disable=SC1091
    source /etc/os-release

    say "System : ${PRETTY_NAME:-unknown}"

    if [ "${ID:-}" != debian ]; then
        die "Cet installateur est actuellement prévu pour Debian."
    fi

    ok "Debian detected"

    if command -v Hyprland >/dev/null 2>&1 ||
       command -v hyprctl >/dev/null 2>&1; then
        ok "Hyprland detected"
    else
        warn "Hyprland n'est pas encore détecté."
    fi
}

check_privileges() {
    step "2/8 — Administrator access"

    if command -v sudo >/dev/null 2>&1; then
        ok "sudo available"
    elif command -v su >/dev/null 2>&1; then
        warn "sudo absent — root access will use 'su'."
    else
        die "Ni sudo ni su ne sont disponibles."
    fi

    if [ "$EUID" -eq 0 ]; then
        die "Ne lance pas MPVpaper Engine entièrement en root. Connecte-toi avec ton utilisateur normal."
    fi
}

required_packages=(
    git
    ffmpeg
    ffmpegthumbnailer
    python3
    python3-venv
    python3-gi
    gir1.2-gtk-4.0
    gir1.2-adw-1
    gir1.2-webkit-6.0
)

optional_packages=(
    python3-gi-cairo
    gir1.2-gtklayershell-0.1
)

build_packages=(
    build-essential
    pkg-config
    meson
    ninja-build
    libmpv-dev
    libwayland-dev
    wayland-protocols
    libegl-dev
    mpv
)

missing_required=()

check_packages() {
    step "3/8 — Dependencies"

    missing_required=()

    for package in "${required_packages[@]}"; do
        if dpkg-query -W -f='${db:Status-Abbrev}' "$package" 2>/dev/null |
           grep -q '^ii '; then
            ok "$package"
        else
            missing "$package"
            missing_required+=("$package")
        fi
    done

    say ""
    say "${BOLD}Optional desktop HUD:${RESET}"

    for package in "${optional_packages[@]}"; do
        if dpkg-query -W -f='${db:Status-Abbrev}' "$package" 2>/dev/null |
           grep -q '^ii '; then
            ok "$package"
        else
            warn "$package"
        fi
    done

    check_command systemctl "systemd service manager" || true
    check_command python3 "MPVpaper Engine runtime" || true
    check_command ffmpeg "video processing" || true
    check_command ffprobe "media inspection" || true

    if command -v hyprctl >/dev/null 2>&1; then
        ok "hyprctl — Hyprland control interface"
    else
        missing "hyprctl — Hyprland is required for full integration"
    fi
}

install_packages() {
    ((${#missing_required[@]})) || return 0

    step "4/8 — Install missing Debian packages"

    say "Packages to install:"
    printf '  • %s\n' "${missing_required[@]}"

    if ! confirm "Install these packages now?"; then
        die "Installation cancelled."
    fi

    run_root apt-get update

    run_root apt-get install -y \
        "${required_packages[@]}" \
        "${optional_packages[@]}"
}

install_mpvpaper() {
    step "5/8 — mpvpaper backend"

    export PATH="$HOME/.local/bin:$PATH"

    if command -v mpvpaper >/dev/null 2>&1; then
        ok "mpvpaper already installed"
        return
    fi

    missing "mpvpaper"

    say ""
    say "MPVpaper Engine uses mpvpaper to render video wallpapers."

    if ! confirm "Build and install mpvpaper automatically?"; then
        die "mpvpaper is required."
    fi

    say "Installing compilation dependencies..."

    run_root apt-get update
    run_root apt-get install -y "${build_packages[@]}"

    mkdir -p "$CACHE_DIR"
    local source_dir="$CACHE_DIR/mpvpaper"

    if [ -d "$source_dir/.git" ]; then
        say "Updating existing mpvpaper source..."
        git -C "$source_dir" pull --ff-only
    else
        say "Downloading official mpvpaper source..."
        git clone --depth 1 \
            https://github.com/GhostNaN/mpvpaper.git \
            "$source_dir"
    fi

    say "Configuring mpvpaper..."

    cd "$source_dir"
    rm -rf build

    meson setup build \
        --prefix="$HOME/.local" \
        --buildtype=release

    say "Compiling mpvpaper..."
    ninja -C build

    say "Installing mpvpaper into ~/.local..."
    ninja -C build install

    export PATH="$HOME/.local/bin:$PATH"

    command -v mpvpaper >/dev/null 2>&1 ||
        die "mpvpaper installation failed."

    ok "mpvpaper installed"
}

download_project() {
    step "6/8 — Download MPVpaper Engine"

    if [ -f "$TARGET_DIR/install-mpvpaper-engine.sh" ] &&
       [ -d "$TARGET_DIR/config/mpvpaper-engine" ]; then
        say "Existing project found: $TARGET_DIR"

        if [ -d "$TARGET_DIR/.git" ]; then
            say "Checking for updates..."
            git -C "$TARGET_DIR" pull --ff-only || \
                warn "Update skipped because the repository contains local changes."
        fi
    else
        if [ -e "$TARGET_DIR" ]; then
            die "$TARGET_DIR existe déjà mais n'est pas un dépôt MPVpaper Engine valide."
        fi

        say "Repository:"
        say "  $REPO_URL"
        say ""
        say "Only the MPVpaper Engine section will be downloaded."

        git clone \
            --depth 1 \
            --filter=blob:none \
            --sparse \
            "$REPO_URL" \
            "$TARGET_DIR"

        git -C "$TARGET_DIR" sparse-checkout set \
            config/mpvpaper-engine
    fi

    ok "Source downloaded"
}

install_engine() {
    step "7/8 — Install MPVpaper Engine"

    cd "$TARGET_DIR"

    say "Running the project's own dependency check..."
    say ""

    if ! ./install-mpvpaper-engine.sh check; then
        die "Some required dependencies are still missing."
    fi

    say ""

    if ! confirm "Install MPVpaper Engine now?"; then
        die "Installation cancelled."
    fi

    ./install-mpvpaper-engine.sh install

    export PATH="$HOME/.local/bin:$PATH"

    [ -x "$HOME/.local/bin/mpvpaper-engine" ] ||
        die "mpvpaper-engine command was not installed."

    [ -x "$HOME/.local/bin/mpvpaper-enginectl" ] ||
        die "mpvpaper-enginectl command was not installed."

    ok "MPVpaper Engine installed"
}

final_check() {
    step "8/8 — Final verification"

    export PATH="$HOME/.local/bin:$PATH"

    check_command mpvpaper "video wallpaper backend" || true
    check_command mpvpaper-engine "graphical application" || true
    check_command mpvpaper-enginectl "control tool" || true

    say ""

    if systemctl --user status mpvpaper-engine.service \
        --no-pager >/dev/null 2>&1; then
        ok "MPVpaper Engine systemd service"
    else
        warn "The user service is not active yet."
    fi

    if command -v mpvpaper-enginectl >/dev/null 2>&1; then
        say ""
        say "Engine status:"
        mpvpaper-enginectl status --json || \
            warn "The engine is installed but not responding yet."
    fi

    say ""
    say "${GREEN}${BOLD}Installation complete.${RESET}"
    say ""
    say "Launch with:"
    say ""
    say "    mpvpaper-engine"
    say ""

    if [ "$NON_INTERACTIVE" = 0 ] &&
       [ -n "${WAYLAND_DISPLAY:-}" ] &&
       confirm "Launch MPVpaper Engine now?"; then
        mpvpaper-engine >/dev/null 2>&1 &
    fi
}

check_os
check_privileges
check_packages

if [ "$ACTION" = check ]; then
    say ""
    say "${GREEN}Check complete. No changes were made.${RESET}"
    exit 0
fi

install_packages

# Re-check after package installation.
check_packages

install_mpvpaper
download_project
install_engine
final_check
