"""Logging setup and global constants shared across the whole app."""
import logging
import os

# ── Log file ────────────────────────────────────────────────────────────────
_log_dir = os.path.expanduser("~/.local/share/pw-rate-switcher")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "debug.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_file, mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("pw-switcher")

# ── Persistent config ────────────────────────────────────────────────────────
CONFIG_DIR = os.path.expanduser("~/.config/pw-rate-switcher")
EXCLUSIVE_APPS_FILE = os.path.join(CONFIG_DIR, "exclusive_apps.json")
STRICT_APPS_FILE    = os.path.join(CONFIG_DIR, "strict_apps.json")
PREFERENCES_FILE    = os.path.join(CONFIG_DIR, "preferences.json")
MUTED_INPUTS_FILE   = os.path.join(CONFIG_DIR, "muted_inputs.json")
