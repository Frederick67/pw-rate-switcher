"""AutoRateSwitcher — main application class."""
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from .config import log
from .config_mixin import ConfigMixin
from .pipewire_mixin import PipeWireMixin
from .ui_mixin import UIMixin


class AutoRateSwitcher(Adw.Application, ConfigMixin, UIMixin, PipeWireMixin):
    def __init__(self, **kwargs):
        app_id = "com.eason.RateSwitcher.Dev" if os.environ.get("PW_RATE_SWITCHER_DEV") else "com.eason.RateSwitcher"
        super().__init__(application_id=app_id, **kwargs)
        self.current_rate = "Unknown"
        self.running = True
        self.auto_mode = True
        self.strict_mode = False
        self.tray_process = None
        self.manual_buttons = []
        self._active_app_name = None
        self._exclusive_owner_node_id = None
        self._muted_sink_inputs = {}
        self._persisted_muted_inputs = self._load_muted_input_state()
        self.preferences = self._load_preferences()
        self.preferred_sink_by_app = {
            str(app).lower(): sink
            for app, sink in self.preferences.get("preferred_sink_by_app", {}).items()
            if sink
        }
        self.hard_lock_enabled = bool(self.preferences.get("hard_lock_enabled", True))
        self.exclusive_apps = self._load_exclusive_apps()
        self.strict_apps     = self._load_strict_apps()
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)
        log.debug("[App] AutoRateSwitcher initialised.")

    def on_shutdown(self, _app):
        log.info("[App] Shutdown requested — restoring exclusive isolation state.")
        if hasattr(self, "_stop_spectrum_pipeline"):
            self._stop_spectrum_pipeline()
        self._restore_exclusive_isolation()
