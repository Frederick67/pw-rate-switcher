/**
 * PipeWire Rate Switcher — Cinnamon panel applet
 *
 * Shows the current PipeWire clock rate in the panel.
 * Click to open a popup with:
 *   • Active audio streams (who is using audio)
 *   • Per-stream volume slider and mute toggle
 *   • Button to open the full GTK settings window
 *
 * Requires: pw-metadata, pactl  (both present when pw-rate-switcher is installed)
 */

const Applet      = imports.ui.applet;
const PopupMenu   = imports.ui.popupMenu;
const GLib        = imports.gi.GLib;
const St          = imports.gi.St;
const Clutter     = imports.gi.Clutter;
const Mainloop    = imports.mainloop;
const Util        = imports.misc.util;

// ─── I/O helpers ─────────────────────────────────────────────────────────────

function _toStr(bytes) {
    if (!bytes) return "";
    if (typeof bytes === "string") return bytes;
    try { return imports.byteArray.toString(bytes); }
    catch (_) { return String.fromCharCode.apply(null, new Uint8Array(bytes)); }
}

/** Run argv synchronously, return trimmed stdout or "" on any error. */
function _run(argv) {
    try {
        const [ok, stdout] = GLib.spawn_sync(
            null, argv, null, GLib.SpawnFlags.SEARCH_PATH, null
        );
        if (ok) return _toStr(stdout).trim();
    } catch (_) {}
    return "";
}

/** Fire-and-forget shell command. */
function _async(cmd) {
    try { GLib.spawn_command_line_async(cmd); } catch (_) {}
}

// ─── PipeWire / PulseAudio queries ───────────────────────────────────────────

