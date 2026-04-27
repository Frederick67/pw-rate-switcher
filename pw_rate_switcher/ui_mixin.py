"""Mixin: all GTK 4 / Libadwaita UI builder methods."""
import math
import os
import re
import subprocess
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk

GST_AVAILABLE = False
try:
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    GST_AVAILABLE = True
except (ValueError, ImportError):
    Gst = None

from .config import log


APP_CSS = """
@define-color panel_edge rgba(120, 120, 120, 0.14);
@define-color text_primary rgba(244, 247, 251, 0.96);
@define-color text_muted rgba(191, 201, 214, 0.70);
@define-color accent_a rgba(200, 200, 200, 0.94);
@define-color accent_b rgba(180, 180, 180, 0.92);

window.pwrs-window {
    color: @text_primary;
    background-color: rgba(8, 8, 8, 0.98);
    background-image: linear-gradient(135deg, rgba(10, 10, 10, 0.99), rgba(15, 15, 15, 0.97));
}

headerbar {
    background-color: rgba(10, 10, 10, 0.78);
    background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.01));
    border-bottom: 1px solid rgba(120, 120, 120, 0.10);
    box-shadow: none;
}

label {
    color: @text_primary;
}

separator {
    background-color: rgba(120, 120, 120, 0.10);
    min-height: 1px;
}

.panel-shell {
    background-color: rgba(15, 15, 15, 0.82);
    background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.01));
    border: 1px solid @panel_edge;
    border-radius: 24px;
    padding: 22px;
    box-shadow: 0 22px 52px rgba(0, 0, 0, 0.22);
}

.panel-left {
    background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
}

.panel-right {
    background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.015));
}

.section-block {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(120, 120, 120, 0.08);
    border-radius: 20px;
    padding: 14px;
}

.control-row {
    background-color: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(120, 120, 120, 0.08);
    border-radius: 18px;
    padding: 10px 12px;
}

.toolbar-row {
    background-color: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(120, 120, 120, 0.08);
    border-radius: 18px;
    padding: 10px;
}

.pill-row {
    padding-top: 4px;
    padding-bottom: 2px;
}

.profile-card,
.mixer-row {
    background-color: rgba(18, 18, 18, 0.84);
    background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.01));
    border: 1px solid rgba(120, 120, 120, 0.08);
    border-radius: 18px;
    padding: 12px;
}

.waveform-frame {
    background-color: rgba(10, 10, 10, 0.95);
    border: 1px solid rgba(150, 150, 150, 0.16);
    border-radius: 18px;
}

.hero-rate {
    font-size: 40px;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: rgba(247, 250, 252, 0.98);
}

.heading {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: rgba(232, 238, 245, 0.92);
}

.muted-note,
.section-note {
    color: @text_muted;
}

.card,
.meter-stat {
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(120, 120, 120, 0.10);
    border-radius: 999px;
    padding: 9px 14px;
}

.card.accent,
.path-node-owner,
button.suggested-action {
    color: rgba(0, 0, 0, 0.98);
    background-color: rgba(200, 200, 200, 0.92);
    background-image: linear-gradient(180deg, rgba(220, 220, 220, 0.98), rgba(180, 180, 180, 0.90));
    border: 1px solid rgba(180, 180, 180, 0.26);
}

button,
entry,
togglebutton {
    color: @text_primary;
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(120, 120, 120, 0.12);
    border-radius: 14px;
}

button {
    padding: 10px 14px;
}

button:hover,
togglebutton:hover,
entry:focus {
    background-color: rgba(255, 255, 255, 0.09);
    border-color: rgba(160, 160, 160, 0.24);
}

button.flat {
    background-color: rgba(255, 255, 255, 0.02);
}

button.destructive-action {
    background-color: rgba(139, 49, 49, 0.42);
    border-color: rgba(239, 111, 111, 0.22);
}

togglebutton:checked,
switch:checked {
    background-color: rgba(180, 180, 180, 0.82);
    background-image: linear-gradient(180deg, rgba(200, 200, 200, 0.98), rgba(160, 160, 160, 0.88));
    color: rgba(0, 0, 0, 0.96);
}

entry {
    padding: 10px 12px;
}

listbox.boxed-list {
    background-color: transparent;
}

listbox.boxed-list row {
    background-color: transparent;
}

scale trough {
    min-height: 6px;
    border-radius: 999px;
    background-color: rgba(255, 255, 255, 0.10);
}

scale highlight {
    border-radius: 999px;
    background-color: rgba(180, 180, 180, 0.90);
    background-image: linear-gradient(90deg, rgba(190, 190, 190, 0.92), rgba(170, 170, 170, 0.92));
}

scale slider {
    min-width: 18px;
    min-height: 18px;
    border-radius: 999px;
    background-color: rgba(244, 247, 251, 0.96);
    border: 2px solid rgba(50, 50, 50, 0.70);
}

.path-strip {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(120, 120, 120, 0.09);
    border-radius: 20px;
    padding: 14px;
}

.path-node {
    background-color: rgba(20, 20, 20, 0.88);
    border: 1px solid rgba(120, 120, 120, 0.12);
    border-radius: 16px;
    padding: 10px 14px;
}

.mixer-shell {
    background-color: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(120, 120, 120, 0.08);
    border-radius: 18px;
    padding: 8px;
}
"""


