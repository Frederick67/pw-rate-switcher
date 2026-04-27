#!/usr/bin/env bash
# =============================================================================
# install.sh — Arch Linux installer for pw-rate-switcher
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_BIN="/usr/local/bin/pw-rate-switcher"
ICON_BASE="/usr/share/icons/hicolor"
APP_DIR="/usr/share/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
warn()  { echo "[WARN]  $*"; }
die()   { echo "[ERROR] $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Dependency check
# ---------------------------------------------------------------------------
info "Checking dependencies..."

missing_pacman=()
missing_pip=()

check_pkg() {
    # $1 = pacman package name to suggest, $2 = command to test
    if ! command -v "$2" &>/dev/null; then
        missing_pacman+=("$1")
    fi
}

check_pkg "pipewire"      "pw-dump"
check_pkg "pipewire"      "pw-metadata"
check_pkg "pipewire"      "pw-cli"
check_pkg "libpulse"      "pactl"
check_pkg "gstreamer"     "gst-inspect-1.0"

if ! python3 -c "import gi" 2>/dev/null; then
    missing_pacman+=("python-gobject")
fi

if ! python3 -c "
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
" 2>/dev/null; then
    missing_pacman+=("gtk4" "libadwaita")
fi

if ! python3 -c "
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
" 2>/dev/null; then
    missing_pacman+=("gstreamer")
fi

if command -v gst-inspect-1.0 &>/dev/null; then
    if ! gst-inspect-1.0 pulsesrc &>/dev/null; then
        missing_pacman+=("gst-plugins-good")
    fi
    if ! gst-inspect-1.0 spectrum &>/dev/null; then
        missing_pacman+=("gst-plugins-good")
    fi
    if ! gst-inspect-1.0 audioconvert &>/dev/null; then
        missing_pacman+=("gst-plugins-base")
    fi
fi

# AppIndicator for system tray (try both variants)
_has_indicator=false
for mod in AppIndicator3 AyatanaAppIndicator3; do
    if python3 -c "
import gi
try:
    gi.require_version('$mod', '0.1')
    from gi.repository import $mod
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; then
        _has_indicator=true
        break
    fi
done
if ! $_has_indicator; then
    missing_pacman+=("libayatana-appindicator")
    warn "No AppIndicator library found — the system tray icon may not appear."
    warn "Install 'libayatana-appindicator' (AUR) or 'libappindicator-gtk3'."
fi

if [ ${#missing_pacman[@]} -gt 0 ]; then
    # Remove duplicates
    mapfile -t missing_pacman < <(printf '%s\n' "${missing_pacman[@]}" | sort -u)
    die "Missing packages: ${missing_pacman[*]}\nInstall them with:\n  sudo pacman -S ${missing_pacman[*]}"
fi

ok "All dependencies satisfied."

# ---------------------------------------------------------------------------
# 2. Install the Python script + package
# ---------------------------------------------------------------------------
info "Installing script to $INSTALL_BIN ..."
sudo install -Dm755 "$SCRIPT_DIR/pw-rate-switcher.py" "$INSTALL_BIN"

# Install the pw_rate_switcher package next to the script so Python can import it
INSTALL_PKG_DIR="/usr/local/lib/pw-rate-switcher"
sudo mkdir -p "$INSTALL_PKG_DIR"
sudo cp -r "$SCRIPT_DIR/pw_rate_switcher" "$INSTALL_PKG_DIR/"

# Prepend the package dir to PYTHONPATH inside the installed script
sudo sed -i "1a import sys; sys.path.insert(0, '$INSTALL_PKG_DIR')" "$INSTALL_BIN"
ok "Script + package installed."

# ---------------------------------------------------------------------------
# 3. Install icons  (skip sizes already present)
# ---------------------------------------------------------------------------
info "Installing icons..."
ICON_SRC="$SCRIPT_DIR/build/pw-rate-switcher/usr/share/icons/hicolor"
if [ -d "$ICON_SRC" ]; then
    for size_dir in "$ICON_SRC"/*/; do
        size=$(basename "$size_dir")
        for icon_file in "$size_dir"apps/*; do
            [ -f "$icon_file" ] || continue
            dest="$ICON_BASE/$size/apps/$(basename "$icon_file")"
            sudo install -Dm644 "$icon_file" "$dest"
        done
    done
    sudo gtk-update-icon-cache -f -t "$ICON_BASE" 2>/dev/null && ok "Icon cache updated." || warn "gtk-update-icon-cache not found — icons may need a re-login to appear."
else
    warn "Icon source directory not found, skipping icon install."
fi

# ---------------------------------------------------------------------------
# 4. Install .desktop launcher
# ---------------------------------------------------------------------------
info "Installing .desktop file..."
DESKTOP_SRC="$SCRIPT_DIR/build/pw-rate-switcher/usr/share/applications/pw-rate-switcher.desktop"
if [ -f "$DESKTOP_SRC" ]; then
    sudo install -Dm644 "$DESKTOP_SRC" "$APP_DIR/pw-rate-switcher.desktop"
    ok ".desktop file installed."
else
    # Generate a minimal one if the build copy is missing
    sudo tee "$APP_DIR/pw-rate-switcher.desktop" > /dev/null << 'EOF'
[Desktop Entry]
Name=PipeWire Rate Switcher
Comment=Auto-switch sample rate for Bit-Perfect Audio
Exec=pw-rate-switcher
Icon=pw-rate-switcher
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Utility;
StartupNotify=true
StartupWMClass=com.eason.RateSwitcher
EOF
    ok ".desktop file generated."
fi

# ---------------------------------------------------------------------------
# 5. XDG autostart entry (starts with the desktop session)
# ---------------------------------------------------------------------------
info "Setting up autostart entry..."
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/pw-rate-switcher.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=PipeWire Rate Switcher
Comment=Auto sample rate switcher for PipeWire (starts at login)
Exec=pw-rate-switcher
Icon=pw-rate-switcher
Terminal=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF
ok "Autostart entry created at $AUTOSTART_DIR/pw-rate-switcher.desktop"

# ---------------------------------------------------------------------------
# 6. Optional: systemd user service
# ---------------------------------------------------------------------------
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
read -rp "[?] Also install a systemd user service? (y/N) " _ans
if [[ "${_ans,,}" == "y" ]]; then
    mkdir -p "$SYSTEMD_USER_DIR"
    cat > "$SYSTEMD_USER_DIR/pw-rate-switcher.service" << 'EOF'
[Unit]
Description=PipeWire Rate Switcher
After=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/local/bin/pw-rate-switcher
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now pw-rate-switcher.service
    ok "systemd user service enabled and started."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
ok "Installation complete!"
echo "  Run it now:  pw-rate-switcher"
echo "  It will also start automatically on your next login."
