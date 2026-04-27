"""Mixin: PipeWire monitoring, rate/quantum control, exclusive volume."""
import json
import os
import re
import subprocess
import sys
import time

from gi.repository import GLib  # GLib needs no require_version

from .config import MUTED_INPUTS_FILE, log


def _resolve_app_name(props: dict, cprops: dict) -> str:
    """Best-effort human-readable app name from node + client props."""
    name = (
        props.get("application.name")
        or props.get("application.process.binary")
        or cprops.get("application.name")
        or cprops.get("application.process.binary")
        or props.get("media.name")
        or props.get("node.name", "Unknown")
    ).strip()
    # Capitalise single-word lowercase names (e.g. "spotify" → "Spotify")
    if name and name[0].islower() and " " not in name:
        name = name.capitalize()
    return name


class PipeWireMixin:
    def _list_sinks(self) -> list:
        try:
            result = subprocess.run(
                ["pactl", "--format=json", "list", "sinks"],
                capture_output=True,
                text=True,
            )
            output = result.stdout.strip()
            if not output:
                return []
            data = json.loads(output)
            return data if isinstance(data, list) else []
        except Exception as e:
            log.warning(f"[Pulse] Could not list sinks: {e}")
            return []

    def _get_sink_info(self, sink_name: str | None) -> dict | None:
        if not sink_name:
            return None
        for sink in self._list_sinks():
            if sink.get("name") == sink_name:
                return sink
        return None

    def _get_default_sink_info(self) -> dict | None:
        try:
            result = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True,
                text=True,
            )
            return self._get_sink_info(result.stdout.strip())
        except Exception as e:
            log.warning(f"[Pulse] Could not resolve default sink: {e}")
            return None

    def _describe_sink(self, sink_info: dict | None) -> str:
        if not sink_info:
            return "Unavailable"
        props = sink_info.get("properties", {})
        description = (
            sink_info.get("description")
            or props.get("device.description")
            or props.get("alsa.card_name")
            or sink_info.get("name")
            or "Unknown output"
        )
        sample_spec = sink_info.get("sample_specification") or "format unavailable"
        return f"{description} • {sample_spec}"

    def _get_target_sink_info(self, app_name: str | None = None, is_exclusive: bool = False) -> tuple[dict | None, bool]:
        sink_info = None
        using_preferred = False
        if app_name and is_exclusive:
            preferred_sink = self.preferred_sink_by_app.get(app_name.lower())
            sink_info = self._get_sink_info(preferred_sink)
            using_preferred = sink_info is not None
        if sink_info is None:
            sink_info = self._get_default_sink_info()
        return sink_info, using_preferred

    def _find_owner_sink_input(self, app_name: str, node_id: int, sink_inputs: list | None = None) -> dict | None:
        sink_inputs = sink_inputs or self._list_sink_inputs()
        fallback = None
        for inp in sink_inputs:
            props = inp.get("properties", {})
            obj_id = props.get("object.id")
            inp_app = (
                props.get("application.name")
                or props.get("application.process.binary")
                or props.get("media.name")
                or props.get("node.name")
                or ""
            ).lower()
            if obj_id is not None and str(obj_id) == str(node_id):
                return inp
            if inp_app and inp_app == app_name.lower():
                fallback = inp
        return fallback

    def _route_exclusive_app_to_preferred_sink(self, app_name: str, node_id: int, sink_inputs: list | None = None) -> None:
        preferred_sink = self.preferred_sink_by_app.get(app_name.lower())
        if not preferred_sink:
            return

        sink_info = self._get_sink_info(preferred_sink)
        if sink_info is None:
            log.warning(f"[Route] Preferred sink '{preferred_sink}' for {app_name} is not available")
            return

        owner_input = self._find_owner_sink_input(app_name, node_id, sink_inputs)
        if owner_input is None:
            return

        if owner_input.get("sink") == sink_info.get("index"):
            return

        try:
            subprocess.run(
                ["pactl", "move-sink-input", str(owner_input.get("index")), preferred_sink],
                capture_output=True,
                check=False,
            )
            log.info(
                f"[Route] Moved {app_name} sink-input {owner_input.get('index')} to preferred output {preferred_sink}"
            )
        except Exception as e:
            log.warning(f"[Route] Could not move {app_name} to preferred output {preferred_sink}: {e}")

    def _load_muted_input_state(self) -> list:
        try:
            if not os.path.exists(MUTED_INPUTS_FILE):
                return []
            with open(MUTED_INPUTS_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                log.info(f"[Exclusive] Loaded {len(data)} persisted muted sink-input record(s).")
                return data
        except Exception as e:
            log.warning(f"[Exclusive] Could not load muted sink-input state: {e}")
        return []

    def _save_muted_input_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(MUTED_INPUTS_FILE), exist_ok=True)
            data = list(self._muted_sink_inputs.values()) + list(self._persisted_muted_inputs)
            with open(MUTED_INPUTS_FILE, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
        except Exception as e:
            log.warning(f"[Exclusive] Could not save muted sink-input state: {e}")

    def _match_persisted_sink_input(self, record: dict, sink_inputs: dict) -> tuple[dict | None, str | None]:
        sink_input_id = record.get("sink_input_id")
        if sink_input_id in sink_inputs:
            return sink_inputs[sink_input_id], f"sink-input {sink_input_id}"

        object_id = record.get("object_id")
        if object_id is not None:
            for inp in sink_inputs.values():
                props = inp.get("properties", {})
                if str(props.get("object.id")) == str(object_id):
                    return inp, f"object.id={object_id}"

        app_name = (record.get("app_name") or "").lower()
        if app_name:
            for inp in sink_inputs.values():
                props = inp.get("properties", {})
                candidate = (
                    props.get("application.name")
                    or props.get("application.process.binary")
                    or props.get("media.name")
                    or props.get("node.name")
                    or ""
                ).lower()
                if candidate == app_name:
                    return inp, f"app='{app_name}'"

        return None, None

    def _list_sink_inputs(self) -> list:
        """Return current PulseAudio-compatible sink-inputs from PipeWire Pulse."""
        try:
            result = subprocess.run(
                ["pactl", "--format=json", "list", "sink-inputs"],
                capture_output=True,
                text=True,
            )
            output = result.stdout.strip()
            if not output:
                return []
            data = json.loads(output)
            if isinstance(data, list):
                return data
        except Exception as e:
            log.warning(f"[Pulse] Could not list sink-inputs: {e}")
        return []

    def _get_clock_settings(self) -> tuple[str, str]:
        """Return current PipeWire forced clock settings as (rate, quantum)."""
        try:
            result = subprocess.run(
                ["pw-metadata", "-n", "settings", "0"],
                capture_output=True,
                text=True,
            )
            output = result.stdout
            rate_match = re.search(r"clock\.force-rate' value:'(\d+)'", output)
            quantum_match = re.search(r"clock\.force-quantum' value:'(\d+)'", output)
            return (
                rate_match.group(1) if rate_match else "0",
                quantum_match.group(1) if quantum_match else "0",
            )
        except Exception as e:
            log.warning(f"[PW] Could not read clock settings: {e}")
            return "0", "0"

    def _sink_input_state_map(self) -> dict[str, dict]:
        state = {}
        for sink_input in self._list_sink_inputs():
            object_id = sink_input.get("properties", {}).get("object.id")
            if object_id is not None:
                state[str(object_id)] = sink_input
        return state

    def _build_signal_diagram(self, best: dict, streams: list, use_strict: bool) -> str:
        competing = [stream for stream in streams if stream["node_id"] != best["node_id"]]
        owner_mode = "EXCLUSIVE" if best["is_exclusive"] else "STRICT" if use_strict else "AUTO"
        sink_input_state = self._sink_input_state_map()
        target_sink_info, using_preferred = self._get_target_sink_info(best["app_name"], best["is_exclusive"])
        dac_node = self._describe_sink(target_sink_info).split(" • ")[0] if target_sink_info else "DAC"

        route_nodes = [best["app_name"]]
        if best["is_exclusive"] and self.hard_lock_enabled:
            route_nodes.extend(["Exclusive Lock", dac_node, "Amplifier"])
            summary = "Exclusive chain locked straight to the DAC. Competing streams are held back."
        elif use_strict:
            route_nodes.extend(["Strict Clock", dac_node, "Amplifier"])
            summary = "Strict timing is active. The clock is pinned, but the mixer is still shared."
        else:
            route_nodes.extend(["PipeWire Mixer", dac_node, "Amplifier"])
            summary = "Shared playback path active. Good for desktop use, less rigid for critical listening."

        if using_preferred:
            summary += " Preferred DAC routing is active for this exclusive app."

        competing_entries = []
        for stream in competing:
            sink_input = sink_input_state.get(str(stream["node_id"]), {})
            if sink_input.get("mute"):
                state = "Muted"
            elif sink_input.get("corked"):
                state = "Paused"
            else:
                state = "Live"
            competing_entries.append({"app_name": stream["app_name"], "state": state})

        return {
            "owner_mode": owner_mode,
            "hard_lock": self.hard_lock_enabled,
            "route_nodes": route_nodes,
            "competing": competing_entries,
            "summary": summary,
        }

    # ──────────────────────────────────────────────────────────────────
    # Dynamic format / rate via pw-cli
    # ──────────────────────────────────────────────────────────────────
    def get_dynamic_info(self, node_id: int):
        """Return (rate_str, fmt_str) by calling pw-cli enum-params."""
        rate, fmt = None, "Unknown"
        try:
            result = subprocess.run(
                ["pw-cli", "enum-params", str(node_id), "Format"],
                capture_output=True, text=True,
            )
            output = result.stdout.strip()
            log.debug(f"[pw-cli] Node {node_id} Format output ({len(output)} chars)")
            if output:
                # SPA output has "Audio:rate (65539)" on one line, then "Int 44100"
                # a few lines later. We skip the SPA key number and grab the Int.
                m = re.search(
                    r"Audio:rate[^\n]*\n(?:[^\n]*\n)*?\s+Int\s+(\d+)",
                    output, re.IGNORECASE,
                )
                if m:
                    rate = m.group(1)
                    log.debug(f"[pw-cli] Node {node_id} rate={rate}")
                m2 = re.search(r"\b(F32LE|S32LE|S24_32LE|S24LE|S16LE)\b", output)
                if m2:
                    fmt = m2.group(1)
                    log.debug(f"[pw-cli] Node {node_id} fmt={fmt}")
        except Exception as e:
            log.warning(f"[pw-cli] enum-params error for node {node_id}: {e}")
        return rate, fmt

    # ──────────────────────────────────────────────────────────────────
    # Exclusive mode: force stream volume to 100 % via pactl
    # ──────────────────────────────────────────────────────────────────
    def _apply_exclusive_volume(self, app_name: str, node_id: int) -> None:
        """Set sink-input volume to exactly 100 % — no digital attenuation.

        Matches by PipeWire object.id first (reliable for GStreamer apps like
        Spotify that expose no application.name in PulseAudio/pactl), then
        falls back to application.name / application.process.binary.
        """
        try:
            result = subprocess.run(
                ["pactl", "--format=json", "list", "sink-inputs"],
                capture_output=True, text=True,
            )
            for inp in json.loads(result.stdout):
                props  = inp.get("properties", {})
                obj_id = props.get("object.id")
                matched_by = None

                if obj_id is not None and str(obj_id) == str(node_id):
                    matched_by = f"object.id={node_id}"
                else:
                    inp_app = (
                        props.get("application.name")
                        or props.get("application.process.binary")
                        or ""
                    ).lower()
                    if inp_app and inp_app == app_name.lower():
                        matched_by = f"app.name={app_name}"

                if matched_by:
                    inp_id = inp.get("index")
                    subprocess.run(
                        ["pactl", "set-sink-input-volume", str(inp_id), "100%"],
                        capture_output=True,
                    )
                    log.info(
                        f"[Exclusive] Sink-input {inp_id} ({app_name}) "
                        f"volume → 100%  [matched by {matched_by}]"
                    )
                    return
            log.debug(
                f"[Exclusive] No pactl sink-input found for "
                f"'{app_name}' / node_id={node_id}"
            )
        except Exception as e:
            log.warning(f"[Exclusive] pactl volume set failed: {e}")

    def _set_sink_input_mute(self, sink_input_id: int, mute: bool) -> bool:
        try:
            subprocess.run(
                ["pactl", "set-sink-input-mute", str(sink_input_id), "1" if mute else "0"],
                capture_output=True,
                check=False,
            )
            return True
        except Exception as e:
            log.warning(
                f"[Exclusive] Could not set mute={mute} for sink-input {sink_input_id}: {e}"
            )
            return False

    def _apply_exclusive_isolation(self, app_name: str, node_id: int) -> None:
        """Mute every other running audio sink-input while one exclusive app owns the DAC."""
        sink_inputs = self._list_sink_inputs()
        owner_input_id = None

        for inp in sink_inputs:
            props = inp.get("properties", {})
            obj_id = props.get("object.id")
            inp_app = (
                props.get("application.name")
                or props.get("application.process.binary")
                or props.get("media.name")
                or props.get("node.name")
                or ""
            ).lower()
            if obj_id is not None and str(obj_id) == str(node_id):
                owner_input_id = inp.get("index")
                break
            if inp_app and inp_app == app_name.lower():
                owner_input_id = inp.get("index")

        if owner_input_id is None:
            log.debug(
                f"[Exclusive] No owner sink-input found for '{app_name}' / node_id={node_id}; "
                "cannot isolate other streams."
            )
            return

        current_ids = {inp.get("index") for inp in sink_inputs}
        for sink_input_id in list(self._muted_sink_inputs):
            if sink_input_id not in current_ids:
                self._muted_sink_inputs.pop(sink_input_id, None)

        for inp in sink_inputs:
            sink_input_id = inp.get("index")
            props = inp.get("properties", {})
            if sink_input_id == owner_input_id:
                continue
            if props.get("media.class") != "Stream/Output/Audio":
                continue
            if sink_input_id in self._muted_sink_inputs:
                continue
            was_muted = bool(inp.get("mute"))
            if was_muted:
                continue
            if self._set_sink_input_mute(sink_input_id, True):
                self._muted_sink_inputs[sink_input_id] = {
                    "sink_input_id": sink_input_id,
                    "object_id": props.get("object.id"),
                    "app_name": (
                        props.get("application.name")
                        or props.get("application.process.binary")
                        or props.get("media.name")
                        or props.get("node.name")
                        or app_name
                    ),
                    "was_muted": was_muted,
                }
                self._save_muted_input_state()
                log.info(
                    f"[Exclusive] Muted competing sink-input {sink_input_id} while '{app_name}' owns output"
                )

        self._exclusive_owner_node_id = node_id

    def _restore_exclusive_isolation(self) -> None:
        """Unmute sink-inputs that this app muted while exclusive mode was active."""
        if (
            not self._muted_sink_inputs
            and not self._persisted_muted_inputs
            and self._exclusive_owner_node_id is None
        ):
            return

        sink_inputs = {inp.get("index"): inp for inp in self._list_sink_inputs()}
        for sink_input_id, record in list(self._muted_sink_inputs.items()):
            if record.get("was_muted"):
                self._muted_sink_inputs.pop(sink_input_id, None)
                continue
            if sink_input_id not in sink_inputs:
                self._muted_sink_inputs.pop(sink_input_id, None)
                continue
            if self._set_sink_input_mute(sink_input_id, False):
                log.info(f"[Exclusive] Restored sink-input {sink_input_id} after exclusive mode")
            self._muted_sink_inputs.pop(sink_input_id, None)

        remaining_persisted = []
        for record in self._persisted_muted_inputs:
            if record.get("was_muted"):
                continue
            matched_input, matched_by = self._match_persisted_sink_input(record, sink_inputs)
            if matched_input is None:
                continue
            sink_input_id = matched_input.get("index")
            if sink_input_id in self._muted_sink_inputs:
                continue
            if not matched_input.get("mute"):
                continue
            if self._set_sink_input_mute(sink_input_id, False):
                log.info(
                    f"[Exclusive] Restored orphaned sink-input {sink_input_id} "
                    f"after restart [{matched_by}]"
                )
            else:
                remaining_persisted.append(record)

        self._persisted_muted_inputs = remaining_persisted
        self._save_muted_input_state()

        self._exclusive_owner_node_id = None

    # ──────────────────────────────────────────────────────────────────
    # PipeWire clock control
    # ──────────────────────────────────────────────────────────────────
    def apply_rate(self, rate, quantum: int = 0) -> None:
        try:
            log.debug(f"[PW] clock.force-rate={rate}  clock.force-quantum={quantum}")
            subprocess.run(
                ["pw-metadata", "-n", "settings", "0", "clock.force-rate", str(rate)],
                capture_output=True,
            )
            valid_q = quantum > 0 and (quantum & (quantum - 1) == 0) and 32 <= quantum <= 8192
            subprocess.run(
                ["pw-metadata", "-n", "settings", "0", "clock.force-quantum",
                 str(quantum) if valid_q else "0"],
                capture_output=True,
            )
            self.current_rate = str(rate)
        except Exception as e:
            log.error(f"[PW] apply_rate failed: {e}")

    # ──────────────────────────────────────────────────────────────────
    # Stream info helper
    # ──────────────────────────────────────────────────────────────────
    def _get_stream_info(self, obj: dict, client_props_map: dict) -> "dict | None":
        """Parse one pw-dump node object. Returns a stream-info dict or None."""
        if obj.get("type") != "PipeWire:Interface:Node":
            return None
        info  = obj.get("info", {})
        props = info.get("props", {})
        if info.get("state", "").lower() != "running":
            return None
        if "Stream/Output/Audio" not in props.get("media.class", ""):
            return None

        node_id   = obj.get("id")
        cprops    = client_props_map.get(props.get("client.id"), {})
        app_name  = _resolve_app_name(props, cprops)

        # ── Rate ──────────────────────────────────────────────────────
        rate = None
        fmt  = props.get("audio.format")
        if props.get("audio.rate"):
            rate = str(props["audio.rate"])
        elif (nr := props.get("node.rate")) and isinstance(nr, str):
            if "/" in nr:
                try:
                    denom = nr.split("/")[1].strip()
                    if denom.isdigit():
                        rate = denom
                except Exception:
                    pass
            elif nr.strip().isdigit():
                rate = nr.strip()

        if not rate or str(rate) == "0" or not fmt or fmt in (None, "Unknown"):
            dyn_rate, dyn_fmt = self.get_dynamic_info(node_id)
            if not rate or str(rate) == "0":
                rate = dyn_rate
            if dyn_fmt not in (None, "Unknown"):
                fmt = dyn_fmt

        if not (rate and str(rate).isdigit() and int(rate) > 0):
            log.debug(f"[Monitor] Node {node_id} ({app_name}): no valid rate, skipping.")
            return None

        # ── Latency / quantum ──────────────────────────────────────────
        quantum    = 0
        latency_ms = "-- ms"
        lat_str    = props.get("node.latency")
        if lat_str and "/" in str(lat_str):
            try:
                samples, freq = (float(x) for x in str(lat_str).split("/"))
                latency_ms = f"{(samples / freq) * 1000:.1f} ms"
                quantum    = int(samples)
            except Exception:
                pass

        app_lower = app_name.lower()
        log.debug(
            f"[Monitor] Stream id={node_id} app='{app_name}' rate={rate} fmt={fmt} "
            f"lat={latency_ms} excl={app_lower in self.exclusive_apps} "
            f"strict={app_lower in self.strict_apps}"
        )
        return {
            "node_id":      node_id,
            "app_name":     app_name,
            "rate":         str(rate),
            "quantum":      quantum,
            "fmt":          fmt or "Unknown",
            "latency":      latency_ms,
            "is_exclusive": app_lower in self.exclusive_apps,
            "is_strict":    app_lower in self.strict_apps,
        }

    # ──────────────────────────────────────────────────────────────────
    # Main monitor loop (background thread)
    # ──────────────────────────────────────────────────────────────────
    def monitor_pipewire(self) -> None:
        idle_counter = 0
        MAX_IDLE_CYCLES = 3
        log.info("[Monitor] Background thread started.")

        while self.running:
            # Exit if the tray process has died
            if self.tray_process and self.tray_process.poll() is not None:
                log.info("[Monitor] Tray process exited — quitting app.")
                self.running = False
                self.quit()
                sys.exit(0)

            try:
                if not (self.auto_mode or self.strict_mode):
                    log.debug("[Monitor] Auto mode off — sleeping.")
                    time.sleep(1)
                    continue

                result = subprocess.run(["pw-dump"], capture_output=True, text=True)
                if not result.stdout:
                    log.warning("[Monitor] pw-dump returned empty output.")
                    time.sleep(2)
                    continue

                data = json.loads(result.stdout)

                # Build client-id → props map.
                # GStreamer apps (e.g. Spotify) store application.name on the
                # PipeWire:Interface:Client object, not on the stream Node.
                client_props_map: dict = {}
                for obj in data:
                    if obj.get("type") == "PipeWire:Interface:Client":
                        cid = obj.get("id")
                        if cid is not None:
                            client_props_map[cid] = obj.get("info", {}).get("props", {})

                log.debug(
                    f"[Monitor] pw-dump: {len(data)} objects, "
                    f"{len(client_props_map)} clients"
                )

                # Pulse exposes paused streams as "corked" even when the
                # PipeWire node may still appear running. Skip those so a
                # paused exclusive app does not keep ownership of the DAC.
                sink_inputs = self._list_sink_inputs()
                corked_object_ids = {
                    str(inp.get("properties", {}).get("object.id"))
                    for inp in sink_inputs
                    if inp.get("properties", {}).get("object.id") is not None
                    and bool(inp.get("corked"))
                }

                # ── Collect ALL running audio streams ──────────────────
                streams = []
                for obj in data:
                    s = self._get_stream_info(obj, client_props_map)
                    if s:
                        if str(s["node_id"]) in corked_object_ids:
                            log.debug(
                                f"[Monitor] Skipping corked stream id={s['node_id']} "
                                f"app='{s['app_name']}'"
                            )
                            continue
                        streams.append(s)

                if len(streams) > 1:
                    log.info(
                        f"[Monitor] {len(streams)} concurrent streams: "
                        + ", ".join(
                            f"{s['app_name']}"
                            f"({'E' if s['is_exclusive'] else 'S' if s['is_strict'] else 'A'})"
                            for s in streams
                        )
                    )

                # ── Priority: Exclusive(3) > per-app Strict(2) > any(1) ──
                streams.sort(
                    key=lambda s: 3 if s["is_exclusive"] else 2 if s["is_strict"] else 1,
                    reverse=True,
                )

                # ── Apply best-priority stream ─────────────────────────
                if streams:
                    idle_counter = 0
                    best = streams[0]
                    rate_changed = best["rate"] != self.current_rate
                    use_strict   = best["is_strict"] or self.strict_mode

                    if rate_changed or best["is_exclusive"] or use_strict:
                        if best["is_exclusive"]:
                            q = best["quantum"] if best["quantum"] > 0 else 1024
                            log.info(
                                f"[Exclusive] {best['app_name']} → {best['rate']} Hz "
                                f"q={q} fmt={best['fmt']}"
                            )
                            self.apply_rate(best["rate"], q)
                            self._route_exclusive_app_to_preferred_sink(best["app_name"], best["node_id"], sink_inputs)
                            self._apply_exclusive_volume(best["app_name"], best["node_id"])
                            if self.hard_lock_enabled:
                                self._apply_exclusive_isolation(best["app_name"], best["node_id"])
                            else:
                                self._restore_exclusive_isolation()
                        elif use_strict:
                            self._restore_exclusive_isolation()
                            log.info(
                                f"[Strict] {best['app_name']} → {best['rate']} Hz "
                                f"q={best['quantum']}"
                            )
                            self.apply_rate(best["rate"], best["quantum"])
                        else:
                            self._restore_exclusive_isolation()
                            log.info(f"[Auto] {best['app_name']} → {best['rate']} Hz")
                            self.apply_rate(best["rate"], 0)

                    elif not best["is_exclusive"]:
                        self._restore_exclusive_isolation()

                    self._active_app_name = best["app_name"]
                    clock_rate, clock_quantum = self._get_clock_settings()
                    muted_count = len(self._muted_sink_inputs)
                    concurrent_count = len(streams)
                    if best["is_exclusive"] and self.hard_lock_enabled:
                        status = "PASS"
                        note = "Exclusive app owns the DAC and competing streams are hard-locked."
                    elif best["is_exclusive"]:
                        status = "WARN"
                        note = "Exclusive app active, but hard lock is disabled so other streams may mix."
                    elif use_strict:
                        status = "INFO"
                        note = "Strict rate/quantum lock active without stream isolation."
                    else:
                        status = "INFO"
                        note = "Shared mixer path active."
                    GLib.idle_add(self._sync_add_current_btn, best["app_name"])
                    GLib.idle_add(
                        self.update_ui,
                        best["rate"], best["app_name"],
                        str(best["fmt"]), str(best["latency"]), best["is_exclusive"],
                    )
                    GLib.idle_add(
                        self.update_active_mode,
                        use_strict,
                        best["app_name"] if use_strict else None,
                    )
                    GLib.idle_add(
                        self.update_verification,
                        status,
                        f"{best['app_name']} ({'Exclusive' if best['is_exclusive'] else 'Strict' if use_strict else 'Auto'})",
                        f"forced {clock_rate} Hz / q {clock_quantum}",
                        self._describe_sink(self._get_target_sink_info(best["app_name"], best["is_exclusive"])[0]),
                        f"{concurrent_count} active, {muted_count} muted, hard-lock {'ON' if self.hard_lock_enabled else 'OFF'}",
                        note,
                    )
                    GLib.idle_add(
                        self.update_signal_diagram,
                        self._build_signal_diagram(best, streams, use_strict),
                    )
                    GLib.idle_add(self.update_audio_mixer, sink_inputs, best["app_name"])

                else:
                    self._restore_exclusive_isolation()
                    GLib.idle_add(self.update_audio_mixer, sink_inputs, None)
                    idle_counter += 1
                    log.debug(
                        f"[Monitor] No active stream "
                        f"(idle_counter={idle_counter}/{MAX_IDLE_CYCLES})"
                    )
                    if idle_counter >= MAX_IDLE_CYCLES and self.current_rate != "Unknown":
                        log.info("[Monitor] Confirmed idle — resetting PipeWire clock.")
                        self.current_rate = "Unknown"
                        GLib.idle_add(self.update_status, "Idle")
                        subprocess.run(
                            ["pw-metadata", "-n", "settings", "0",
                             "clock.force-quantum", "0"],
                            capture_output=True,
                        )

                time.sleep(1.5)

            except Exception as e:
                log.error(f"[Monitor] Unhandled exception: {e}", exc_info=True)
                time.sleep(5)