class UIMixin:
    def _install_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(APP_CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _init_waveform_state(self):
        self._waveform_points_count = 160
        self._peak_history = [0.0] * self._waveform_points_count
        self._rms_history = [0.0] * self._waveform_points_count
        self._current_peak_db = -90.0
        self._current_rms_db = -90.0
        self._current_headroom_db = 90.0
        self._clip_detected = False
        self._waveform_pipeline = None
        self._waveform_sink = None
        self._waveform_bus = None
        self._waveform_monitor_name = None

    def _init_mixer_state(self):
        self._mixer_rows = {}

    def _resolve_monitor_source_name(self):
        try:
            sink_name = __import__("subprocess").run(
                ["pactl", "get-default-sink"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if not sink_name:
                return None

            monitor_name = f"{sink_name}.monitor"
            result = __import__("subprocess").run(
                ["pactl", "--format=json", "list", "sources"],
                capture_output=True,
                text=True,
            )
            if not result.stdout.strip():
                return monitor_name

            for source in __import__("json").loads(result.stdout):
                if source.get("name") == monitor_name:
                    return monitor_name

            for source in __import__("json").loads(result.stdout):
                name = source.get("name", "")
                if name.endswith(".monitor") and sink_name in name:
                    return name
            return monitor_name
        except Exception as e:
            log.warning(f"[Spectrum] Could not resolve monitor source: {e}")
            return None

    def _push_waveform_samples(self, samples):
        if not samples:
            return

        normalized = [abs(max(-1.0, min(1.0, float(sample)))) for sample in samples]
        peak_value = max(normalized)
        rms_value = math.sqrt(sum(value * value for value in normalized) / len(normalized))

        self._peak_history.pop(0)
        self._peak_history.append(peak_value)
        self._rms_history.pop(0)
        self._rms_history.append(rms_value)

        self._current_peak_db = 20.0 * math.log10(max(peak_value, 1e-5))
        self._current_rms_db = 20.0 * math.log10(max(rms_value, 1e-5))
        self._current_headroom_db = max(0.0, -self._current_peak_db)
        self._clip_detected = peak_value >= 0.995

        if hasattr(self, "meter_peak_label"):
            self.meter_peak_label.set_label(f"Peak {self._current_peak_db:.1f} dBFS")
        if hasattr(self, "meter_rms_label"):
            self.meter_rms_label.set_label(f"RMS {self._current_rms_db:.1f} dBFS")
        if hasattr(self, "meter_headroom_label"):
            self.meter_headroom_label.set_label(f"Headroom {self._current_headroom_db:.1f} dB")
        if hasattr(self, "meter_clip_label"):
            self.meter_clip_label.set_label("Clip risk" if self._clip_detected else "Safe")

        if hasattr(self, "waveform_area"):
            self.waveform_area.queue_draw()

    def _on_waveform_sample(self, sink):
        try:
            sample = sink.emit("pull-sample")
            if sample is None:
                return Gst.FlowReturn.OK
            buffer = sample.get_buffer()
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.OK
            try:
                payload = memoryview(map_info.data)
                if len(payload) < 4:
                    return Gst.FlowReturn.OK
                frames = payload.cast("f")
                self._push_waveform_samples(list(frames))
            finally:
                buffer.unmap(map_info)
        except Exception as e:
            log.warning(f"[Waveform] Sample decode failed: {e}")
        return Gst.FlowReturn.OK

    def _on_waveform_bus_message(self, _bus, message):
        if not GST_AVAILABLE:
            return
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            log.warning(f"[Waveform] Pipeline error: {err} ({debug})")

    def _start_waveform_pipeline(self):
        if not GST_AVAILABLE:
            if hasattr(self, "waveform_status_label"):
                self.waveform_status_label.set_label("Waveform unavailable: GStreamer missing")
            return
        if self._waveform_pipeline is not None:
            return

        self._waveform_monitor_name = self._resolve_monitor_source_name()
        if not self._waveform_monitor_name:
            if hasattr(self, "waveform_status_label"):
                self.waveform_status_label.set_label("Waveform unavailable: no monitor source")
            return

        pipeline_desc = (
            f"pulsesrc device={self._waveform_monitor_name} ! "
            "audioconvert ! audioresample ! audio/x-raw,format=F32LE,channels=1,rate=12000 ! "
            "appsink name=waveform_sink emit-signals=true max-buffers=2 drop=true sync=false"
        )
        try:
            self._waveform_pipeline = Gst.parse_launch(pipeline_desc)
            self._waveform_sink = self._waveform_pipeline.get_by_name("waveform_sink")
            self._waveform_sink.connect("new-sample", self._on_waveform_sample)
            self._waveform_bus = self._waveform_pipeline.get_bus()
            self._waveform_bus.add_signal_watch()
            self._waveform_bus.connect("message", self._on_waveform_bus_message)
            self._waveform_pipeline.set_state(Gst.State.PLAYING)
            if hasattr(self, "waveform_status_label"):
                self.waveform_status_label.set_label(
                    f"Live output meter from {self._waveform_monitor_name}"
                )
            log.info(f"[Waveform] Started monitor on {self._waveform_monitor_name}")
        except Exception as e:
            log.warning(f"[Waveform] Could not start pipeline: {e}")
            self._waveform_pipeline = None
            self._waveform_bus = None
            self._waveform_sink = None
            if hasattr(self, "waveform_status_label"):
                self.waveform_status_label.set_label(f"Waveform error: {e}")

    def _stop_waveform_pipeline(self):
        if not GST_AVAILABLE or self._waveform_pipeline is None:
            return
        try:
            if self._waveform_bus is not None:
                self._waveform_bus.remove_signal_watch()
            self._waveform_pipeline.set_state(Gst.State.NULL)
            log.info("[Waveform] Pipeline stopped.")
        except Exception as e:
            log.warning(f"[Waveform] Could not stop pipeline: {e}")
        finally:
            self._waveform_pipeline = None
            self._waveform_bus = None
            self._waveform_sink = None

    def _stop_spectrum_pipeline(self):
        self._stop_waveform_pipeline()

    def _draw_waveform(self, _area, cr, width, height):
        cr.set_source_rgb(0.03, 0.05, 0.08)
        cr.paint()

        min_db = -60.0
        max_db = 0.0

        def y_for_level(value: float) -> float:
            db = 20.0 * math.log10(max(value, 1e-5))
            db = max(min_db, min(max_db, db))
            return ((max_db - db) / (max_db - min_db)) * (height - 24) + 12

        grid_levels = (-48, -36, -24, -12, -6, -3, 0)
        cr.set_source_rgba(0.56, 0.70, 0.85, 0.10)
        for db in grid_levels:
            y = ((max_db - db) / (max_db - min_db)) * (height - 24) + 12
            cr.move_to(0, y)
            cr.line_to(width, y)
        cr.stroke()

        if not self._peak_history:
            return

        threshold_y = ((max_db - (-3.0)) / (max_db - min_db)) * (height - 24) + 12
        cr.set_source_rgba(1.00, 0.68, 0.29, 0.18)
        cr.rectangle(0, 0, width, threshold_y)
        cr.fill()

        step_x = width / max(1, len(self._peak_history) - 1)

        cr.set_line_width(1.6)
        cr.set_source_rgba(0.47, 0.94, 0.77, 0.92)
        for index, value in enumerate(self._rms_history):
            x = index * step_x
            y = y_for_level(value)
            if index == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()

        cr.set_line_width(2.4)
        cr.set_source_rgba(0.43, 0.84, 1.00, 0.96)
        for index, value in enumerate(self._peak_history):
            x = index * step_x
            y = y_for_level(value)
            if index == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()

    # ──────────────────────────────────────────────────────────────────
    # Main window
    # ──────────────────────────────────────────────────────────────────
    def on_activate(self, app):
        # Re-activation (from tray "Open Settings") → just raise the window.
        if hasattr(self, "window") and self.window:
            self.window.present()
            return

        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        self._install_css()
        self._init_waveform_state()
        self._init_mixer_state()
        self.start_tray_icon()

        self.window = Adw.ApplicationWindow(application=app)
        title = "PipeWire Rate Switcher [DEV]" if os.environ.get("PW_RATE_SWITCHER_DEV") else "PipeWire Rate Switcher"
        self.window.set_title(title)
        self.window.set_default_size(1220, 840)
        self.window.set_icon_name("pw-rate-switcher")
        self.window.add_css_class("pwrs-window")
        self.window.connect("close-request", self.on_window_close_request)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        root.append(Adw.HeaderBar())
        root.append(scroll)
        self.window.set_content(root)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        scroll.set_child(content)

        left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        left_panel.set_hexpand(True)
        left_panel.set_vexpand(True)
        left_panel.add_css_class("panel-shell")
        left_panel.add_css_class("panel-left")
        content.append(left_panel)

        right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        right_panel.set_size_request(430, -1)
        right_panel.set_vexpand(True)
        right_panel.add_css_class("panel-shell")
        right_panel.add_css_class("panel-right")
        content.append(right_panel)

        self._build_info_section(left_panel)
        left_panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self._build_strict_section(left_panel)
        left_panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self._build_standard_controls(left_panel)
        left_panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self._build_exclusive_section(left_panel)

        self._build_verification_section(right_panel)

        self.window.present()
        log.info("[UI] Window presented.")
        threading.Thread(target=self.monitor_pipewire, daemon=True).start()

    # ── Section builders ───────────────────────────────────────────────
    def _build_info_section(self, parent):
        self.rate_label = Gtk.Label(label="Scanning...")
        self.rate_label.add_css_class("title-1")
        self.rate_label.add_css_class("hero-rate")
        parent.append(self.rate_label)

        self.status_label = Gtk.Label(label="Initializing...")
        self.status_label.add_css_class("title-3")
        self.status_label.set_opacity(0.7)
        parent.append(self.status_label)

        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        stats_box.set_halign(Gtk.Align.CENTER)
        stats_box.add_css_class("pill-row")

        self.bit_depth_label = Gtk.Label(label="-- bit")
        self.bit_depth_label.add_css_class("card")
        stats_box.append(self.bit_depth_label)

        self.latency_label = Gtk.Label(label="-- ms")
        self.latency_label.add_css_class("card")
        stats_box.append(self.latency_label)

        self.exclusive_badge = Gtk.Label(label=" ⬡ Exclusive ")
        self.exclusive_badge.add_css_class("card")
        self.exclusive_badge.add_css_class("accent")
        self.exclusive_badge.set_visible(False)
        stats_box.append(self.exclusive_badge)

        self.strict_badge = Gtk.Label(label=" ◎ Strict ")
        self.strict_badge.add_css_class("card")
        self.strict_badge.set_visible(False)
        stats_box.append(self.strict_badge)

        parent.append(stats_box)

    def _build_strict_section(self, parent):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_halign(Gtk.Align.CENTER)
        box.add_css_class("control-row")

        lbl = Gtk.Label(label="Strict Bit-Perfect Mode")
        lbl.add_css_class("heading")
        lbl.set_tooltip_text(
            "Force 1:1 rate + quantum for all streams.\nDisables manual controls."
        )
        self.strict_title_label = lbl
        self.strict_switch = Gtk.Switch()
        self.strict_switch.set_active(False)
        self.strict_switch.connect("state-set", self.on_strict_toggled)

        box.append(lbl)
        box.append(self.strict_switch)
        parent.append(box)

        self.strict_state_label = Gtk.Label(label="Global strict: OFF")
        self.strict_state_label.set_opacity(0.7)
        self.strict_state_label.set_halign(Gtk.Align.CENTER)
        parent.append(self.strict_state_label)

    def _build_standard_controls(self, parent):
        self.standard_controls_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=15
        )
        self.standard_controls_box.add_css_class("section-block")
        parent.append(self.standard_controls_box)

        # Auto-switch toggle
        auto_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        auto_box.set_halign(Gtk.Align.CENTER)
        auto_box.add_css_class("control-row")
        auto_box.append(Gtk.Label(label="Standard Auto-Switch"))
        self.auto_switch = Gtk.Switch()
        self.auto_switch.set_active(True)
        self.auto_switch.connect("state-set", self.on_auto_toggled)
        auto_box.append(self.auto_switch)
        self.standard_controls_box.append(auto_box)

        # Manual rate grid
        lbl = Gtk.Label(label="Manual Override")
        lbl.add_css_class("heading")
        self.standard_controls_box.append(lbl)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_halign(Gtk.Align.CENTER)
        for i, rate in enumerate(["44100", "48000", "88200", "96000", "176400", "192000"]):
            btn = Gtk.Button(label=f"{int(rate) // 1000} kHz")
            btn.connect("clicked", self.on_manual_click, rate)
            btn.set_size_request(100, 40)
            grid.attach(btn, i % 2, i // 2, 1, 1)
            self.manual_buttons.append(btn)
        self.standard_controls_box.append(grid)

    def _build_exclusive_section(self, parent):
        title = Gtk.Label(label="App Audio Profiles")
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.CENTER)
        title.set_tooltip_text(
            "Per-app audio behaviour:\n"
            "• Exclusive — bit-perfect DAC output: exact rate+quantum lock, 100% volume.\n"
            "  Takes priority over all other concurrent streams.\n"
            "• Strict — force exact rate+quantum match (no volume override).\n"
            "\n"
            "Priority when multiple apps play simultaneously:\n"
            "  Exclusive  >  Strict  >  Auto"
        )
        parent.append(title)

        desc = Gtk.Label(
            label="Exclusive and Strict settings are saved per-app and persist across restarts."
        )
        desc.set_wrap(True)
        desc.set_opacity(0.55)
        desc.set_halign(Gtk.Align.CENTER)
        desc.add_css_class("muted-note")
        parent.append(desc)

        self.output_profile_status_label = Gtk.Label(label="Current output: detecting...")
        self.output_profile_status_label.set_wrap(True)
        self.output_profile_status_label.set_halign(Gtk.Align.CENTER)
        self.output_profile_status_label.add_css_class("muted-note")
        parent.append(self.output_profile_status_label)
        self._refresh_output_profile_status()

        self.app_listbox = Gtk.ListBox()
        self.app_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.app_listbox.add_css_class("boxed-list")
        ph = Gtk.Label(label="No apps added yet")
        ph.set_opacity(0.4)
        ph.set_margin_top(10)
        ph.set_margin_bottom(10)
        self.app_listbox.set_placeholder(ph)
        parent.append(self.app_listbox)
        self._refresh_app_profiles_list()

        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.set_halign(Gtk.Align.CENTER)
        add_box.add_css_class("toolbar-row")

        self.excl_entry = Gtk.Entry()
        self.excl_entry.set_placeholder_text("App name (e.g. spotify)")
        self.excl_entry.set_size_request(170, -1)
        self.excl_entry.connect("activate", self._on_add_exclusive_entry)
        add_box.append(self.excl_entry)

        add_btn = Gtk.Button(label="+ Add")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", self._on_add_exclusive_entry)
        add_box.append(add_btn)

        self.add_current_btn = Gtk.Button(label="Add Current App")
        self.add_current_btn.set_sensitive(False)
        self.add_current_btn.connect("clicked", self._on_add_current_app)
        add_box.append(self.add_current_btn)

        parent.append(add_box)

    def _build_verification_section(self, parent):
        mixer_title = Gtk.Label(label="PipeWire Mixer")
        mixer_title.add_css_class("heading")
        mixer_title.set_halign(Gtk.Align.CENTER)
        parent.append(mixer_title)

        mixer_note = Gtk.Label(label="All active audio apps, each with its own volume and mute like a desktop mixer.")
        mixer_note.set_wrap(True)
        mixer_note.set_xalign(0.0)
        mixer_note.add_css_class("section-note")
        parent.append(mixer_note)

        self.mixer_listbox = Gtk.ListBox()
        self.mixer_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.mixer_listbox.add_css_class("boxed-list")
        self.mixer_listbox.add_css_class("mixer-shell")
        mixer_placeholder = Gtk.Label(label="No apps are using audio right now")
        mixer_placeholder.set_margin_top(10)
        mixer_placeholder.set_margin_bottom(10)
        mixer_placeholder.add_css_class("muted-note")
        self.mixer_listbox.set_placeholder(mixer_placeholder)
        parent.append(self.mixer_listbox)

        title = Gtk.Label(label="Bit-Perfect Verification")
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.CENTER)
        parent.append(title)

        lock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lock_box.set_halign(Gtk.Align.CENTER)
        lock_box.add_css_class("control-row")
        lock_box.append(Gtk.Label(label="Hard Lock Competing Streams"))
        self.hard_lock_switch = Gtk.Switch()
        self.hard_lock_switch.set_active(self.hard_lock_enabled)
        self.hard_lock_switch.set_tooltip_text(
            "When an exclusive app is active, immediately mute every other audio stream."
        )
        self.hard_lock_switch.connect("state-set", self.on_hard_lock_toggled)
        lock_box.append(self.hard_lock_switch)
        parent.append(lock_box)

        self.verify_status_label = Gtk.Label(label="Status: Waiting for stream")
        self.verify_status_label.set_wrap(True)
        self.verify_status_label.set_halign(Gtk.Align.START)
        parent.append(self.verify_status_label)

        self.verify_owner_label = Gtk.Label(label="Owner: --")
        self.verify_owner_label.set_halign(Gtk.Align.START)
        parent.append(self.verify_owner_label)

        self.verify_clock_label = Gtk.Label(label="Clock: --")
        self.verify_clock_label.set_halign(Gtk.Align.START)
        parent.append(self.verify_clock_label)

        self.verify_dac_label = Gtk.Label(label="DAC Output: --")
        self.verify_dac_label.set_halign(Gtk.Align.START)
        self.verify_dac_label.set_wrap(True)
        parent.append(self.verify_dac_label)

        self.verify_streams_label = Gtk.Label(label="Streams: --")
        self.verify_streams_label.set_halign(Gtk.Align.START)
        parent.append(self.verify_streams_label)

        self.verify_note_label = Gtk.Label(label="Integrity: --")
        self.verify_note_label.set_wrap(True)
        self.verify_note_label.set_halign(Gtk.Align.START)
        self.verify_note_label.set_opacity(0.75)
        parent.append(self.verify_note_label)

        diagram_title = Gtk.Label(label="Live Signal Path")
        diagram_title.add_css_class("heading")
        diagram_title.set_halign(Gtk.Align.CENTER)
        parent.append(diagram_title)

        signal_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        signal_shell.add_css_class("path-strip")
        signal_shell.add_css_class("section-block")
        parent.append(signal_shell)

        self.signal_path_state_label = Gtk.Label(label="Waiting for stream")
        self.signal_path_state_label.set_wrap(True)
        self.signal_path_state_label.set_xalign(0.0)
        signal_shell.append(self.signal_path_state_label)

        self.signal_path_nodes_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.signal_path_nodes_box.set_halign(Gtk.Align.START)
        signal_shell.append(self.signal_path_nodes_box)

        self.signal_path_competing_label = Gtk.Label(label="Competing streams: --")
        self.signal_path_competing_label.set_wrap(True)
        self.signal_path_competing_label.set_xalign(0.0)
        self.signal_path_competing_label.add_css_class("section-note")
        signal_shell.append(self.signal_path_competing_label)

        graph_disabled_title = Gtk.Label(label="Graph")
        graph_disabled_title.add_css_class("heading")
        graph_disabled_title.set_halign(Gtk.Align.CENTER)
        parent.append(graph_disabled_title)

        graph_disabled_note = Gtk.Label(label="Live graph disabled.")
        graph_disabled_note.set_wrap(True)
        graph_disabled_note.set_xalign(0.0)
        graph_disabled_note.add_css_class("section-note")
        parent.append(graph_disabled_note)

    def _create_path_node(self, title: str, is_owner: bool = False):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.add_css_class("path-node")
        if is_owner:
            card.add_css_class("path-node-owner")

        label = Gtk.Label(label=title)
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_halign(Gtk.Align.CENTER)
        card.append(label)
        return card

    def _render_signal_path_nodes(self, nodes, owner_mode: str):
        while (child := self.signal_path_nodes_box.get_first_child()) is not None:
            self.signal_path_nodes_box.remove(child)

        for index, node in enumerate(nodes):
            self.signal_path_nodes_box.append(
                self._create_path_node(node, is_owner=(index == 0 and owner_mode == "EXCLUSIVE"))
            )
            if index < len(nodes) - 1:
                arrow = Gtk.Label(label="→")
                arrow.add_css_class("title-4")
                self.signal_path_nodes_box.append(arrow)

    def _extract_sink_input_name(self, sink_input: dict) -> str:
        props = sink_input.get("properties", {})
        name = (
            props.get("application.name")
            or props.get("application.process.binary")
            or props.get("media.name")
            or props.get("node.name")
            or "Unknown"
        )
        if name and name[0].islower() and " " not in name:
            name = name.capitalize()
        return name

    def _read_sink_input_percent(self, sink_input: dict) -> int:
        volume = sink_input.get("volume", {})
        for channel in volume.values():
            percent = str(channel.get("value_percent", "100%")).strip().replace("%", "")
            if percent.replace(".", "", 1).isdigit():
                return int(float(percent))
        return 100

    def _on_mixer_volume_changed(self, scale, sink_input_id: int, percent_label):
        percent = int(round(scale.get_value()))
        percent_label.set_label(f"{percent}%")
        try:
            subprocess.run(
                ["pactl", "set-sink-input-volume", str(sink_input_id), f"{percent}%"],
                capture_output=True,
                check=False,
            )
        except Exception as e:
            log.warning(f"[Mixer] Could not set volume for sink-input {sink_input_id}: {e}")

    def _on_mixer_mute_toggled(self, button, sink_input_id: int):
        state = bool(button.get_active())
        button.set_label("Muted" if state else "Mute")
        try:
            subprocess.run(
                ["pactl", "set-sink-input-mute", str(sink_input_id), "1" if state else "0"],
                capture_output=True,
                check=False,
            )
        except Exception as e:
            log.warning(f"[Mixer] Could not set mute for sink-input {sink_input_id}: {e}")

    def update_audio_mixer(self, sink_inputs, active_app_name: str | None):
        if not hasattr(self, "mixer_listbox"):
            return False

        while (row := self.mixer_listbox.get_row_at_index(0)) is not None:
            self.mixer_listbox.remove(row)

        for sink_input in sorted(sink_inputs, key=lambda entry: self._extract_sink_input_name(entry).lower()):
            sink_input_id = sink_input.get("index")
            app_name = self._extract_sink_input_name(sink_input)
            volume_percent = self._read_sink_input_percent(sink_input)
            is_muted = bool(sink_input.get("mute"))
            is_corked = bool(sink_input.get("corked"))
            is_active = bool(active_app_name) and app_name.lower() == active_app_name.lower()

            row = Gtk.ListBoxRow()
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            card.add_css_class("mixer-row")

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            title = Gtk.Label(label=app_name)
            title.set_hexpand(True)
            title.set_xalign(0.0)
            title.add_css_class("title-5")
            header.append(title)

            badge = Gtk.Label(
                label=("Active" if is_active else "Paused" if is_corked else "Live")
            )
            badge.add_css_class("card")
            header.append(badge)
            card.append(header)

            control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            slider.set_hexpand(True)
            slider.set_draw_value(False)
            slider.set_value(volume_percent)
            percent_label = Gtk.Label(label=f"{volume_percent}%")
            slider.connect("value-changed", self._on_mixer_volume_changed, sink_input_id, percent_label)
            control_row.append(slider)
            control_row.append(percent_label)

            mute_button = Gtk.ToggleButton(label="Muted" if is_muted else "Mute")
            mute_button.set_active(is_muted)
            mute_button.connect("toggled", self._on_mixer_mute_toggled, sink_input_id)
            control_row.append(mute_button)
            card.append(control_row)

            row.set_child(card)
            self.mixer_listbox.append(row)

        return False

    def _refresh_output_profile_status(self):
        if not hasattr(self, "output_profile_status_label"):
            return
        sink_info = self._get_default_sink_info() if hasattr(self, "_get_default_sink_info") else None
        if not sink_info:
            self.output_profile_status_label.set_label("Current output: unavailable")
            return
        self.output_profile_status_label.set_label(
            f"Current output: {self._describe_sink(sink_info)}"
        )

    def _format_output_binding(self, app_name: str) -> str:
        sink_name = self.preferred_sink_by_app.get(app_name)
        if not sink_name:
            return "System default output"
        sink_info = self._get_sink_info(sink_name) if hasattr(self, "_get_sink_info") else None
        return self._describe_sink(sink_info) if sink_info else sink_name

    def _on_bind_app_output(self, _widget, app_name: str):
        sink_info = self._get_default_sink_info() if hasattr(self, "_get_default_sink_info") else None
        if not sink_info:
            log.warning(f"[Profile] Could not bind output for {app_name}: no active sink found")
            return
        self.preferred_sink_by_app[app_name] = sink_info["name"]
        self.preferences["preferred_sink_by_app"] = dict(self.preferred_sink_by_app)
        self._save_preferences()
        self._refresh_app_profiles_list()
        self._refresh_output_profile_status()
        log.info(f"[Profile] Bound {app_name} to output {sink_info['name']}")

    def _on_clear_app_output(self, _widget, app_name: str):
        if app_name in self.preferred_sink_by_app:
            self.preferred_sink_by_app.pop(app_name, None)
            self.preferences["preferred_sink_by_app"] = dict(self.preferred_sink_by_app)
            self._save_preferences()
            self._refresh_app_profiles_list()
            log.info(f"[Profile] Cleared preferred output for {app_name}")

    # ── App profiles list management ──────────────────────────────────
    def _refresh_app_profiles_list(self):
        while (row := self.app_listbox.get_row_at_index(0)) is not None:
            self.app_listbox.remove(row)
        all_apps = self.exclusive_apps | self.strict_apps
        for app in sorted(all_apps):
            row  = Gtk.ListBoxRow()
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.add_css_class("profile-card")
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hbox.set_margin_top(6)
            hbox.set_margin_bottom(2)
            hbox.set_margin_start(8)
            hbox.set_margin_end(8)

            lbl = Gtk.Label(label=app.capitalize())
            lbl.set_hexpand(True)
            lbl.set_halign(Gtk.Align.START)
            hbox.append(lbl)

            # Exclusive toggle
            excl_lbl = Gtk.Label(label="Excl.")
            excl_lbl.set_opacity(0.65)
            hbox.append(excl_lbl)
            excl_sw = Gtk.Switch()
            excl_sw.set_active(app in self.exclusive_apps)
            excl_sw.set_valign(Gtk.Align.CENTER)
            excl_sw.set_tooltip_text("Exclusive DAC: lock rate+quantum and force 100% volume")
            excl_sw.connect("state-set", self._on_excl_toggled, app)
            hbox.append(excl_sw)

            # Strict toggle
            strict_lbl = Gtk.Label(label="Strict")
            strict_lbl.set_opacity(0.65)
            strict_lbl.set_margin_start(4)
            hbox.append(strict_lbl)
            strict_sw = Gtk.Switch()
            strict_sw.set_active(app in self.strict_apps)
            strict_sw.set_valign(Gtk.Align.CENTER)
            strict_sw.set_tooltip_text("Strict: force exact rate+quantum (no volume override)")
            strict_sw.connect("state-set", self._on_strict_app_toggled, app)
            hbox.append(strict_sw)

            rm = Gtk.Button(label="✕")
            rm.add_css_class("destructive-action")
            rm.add_css_class("flat")
            rm.connect("clicked", self._on_remove_app_profile, app)
            hbox.append(rm)

            route_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            route_box.add_css_class("toolbar-row")
            route_box.set_margin_start(8)
            route_box.set_margin_end(8)
            route_box.set_margin_bottom(6)
            route_label = Gtk.Label(label=f"Output: {self._format_output_binding(app)}")
            route_label.set_hexpand(True)
            route_label.set_xalign(0.0)
            route_label.add_css_class("muted-note")
            route_box.append(route_label)

            bind_btn = Gtk.Button(label="Bind Current Output")
            bind_btn.add_css_class("flat")
            bind_btn.connect("clicked", self._on_bind_app_output, app)
            route_box.append(bind_btn)

            if app in self.preferred_sink_by_app:
                clear_btn = Gtk.Button(label="Clear")
                clear_btn.add_css_class("flat")
                clear_btn.connect("clicked", self._on_clear_app_output, app)
                route_box.append(clear_btn)

            card.append(hbox)
            card.append(route_box)
            row.set_child(card)
            self.app_listbox.append(row)

    def _on_excl_toggled(self, _switch, state: bool, app_name: str):
        if state:
            self.exclusive_apps.add(app_name)
        else:
            self.exclusive_apps.discard(app_name)
        self._save_exclusive_apps()
        log.info(f"[Profile] {app_name}: exclusive={state}")
        return False

    def _on_strict_app_toggled(self, _switch, state: bool, app_name: str):
        if state:
            self.strict_apps.add(app_name)
        else:
            self.strict_apps.discard(app_name)
        self._save_strict_apps()
        log.info(f"[Profile] {app_name}: strict={state}")
        return False

    def _on_add_exclusive_entry(self, _widget):
        name = self.excl_entry.get_text().strip().lower()
        if name:
            self.exclusive_apps.add(name)
            self._save_exclusive_apps()
            self._refresh_app_profiles_list()
            self.excl_entry.set_text("")
            log.info(f"[Profile] Added app: {name} (exclusive=True)")

    def _on_add_current_app(self, _widget):
        if self._active_app_name:
            name = self._active_app_name.lower()
            self.exclusive_apps.add(name)
            self._save_exclusive_apps()
            self._refresh_app_profiles_list()
            GLib.idle_add(self._sync_add_current_btn, self._active_app_name)
            log.info(f"[Profile] Added current app: {name} (exclusive=True)")

    def _on_remove_app_profile(self, _widget, app_name: str):
        self.exclusive_apps.discard(app_name)
        self.strict_apps.discard(app_name)
        self._save_exclusive_apps()
        self._save_strict_apps()
        self._refresh_app_profiles_list()
        log.info(f"[Profile] Removed app profile: {app_name}")

    # ── Tray / lifecycle ──────────────────────────────────────────────
    def start_tray_icon(self):
        if os.environ.get("PW_RATE_SWITCHER_DISABLE_TRAY"):
            log.debug("[Tray] Disabled by environment.")
            return
        if self.tray_process is None:
            log.debug("[Tray] Launching tray process.")
            self.tray_process = __import__("subprocess").Popen(
                [sys.executable, sys.argv[0], "--tray"]
            )

    def on_window_close_request(self, _window):
        log.info("[UI] Window hidden — running in system tray.")
        self.window.hide()
        return True

    # ── Mode toggles ──────────────────────────────────────────────────
    def on_strict_toggled(self, _switch, state: bool):
        self.strict_mode = state
        self.standard_controls_box.set_sensitive(not state)
        if state:
            log.info("[Mode] Strict Bit-Perfect ON.")
            self.auto_mode = True
            self.rate_label.add_css_class("accent")
        else:
            log.info("[Mode] Strict Bit-Perfect OFF.")
            self.auto_mode = self.auto_switch.get_active()
            self.rate_label.remove_css_class("accent")
        self._sync_strict_ui(False, None)
        self.current_rate = "Unknown"
        return False

    def on_auto_toggled(self, _switch, state: bool):
        if not self.strict_mode:
            self.auto_mode = state
            log.info(f"[Mode] Auto-switch {'ON' if state else 'OFF'}.")
        return False

    def on_manual_click(self, _button, rate: str):
        if not self.strict_mode:
            log.info(f"[Mode] Manual override → {rate} Hz.")
            self.auto_mode = False
            self.auto_switch.set_active(False)
            self.apply_rate(rate, 0)

    def on_hard_lock_toggled(self, _switch, state: bool):
        self.hard_lock_enabled = state
        self.preferences["hard_lock_enabled"] = state
        self._save_preferences()
        if not state:
            self._restore_exclusive_isolation()
        log.info(f"[Mode] Hard-lock {'ON' if state else 'OFF'}.")
        return False

    # ── UI update helpers (GLib main thread via idle_add) ─────────────
    def _sync_add_current_btn(self, app_name):
        if hasattr(self, "add_current_btn"):
            already_added = bool(app_name) and (
                app_name.lower() in self.exclusive_apps
                or app_name.lower() in self.strict_apps
            )
            self.add_current_btn.set_sensitive(bool(app_name) and not already_added)
            self.add_current_btn.set_label(
                f"Add  '{app_name}'" if app_name else "Add Current App"
            )
        return False

    def update_ui(self, rate, app_name, fmt, latency, is_exclusive=False):
        self.rate_label.set_label(f"{rate} Hz")
        self.status_label.set_label(str(app_name))
        if hasattr(self, "waveform_status_label"):
            self.waveform_status_label.set_label(f"Amplifier level live from {app_name}")
        self._refresh_output_profile_status()

        fmt_map = {
            "F32LE": "32-bit Float", "S32LE": "32-bit Int",
            "S24LE": "24-bit",       "S16LE": "16-bit",
            "S24_32LE": "24/32-bit",
        }
        self.bit_depth_label.set_label(f" {fmt_map.get(fmt, fmt or 'Unknown')} ")
        self.latency_label.set_label(f" {latency} ")
        if hasattr(self, "exclusive_badge"):
            self.exclusive_badge.set_visible(is_exclusive)
        return False

    def update_active_mode(self, is_strict_active: bool, strict_owner: str | None):
        self._sync_strict_ui(is_strict_active, strict_owner)
        if hasattr(self, "strict_badge"):
            self.strict_badge.set_visible(is_strict_active)
        return False

    def _sync_strict_ui(self, is_strict_active: bool, strict_owner: str | None):
        if not hasattr(self, "strict_state_label"):
            return

        if self.strict_mode:
            self.strict_title_label.set_label("Strict Bit-Perfect Mode (Global)")
            self.strict_state_label.set_label("Global strict: ON for all streams")
            return

        if is_strict_active and strict_owner:
            self.strict_title_label.set_label("Strict Bit-Perfect Mode (Per-App Active)")
            self.strict_state_label.set_label(f"Per-app strict active: {strict_owner}")
        else:
            self.strict_title_label.set_label("Strict Bit-Perfect Mode")
            self.strict_state_label.set_label("Global strict: OFF")

    def update_verification(self, status, owner, clock, dac_output, streams, note):
        if hasattr(self, "verify_status_label"):
            self.verify_status_label.set_label(f"Status: {status}")
            self.verify_owner_label.set_label(f"Owner: {owner}")
            self.verify_clock_label.set_label(f"Clock: {clock}")
            self.verify_dac_label.set_label(f"DAC Output: {dac_output}")
            self.verify_streams_label.set_label(f"Streams: {streams}")
            self.verify_note_label.set_label(f"Integrity: {note}")
        return False

    def update_signal_diagram(self, diagram_text: str):
        if isinstance(diagram_text, dict) and hasattr(self, "signal_path_state_label"):
            self.signal_path_state_label.set_label(diagram_text.get("summary", "Waiting for stream"))
            self.signal_path_competing_label.set_label(
                "Competing streams: " + ", ".join(
                    f"{entry['app_name']} ({entry['state']})"
                    for entry in diagram_text.get("competing", [])
                )
                if diagram_text.get("competing") else "Competing streams: none"
            )
            self._render_signal_path_nodes(
                diagram_text.get("route_nodes", []),
                diagram_text.get("owner_mode", "AUTO"),
            )
            return False

        if hasattr(self, "signal_path_state_label"):
            self.signal_path_state_label.set_label(str(diagram_text))
        return False

    def update_status(self, text: str):
        self.status_label.set_label(text)
        self.rate_label.set_label("Scanning...")
        self.bit_depth_label.set_label("--")
        self.latency_label.set_label("--")
        if hasattr(self, "exclusive_badge"):
            self.exclusive_badge.set_visible(False)
        if hasattr(self, "strict_badge"):
            self.strict_badge.set_visible(False)
        self._sync_strict_ui(False, None)
        self.update_verification("Waiting for stream", "--", "--", "--", "--", "No active stream")
        if hasattr(self, "waveform_status_label"):
            self.waveform_status_label.set_label("Amplifier level waiting for audio")
        if hasattr(self, "meter_peak_label"):
            self.meter_peak_label.set_label("Peak -- dBFS")
            self.meter_rms_label.set_label("RMS -- dBFS")
            self.meter_headroom_label.set_label("Headroom -- dB")
            self.meter_clip_label.set_label("Safe")
        self.update_signal_diagram(
            {
                "summary": "No active stream. The chain is idle and ready.",
                "route_nodes": ["Source", "PipeWire Mixer", "DAC", "Amplifier"],
                "competing": [],
                "owner_mode": "AUTO",
            }
        )
        self.update_audio_mixer([], None)
        self._refresh_output_profile_status()
        return False
