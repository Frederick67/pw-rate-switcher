"""Mixin: persistent storage for app profiles and runtime preferences."""
import json
import os

from .config import (
    log,
    CONFIG_DIR,
    EXCLUSIVE_APPS_FILE,
    STRICT_APPS_FILE,
    PREFERENCES_FILE,
)


class ConfigMixin:
    def _load_exclusive_apps(self) -> set:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(EXCLUSIVE_APPS_FILE) as f:
                apps = json.load(f)
            log.info(f"[Config] Loaded exclusive apps: {apps}")
            return set(a.lower() for a in apps)
        except FileNotFoundError:
            log.debug("[Config] No exclusive_apps.json — starting empty.")
            return set()
        except Exception as e:
            log.warning(f"[Config] Could not load exclusive apps: {e}")
            return set()

    def _save_exclusive_apps(self) -> None:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(EXCLUSIVE_APPS_FILE, "w") as f:
                json.dump(sorted(self.exclusive_apps), f, indent=2)
            log.debug(f"[Config] Saved exclusive apps: {sorted(self.exclusive_apps)}")
        except Exception as e:
            log.warning(f"[Config] Could not save exclusive apps: {e}")

    def _load_strict_apps(self) -> set:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(STRICT_APPS_FILE) as f:
                apps = json.load(f)
            log.info(f"[Config] Loaded strict apps: {apps}")
            return set(a.lower() for a in apps)
        except FileNotFoundError:
            log.debug("[Config] No strict_apps.json — starting empty.")
            return set()
        except Exception as e:
            log.warning(f"[Config] Could not load strict apps: {e}")
            return set()

    def _save_strict_apps(self) -> None:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(STRICT_APPS_FILE, "w") as f:
                json.dump(sorted(self.strict_apps), f, indent=2)
            log.debug(f"[Config] Saved strict apps: {sorted(self.strict_apps)}")
        except Exception as e:
            log.warning(f"[Config] Could not save strict apps: {e}")

    def _load_preferences(self) -> dict:
        defaults = {"hard_lock_enabled": True}
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(PREFERENCES_FILE) as f:
                prefs = json.load(f)
            if not isinstance(prefs, dict):
                raise ValueError("preferences.json is not a JSON object")
            merged = {**defaults, **prefs}
            log.info(f"[Config] Loaded preferences: {merged}")
            return merged
        except FileNotFoundError:
            log.debug("[Config] No preferences.json — using defaults.")
            return defaults
        except Exception as e:
            log.warning(f"[Config] Could not load preferences: {e}")
            return defaults

    def _save_preferences(self) -> None:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(PREFERENCES_FILE, "w") as f:
                json.dump(self.preferences, f, indent=2, sort_keys=True)
            log.debug(f"[Config] Saved preferences: {self.preferences}")
        except Exception as e:
            log.warning(f"[Config] Could not save preferences: {e}")