/** Return PipeWire clock settings from pw-metadata. */
function _getPWSettings() {
    const out = _run(["pw-metadata", "-n", "settings", "0"]);
    const _i  = (re) => { const m = out.match(re); return m ? parseInt(m[1], 10) : 0; };
    return {
        forceRate:    _i(/clock\.force-rate' value:'(\d+)'/),
        actualRate:   _i(/clock\.rate' value:'(\d+)'/),
        actualQuantum:_i(/clock\.quantum' value:'(\d+)'/),
    };
}

/** Return the list of active PulseAudio sink-inputs from pactl. */
function _getSinkInputs() {
    const raw = _run(["pactl", "--format=json", "list", "sink-inputs"]);
    try { return JSON.parse(raw) || []; }
    catch (_) { return []; }
}

/** Return a map of sink index → human-readable description. */
function _getSinks() {
    const raw = _run(["pactl", "--format=json", "list", "sinks"]);
    try {
        const map = {};
        for (const s of (JSON.parse(raw) || []))
            map[s.index] = s.description || s.name || `Sink ${s.index}`;
        return map;
    } catch (_) { return {}; }
}

/** Resolve a human-readable app name from sink-input properties. */
function _appName(props) {
    const raw = (
        props["application.name"]           ||
        props["application.process.binary"] ||
        props["media.name"]                 ||
        props["node.name"]                  ||
        "Unknown"
    ).trim();
    // Capitalise single-word lowercase names (e.g. "spotify" → "Spotify")
    return (raw.length && raw[0] === raw[0].toLowerCase() && !/\s/.test(raw))
        ? raw[0].toUpperCase() + raw.slice(1)
        : raw;
}

/** Read volume percent from a sink-input object (first channel). */
function _volPct(si) {
    const volume = si.volume || {};
    for (const ch in volume) {
        const raw = String(volume[ch].value_percent || "100%").replace("%", "").trim();
        const v   = parseFloat(raw);
        if (!isNaN(v)) return Math.round(v);
    }
    return 100;
}

/** Format a rate integer as a human-readable kHz string. */
function _fmtRate(rate) {
    if (!rate || rate <= 0) return "Auto";
    if (rate % 1000 === 0) return `${rate / 1000}k`;
    return `${(rate / 1000).toFixed(1)}k`;
}

/** Format the sample spec of a sink-input (format · channels · rate). */
function _fmtSpec(si) {
    const spec = si.sample_specification;
    if (spec && typeof spec === "object" && spec.format) {
        const fmt = spec.format.replace(/le$|be$/i, "").toUpperCase();
        const ch  = spec.channels === 2 ? "Stereo" : spec.channels === 1 ? "Mono" : `${spec.channels}ch`;
        const r   = spec.rate ? _fmtRate(spec.rate) : "";
        return [fmt, ch, r].filter(Boolean).join(" · ");
    }
    if (typeof spec === "string" && spec.trim()) {
        const p   = spec.trim().split(/\s+/);
        const fmt = (p[0] || "").replace(/le$|be$/i, "").toUpperCase();
        const ch  = p[1] === "2ch" ? "Stereo" : p[1] === "1ch" ? "Mono" : (p[1] || "");
        const rn  = parseInt(p[2]);
        const r   = isNaN(rn) ? "" : _fmtRate(rn);
        return [fmt, ch, r].filter(Boolean).join(" · ");
    }
    const fp = si.format && si.format.properties;
    if (fp) {
        const fmt = (fp["format.sample_format"] || "").replace(/le$|be$/i, "").toUpperCase();
        const chN = parseInt(fp["format.channels"]);
        const ch  = chN === 2 ? "Stereo" : chN === 1 ? "Mono" : chN ? `${chN}ch` : "";
        const rn  = parseInt(fp["format.rate"]);
        const r   = isNaN(rn) ? "" : _fmtRate(rn);
        return [fmt, ch, r].filter(Boolean).join(" · ");
    }
    return "";
}

/** Format sink-input latency as a ms string. */
function _fmtLatency(si) {
    let usec = 0;
    if (typeof si.latency === "number")          usec = si.latency;
    else if (si.latency && typeof si.latency === "object")
        usec = si.latency.actual || si.latency.configured || 0;
    if (!usec) return "";
    const ms = usec / 1000;
    return `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`;
}

// ─── Applet ───────────────────────────────────────────────────────────────────

class PWSwitcherApplet extends Applet.TextIconApplet {

    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);

        // Font Awesome volume-high icon (SVG shipped with applet)
        this.set_applet_icon_path(metadata.path + "/icon.svg");
        this.set_applet_label("");
        
        this.set_applet_tooltip("PipeWire Rate Switcher — click to open mixer");

        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu        = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);
        
        // Apply custom CSS class to the menu wrapper
        if (this.menu.box) {
            this.menu.box.add_style_class_name("pw-menu-container");
        }

        // Cached state
        this._rate        = 0;
        this._actualRate  = 0;
        this._quantum     = 0;
        this._inputs      = [];
        this._sinks       = {};
        this._pollId      = null;

        // Rebuild mixer every time the popup opens
        this.menu.connect("open-state-changed", (_, open) => {
            if (open) {
                this._fetchData();
                this._rebuildMenu();
            }
        });

        this._startPolling();
    }

    // ── Data ──────────────────────────────────────────────────────────────────

    _fetchData() {
        const pw         = _getPWSettings();
        this._rate       = pw.forceRate;
        this._actualRate = pw.actualRate;
        this._quantum    = pw.actualQuantum;
        this._inputs     = _getSinkInputs();
        this._sinks      = _getSinks();
    }

    _updatePanelLabel() {
        const live     = this._inputs.filter(si => !si.corked && !si.mute);
        const dispRate = this._rate > 0 ? this._rate : this._actualRate;
        const rateStr  = dispRate > 0 ? `${(dispRate / 1000).toFixed(1)} kHz` : "Auto";
        const appsStr  = live.length
            ? live.map(si => _appName(si.properties || {})).join(" · ")
            : "Idle";

        this.set_applet_label(_fmtRate(dispRate));
        this.set_applet_tooltip(`PipeWire ${rateStr} — ${appsStr}`);
    }

    // ── Menu ──────────────────────────────────────────────────────────────────

    _rebuildMenu() {
        this.menu.removeAll();

        // ── Status header ──
        const dispRate = this._rate > 0 ? this._rate : this._actualRate;
        const rateStr  = dispRate > 0 ? _fmtRate(dispRate) : "Auto";
        const forced   = this._rate > 0 ? "  (forced)" : "";
        const latMs    = (dispRate > 0 && this._quantum > 0)
            ? `  ·  ${(this._quantum / dispRate * 1000).toFixed(1)} ms`
            : "";
        const bufStr   = this._quantum > 0 ? `  ·  ${this._quantum} buf` : "";

        this._addInfoRow(`\u266a  ${rateStr}${forced}${bufStr}${latMs}`, "pw-header-row");

        const live    = this._inputs.filter(si => !si.corked);
        const names   = live.map(si => _appName(si.properties || {}));
        const summary = names.length
            ? names.join("  ·  ")
            : "No active streams";
        this._addInfoRow(summary, "pw-summary-row");

        // ── Mixer ──
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(_("Active Streams")));

        if (this._inputs.length === 0) {
            this._addInfoRow("No audio streams active");
        } else {
            // Sort: active (non-corked, non-muted) first
            const sorted = [...this._inputs].sort((a, b) => {
                const aLive = !a.corked && !a.mute ? 0 : 1;
                const bLive = !b.corked && !b.mute ? 0 : 1;
                return aLive - bLive;
            });
            for (const si of sorted) {
                this._addMixerEntry(si);
            }
        }

        // ── Footer ──
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const openItem = new PopupMenu.PopupMenuItem(_("Open PipeWire Rate Switcher…"));
        openItem.connect("activate", () => Util.spawnCommandLine("pw-rate-switcher"));
        this.menu.addMenuItem(openItem);
    }

    /** Add a non-interactive text row to the menu. */
    _addInfoRow(text, styleClass) {
        const item = new PopupMenu.PopupMenuItem(text, { reactive: false });
        if (styleClass) item.actor.add_style_class_name(styleClass);
        this.menu.addMenuItem(item);
    }

    /** Add one app entry: a header row + a volume slider. */
    _addMixerEntry(si) {
        const props  = si.properties || {};
        const name   = _appName(props);
        const id     = si.index;
        let   muted  = !!(si.mute);
        const corked = !!(si.corked);
        let   vol    = _volPct(si);

        // ── App name row ──────────────────────────────────────────────
        const nameItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });

        const hbox = new St.BoxLayout({
            vertical:  false,
            x_expand:  true,
            style_class: "pw-app-box"
        });

        // App name label (expands)
        const nameLabel = new St.Label({
            text:    name,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: "pw-app-name"
        });
        hbox.add_child(nameLabel);

        // Status badge
        const statusText  = muted ? "\u2715" : corked ? "\u23f8" : "\u25cf";
        const statusClass = muted   ? "pw-app-status pw-app-status-muted"
                          : corked  ? "pw-app-status pw-app-status-paused"
                                    : "pw-app-status";
        const statusLabel = new St.Label({
            text:    statusText,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: statusClass
        });
        hbox.add_child(statusLabel);

        // Volume percentage display (updated by slider)
        const volLabel = new St.Label({
            text:    `${vol}%`,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: "pw-app-vol"
        });
        hbox.add_child(volLabel);

        // Mute toggle button
        const muteBtn = new St.Button({
            label:     muted ? "Unmute" : "Mute",
            reactive:  true,
            can_focus: true,
            y_align:   Clutter.ActorAlign.CENTER,
            style_class: "pw-mute-btn"
        });
        muteBtn.connect("clicked", () => {
            muted = !muted;
            muteBtn.set_label(muted ? "Unmute" : "Mute");
            statusLabel.set_text(muted ? "\u2715" : (corked ? "\u23f8" : "\u25cf"));
            statusLabel.set_style_class_name(
                muted  ? "pw-app-status pw-app-status-muted"
                       : (corked ? "pw-app-status pw-app-status-paused" : "pw-app-status")
            );
            _async(`pactl set-sink-input-mute ${id} ${muted ? "1" : "0"}`);
        });
        hbox.add_child(muteBtn);

        // Attach custom hbox to the PopupBaseMenuItem actor
        try {
            nameItem.addActor(hbox, { expand: true, span: -1 });
        } catch (_) {
            nameItem.actor.add_child(hbox);
        }
        this.menu.addMenuItem(nameItem);

        // ── App info row (format · latency · sink) ────────────────────
        const spec      = _fmtSpec(si);
        const latency   = _fmtLatency(si);
        const sinkName  = this._sinks[si.sink] || "";
        const exclusive = (props["pipewire.access"] === "exclusive" ||
                           props["node.exclusive"]  === "true");
        const sinkShort = sinkName.length > 32 ? sinkName.slice(0, 30) + "\u2026" : sinkName;
        const infoParts = [spec, latency, sinkShort].filter(Boolean);
        if (infoParts.length || exclusive) {
            const infoText = (exclusive ? "\u26a1 Exclusive  " : "") + infoParts.join("  ·  ");
            const infoItem = new PopupMenu.PopupMenuItem(infoText, { reactive: false });
            infoItem.actor.add_style_class_name(
                exclusive ? "pw-app-info pw-app-info-exclusive" : "pw-app-info"
            );
            this.menu.addMenuItem(infoItem);
        }

        // ── Volume slider ─────────────────────────────────────────────
        const slider = new PopupMenu.PopupSliderMenuItem(vol / 100);

        // Debounced pactl call: apply 150 ms after last drag event
        let debounceId = null;
        slider.connect("value-changed", (s) => {
            const pct = Math.round((s._value !== undefined ? s._value : vol / 100) * 100);
            volLabel.set_text(`${pct}%`);
            vol = pct;

            if (debounceId !== null) {
                GLib.source_remove(debounceId);
                debounceId = null;
            }
            debounceId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
                _async(`pactl set-sink-input-volume ${id} ${pct}%`);
                debounceId = null;
                return GLib.SOURCE_REMOVE;
            });
        });

        this.menu.addMenuItem(slider);
    }

    // ── Polling ───────────────────────────────────────────────────────────────

    _startPolling() {
        this._fetchData();
        this._updatePanelLabel();

        // Update panel label every 2 seconds in the background
        this._pollId = Mainloop.timeout_add_seconds(2, () => {
            this._fetchData();
            this._updatePanelLabel();
            return true; // GLib.SOURCE_CONTINUE
        });
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    on_applet_clicked(_event) {
        this.menu.toggle();
    }

    on_applet_removed_from_panel() {
        if (this._pollId !== null) {
            Mainloop.source_remove(this._pollId);
            this._pollId = null;
        }
    }
}

// ── Entry point ───────────────────────────────────────────────────────────────

function main(metadata, orientation, panelHeight, instanceId) {
    return new PWSwitcherApplet(metadata, orientation, panelHeight, instanceId);
}
