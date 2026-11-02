#!/usr/bin/env bash
# Install totp and its age plugin into ~/.local/bin (no root needed).
# Packages are only checked; the missing ones are printed as one apt command.
#   --link  symlink totp to this checkout instead of copying it (edits here take effect at once)
set -euo pipefail

LINK=false
case "${1:-}" in
    "") ;;
    --link) LINK=true ;;
    *) echo "usage: $0 [--link]" >&2; exit 2 ;;
esac

BIN="${TOTP_BIN:-$HOME/.local/bin}"
PLUGIN_VERSION="v0.5.0"
PLUGIN_SHA256="f837ee7eea5a94c33366b7a78cd143a2a64a1cbae8532b58f16335ca05cccc92"      # linux-amd64 tarball
PLUGIN_BIN_SHA256="89821f7c88af9d097173ce08efc1754e7020b5920cd125f1aacd52f4848aa9fe"  # binary inside it
PLUGIN_URL="https://github.com/olastor/age-plugin-fido2-hmac/releases/download/$PLUGIN_VERSION/age-plugin-fido2-hmac-$PLUGIN_VERSION-linux-amd64.tar.gz"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(uname -sm)" != "Linux x86_64" ]; then
    echo "Only Linux x86_64 is supported (the age plugin download is linux-amd64)." >&2
    exit 1
fi

# command -> Debian/Ubuntu package
declare -A NEED=(
    [python3]=python3 [age]=age [rofi]=rofi [wl-copy]=wl-clipboard [wl-paste]=wl-clipboard
    [notify-send]=libnotify-bin
)
declare -A OPTIONAL=(
    [wtype]="wtype (totp pick --type)"
    [zbarcam]="zbar-tools (totp import-google)"
    [v4l2-ctl]="v4l-utils (exposure sweep while scanning QRs)"
)
missing=()
for cmd in "${!NEED[@]}"; do
    command -v "$cmd" >/dev/null || missing+=("${NEED[$cmd]}")
done
[ -e /usr/lib/x86_64-linux-gnu/libfido2.so.1 ] || missing+=(libfido2-1)
if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing packages. Install them, then rerun this script:" >&2
    echo "  sudo apt install $(printf '%s\n' "${missing[@]}" | sort -u | paste -sd' ')" >&2
    exit 1
fi
for cmd in "${!OPTIONAL[@]}"; do
    command -v "$cmd" >/dev/null || echo "Optional, not installed: ${OPTIONAL[$cmd]}"
done

mkdir -p "$BIN"
if [ "$(sha256sum "$BIN/age-plugin-fido2-hmac" 2>/dev/null | cut -d' ' -f1)" != "$PLUGIN_BIN_SHA256" ]; then
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    curl -fsSL -o "$tmp/plugin.tar.gz" "$PLUGIN_URL"
    echo "$PLUGIN_SHA256  $tmp/plugin.tar.gz" | sha256sum -c --quiet
    tar -xzf "$tmp/plugin.tar.gz" -C "$tmp"
    install -m755 "$tmp/age-plugin-fido2-hmac/age-plugin-fido2-hmac" "$BIN/"
    echo "Installed age-plugin-fido2-hmac $PLUGIN_VERSION"
fi
if $LINK; then
    ln -sfn "$HERE/totp" "$BIN/totp"
    echo "Linked $BIN/totp -> $HERE/totp"
else
    rm -f "$BIN/totp"  # a previous --link symlink would otherwise be written through
    install -m755 "$HERE/totp" "$BIN/totp"
    echo "Installed $BIN/totp"
fi

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Note: $BIN is not in PATH; add it, or call totp by its full path." ;;
esac
echo "Next: plug in the key and run 'totp init' in a terminal."
