#!/usr/bin/env bash

set -u

rain_clock_url="https://github.com/hugo-sants/rain-clock-gnome.git"
rain_clock_ref="${RAIN_CLOCK_REF:-886da8923b08a4653443dab138b2db6ed3c11935}"
cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/mpvpaper-engine/rain-clock-gnome"
repository="$cache_dir/repository"
font_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/mpvpaper-engine-rain-clock"
font_files=(
    Anurati.otf
    Poppins.ttf
    electroharmonix.ttf
    Outfit-ExtraBold.ttf
    GoogleSans-Regular.ttf
    Gilroy-Bold.ttf
    Gilroy-SemiBold.ttf
)
font_families=(
    "Anurati"
    "Poppins"
    "Electroharmonix"
    "Outfit"
    "Google Sans"
    "Gilroy-Bold"
    "Gilroy-SemiBold"
)

fonts_available() {
    command -v fc-match >/dev/null 2>&1 || return 1
    local family
    for family in "${font_families[@]}"; do
        fc-match -f '%{family}' "$family" 2>/dev/null |
            grep -Fqi "$family" || return 1
    done
}

if [ "${1:-install}" = check ]; then
    if fonts_available; then
        printf 'OK       polices HUD Rain Clock (Mond, Summit et Meenimal)\n'
        exit 0
    fi
    printf 'MANQUANT polices HUD Rain Clock; relancer l’installation\n'
    exit 1
fi

if fonts_available; then
    printf 'OK       polices HUD Rain Clock déjà installées\n'
    exit 0
fi

if [ "${RAIN_CLOCK_SKIP_FONT_INSTALL:-0}" = 1 ]; then
    printf 'AVERTISSEMENT installation des polices Rain Clock ignorée\n' >&2
    exit 0
fi

mkdir -p "$cache_dir" "$font_dir"
if [ ! -d "$repository/.git" ]; then
    if ! git clone --filter=blob:none --no-checkout "$rain_clock_url" "$repository"; then
        printf 'AVERTISSEMENT téléchargement des polices Rain Clock impossible\n' >&2
        exit 0
    fi
fi
if ! git -C "$repository" fetch --depth 1 origin "$rain_clock_ref" \
    || ! git -C "$repository" checkout --detach FETCH_HEAD; then
    printf 'AVERTISSEMENT version Rain Clock %s indisponible\n' "$rain_clock_ref" >&2
    exit 0
fi

for font in "${font_files[@]}"; do
    if [ ! -f "$repository/fonts/$font" ]; then
        printf 'AVERTISSEMENT police Rain Clock absente : %s\n' "$font" >&2
        exit 0
    fi
    install -m 0644 "$repository/fonts/$font" "$font_dir/$font"
done

cat >"$font_dir/SOURCE.txt" <<EOF
Rain Clock GNOME — Hugo Santos (@hugo-sants)
$rain_clock_url
Source revision: $rain_clock_ref

Styles adapted in MPVpaper Engine: Mond, Summit and Meenimal.
Rain Clock source code is GPL-3.0-or-later. Font authors are credited in
the upstream README; each bundled font remains subject to its own terms.
EOF

if command -v fc-cache >/dev/null 2>&1; then
    fc-cache -f "$font_dir" >/dev/null
fi
printf 'OK       polices HUD Rain Clock installées depuis %s\n' "$rain_clock_url"
