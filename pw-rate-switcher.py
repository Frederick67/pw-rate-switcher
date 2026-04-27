#!/usr/bin/env python3
"""
pw-rate-switcher — entry point.

Handles two roles depending on argv:
  (no args)   → launch the GTK 4 main window
  --tray      → run the GTK 3 system-tray indicator (spawned as a subprocess)
"""
import sys
import subprocess
import signal
import gi

# Logging + constants are set up on first import.
from pw_rate_switcher.config import log, _log_file

# ===========================================================================
# TRAY PROCESS  (GTK 3 + AppIndicator)
# Spawned by the main process; exits independently.
# ===========================================================================
if len(sys.argv) > 1 and sys.argv[1] == "--tray":
    try:
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk as Gtk3
    except (ValueError, ImportError):
        sys.exit(0)

    AppIndicator = None
    for _mod in ("AppIndicator3", "AyatanaAppIndicator3"):
        try:
            gi.require_version(_mod, "0.1")
            from gi.repository import AppIndicator3 as AppIndicator  # noqa: F401
            break
        except (ValueError, ImportError):
            pass
    if AppIndicator is None:
        sys.exit(0)

    def _open_main_window(_source):
        subprocess.Popen([sys.executable, sys.argv[0]])

    def _quit_all(_source):
        Gtk3.main_quit()
        sys.exit(0)

    _indicator = AppIndicator.Indicator.new(
        "pw-rate-switcher-tray",
        "pw-rate-switcher",
        AppIndicator.IndicatorCategory.APPLICATION_STATUS,
    )
    _indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

    _menu = Gtk3.Menu()
    _item_show = Gtk3.MenuItem(label="Open Settings")
    _item_show.connect("activate", _open_main_window)
    _menu.append(_item_show)
    _menu.append(Gtk3.SeparatorMenuItem())
    _item_quit = Gtk3.MenuItem(label="Quit")
    _item_quit.connect("activate", _quit_all)
    _menu.append(_item_quit)
    _menu.show_all()
    _indicator.set_menu(_menu)
    Gtk3.main()
    sys.exit(0)

# ===========================================================================
# MAIN APP  (GTK 4 / Libadwaita)
# ===========================================================================
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
except ValueError:
    log.critical("GTK4 or Libadwaita not found.")
    sys.exit(1)

from pw_rate_switcher.app import AutoRateSwitcher  # noqa: E402 (after gi version check)

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("PipeWire Rate Switcher — starting up")
    log.info(f"Log file: {_log_file}")
    log.info("=" * 60)
    app = AutoRateSwitcher()

    def _cleanup_and_exit(signum, _frame):
        log.info(f"[App] Received signal {signum} — restoring audio state before exit.")
        try:
            app._restore_exclusive_isolation()
        finally:
            app.quit()
            raise SystemExit(0)

    signal.signal(signal.SIGINT, _cleanup_and_exit)
    signal.signal(signal.SIGTERM, _cleanup_and_exit)
    app.run(sys.argv)
