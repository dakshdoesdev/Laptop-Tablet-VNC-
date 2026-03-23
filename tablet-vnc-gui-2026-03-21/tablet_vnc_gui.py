#!/usr/bin/env python3

import json
import os
import shlex
import shutil
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk


APP_ID = "local.dux.TabletVncGui"
HOME = Path("/home/dux")
LAYOUTS_FILE = HOME / ".local/state/tablet-vnc-gui/layouts.json"
SPATIAL_ALIGNMENTS = ("top", "center", "bottom")

# Nerd Font icon mapping (JetBrainsMonoNL Nerd Font Mono)
ICON_MAP = {
    "usb": "\U000f0553",         # nf-md-usb
    "cable": "\U000f01a1",        # nf-md-dip_switch / cable
    "mobile_layout": "\U000f035a", # nf-md-monitor_dashboard
    "map": "\U000f034d",          # nf-md-map
    "multiline_chart": "\U000f012e",# nf-md-chart_line
    "terminal": "\uf489",         # nf-md-console / terminal
    "desktop_windows": "\U000f0379",# nf-md-monitor
    "tablet_mac": "\U000f04f7",   # nf-md-tablet
    "monitoring": "\U000f012d",    # nf-md-chart_areaspline
    "arrow_back": "\uf060",       # nf-fa-arrow_left
    "bolt": "\U000f0311",          # nf-md-lightning_bolt
    "info": "\U000f02fc",          # nf-md-information_outline
}
KEYBIND_FILE = HOME / ".config/hypr/bindings.conf"
STACK_SCRIPT = HOME / ".local/bin/tablet-vnc-stack"
PROFILE_SPECS = {
    "usb": {
        "title": "USB Tablet",
        "name": "Wacom Cintiq",
        "script": HOME / ".local/bin/tablet-vnc",
        "profile": HOME / ".local/state/tablet-vnc/profile.env",
        "positions": ["left", "right", "top", "bottom"],
        "default_position": "left",
        "default_mode": "adb",
        "default_refresh": "60",
        "default_fps": "30",
        "default_ws_start": "7",
        "default_ws_count": "3",
        "default_port": "5900",
        "accent": "#FFB800",
        "icon": ICON_MAP["usb"],
    },
    "typec": {
        "title": "Type-C Tablet",
        "name": "iPad Pro",
        "script": HOME / ".local/bin/tablet-vnc-top",
        "profile": HOME / ".local/state/tablet-vnc-top/profile.env",
        "positions": ["top", "left", "right", "bottom"],
        "default_position": "top",
        "default_mode": "tether",
        "default_refresh": "60",
        "default_fps": "30",
        "default_ws_start": "9",
        "default_ws_count": "1",
        "default_port": "5901",
        "accent": "#FF007F",
        "icon": ICON_MAP["cable"],
    },
}
PROFILE_WRITE_ORDER = [
    "PROFILE_POSITION",
    "PROFILE_REFRESH",
    "PROFILE_FPS",
    "PROFILE_ALIGN",
    "PROFILE_MODE",
    "PROFILE_HOST",
    "PROFILE_WS_START",
    "PROFILE_WS_COUNT",
    "GUI_ENABLED",
]


def read_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def write_env_file(path: Path, data: dict[str, str]) -> None:
    existing = read_env_file(path)
    merged = {**existing, **data}
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={merged.get(key, '')}" for key in PROFILE_WRITE_ORDER]
    for key in sorted(k for k in merged if k not in PROFILE_WRITE_ORDER):
        lines.append(f"{key}={merged[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("WAYLAND_DISPLAY", "wayland-1")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return subprocess.run(argv, capture_output=True, text=True, env=env)


def tail_file(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-lines:])


def get_profile_log_path(key: str) -> Path:
    return PROFILE_SPECS[key]["profile"].parent / "wayvnc.log"


def get_hypr_monitors() -> list[dict]:
    result = run_command(["hyprctl", "monitors", "-j"])
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return payload
    return []


def get_adb_device_count() -> int:
    if not shutil.which("adb"):
        return 0
    result = run_command(["adb", "devices"])
    count = 0
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            count += 1
    return count


def get_tether_ip() -> str:
    result = run_command(["ip", "-4", "-o", "addr", "show", "up", "scope", "global"])
    preferred_prefixes = ("usb", "rndis", "enx")
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        iface = parts[1]
        address = parts[3].split("/", 1)[0]
        if iface.startswith(preferred_prefixes):
            return address
    return ""


def get_network_ip() -> str:
    result = run_command(["ip", "-4", "-o", "addr", "show", "up", "scope", "global"])
    skip_prefixes = ("lo", "usb", "rndis", "enx", "tailscale", "docker", "virbr", "veth", "br-")
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        iface = parts[1]
        address = parts[3].split("/", 1)[0]
        if not iface.startswith(skip_prefixes):
            return address
    return ""


def get_wayvnc_runtime_count() -> int:
    result = run_command(["pgrep", "-af", "wayvnc"])
    count = 0
    for line in result.stdout.splitlines():
        if " -o TABLET-VNC " in line or " -o TABLET-VNC-TOP " in line:
            count += 1
    return count


def normalized_spatial_snapshot(snapshot: dict | None) -> dict[str, dict[str, object]]:
    payload = snapshot or {}
    normalized: dict[str, dict[str, object]] = {}
    for key, spec in PROFILE_SPECS.items():
        raw = payload.get(key, {}) if isinstance(payload, dict) else {}
        position = raw.get("position", spec["default_position"])
        if position not in spec["positions"]:
            position = spec["default_position"]
        align = raw.get("align", "top")
        if align not in SPATIAL_ALIGNMENTS:
            align = "top"
        normalized[key] = {
            "position": position,
            "align": align,
            "enabled": bool(raw.get("enabled", True)),
        }
    return normalized


def spatial_snapshot_from_profile(key: str, data: dict[str, str] | None = None) -> dict[str, object]:
    spec = PROFILE_SPECS[key]
    profile_data = data or read_env_file(spec["profile"])
    snapshot = normalized_spatial_snapshot({
        key: {
            "position": profile_data.get("PROFILE_POSITION", spec["default_position"]),
            "align": profile_data.get("PROFILE_ALIGN", "top"),
            "enabled": profile_data.get("GUI_ENABLED", "1") != "0",
        }
    })
    return snapshot[key]


def read_layouts_file() -> dict[str, dict[str, dict[str, object]]]:
    if not LAYOUTS_FILE.exists():
        return {}
    try:
        payload = json.loads(LAYOUTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_layouts = payload.get("layouts", payload)
    if not isinstance(raw_layouts, dict):
        return {}
    layouts: dict[str, dict[str, dict[str, object]]] = {}
    for name, snapshot in raw_layouts.items():
        if isinstance(name, str):
            layouts[name] = normalized_spatial_snapshot(snapshot if isinstance(snapshot, dict) else {})
    return layouts


def write_layouts_file(layouts: dict[str, dict[str, dict[str, object]]]) -> None:
    LAYOUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "layouts": {name: normalized_spatial_snapshot(snapshot) for name, snapshot in layouts.items()},
    }
    LAYOUTS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def describe_layout(snapshot: dict[str, dict[str, object]]) -> str:
    parts = []
    normalized = normalized_spatial_snapshot(snapshot)
    for key in ("usb", "typec"):
        item = normalized[key]
        state = "on" if item["enabled"] else "off"
        parts.append(f"{PROFILE_SPECS[key]['title']}: {item['position']} / {item['align']} / {state}")
    return " | ".join(parts)


# Map accent hex to CSS class name
ACCENT_CSS_MAP = {
    "#FFB800": "accent-usb",
    "#FF007F": "accent-typec",
    "#13d6ec": "accent-cyan",
    "#13D6EC": "accent-cyan",
}


