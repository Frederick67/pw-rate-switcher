#!/usr/bin/env bash
# install-applet.sh — installs the pw-rate-switcher Cinnamon panel applet
set -euo pipefail

UUID="pw-rate-switcher@kap"
SRC="$(cd "$(dirname "$0")" && pwd)/applet/${UUID}"
DEST="${HOME}/.local/share/cinnamon/applets/${UUID}"

# ── Copy files ───────────────────────────────────────────────────────────────
echo "[INFO]  Installing Cinnamon applet '${UUID}'..."
mkdir -p "${DEST}"
cp -f "${SRC}/applet.js"      "${DEST}/"
cp -f "${SRC}/metadata.json"  "${DEST}/"
cp -f "${SRC}/stylesheet.css" "${DEST}/"
cp -f "${SRC}/icon.svg"       "${DEST}/"
echo "[OK]    Applet files installed to ${DEST}"

# ── Enable on panel ──────────────────────────────────────────────────────────
echo ""
read -rp "[?] Add the applet to the right side of panel 1? (y/N) " reply
if [[ "${reply,,}" != "y" ]]; then
    echo "[INFO]  Skipped. Add it manually: System Settings → Applets → PipeWire Rate Switcher"
    exit 0
fi

# Use Python to safely edit the GSettings list (handles quoting / type prefix)
python3 - <<'PYEOF'
import subprocess, sys, ast, re

KEY  = "org.cinnamon"
ATTR = "enabled-applets"
UUID = "pw-rate-switcher@kap"
ENTRY = f"panel1:right:99:{UUID}:0"

result = subprocess.run(
    ["gsettings", "get", KEY, ATTR],
    capture_output=True, text=True
)
raw = result.stdout.strip()

# gsettings wraps GVariant: strip '@as' type prefix if present
raw = re.sub(r"^@as\s+", "", raw)

try:
    applets = ast.literal_eval(raw)
    if not isinstance(applets, list):
        raise ValueError("not a list")
except Exception:
    applets = []

# Remove any stale entry for our UUID
applets = [a for a in applets if UUID not in a]
applets.append(ENTRY)

new_value = "[" + ", ".join(repr(a) for a in applets) + "]"
r = subprocess.run(["gsettings", "set", KEY, ATTR, new_value])
if r.returncode != 0:
    print("[WARN]  gsettings set failed — add the applet manually.", file=sys.stderr)
    sys.exit(1)

print(f"[OK]    Applet entry added: {ENTRY}")
PYEOF

# ── Notify Cinnamon ──────────────────────────────────────────────────────────
echo ""
echo "[INFO]  Signalling Cinnamon to reload applets..."
if dbus-send --session --dest=org.Cinnamon --type=method_call \
        /org/Cinnamon org.Cinnamon.ReloadXlet \
        string:"APPLET" string:"${UUID}" 2>/dev/null; then
    echo "[OK]    Cinnamon reloaded the applet."
else
    # Fallback: ask Cinnamon to restart just its applet list
    dbus-send --session --dest=org.Cinnamon --type=method_call \
        /org/Cinnamon org.Cinnamon.Eval \
        string:"Main.panel._rightBox._applets.forEach(a => a.destroy()); \
                Main.loadApplets();" 2>/dev/null || true
    echo "[INFO]  If the applet does not appear, press Alt+F2 and type 'r' to reload Cinnamon."
fi

echo ""
echo "[OK]    Installation complete!"
echo "        Look for the 'PW' label on the right side of your panel."
echo "        Click it to open the audio mixer popup."