class BentoCard(Gtk.EventBox):
    def __init__(self, title, subtitle=None, icon=None, accent=None):
        super().__init__()
        self.get_style_context().add_class("bento-card")
        
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_start(20); inner.set_margin_end(20); inner.set_margin_top(20); inner.set_margin_bottom(20)
        self.add(inner)

        header = Gtk.Box(spacing=12)
        inner.pack_start(header, False, False, 0)

        if icon:
            icon_label = Gtk.Label()
            icon_label.set_markup(f"<span font_family='JetBrainsMonoNL Nerd Font Mono' size='x-large'>{icon}</span>")
            if accent:
                css_class = ACCENT_CSS_MAP.get(accent, "accent-cyan")
                icon_label.get_style_context().add_class(css_class)
            header.pack_start(icon_label, False, False, 0)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header.pack_start(title_box, True, True, 0)
        
        self.title_label = Gtk.Label(label=title, xalign=0)
        self.title_label.get_style_context().add_class("card-title")
        title_box.pack_start(self.title_label, False, False, 0)

        if subtitle:
            self.subtitle_label = Gtk.Label(label=subtitle, xalign=0)
            self.subtitle_label.get_style_context().add_class("card-subtitle")
            title_box.pack_start(self.subtitle_label, False, False, 0)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner.pack_start(self.content, True, True, 0)


class TabletStatusWidget(BentoCard):
    def __init__(self, app_window, key):
        self.spec = PROFILE_SPECS[key]
        super().__init__(title=self.spec["name"], subtitle=self.spec["title"], icon=self.spec["icon"], accent=self.spec["accent"])
        self.app_window = app_window; self.key = key
        
        self.status_pill = Gtk.Box(spacing=6); self.status_pill.get_style_context().add_class("status-pill")
        self.status_dot = Gtk.Box(); self.status_dot.set_size_request(8, 8); self.status_dot.get_style_context().add_class("status-dot-off")
        self.status_pill.pack_start(self.status_dot, False, False, 0)
        self.status_label = Gtk.Label(label="Off"); self.status_label.get_style_context().add_class("status-text")
        self.status_pill.pack_start(self.status_label, False, False, 0)
        
        header = self.get_child().get_children()[0]
        header.pack_end(self.status_pill, False, False, 0)

        info_grid = Gtk.Grid(column_spacing=24, row_spacing=4); info_grid.set_margin_top(12)
        self.content.pack_start(info_grid, True, True, 0)

        l1 = Gtk.Label(label="Interface", xalign=0); l1.get_style_context().add_class("muted")
        info_grid.attach(l1, 0, 0, 1, 1)
        self.interface_label = Gtk.Label(label="USB 3.0" if key == "usb" else "Type-C", xalign=0)
        self.interface_label.get_style_context().add_class("info-value")
        css_class = ACCENT_CSS_MAP.get(self.spec["accent"], "accent-cyan")
        self.interface_label.get_style_context().add_class(css_class)
        info_grid.attach(self.interface_label, 0, 1, 1, 1)

        l2 = Gtk.Label(label="Resolution", xalign=1); l2.get_style_context().add_class("muted")
        info_grid.attach(l2, 1, 0, 1, 1)
        self.res_label = Gtk.Label(label="1280x800 @60Hz", xalign=1); self.res_label.get_style_context().add_class("info-value")
        info_grid.attach(self.res_label, 1, 1, 1, 1)

        action_row = Gtk.Box(spacing=8)
        self.content.pack_start(action_row, False, False, 0)

        start_btn = Gtk.Button(label="Start")
        start_btn.get_style_context().add_class("action-btn-primary")
        start_btn.connect("clicked", lambda _: self.app_window.start_profile(self.key))
        action_row.pack_start(start_btn, True, True, 0)

        stop_btn = Gtk.Button(label="Stop")
        stop_btn.get_style_context().add_class("action-btn-secondary")
        stop_btn.connect("clicked", lambda _: self.app_window.stop_profile(self.key))
        action_row.pack_start(stop_btn, True, True, 0)

        logs_btn = Gtk.Button(label="Logs")
        logs_btn.get_style_context().add_class("action-btn-secondary")
        logs_btn.connect("clicked", lambda _: self.app_window.show_profile_logs(self.key))
        action_row.pack_start(logs_btn, True, True, 0)

    def update_status(self, state, details=""):
        self.status_dot.get_style_context().remove_class("status-dot-off")
        self.status_dot.get_style_context().remove_class("status-dot-on")
        self.status_dot.get_style_context().remove_class("status-dot-warn")
        if state == "active":
            self.status_dot.get_style_context().add_class("status-dot-on")
            self.status_label.set_text("Active")
        elif state == "stale":
            self.status_dot.get_style_context().add_class("status-dot-warn")
            self.status_label.set_text("Issue")
        else:
            self.status_dot.get_style_context().add_class("status-dot-off")
            self.status_label.set_text("Off")
        self.set_tooltip_text(details.strip() or "No status details available.")
        for line in details.splitlines():
            if "Resolution:" in line:
                self.res_label.set_text(line.split("Resolution:", 1)[1].strip())
                break


class SpatialMatrix(Gtk.Box):
    def __init__(self, app_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.app_window = app_window
        self.layouts = read_layouts_file()
        self.editor_controls: dict[str, dict[str, object]] = {}
        self.set_margin_start(40); self.set_margin_end(40); self.set_margin_bottom(40)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        l1 = Gtk.Label(label="Spatial Matrix", xalign=0); l1.get_style_context().add_class("header-title")
        l2 = Gtk.Label(label="Build named layouts, save as many as you want, then apply or start them.", xalign=0); l2.get_style_context().add_class("muted")
        info_box.add(l1); info_box.add(l2); self.pack_start(info_box, False, False, 0)
        self.live_status = Gtk.Label(label="Live outputs: checking", xalign=0)
        self.live_status.get_style_context().add_class("muted")
        self.pack_start(self.live_status, False, False, 0)

        split = Gtk.Box(spacing=24)
        self.pack_start(split, True, True, 0)

        left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        left_col.set_size_request(420, -1)
        split.pack_start(left_col, False, False, 0)

        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        split.pack_start(right_col, True, True, 0)

        library_card = BentoCard(title="Named Layouts", subtitle="Save and reuse spatial presets by name")
        left_col.pack_start(library_card, False, False, 0)

        self.layout_name_entry = Gtk.Entry()
        self.layout_name_entry.set_placeholder_text("Layout name")
        library_card.content.pack_start(self.layout_name_entry, False, False, 0)

        name_actions = Gtk.Box(spacing=8)
        library_card.content.pack_start(name_actions, False, False, 0)

        save_btn = Gtk.Button(label="Save Layout")
        save_btn.get_style_context().add_class("action-btn-primary")
        save_btn.connect("clicked", lambda *_: self.save_layout())
        name_actions.pack_start(save_btn, True, True, 0)

        sync_btn = Gtk.Button(label="Sync Current")
        sync_btn.get_style_context().add_class("action-btn-secondary")
        sync_btn.connect("clicked", lambda *_: self.sync_from_profiles())
        name_actions.pack_start(sync_btn, True, True, 0)

        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_scroll.set_min_content_height(250)
        library_card.content.pack_start(list_scroll, True, True, 0)

        self.layout_list = Gtk.ListBox()
        self.layout_list.set_selection_mode(Gtk.SelectionMode.NONE)
        list_scroll.add(self.layout_list)

        draft_card = BentoCard(title="Draft Layout", subtitle="Edit positions, then apply the draft or save it")
        left_col.pack_start(draft_card, True, True, 0)

        for key in ("usb", "typec"):
            spec = PROFILE_SPECS[key]
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            section.get_style_context().add_class("layout-editor-section")
            draft_card.content.pack_start(section, False, False, 0)

            row = Gtk.Box(spacing=12)
            section.pack_start(row, False, False, 0)

            title = Gtk.Label(label=spec["title"], xalign=0)
            title.get_style_context().add_class("info-value")
            row.pack_start(title, True, True, 0)

            enabled = Gtk.CheckButton(label="Enabled")
            enabled.connect("toggled", lambda *_: self.render_preview())
            row.pack_end(enabled, False, False, 0)

            pos_label = Gtk.Label(label="Position", xalign=0)
            pos_label.get_style_context().add_class("muted")
            section.pack_start(pos_label, False, False, 0)
            pos_row = Gtk.Box(spacing=8)
            section.pack_start(pos_row, False, False, 0)
            position_group = self._add_toggle_group(pos_row, [(pos, pos.title()) for pos in spec["positions"]])

            align_label = Gtk.Label(label="Align", xalign=0)
            align_label.get_style_context().add_class("muted")
            section.pack_start(align_label, False, False, 0)
            align_row = Gtk.Box(spacing=8)
            section.pack_start(align_row, False, False, 0)
            align_group = self._add_toggle_group(align_row, [(align, align.title()) for align in SPATIAL_ALIGNMENTS])

            self.editor_controls[key] = {
                "enabled": enabled,
                "position": position_group,
                "align": align_group,
            }

        draft_actions = Gtk.Box(spacing=8)
        draft_card.content.pack_start(draft_actions, False, False, 0)

        apply_btn = Gtk.Button(label="Apply Draft")
        apply_btn.get_style_context().add_class("action-btn-secondary")
        apply_btn.connect("clicked", lambda *_: self.apply_draft(False))
        draft_actions.pack_start(apply_btn, True, True, 0)

        start_btn = Gtk.Button(label="Apply + Start")
        start_btn.get_style_context().add_class("action-btn-primary")
        start_btn.connect("clicked", lambda *_: self.apply_draft(True))
        draft_actions.pack_start(start_btn, True, True, 0)

        preview_card = BentoCard(title="Layout Preview", subtitle="Square blocks show the draft before you apply it")
        right_col.pack_start(preview_card, True, True, 0)

        self.preview_summary = Gtk.Label(label="", xalign=0)
        self.preview_summary.get_style_context().add_class("muted")
        preview_card.content.pack_start(self.preview_summary, False, False, 0)

        self.preview_sandbox = Gtk.Fixed()
        self.preview_sandbox.set_size_request(-1, 520)
        self.preview_sandbox.get_style_context().add_class("matrix-sandbox")
        preview_card.content.pack_start(self.preview_sandbox, True, True, 0)

        self.sync_from_profiles()
        self._rebuild_layout_list()
        self.refresh()

    def _add_toggle_group(self, container, options):
        group = {}
        for value, label in options:
            btn = Gtk.ToggleButton(label=label)
            btn.get_style_context().add_class("toggle-btn")
            btn.set_size_request(84, 40)
            btn.connect("toggled", self._on_group_toggled, group, value)
            btn.connect("toggled", lambda *_: self.render_preview())
            container.pack_start(btn, True, True, 0)
            group[value] = btn
        return group

    def _on_group_toggled(self, btn, group, active_value):
        if btn.get_active():
            for value, other in group.items():
                if value != active_value:
                    other.set_active(False)
        elif not any(other.get_active() for other in group.values()):
            btn.set_active(True)

    def _snapshot_from_controls(self) -> dict[str, dict[str, object]]:
        snapshot: dict[str, dict[str, object]] = {}
        for key in ("usb", "typec"):
            controls = self.editor_controls[key]
            position = next((value for value, btn in controls["position"].items() if btn.get_active()), PROFILE_SPECS[key]["default_position"])
            align = next((value for value, btn in controls["align"].items() if btn.get_active()), "top")
            snapshot[key] = {
                "position": position,
                "align": align,
                "enabled": controls["enabled"].get_active(),
            }
        return normalized_spatial_snapshot(snapshot)

    def _load_snapshot_into_controls(self, snapshot: dict[str, dict[str, object]]) -> None:
        normalized = normalized_spatial_snapshot(snapshot)
        for key, item in normalized.items():
            controls = self.editor_controls[key]
            controls["enabled"].set_active(bool(item["enabled"]))
            for value, btn in controls["position"].items():
                btn.set_active(value == item["position"])
            for value, btn in controls["align"].items():
                btn.set_active(value == item["align"])
        self.render_preview()

    def _rebuild_layout_list(self) -> None:
        for child in list(self.layout_list.get_children()):
            self.layout_list.remove(child)

        if not self.layouts:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label="No saved layouts yet.", xalign=0)
            label.get_style_context().add_class("muted")
            row.add(label)
            self.layout_list.add(row)
            self.layout_list.show_all()
            return

        for name, snapshot in self.layouts.items():
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("layout-list-row")

            wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            wrapper.set_margin_start(12); wrapper.set_margin_end(12); wrapper.set_margin_top(12); wrapper.set_margin_bottom(12)
            row.add(wrapper)

            title_row = Gtk.Box(spacing=12)
            wrapper.pack_start(title_row, False, False, 0)

            name_label = Gtk.Label(label=name, xalign=0)
            name_label.get_style_context().add_class("info-value")
            title_row.pack_start(name_label, True, True, 0)

            actions = Gtk.Box(spacing=6)
            title_row.pack_end(actions, False, False, 0)

            load_btn = Gtk.Button(label="Load")
            load_btn.get_style_context().add_class("action-btn-secondary")
            load_btn.connect("clicked", lambda _, n=name: self.load_layout(n))
            actions.pack_start(load_btn, False, False, 0)

            apply_btn = Gtk.Button(label="Apply")
            apply_btn.get_style_context().add_class("action-btn-secondary")
            apply_btn.connect("clicked", lambda _, n=name: self.apply_saved_layout(n, False))
            actions.pack_start(apply_btn, False, False, 0)

            start_btn = Gtk.Button(label="Start")
            start_btn.get_style_context().add_class("action-btn-primary")
            start_btn.connect("clicked", lambda _, n=name: self.apply_saved_layout(n, True))
            actions.pack_start(start_btn, False, False, 0)

            delete_btn = Gtk.Button(label="Delete")
            delete_btn.get_style_context().add_class("action-btn-secondary")
            delete_btn.connect("clicked", lambda _, n=name: self.delete_layout(n))
            actions.pack_start(delete_btn, False, False, 0)

            summary = Gtk.Label(label=describe_layout(snapshot), xalign=0)
            summary.get_style_context().add_class("muted")
            summary.set_line_wrap(True)
            wrapper.pack_start(summary, False, False, 0)

            self.layout_list.add(row)

        self.layout_list.show_all()

    def save_layout(self) -> None:
        name = self.layout_name_entry.get_text().strip()
        if not name:
            self.app_window.append_log("Layout name required before saving.")
            return
        self.layouts[name] = self._snapshot_from_controls()
        write_layouts_file(self.layouts)
        self.app_window.append_log(f"Saved layout '{name}'.")
        self._rebuild_layout_list()

    def load_layout(self, name: str) -> None:
        snapshot = self.layouts.get(name)
        if not snapshot:
            return
        self.layout_name_entry.set_text(name)
        self._load_snapshot_into_controls(snapshot)
        self.app_window.append_log(f"Loaded layout '{name}' into draft.")

    def delete_layout(self, name: str) -> None:
        if name not in self.layouts:
            return
        del self.layouts[name]
        write_layouts_file(self.layouts)
        if self.layout_name_entry.get_text().strip() == name:
            self.layout_name_entry.set_text("")
        self.app_window.append_log(f"Deleted layout '{name}'.")
        self._rebuild_layout_list()

    def apply_saved_layout(self, name: str, start_after: bool) -> None:
        snapshot = self.layouts.get(name)
        if not snapshot:
            return
        self.layout_name_entry.set_text(name)
        self._load_snapshot_into_controls(snapshot)
        self.app_window.apply_spatial_layout_snapshot(snapshot, name, start_after)

    def apply_draft(self, start_after: bool) -> None:
        name = self.layout_name_entry.get_text().strip() or "Draft Layout"
        self.app_window.apply_spatial_layout_snapshot(self._snapshot_from_controls(), name, start_after)

    def sync_from_profiles(self) -> None:
        snapshot = self.app_window.current_spatial_snapshot()
        self._load_snapshot_into_controls(snapshot)
        self.refresh()

    def _update_live_status(self) -> None:
        monitors = get_hypr_monitors()
        if not monitors:
            self.live_status.set_text("Live outputs: no Hyprland monitor data")
            return
        parts = []
        for monitor in monitors:
            parts.append(f"{monitor.get('name', 'unknown')} @ {int(round(float(monitor.get('refreshRate', 0) or 0)))}Hz")
        self.live_status.set_text("Live outputs: " + " | ".join(parts))

    def _create_preview_block(self, title: str, subtitle: str, css_class: str) -> Gtk.EventBox:
        block = Gtk.EventBox()
        block.get_style_context().add_class("layout-monitor-card")
        block.get_style_context().add_class(css_class)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.set_margin_start(12); inner.set_margin_end(12); inner.set_margin_top(12); inner.set_margin_bottom(12)
        block.add(inner)

        title_label = Gtk.Label(label=title, xalign=0)
        title_label.get_style_context().add_class("layout-monitor-title")
        inner.pack_start(title_label, False, False, 0)

        subtitle_label = Gtk.Label(label=subtitle, xalign=0)
        subtitle_label.get_style_context().add_class("layout-monitor-subtitle")
        subtitle_label.set_line_wrap(True)
        inner.pack_start(subtitle_label, False, False, 0)
        return block

    def render_preview(self) -> None:
        for child in list(self.preview_sandbox.get_children()):
            self.preview_sandbox.remove(child)

        snapshot = self._snapshot_from_controls()
        self.preview_summary.set_text(describe_layout(snapshot))

        main_width, main_height = 1920, 1080
        tablet_width, tablet_height = 1280, 800
        entries = [{
            "title": "Laptop",
            "subtitle": "Main display",
            "x": 0,
            "y": 0,
            "width": main_width,
            "height": main_height,
            "css": "layout-monitor-main",
        }]

        overlap_counts: dict[str, int] = {}
        for key in ("usb", "typec"):
            item = snapshot[key]
            if not item["enabled"]:
                continue
            position = str(item["position"])
            align = str(item["align"])
            index = overlap_counts.get(position, 0)
            overlap_counts[position] = index + 1

            if position == "left":
                x = -tablet_width
                if align == "center":
                    y = (main_height - tablet_height) // 2
                elif align == "bottom":
                    y = main_height - tablet_height
                else:
                    y = 0
                y += index * 64
            elif position == "right":
                x = main_width
                if align == "center":
                    y = (main_height - tablet_height) // 2
                elif align == "bottom":
                    y = main_height - tablet_height
                else:
                    y = 0
                y += index * 64
            elif position == "bottom":
                x = (main_width - tablet_width) // 2 + (index * 96)
                y = main_height
            else:
                x = (main_width - tablet_width) // 2 + (index * 96)
                y = -tablet_height

            entries.append({
                "title": PROFILE_SPECS[key]["title"],
                "subtitle": f"{position.title()} / {align.title()}",
                "x": x,
                "y": y,
                "width": tablet_width,
                "height": tablet_height,
                "css": "layout-monitor-usb" if key == "usb" else "layout-monitor-typec",
            })

        min_x = min(entry["x"] for entry in entries)
        min_y = min(entry["y"] for entry in entries)
        max_x = max(entry["x"] + entry["width"] for entry in entries)
        max_y = max(entry["y"] + entry["height"] for entry in entries)
        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)
        scale = min(760 / span_x, 440 / span_y)
        scale = max(min(scale, 0.34), 0.1)
        padding = 28

        for entry in entries:
            block = self._create_preview_block(entry["title"], entry["subtitle"], entry["css"])
            draw_x = padding + int((entry["x"] - min_x) * scale)
            draw_y = padding + int((entry["y"] - min_y) * scale)
            draw_w = max(140, int(entry["width"] * scale))
            draw_h = max(90, int(entry["height"] * scale))
            block.set_size_request(draw_w, draw_h)
            self.preview_sandbox.put(block, draw_x, draw_y)

        self.preview_sandbox.show_all()

    def refresh(self):
        self._update_live_status()
        self.render_preview()


class TabletVncWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("VNC Manager"); self.set_default_size(1240, 900); self.refresh_in_flight = False
        self.command_log_lines: list[str] = []
        self.profiles = {k: read_env_file(v["profile"]) for k, v in PROFILE_SPECS.items()}
        self._install_css(); main_box = Gtk.Box(); self.add(main_box)
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); self.sidebar.get_style_context().add_class("sidebar"); self.sidebar.set_size_request(240, -1); main_box.pack_start(self.sidebar, False, False, 0)
        side_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); side_header.set_margin_start(24); side_header.set_margin_top(24); side_header.set_margin_bottom(32); self.sidebar.pack_start(side_header, False, False, 0)
        l_t = Gtk.Label(label="VNC Manager", xalign=0); l_t.get_style_context().add_class("sidebar-title")
        l_s = Gtk.Label(label="Dual Tablet Control", xalign=0); l_s.get_style_context().add_class("sidebar-subtitle")
        side_header.add(l_t); side_header.add(l_s)
        self.stack = Gtk.Stack(); self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE); self.stack.set_transition_duration(200)
        self.nav_btns = {}
        self._add_nav_item("dashboard", "Dashboard", ICON_MAP["mobile_layout"], True)
        self._add_nav_item("spatial_mapper", "Spatial Mapper", ICON_MAP["map"])
        self._add_nav_item("usb_profile", "USB Profile", ICON_MAP["usb"])
        self._add_nav_item("typec_profile", "Type-C Profile", ICON_MAP["cable"])
        self._add_nav_item("diagnostics", "Diagnostics", ICON_MAP["multiline_chart"])
        d_box = Gtk.Box(spacing=12); d_box.get_style_context().add_class("daemon-card")
        i_box = Gtk.Box(); i_box.get_style_context().add_class("daemon-icon-box")
        l = Gtk.Label(); l.set_markup(f"<span font_family='JetBrainsMonoNL Nerd Font Mono'>{ICON_MAP['terminal']}</span>"); i_box.add(l); d_box.pack_start(i_box, False, False, 0)
        inf_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); inf_box.pack_start(Gtk.Label(label="Daemon Status", xalign=0), False, False, 0)
        self.daemon_label = Gtk.Label(label="Checking", xalign=0); self.daemon_label.get_style_context().add_class("status-text-off")
        inf_box.pack_start(self.daemon_label, False, False, 0); d_box.pack_start(inf_box, True, True, 0)
        b_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); b_box.set_margin_start(16); b_box.set_margin_end(16); b_box.set_margin_bottom(24); b_box.add(d_box)
        ver_label = Gtk.Label(label="v1.0.0", xalign=0.5); ver_label.get_style_context().add_class("version-label")
        b_box.add(ver_label)
        self.sidebar.pack_end(b_box, False, False, 0)
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); main_box.pack_start(main_content, True, True, 0)
        self.header_box = Gtk.Box(spacing=16); self.header_box.set_margin_start(40); self.header_box.set_margin_end(40); self.header_box.set_margin_top(40); self.header_box.set_margin_bottom(20); main_content.pack_start(self.header_box, False, False, 0)
        self.back_btn = Gtk.Button(); self.back_btn.get_style_context().add_class("back-btn"); self.back_btn.set_no_show_all(True); self.back_btn.hide()
        b_icon = Gtk.Label(); b_icon.set_markup(f"<span font_family='JetBrainsMonoNL Nerd Font Mono'>{ICON_MAP['arrow_back']}</span>"); self.back_btn.add(b_icon); self.back_btn.connect("clicked", lambda _: self._on_nav_clicked(self.nav_btns["dashboard"], "dashboard")); self.header_box.pack_start(self.back_btn, False, False, 0)
        self.header_title = Gtk.Label(label="Dashboard"); self.header_title.get_style_context().add_class("header-title"); self.header_box.pack_start(self.header_title, False, False, 0)
        self.header_actions = Gtk.Box(spacing=12); self.header_box.pack_end(self.header_actions, False, False, 0)
        main_content.pack_start(self.stack, True, True, 0)
        self._init_dashboard(); self._init_spatial_mapper(); self._init_profile_editors(); self._init_diagnostics()
        self.refresh_statuses(); GLib.timeout_add_seconds(5, self._scheduled_refresh); self.show_all()

    def _add_nav_item(self, target, label, icon, active=False):
        btn = Gtk.Button(); btn.get_style_context().add_class("nav-item")
        if active: btn.get_style_context().add_class("nav-item-active")
        box = Gtk.Box(spacing=16); box.set_margin_start(16); btn.add(box)
        l = Gtk.Label(); l.set_markup(f"<span font_family='JetBrainsMonoNL Nerd Font Mono'>{icon}</span>"); box.pack_start(l, False, False, 0); box.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0); btn.connect("clicked", self._on_nav_clicked, target); self.sidebar.pack_start(btn, False, False, 0); self.nav_btns[target] = btn

    def _on_nav_clicked(self, btn, target):
        for b in self.nav_btns.values(): b.get_style_context().remove_class("nav-item-active")
        btn.get_style_context().add_class("nav-item-active"); self.stack.set_visible_child_name(target); self.header_title.set_text(btn.get_child().get_children()[1].get_text())
        if target == "dashboard": self.back_btn.hide()
        else: self.back_btn.show()
        for child in self.header_actions.get_children(): self.header_actions.remove(child)
        if target == "spatial_mapper":
            r = Gtk.Button(label="Refresh Layout"); r.get_style_context().add_class("action-btn-primary")
            r.connect("clicked", lambda *_: self.spatial_matrix.refresh())
            self.header_actions.add(r); self.header_actions.show_all()
        elif target == "diagnostics":
            r = Gtk.Button(label="Refresh Logs"); r.get_style_context().add_class("action-btn-primary")
            r.connect("clicked", lambda *_: self.refresh_log_view())
            self.header_actions.add(r); self.header_actions.show_all()

    def _init_dashboard(self):
        dash = Gtk.ScrolledWindow(); dash.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); self.stack.add_named(dash, "dashboard")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24); vbox.set_margin_start(40); vbox.set_margin_end(40); vbox.set_margin_bottom(40); dash.add(vbox)

        # Active Connections card (full width)
        c_card = BentoCard(title="Active Connections"); vbox.pack_start(c_card, False, False, 0)
        t_box = Gtk.Box(spacing=20); t_box.set_margin_top(12); c_card.content.pack_start(t_box, True, True, 0)
        self.status_widgets = {"usb": TabletStatusWidget(self, "usb"), "typec": TabletStatusWidget(self, "typec")}
        t_box.pack_start(self.status_widgets["usb"], True, True, 0); t_box.pack_start(self.status_widgets["typec"], True, True, 0)

        # Bottom row: Quick Actions + System Info side by side
        bottom_row = Gtk.Box(spacing=24); vbox.pack_start(bottom_row, False, False, 0)

        a_card = BentoCard(title="Quick Actions", icon=ICON_MAP["bolt"], accent="#13D6EC")
        r_b = Gtk.Button(label="Start Enabled Tablets"); r_b.get_style_context().add_class("action-btn-primary"); r_b.connect("clicked", self._on_start_enabled_clicked); a_card.content.pack_start(r_b, False, False, 0)
        s_b = Gtk.Button(label="Stop All"); s_b.get_style_context().add_class("action-btn-secondary"); s_b.connect("clicked", self._on_stop_all_clicked); a_card.content.pack_start(s_b, False, False, 0)
        f_b = Gtk.Button(label="Refresh Status"); f_b.get_style_context().add_class("action-btn-secondary"); f_b.connect("clicked", lambda *_: self.refresh_statuses()); a_card.content.pack_start(f_b, False, False, 0)
        bottom_row.pack_start(a_card, True, True, 0)

        s_card = BentoCard(title="System Info", icon=ICON_MAP["info"], accent="#13D6EC")
        host_l = Gtk.Label(label="Host", xalign=0); host_l.get_style_context().add_class("muted"); s_card.content.pack_start(host_l, False, False, 0)
        host_v = Gtk.Label(label="Hyprland / Wayland", xalign=0); host_v.get_style_context().add_class("info-value"); s_card.content.pack_start(host_v, False, False, 0)
        gpu_l = Gtk.Label(label="GPU", xalign=0); gpu_l.get_style_context().add_class("muted"); gpu_l.set_margin_top(8); s_card.content.pack_start(gpu_l, False, False, 0)
        gpu_v = Gtk.Label(label="RTX 3050 Mobile", xalign=0); gpu_v.get_style_context().add_class("info-value"); gpu_v.get_style_context().add_class("accent-cyan"); s_card.content.pack_start(gpu_v, False, False, 0)
        bottom_row.pack_start(s_card, True, True, 0)

    def _init_spatial_mapper(self):
        self.spatial_matrix = SpatialMatrix(self)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.spatial_matrix)
        self.stack.add_named(scroll, "spatial_mapper")

    def _init_profile_editors(self):
        self.editor_controls = {}
        for key in ("usb", "typec"):
            scroll = Gtk.ScrolledWindow(); self.stack.add_named(scroll, f"{key}_profile")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24); box.set_margin_start(40); box.set_margin_end(40); box.set_margin_bottom(40); scroll.add(box)
            spec = PROFILE_SPECS[key]; ctrls = {}; self.editor_controls[key] = ctrls
            p_c = BentoCard(title="Display Position", subtitle="Where the virtual tablet output should sit"); box.pack_start(p_c, False, False, 0); p_b = Gtk.Box(spacing=8); p_c.content.pack_start(p_b, False, False, 0)
            ctrls["position"] = self._add_toggle_group(p_b, [(pos, pos.title()) for pos in spec["positions"]])
            a_c = BentoCard(title="Vertical Align", subtitle="How the tablet aligns against the main display"); box.pack_start(a_c, False, False, 0); a_b = Gtk.Box(spacing=8); a_c.content.pack_start(a_b, False, False, 0)
            ctrls["align"] = self._add_toggle_group(a_b, [("top", "Top"), ("center", "Center"), ("bottom", "Bottom")])
            m_c = BentoCard(title="Connection Mode", subtitle="How the tablet connects to the host"); box.pack_start(m_c, False, False, 0); m_b = Gtk.Box(spacing=8); m_c.content.pack_start(m_b, False, False, 0)
            ctrls["mode"] = self._add_toggle_group(m_b, [("adb", "ADB Reverse"), ("tether", "USB Tether")])
            f_c = BentoCard(title="Framerate Target", subtitle="Maximum VNC output refresh rate"); box.pack_start(f_c, False, False, 0); f_b = Gtk.Box(spacing=8); f_c.content.pack_start(f_b, False, False, 0)
            ctrls["fps"] = self._add_toggle_group(f_b, [("30", "30 FPS"), ("60", "60 FPS")])
            r_c = BentoCard(title="Display Refresh", subtitle="Virtual display refresh rate"); box.pack_start(r_c, False, False, 0); slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 30, 60, 30)
            slider.set_draw_value(True); slider.get_style_context().add_class("chunky-slider"); r_c.content.pack_start(slider, False, False, 0); ctrls["refresh"] = slider
            h_c = BentoCard(title="Host / Tether IP", subtitle="Saved target for tether/manual IP mode"); box.pack_start(h_c, False, False, 0)
            host_entry = Gtk.Entry(); host_entry.set_placeholder_text("Auto-detect if left empty"); h_c.content.pack_start(host_entry, False, False, 0); ctrls["host"] = host_entry
            w_c = BentoCard(title="Workspaces", subtitle="Initial workspace mapping"); box.pack_start(w_c, False, False, 0); w_b = Gtk.Box(spacing=24); w_c.content.pack_start(w_b, False, False, 0)
            s_b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); s_b.add(Gtk.Label(label="Start Index", xalign=0)); ctrls["ws_start"] = Gtk.SpinButton.new_with_range(1, 20, 1); s_b.add(ctrls["ws_start"]); w_b.pack_start(s_b, True, True, 0)
            c_b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); c_b.add(Gtk.Label(label="Count", xalign=0)); ctrls["ws_count"] = Gtk.SpinButton.new_with_range(1, 10, 1); c_b.add(ctrls["ws_count"]); w_b.pack_start(c_b, True, True, 0)
            g_c = BentoCard(title="Stack Inclusion", subtitle="Whether stack start should include this profile"); box.pack_start(g_c, False, False, 0)
            gui_toggle = Gtk.CheckButton(label="Enable this tablet in stack start")
            g_c.content.pack_start(gui_toggle, False, False, 0); ctrls["gui_enabled"] = gui_toggle
            action_row = Gtk.Box(spacing=12); box.pack_start(action_row, False, False, 0)
            save_b = Gtk.Button(label=f"Save {spec['title']} Profile"); save_b.get_style_context().add_class("action-btn-primary"); save_b.connect("clicked", lambda _, k=key: self.save_profiles(k)); action_row.pack_start(save_b, False, False, 0)
            start_b = Gtk.Button(label=f"Start {spec['title']}"); start_b.get_style_context().add_class("action-btn-secondary"); start_b.connect("clicked", lambda _, k=key: self.start_profile(k)); action_row.pack_start(start_b, False, False, 0)
            stop_b = Gtk.Button(label=f"Stop {spec['title']}"); stop_b.get_style_context().add_class("action-btn-secondary"); stop_b.connect("clicked", lambda _, k=key: self.stop_profile(k)); action_row.pack_start(stop_b, False, False, 0)
            doctor_b = Gtk.Button(label="Doctor"); doctor_b.get_style_context().add_class("action-btn-secondary"); doctor_b.connect("clicked", lambda _, k=key: self.run_profile_command(k, ["doctor"], "Doctor")); action_row.pack_start(doctor_b, False, False, 0)
            self._load_editor_data(key)

    def _add_toggle_group(self, container, options):
        group = {}
        for val, label in options:
            btn = Gtk.ToggleButton(label=label); btn.get_style_context().add_class("toggle-btn"); btn.set_size_request(140, 48)
            container.pack_start(btn, True, True, 0); group[val] = btn
            btn.connect("toggled", self._on_toggle_clicked, group, val)
        return group

    def _on_toggle_clicked(self, btn, group, active_val):
        if btn.get_active():
            for val, b in group.items():
                if val != active_val: b.set_active(False)
        elif not any(b.get_active() for b in group.values()): btn.set_active(True)

    def _load_editor_data(self, key):
        data = self.profiles[key]; ctrls = self.editor_controls[key]; spec = PROFILE_SPECS[key]
        position = data.get("PROFILE_POSITION", spec["default_position"])
        if position in ctrls["position"]: ctrls["position"][position].set_active(True)
        align = data.get("PROFILE_ALIGN", "top")
        if align in ctrls["align"]: ctrls["align"][align].set_active(True)
        mode = data.get("PROFILE_MODE", spec["default_mode"])
        if mode in ctrls["mode"]: ctrls["mode"][mode].set_active(True)
        fps = data.get("PROFILE_FPS", spec["default_fps"])
        if fps in ctrls["fps"]: ctrls["fps"][fps].set_active(True)
        ctrls["refresh"].set_value(float(data.get("PROFILE_REFRESH", spec["default_refresh"])))
        ctrls["host"].set_text(data.get("PROFILE_HOST", ""))
        ctrls["ws_start"].set_value(int(data.get("PROFILE_WS_START", spec["default_ws_start"])))
        ctrls["ws_count"].set_value(int(data.get("PROFILE_WS_COUNT", spec["default_ws_count"])))
        ctrls["gui_enabled"].set_active(data.get("GUI_ENABLED", "1") != "0")

    def current_spatial_snapshot(self) -> dict[str, dict[str, object]]:
        return {
            key: spatial_snapshot_from_profile(key, self.profiles.get(key, {}))
            for key in ("usb", "typec")
        }

    def apply_spatial_layout_snapshot(self, snapshot: dict[str, dict[str, object]], name: str, start_after: bool = False) -> None:
        normalized = normalized_spatial_snapshot(snapshot)
        for key, item in normalized.items():
            merged = dict(self.profiles.get(key, {}))
            merged["PROFILE_POSITION"] = str(item["position"])
            merged["PROFILE_ALIGN"] = str(item["align"])
            merged["GUI_ENABLED"] = "1" if bool(item["enabled"]) else "0"
            write_env_file(PROFILE_SPECS[key]["profile"], merged)
            self.profiles[key] = read_env_file(PROFILE_SPECS[key]["profile"])
            self._load_editor_data(key)

        self.append_log(f"Applied layout '{name}'.")
        if hasattr(self, "spatial_matrix"):
            self.spatial_matrix.refresh()

        if start_after:
            self.run_background_sequence([
                ([str(STACK_SCRIPT), "stop"], "Stack Stop"),
                ([str(STACK_SCRIPT), "start"], "Stack Start"),
            ], True)
        else:
            self.refresh_statuses()

    def save_profiles(self, key=None):
        if key:
            ctrls = self.editor_controls[key]
            position = next((v for v, b in ctrls["position"].items() if b.get_active()), PROFILE_SPECS[key]["default_position"])
            align = next((v for v, b in ctrls["align"].items() if b.get_active()), "top")
            mode = next((v for v, b in ctrls["mode"].items() if b.get_active()), "tether")
            fps = next((v for v, b in ctrls["fps"].items() if b.get_active()), "30")
            data = {
                "PROFILE_POSITION": position,
                "PROFILE_REFRESH": str(int(ctrls["refresh"].get_value())),
                "PROFILE_FPS": fps,
                "PROFILE_ALIGN": align,
                "PROFILE_MODE": mode,
                "PROFILE_HOST": ctrls["host"].get_text().strip(),
                "PROFILE_WS_START": str(int(ctrls["ws_start"].get_value())),
                "PROFILE_WS_COUNT": str(int(ctrls["ws_count"].get_value())),
                "GUI_ENABLED": "1" if ctrls["gui_enabled"].get_active() else "0",
            }
            write_env_file(PROFILE_SPECS[key]["profile"], data); self.profiles[key] = read_env_file(PROFILE_SPECS[key]["profile"]); self.append_log(f"Profile {key} saved.")
            if hasattr(self, "spatial_matrix"):
                self.spatial_matrix.sync_from_profiles()
        return True

    def _init_diagnostics(self):
        diag = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20); diag.set_margin_start(40); diag.set_margin_end(40); diag.set_margin_bottom(40); self.stack.add_named(diag, "diagnostics")
        h_c = BentoCard(title="Backend Health", icon=ICON_MAP["monitoring"], accent="#13d6ec"); diag.pack_start(h_c, False, False, 0)
        h_grid = Gtk.Grid(column_spacing=24, row_spacing=10); h_c.content.pack_start(h_grid, False, False, 0)
        adb_l = Gtk.Label(label="ADB Devices", xalign=0); adb_l.get_style_context().add_class("muted"); h_grid.attach(adb_l, 0, 0, 1, 1)
        self.adb_status = Gtk.Label(label="Checking", xalign=0); self.adb_status.get_style_context().add_class("info-value"); h_grid.attach(self.adb_status, 0, 1, 1, 1)
        tether_l = Gtk.Label(label="Tether IP", xalign=0); tether_l.get_style_context().add_class("muted"); h_grid.attach(tether_l, 1, 0, 1, 1)
        self.tether_status = Gtk.Label(label="Checking", xalign=0); self.tether_status.get_style_context().add_class("info-value"); h_grid.attach(self.tether_status, 1, 1, 1, 1)
        lan_l = Gtk.Label(label="Host LAN", xalign=0); lan_l.get_style_context().add_class("muted"); h_grid.attach(lan_l, 2, 0, 1, 1)
        self.network_status = Gtk.Label(label="Checking", xalign=0); self.network_status.get_style_context().add_class("info-value"); h_grid.attach(self.network_status, 2, 1, 1, 1)
        wayvnc_l = Gtk.Label(label="wayvnc", xalign=0); wayvnc_l.get_style_context().add_class("muted"); h_grid.attach(wayvnc_l, 3, 0, 1, 1)
        self.wayvnc_status = Gtk.Label(label="Checking", xalign=0); self.wayvnc_status.get_style_context().add_class("info-value"); h_grid.attach(self.wayvnc_status, 3, 1, 1, 1)
        actions = Gtk.Box(spacing=10); h_c.content.pack_start(actions, False, False, 0)
        usb_doctor = Gtk.Button(label="USB Doctor"); usb_doctor.get_style_context().add_class("action-btn-secondary"); usb_doctor.connect("clicked", lambda *_: self.run_profile_command("usb", ["doctor"], "Doctor")); actions.pack_start(usb_doctor, False, False, 0)
        typec_doctor = Gtk.Button(label="Type-C Doctor"); typec_doctor.get_style_context().add_class("action-btn-secondary"); typec_doctor.connect("clicked", lambda *_: self.run_profile_command("typec", ["doctor"], "Doctor")); actions.pack_start(typec_doctor, False, False, 0)
        l_c = BentoCard(title="Daemon Logs", icon=ICON_MAP["terminal"]); diag.pack_start(l_c, True, True, 0)
        self.log_view = Gtk.TextView(); self.log_view.set_editable(False); self.log_view.get_style_context().add_class("terminal-view")
        self.log_buffer = self.log_view.get_buffer(); scroll = Gtk.ScrolledWindow(); scroll.add(self.log_view); l_c.content.pack_start(scroll, True, True, 0)
        self.refresh_log_view()
        self.refresh_backend_health()

    def run_profile_command(self, key, args, label_suffix, refresh_after=True):
        spec = PROFILE_SPECS[key]
        argv = [str(spec["script"]), *args]
        self.run_background_command(argv, f"{spec['title']} {label_suffix}", refresh_after)

    def start_profile(self, key):
        self.save_profiles(key)
        self.run_profile_command(key, ["quickstart"], "Start", True)

    def stop_profile(self, key):
        self.run_profile_command(key, ["stop"], "Stop", True)

    def show_profile_logs(self, key):
        self.run_profile_command(key, ["logs"], "Logs", False)

    def refresh_backend_health(self):
        adb_count = get_adb_device_count()
        tether_ip = get_tether_ip()
        network_ip = get_network_ip()
        wayvnc_path = shutil.which("wayvnc")
        wayvnc_runtime = get_wayvnc_runtime_count()

        self.adb_status.set_text(f"{adb_count} device(s)" if adb_count else "No device")
        self.tether_status.set_text(tether_ip or "Not detected")
        self.network_status.set_text(network_ip or "No LAN IP")
        if wayvnc_path:
            self.wayvnc_status.set_text(f"Installed / {wayvnc_runtime} active")
        else:
            self.wayvnc_status.set_text("Missing")

    def refresh_log_view(self):
        if not hasattr(self, "log_buffer"):
            return
        sections = []
        command_tail = self.command_log_lines[-80:]
        sections.append("== APP COMMAND LOG ==\n" + ("\n".join(command_tail) if command_tail else "No commands yet."))
        for key in ("usb", "typec"):
            title = PROFILE_SPECS[key]["title"].upper()
            log_text = tail_file(get_profile_log_path(key), 60) or "No log file yet."
            sections.append(f"== {title} WAYVNC LOG ==\n{log_text}")
        self.log_buffer.set_text("\n\n".join(sections))

    def _install_css(self) -> None:
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        css = b"""
        * { font-family: 'Noto Sans', 'Liberation Sans', sans-serif; }

        /* ---- Accent color utility classes ---- */
        .accent-usb   { color: #FFB800; }
        .accent-typec  { color: #FF007F; }
        .accent-cyan   { color: #13D6EC; }

        /* ---- Typography ---- */
        .sidebar-title  { font-family: 'Noto Sans', sans-serif; font-size: 22px; font-weight: 800; color: white; letter-spacing: -0.35px; }
        .sidebar-subtitle { font-size: 13px; font-weight: 500; color: #8A8A95; letter-spacing: 0.2px; }
        .header-title   { font-family: 'Noto Sans', sans-serif; font-size: 34px; font-weight: 800; color: white; letter-spacing: -0.9px; }

        /* ---- Window & sidebar ---- */
        window   { background: #09090B; }
        .sidebar { background: linear-gradient(180deg, #0C0C0E 0%, #09090B 100%); border-right: 1px solid #27272A; }

        /* ---- Navigation ---- */
        .nav-item        { background: transparent; border: none; box-shadow: none; color: #71717A;
                           border-left: 3px solid transparent; padding: 12px 0;
                           transition: all 250ms ease; font-size: 14px; font-weight: 600; }
        .nav-item:hover  { background: rgba(39,39,42,0.5); color: #E4E4E7; }
        .nav-item-active { border-left-color: #13D6EC; background: rgba(19,214,236,0.06); color: white; }

        /* ---- Back button ---- */
        .back-btn        { background: #18181B; border: 1px solid rgba(255,255,255,0.06);
                           border-radius: 99px; min-width: 48px; min-height: 48px; color: white;
                           box-shadow: 0 4px 16px rgba(0,0,0,0.4); transition: all 200ms ease; }
        .back-btn:hover  { background: #27272A; color: #13D6EC;
                           box-shadow: 0 0 20px rgba(19,214,236,0.15); }

        /* ---- Bento cards ---- */
        .bento-card       { background: #18181B; border-radius: 16px;
                            border: 1px solid rgba(255,255,255,0.04);
                            box-shadow: 0 8px 32px rgba(0,0,0,0.5); transition: all 250ms ease; }
        .bento-card:hover { background: #1E1E22;
                            border-color: rgba(19,214,236,0.12);
                            box-shadow: 0 12px 40px rgba(0,0,0,0.6), 0 0 20px rgba(19,214,236,0.04); }
        .card-title    { font-family: 'Noto Sans', sans-serif; font-size: 19px; font-weight: 700; color: white; letter-spacing: -0.2px; }
        .card-subtitle { font-size: 13px; font-weight: 500; color: #8A8A95; letter-spacing: 0.15px; }

        /* ---- Toggle buttons ---- */
        .toggle-btn         { background: #27272A; border: 1px solid rgba(255,255,255,0.06);
                              color: #A1A1AA; border-radius: 12px; font-weight: 600;
                              transition: all 200ms ease; font-size: 13px; }
        .toggle-btn:hover   { background: #3F3F46; color: white; }
        .toggle-btn:checked { background: linear-gradient(135deg, #FFB800, #FF9500); color: #09090B;
                              box-shadow: 0 4px 16px rgba(255,184,0,0.35); border-color: transparent; }

        /* ---- Slider ---- */
        .chunky-slider contents trough           { background: #27272A; border-radius: 16px; min-height: 24px; }
        .chunky-slider contents trough highlight  { background: linear-gradient(90deg, rgba(255,184,0,0.25), rgba(255,184,0,0.5)); border-radius: 16px; }
        .chunky-slider contents trough slider     { background: linear-gradient(135deg, #FFB800, #FF9500);
                                                    border-radius: 20px; min-width: 32px; min-height: 48px;
                                                    margin-top: -12px; margin-bottom: -12px;
                                                    box-shadow: 0 4px 16px rgba(255,149,0,0.4); }

        /* ---- Inputs ---- */
        entry, spinbutton { background: #09090B; border: 1px solid #27272A; color: white;
                            border-radius: 8px; padding: 8px; transition: border-color 200ms ease;
                            font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-size: 13px; }
        entry:focus, spinbutton:focus { border-color: rgba(19,214,236,0.4); }

        /* ---- Status pills ---- */
        .status-pill     { background: #09090B; border-radius: 20px; border: 1px solid #27272A; padding: 4px 14px; }
        .status-dot-on   { background: #39FF14; border-radius: 10px; box-shadow: 0 0 10px rgba(57,255,20,0.6); }
        .status-dot-off  { background: #52525B; border-radius: 10px; }
        .status-dot-warn { background: #FFB800; border-radius: 10px; box-shadow: 0 0 10px rgba(255,184,0,0.45); }
        .status-text     { font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-size: 11px; color: #D4D4D8; letter-spacing: 0.5px; }

        /* ---- Muted & info ---- */
        .muted      { color: #71717A; font-size: 12px; font-weight: 500; letter-spacing: 0.5px; }
        .info-value { font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-size: 14px; font-weight: bold; color: #E4E4E7; }

        /* ---- Action buttons ---- */
        .action-btn-primary   { background: linear-gradient(135deg, #13D6EC, #0ABBD1); color: #09090B;
                                font-weight: 700; border-radius: 12px; padding: 12px 20px; border: none;
                                box-shadow: 0 0 20px rgba(19,214,236,0.3); transition: all 200ms ease;
                                font-size: 13px; letter-spacing: 0.3px; }
        .action-btn-primary:hover { box-shadow: 0 0 30px rgba(19,214,236,0.5);
                                     background: linear-gradient(135deg, #2CDFEF, #13D6EC); }
        .action-btn-secondary { background: #27272A; color: #D4D4D8; border-radius: 12px; padding: 12px 20px;
                                border: 1px solid rgba(255,255,255,0.08); transition: all 200ms ease;
                                font-size: 13px; font-weight: 600; }
        .action-btn-secondary:hover { background: #3F3F46; color: white;
                                       border-color: rgba(255,255,255,0.15); }

        /* ---- Daemon card ---- */
        .daemon-card     { background: #18181B; border-radius: 12px; padding: 14px;
                           border: 1px solid rgba(255,255,255,0.04); transition: all 200ms ease; }
        .daemon-card:hover { border-color: rgba(19,214,236,0.15); }
        .daemon-icon-box { background: rgba(19,214,236,0.1); border-radius: 8px; padding: 8px; }
        .status-text-on  { color: #39FF14; font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-weight: bold; font-size: 13px; letter-spacing: 0.5px; }
        .status-text-off { color: #A1A1AA; font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-weight: bold; font-size: 13px; letter-spacing: 0.5px; }
        .status-text-warn { color: #FFB800; font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-weight: bold; font-size: 13px; letter-spacing: 0.5px; }

        /* ---- Terminal / logs ---- */
        .terminal-view { background: #09090B; color: #A1A1AA; font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace;
                         font-size: 12px; padding: 12px; }

        /* ---- Spatial Matrix ---- */
        .matrix-sandbox { background-color: #0A0A0C;
                          background-image:
                            linear-gradient(to right, rgba(19,214,236,0.04) 1px, transparent 1px),
                            linear-gradient(to bottom, rgba(19,214,236,0.04) 1px, transparent 1px);
                          background-size: 50px 50px; border-radius: 0;
                          border: 1px solid rgba(39,39,42,0.8); }
        .layout-list-row { background: rgba(9,9,11,0.55); border: 1px solid rgba(255,255,255,0.05); }
        .layout-editor-section { padding: 8px 0; }
        .layout-monitor-card { border: 1px solid rgba(255,255,255,0.08); border-radius: 0; box-shadow: 0 8px 24px rgba(0,0,0,0.35); }
        .layout-monitor-main { background: rgba(39,39,42,0.72); }
        .layout-monitor-usb { background: rgba(255,184,0,0.16); border-color: rgba(255,184,0,0.55); }
        .layout-monitor-typec { background: rgba(255,0,127,0.16); border-color: rgba(255,0,127,0.55); }
        .layout-monitor-title { font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-size: 14px; font-weight: bold; color: white; }
        .layout-monitor-subtitle { font-size: 12px; color: #D4D4D8; }

        /* ---- Status pill green ---- */
        .status-pill-green { background: rgba(57,255,20,0.08); color: #39FF14;
                             border: 1px solid rgba(57,255,20,0.15); border-radius: 12px;
                             padding: 4px 12px; font-size: 12px; font-weight: bold;
                             font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; }
        .monitor-pill { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
                        border-radius: 12px; padding: 4px 12px; font-size: 12px;
                        font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; }

        /* ---- Version label ---- */
        .version-label { font-family: 'JetBrainsMonoNL Nerd Font Mono', monospace; font-size: 10px; color: #3F3F46; }
        """
        p = Gtk.CssProvider(); p.load_from_data(css); s = Gdk.Screen.get_default()
        if s: Gtk.StyleContext.add_provider_for_screen(s, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def append_log(self, text: str) -> None:
        line = f"[{GLib.DateTime.new_now_local().format('%H:%M:%S')}] {text.rstrip()}"
        self.command_log_lines.append(line)
        self.refresh_log_view()

    def run_background_command(self, argv: list[str], label: str, refresh_after: bool = False) -> None:
        self.append_log(f"$ {shlex.join(argv)}")
        def worker():
            res = run_command(argv); GLib.idle_add(self._finish_command, label, res, refresh_after)
        threading.Thread(target=worker, daemon=True).start()

    def run_background_sequence(self, commands: list[tuple[list[str], str]], refresh_after: bool = False) -> None:
        for argv, _label in commands:
            self.append_log(f"$ {shlex.join(argv)}")

        def worker():
            results = []
            for argv, label in commands:
                results.append((label, run_command(argv)))
            GLib.idle_add(self._finish_command_sequence, results, refresh_after)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_command(self, label, result, refresh_after):
        out = "\n".join(p for p in [result.stdout.strip(), result.stderr.strip()] if p).strip()
        if out:
            self.append_log(f"[{label}] {out}")
        elif result.returncode != 0:
            self.append_log(f"[{label}] command exited with code {result.returncode}")
        if refresh_after: self.refresh_statuses()
        self.refresh_log_view()
        return False

    def _finish_command_sequence(self, results, refresh_after):
        for label, result in results:
            out = "\n".join(p for p in [result.stdout.strip(), result.stderr.strip()] if p).strip()
            if out:
                self.append_log(f"[{label}] {out}")
            elif result.returncode != 0:
                self.append_log(f"[{label}] command exited with code {result.returncode}")
        if refresh_after:
            self.refresh_statuses()
        self.refresh_log_view()
        return False

    def refresh_statuses(self):
        if self.refresh_in_flight: return
        self.refresh_in_flight = True
        def worker():
            results = {k: run_command([str(v["script"]), "status"]) for k,v in PROFILE_SPECS.items()}
            GLib.idle_add(self._apply_statuses, results)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_statuses(self, results):
        overall_state = "idle"
        for k, result in results.items():
            details = "\n".join(p for p in [result.stdout.strip(), result.stderr.strip()] if p).strip()
            if "RUNNING" in details:
                state = "active"
                overall_state = "running"
            elif "STALE OUTPUT" in details or "PARTIALLY BROKEN" in details:
                state = "stale"
                if overall_state != "running":
                    overall_state = "attention"
            else:
                state = "off"
            self.status_widgets[k].update_status(state, details)
        self.daemon_label.get_style_context().remove_class("status-text-on")
        self.daemon_label.get_style_context().remove_class("status-text-off")
        self.daemon_label.get_style_context().remove_class("status-text-warn")
        if overall_state == "running":
            self.daemon_label.set_text("Running")
            self.daemon_label.get_style_context().add_class("status-text-on")
        elif overall_state == "attention":
            self.daemon_label.set_text("Attention")
            self.daemon_label.get_style_context().add_class("status-text-warn")
        else:
            self.daemon_label.set_text("Idle")
            self.daemon_label.get_style_context().add_class("status-text-off")
        self.refresh_backend_health()
        self.refresh_log_view()
        if hasattr(self, "spatial_matrix"):
            self.spatial_matrix.refresh()
        self.refresh_in_flight = False; return False

    def _scheduled_refresh(self): self.refresh_statuses(); return True
    def _on_start_enabled_clicked(self, _): self.run_background_command([str(STACK_SCRIPT), "start"], "Stack Start", True)
    def _on_stop_all_clicked(self, _): self.run_background_command([str(STACK_SCRIPT), "stop"], "Stack Stop", True)

class TabletVncApplication(Gtk.Application):
    def __init__(self): super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
    def do_activate(self):
        if not hasattr(self, "window") or self.window is None: self.window = TabletVncWindow(self)
        self.window.present()

if __name__ == "__main__": app = TabletVncApplication(); app.run(None)
