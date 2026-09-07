"""Timey — a grayscale stopwatch, timers, alarms & world clock.

Built with Python + GTK 4 + Libadwaita.

Architecture notes
------------------
Models (stopwatch, countdowns, alarms, world-clock zones) live on the
:class:`TimeyApplication` and are ticked there, so alarms and timers keep
firing desktop notifications / sounds even while the window is hidden or
running in the background. The window is a view over those models.
Everything is persisted to ``~/.config/timey/state.json``.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import alerts, env, state as statemod, style, worldclock  # noqa: E402
from .alarm import (  # noqa: E402
    WEEKDAY_SHORT,
    Alarm,
    format_time as alarm_time,
    now as alarm_now,
)
from .countdown import Countdown  # noqa: E402
from .stopwatch import format_elapsed  # noqa: E402

APP_ID = "io.github.pixlpixlpixl.Timey"
APP_NAME = "Timey"
VERSION = "0.3.0"
WEBSITE = "https://github.com/PixlPixlPixl/Timey"

TICK_MS = 10        # refresh rate of the live displays
AUTOSAVE_TICKS = 500  # persist running engines every ~5 s

_CSS_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION

#: Page order in the header switch. Alarms live on the far left, the
#: world clock on the far right, by design.
PAGES = (
    ("Alarm", "alarms"),
    ("Stopwatch", "stopwatch"),
    ("Timer", "timers"),
    ("World", "world"),
)


# ─────────────────────────────────────────────────────────────────────
# Countdown card widget
# ─────────────────────────────────────────────────────────────────────
class _TimerCard:
    """A single countdown timer rendered as a card in the Timers view."""

    def __init__(self, window: "TimeyWindow", countdown: Countdown) -> None:
        self.window = window
        self.countdown = countdown

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("timey-card")
        self.card = card

        # header row: status + optional name on the left, total + delete right
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left.set_hexpand(True)
        left.set_halign(Gtk.Align.START)

        self.status_label = Gtk.Label(label="IDLE")
        self.status_label.add_css_class("timey-tstatus")
        left.append(self.status_label)

        if countdown.name:
            name_label = Gtk.Label(label=countdown.name)
            name_label.add_css_class("timey-tname")
            name_label.set_ellipsize(2)  # Pango.EllipsizeMode.END
            name_label.set_max_width_chars(22)
            left.append(name_label)

        header.append(left)

        self.total_label = Gtk.Label(label=format_elapsed(countdown.duration))
        self.total_label.add_css_class("timey-ttotal")
        header.append(self.total_label)

        delete_button = Gtk.Button(icon_name="edit-delete-symbolic")
        delete_button.add_css_class("timey-iconbtn")
        delete_button.set_tooltip_text("Remove this timer")
        delete_button.connect("clicked", self._on_delete)
        header.append(delete_button)

        card.append(header)

        self.time_label = Gtk.Label(label=format_elapsed(countdown.remaining()))
        self.time_label.add_css_class("timey-tleft")
        self.time_label.set_halign(Gtk.Align.CENTER)
        card.append(self.time_label)

        self.progress = Gtk.ProgressBar()
        self.progress.set_halign(Gtk.Align.FILL)
        self.progress.set_hexpand(True)
        card.append(self.progress)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls.set_halign(Gtk.Align.CENTER)
        controls.set_margin_top(2)

        self.start_button = Gtk.Button(label="Start")
        self.start_button.add_css_class("timey-btn")
        self.start_button.add_css_class("timey-primary")
        self.start_button.add_css_class("timey-sm")
        self.start_button.connect("clicked", self._on_start)
        controls.append(self.start_button)

        self.reset_button = Gtk.Button(label="Reset")
        self.reset_button.add_css_class("timey-btn")
        self.reset_button.add_css_class("timey-ghost")
        self.reset_button.add_css_class("timey-sm")
        self.reset_button.connect("clicked", self._on_reset)
        controls.append(self.reset_button)

        card.append(controls)

        self.refresh()

    # ── button handlers ──────────────────────────────────────────────
    def _on_start(self, _button: Gtk.Button) -> None:
        cd = self.countdown
        if cd.is_running():
            cd.pause()
        elif not cd.is_finished():
            cd.start()
        self.window._save()
        self.refresh()

    def _on_reset(self, _button: Gtk.Button) -> None:
        self.countdown.reset()
        self.window._save()
        self.refresh()

    def _on_delete(self, _button: Gtk.Button) -> None:
        self.window.remove_timer(self)

    # ── display ──────────────────────────────────────────────────────
    def update_time(self) -> None:
        """Lightweight per-tick update (time + progress only)."""
        self.time_label.set_text(format_elapsed(self.countdown.remaining()))
        self.progress.set_fraction(self.countdown.progress())

    def refresh(self) -> None:
        """Full refresh: state, time, progress and control sensitivity."""
        cd = self.countdown

        self.status_label.remove_css_class("running")
        self.status_label.remove_css_class("paused")
        self.status_label.remove_css_class("finished")

        if cd.is_running():
            self.status_label.set_text("RUNNING")
            self.status_label.add_css_class("running")
        elif cd.is_paused():
            self.status_label.set_text("PAUSED")
            self.status_label.add_css_class("paused")
        elif cd.is_finished():
            self.status_label.set_text("DONE")
            self.status_label.add_css_class("finished")
        else:
            self.status_label.set_text("IDLE")

        if cd.is_running():
            self.start_button.set_label("Pause")
        elif cd.is_paused():
            self.start_button.set_label("Resume")
        else:
            self.start_button.set_label("Start")

        self.start_button.set_sensitive(not cd.is_finished())
        self.reset_button.set_sensitive(not cd.is_idle() or cd.is_finished())

        self.update_time()


# ─────────────────────────────────────────────────────────────────────
# Alarm card widget
# ─────────────────────────────────────────────────────────────────────
def _alarm_status_text(alarm: Alarm) -> str:
    """Subtitle for an alarm card."""
    if not alarm.enabled:
        if not alarm.repeat and alarm.last_fired is not None:
            return "Rang"
        return "Off"
    if alarm.repeat:
        return f"{alarm.describe_repeat()} · {alarm.describe_next()}"
    return f"Once · {alarm.describe_next()}"


class _AlarmCard:
    """A single alarm rendered as a card in the Alarms view."""

    def __init__(self, window: "TimeyWindow", alarm: Alarm) -> None:
        self.window = window
        self.alarm = alarm

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("timey-card")
        card.set_margin_top(2)
        card.set_margin_bottom(2)
        self.card = card

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_hexpand(True)
        left.set_valign(Gtk.Align.CENTER)

        self.time_label = Gtk.Label(label=alarm_time(alarm.hour, alarm.minute))
        self.time_label.add_css_class("timey-alarmtime")
        self.time_label.set_halign(Gtk.Align.START)
        left.append(self.time_label)

        meta_lines = []
        if alarm.name:
            meta_lines.append(alarm.name)
        meta_lines.append(_alarm_status_text(alarm))
        self.meta_label = Gtk.Label(label="  ".join(meta_lines))
        self.meta_label.add_css_class("timey-alarmmeta")
        self.meta_label.set_halign(Gtk.Align.START)
        self.meta_label.set_ellipsize(2)
        self.meta_label.set_max_width_chars(30)
        left.append(self.meta_label)
        row.append(left)

        self.enabled_switch = Gtk.Switch()
        self.enabled_switch.set_valign(Gtk.Align.CENTER)
        self.enabled_switch.set_active(alarm.enabled)
        self.enabled_switch.set_tooltip_text("Enable / disable this alarm")
        self.enabled_switch.connect("notify::active", self._on_enabled_changed)
        row.append(self.enabled_switch)

        edit_button = Gtk.Button(icon_name="document-edit-symbolic")
        edit_button.add_css_class("timey-iconbtn")
        edit_button.set_tooltip_text("Edit this alarm")
        edit_button.connect("clicked", self._on_edit)
        row.append(edit_button)

        delete_button = Gtk.Button(icon_name="edit-delete-symbolic")
        delete_button.add_css_class("timey-iconbtn")
        delete_button.set_tooltip_text("Delete this alarm")
        delete_button.connect("clicked", self._on_delete)
        row.append(delete_button)

        card.append(row)

    # ── handlers ─────────────────────────────────────────────────────
    def _on_enabled_changed(self, switch: Gtk.Switch, _param) -> None:
        self.alarm.set_enabled(switch.get_active())
        self.window._on_alarm_changed()

    def _on_edit(self, _button: Gtk.Button) -> None:
        self.window._edit_alarm(self.alarm)

    def _on_delete(self, _button: Gtk.Button) -> None:
        self.window._delete_alarm(self.alarm)


# ─────────────────────────────────────────────────────────────────────
# World-clock card widget
# ─────────────────────────────────────────────────────────────────────
class _WorldCard:
    """A clock card for one timezone in the World view."""

    def __init__(self, window: "TimeyWindow", zone: str) -> None:
        self.window = window
        self.zone = zone
        self._last_time = ""
        self._last_meta = ""

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.add_css_class("timey-card")
        card.set_margin_top(2)
        card.set_margin_bottom(2)
        self.card = card

        label, _info = worldclock.zone_info(zone)
        self.title_label = Gtk.Label(label="Local time" if worldclock.is_local(zone) else label)
        self.title_label.add_css_class("timey-worldname")
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.set_hexpand(True)
        self.title_label.set_ellipsize(2)

        self.meta_label = Gtk.Label(label="")
        self.meta_label.add_css_class("timey-worldmeta")
        self.meta_label.set_halign(Gtk.Align.START)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        title_box.set_valign(Gtk.Align.CENTER)
        title_box.append(self.title_label)
        title_box.append(self.meta_label)
        card.append(title_box)

        self.time_label = Gtk.Label(label="--:--:--")
        self.time_label.add_css_class("timey-worldtime")
        card.append(self.time_label)

        remove_button = Gtk.Button(icon_name="edit-delete-symbolic")
        remove_button.add_css_class("timey-iconbtn")
        remove_button.set_tooltip_text("Remove this clock")
        remove_button.connect("clicked", self._on_remove)
        card.append(remove_button)

    def _on_remove(self, _button: Gtk.Button) -> None:
        self.window._remove_zone(self.zone)

    def tick(self) -> None:
        """Refresh the readout; only touches widgets when the text changed."""
        dt = worldclock.current_in(self.zone)
        if dt is None:
            if self._last_time != "unknown":
                self._last_time = "unknown"
                self.time_label.set_text("--:--:--")
            return
        parts = worldclock.snapshot_text(dt)
        if parts["time"] != self._last_time:
            self._last_time = parts["time"]
            self.time_label.set_text(parts["time"])
        meta = f"{parts['offset']}  ·  {parts['date']}"
        if meta != self._last_meta:
            self._last_meta = meta
            self.meta_label.set_text(meta)


# ─────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────
class TimeyWindow(Adw.ApplicationWindow):
    """Main application window (a view over the application's models)."""

    def __init__(self, app: "TimeyApplication") -> None:
        super().__init__(
            application=app,
            title=APP_NAME,
            default_width=460,
            default_height=700,
            resizable=True,
        )
        self.app = app
        self.state = app.state
        self.stopwatch = self.state.stopwatch
        self.timer_cards: list[_TimerCard] = []

        self._theme = self.state.theme
        self._provider = Gtk.CssProvider()
        self._css_installed = False
        self.about_window: Adw.AboutWindow | None = None
        self.world_cards: list[_WorldCard] = []

        self._build_ui()
        self.connect("destroy", self._on_destroy)
        self.connect("realize", self._on_realize)
        self.connect("close-request", self._on_close_request)

        self._apply_theme(self._theme)
        self._refresh_stopwatch()
        self._rebuild_alarm_list()
        self._rebuild_world_list()

    # ── UI construction ──────────────────────────────────────────────
    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()

        self.stack = Adw.ViewStack()
        self.stack.add_named(self._build_alarms_page(), "alarms")
        self.stack.add_named(self._build_stopwatch_page(), "stopwatch")
        self.stack.add_named(self._build_timers_page(), "timers")
        self.stack.add_named(self._build_world_page(), "world")

        # Text-only tool switcher (no icons anywhere, by design).
        switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        switch_box.add_css_class("timey-switch")
        self._mode_buttons: list[Gtk.ToggleButton] = []
        for title, page in PAGES:
            button = Gtk.ToggleButton(label=title)
            button.add_css_class("timey-switchbtn")
            if self._mode_buttons:
                button.set_group(self._mode_buttons[0])
            button.connect("toggled", self._on_mode_toggled, page)
            self._mode_buttons.append(button)
            switch_box.append(button)
        # Stopwatch stays the default page.
        self._mode_buttons[1].set_active(True)
        header.set_title_widget(switch_box)
        toolbar.add_top_bar(header)

        # Header actions: settings, theme toggle (dark ⇄ light), about.
        self.settings_button = Gtk.Button()
        self.settings_button.add_css_class("flat")
        self.settings_button.set_child(Gtk.Image(icon_name="preferences-system-symbolic"))
        self.settings_button.set_tooltip_text("Settings")
        self.settings_button.connect("clicked", self._on_settings)
        header.pack_end(self.settings_button)

        self.theme_button = Gtk.Button()
        self.theme_button.add_css_class("flat")
        self.theme_button.set_child(Gtk.Image(icon_name="weather-clear-symbolic"))
        self.theme_button.connect("clicked", self._on_toggle_theme)
        header.pack_end(self.theme_button)

        about_button = Gtk.Button()
        about_button.add_css_class("flat")
        about_button.set_child(Gtk.Image(icon_name="help-about-symbolic"))
        about_button.set_tooltip_text("About Timey")
        about_button.connect("clicked", self._on_about)
        header.pack_end(about_button)

        toolbar.set_content(self.stack)

        # Keyboard shortcuts (active on the stopwatch page only).
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)

    # ── alarms page ──────────────────────────────────────────────────
    def _build_alarms_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.set_margin_top(18)
        page.set_margin_bottom(18)
        page.set_margin_start(28)
        page.set_margin_end(28)

        intro = Gtk.Label(label="ALARM AT A SET TIME. REPEAT DAILY OR ON SELECTED DAYS, OR RING ONCE.")
        intro.add_css_class("timey-hint")
        intro.set_halign(Gtk.Align.CENTER)
        intro.set_margin_bottom(16)
        page.append(intro)

        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.append(Gtk.Image(icon_name="list-add-symbolic", pixel_size=16))
        add_box.append(Gtk.Label(label="Add Alarm"))
        add_button = Gtk.Button()
        add_button.set_child(add_box)
        add_button.add_css_class("timey-btn")
        add_button.add_css_class("timey-ghost")
        add_button.add_css_class("timey-sm")
        add_button.set_halign(Gtk.Align.CENTER)
        add_button.set_tooltip_text("Add a new alarm")
        add_button.connect("clicked", self._on_add_alarm)
        page.append(add_button)

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.add_css_class("timey-scroller")
        scroller.set_propagate_natural_height(False)
        scroller.set_margin_top(16)
        page.append(scroller)

        self.alarms_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.alarms_box.set_hexpand(True)
        self.alarms_box.set_margin_bottom(6)
        scroller.set_child(self.alarms_box)

        self.alarms_empty = Gtk.Label(
            label='No alarms yet\n\nClick "Add Alarm" to set one. '
                  "Alarms are evaluated in your local timezone."
        )
        self.alarms_empty.add_css_class("timey-empty")
        self.alarms_empty.set_justify(Gtk.Justification.CENTER)
        self.alarms_empty.set_halign(Gtk.Align.CENTER)
        self.alarms_empty.set_margin_top(80)
        self.alarms_empty.set_margin_bottom(80)
        self.alarms_box.append(self.alarms_empty)

        return page

    # ── stopwatch page ───────────────────────────────────────────────
    def _build_stopwatch_page(self) -> Gtk.Widget:
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body.set_margin_top(18)
        body.set_margin_bottom(18)
        body.set_margin_start(28)
        body.set_margin_end(28)

        # time readout
        self.state_label = Gtk.Label(label="STANDBY")
        self.state_label.add_css_class("timey-state")
        self.state_label.set_halign(Gtk.Align.CENTER)
        body.append(self.state_label)

        self.time_label = Gtk.Label(label=format_elapsed(0.0))
        self.time_label.add_css_class("timey-main")
        self.time_label.set_halign(Gtk.Align.CENTER)
        self.time_label.set_valign(Gtk.Align.CENTER)
        body.append(self.time_label)

        hint_label = Gtk.Label(label="Space start/pause   |   L lap   |   R reset")
        hint_label.add_css_class("timey-hint")
        hint_label.set_halign(Gtk.Align.CENTER)
        body.append(hint_label)

        # buttons
        button_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10
        )
        button_row.set_halign(Gtk.Align.CENTER)
        button_row.set_margin_top(20)
        body.append(button_row)

        self.lap_button = self._make_button("Lap", "ghost")
        self.lap_button.connect("clicked", self._on_lap)
        button_row.append(self.lap_button)

        self.start_button = self._make_button("Start", "primary")
        self.start_button.add_css_class("timey-start")
        self.start_button.connect("clicked", self._on_toggle_start)
        button_row.append(self.start_button)

        self.reset_button = self._make_button("Reset", "ghost")
        self.reset_button.connect("clicked", self._on_reset)
        button_row.append(self.reset_button)

        # laps panel
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(24)
        separator.set_margin_bottom(12)
        body.append(separator)

        self.scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroller.add_css_class("timey-scroller")
        self.scroller.set_propagate_natural_height(False)
        body.append(self.scroller)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.add_css_class("timey-lapwrap")
        panel.set_vexpand(True)
        panel.set_hexpand(True)
        self.scroller.set_child(panel)

        self.laps_empty = Gtk.Label(label="No laps recorded yet")
        self.laps_empty.add_css_class("timey-empty")
        self.laps_empty.set_margin_top(28)
        self.laps_empty.set_margin_bottom(28)
        self.laps_empty.set_halign(Gtk.Align.CENTER)
        panel.append(self.laps_empty)

        self.laps_list = Gtk.ListBox()
        self.laps_list.add_css_class("timey-laps")
        self.laps_list.set_selection_mode(Gtk.SelectionMode.NONE)
        panel.append(self.laps_list)

        return body

    # ── timers page ──────────────────────────────────────────────────
    def _build_timers_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.set_margin_top(18)
        page.set_margin_bottom(18)
        page.set_margin_start(28)
        page.set_margin_end(28)

        intro = Gtk.Label(label="RUN SEVERAL COUNTDOWNS AT ONCE, OR PAUSE AND COME BACK")
        intro.add_css_class("timey-hint")
        intro.set_halign(Gtk.Align.CENTER)
        intro.set_margin_bottom(16)
        page.append(intro)

        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.append(Gtk.Image(icon_name="list-add-symbolic", pixel_size=16))
        add_box.append(Gtk.Label(label="Add Timer"))
        add_button = Gtk.Button()
        add_button.set_child(add_box)
        add_button.add_css_class("timey-btn")
        add_button.add_css_class("timey-ghost")
        add_button.add_css_class("timey-sm")
        add_button.set_halign(Gtk.Align.CENTER)
        add_button.set_tooltip_text("Add another countdown timer")
        add_button.connect("clicked", self._on_add_timer)
        page.append(add_button)

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.add_css_class("timey-scroller")
        scroller.set_propagate_natural_height(False)
        scroller.set_margin_top(16)
        page.append(scroller)

        self.timers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.timers_box.set_hexpand(True)
        self.timers_box.set_margin_bottom(6)
        scroller.set_child(self.timers_box)

        self.timers_empty = Gtk.Label(
            label="No timers yet\n\n"
                  'Click "Add Timer" to start one. You can run as many at once as you like.'
        )
        self.timers_empty.add_css_class("timey-empty")
        self.timers_empty.set_justify(Gtk.Justification.CENTER)
        self.timers_empty.set_halign(Gtk.Align.CENTER)
        self.timers_empty.set_margin_top(80)
        self.timers_empty.set_margin_bottom(80)
        self.timers_box.append(self.timers_empty)

        for countdown in self.state.timers:
            card = _TimerCard(self, countdown)
            self.timer_cards.append(card)
            self.timers_box.insert_child_after(card.card, self.timers_empty)
        self._refresh_timers_empty_state()

        return page

    # ── world clock page ─────────────────────────────────────────────
    def _build_world_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.set_margin_top(18)
        page.set_margin_bottom(18)
        page.set_margin_start(28)
        page.set_margin_end(28)

        intro = Gtk.Label(label="CURRENT TIME AROUND THE WORLD — YOUR TIMEZONE IS LISTED FIRST")
        intro.add_css_class("timey-hint")
        intro.set_halign(Gtk.Align.CENTER)
        intro.set_margin_bottom(16)
        page.append(intro)

        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.append(Gtk.Image(icon_name="list-add-symbolic", pixel_size=16))
        add_box.append(Gtk.Label(label="Add City"))
        add_button = Gtk.Button()
        add_button.set_child(add_box)
        add_button.add_css_class("timey-btn")
        add_button.add_css_class("timey-ghost")
        add_button.add_css_class("timey-sm")
        add_button.set_halign(Gtk.Align.CENTER)
        add_button.set_tooltip_text("Add another timezone clock")
        add_button.connect("clicked", self._on_add_zone)
        page.append(add_button)

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.add_css_class("timey-scroller")
        scroller.set_propagate_natural_height(False)
        scroller.set_margin_top(16)
        page.append(scroller)

        self.world_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.world_box.set_hexpand(True)
        self.world_box.set_margin_bottom(6)
        scroller.set_child(self.world_box)

        return page

    @staticmethod
    def _make_button(label: str, kind: str) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.add_css_class("timey-btn")
        button.add_css_class(f"timey-{kind}")
        return button

    # ── alarms logic ─────────────────────────────────────────────────
    def _on_add_alarm(self, *_args) -> None:
        self._alarm_editor().present(self)

    def _edit_alarm(self, alarm: Alarm) -> None:
        self._alarm_editor(alarm).present(self)

    def _delete_alarm(self, alarm: Alarm) -> None:
        if alarm in self.state.alarms:
            self.state.alarms.remove(alarm)
        self._save()
        self._rebuild_alarm_list()

    def _on_alarm_changed(self) -> None:
        self.state.sort_alarms()
        self._save()
        self._rebuild_alarm_list()

    def _alarm_editor(self, alarm: Alarm | None = None) -> Adw.AlertDialog:
        """Shared dialog for creating / editing an alarm."""
        name_row = Adw.EntryRow()
        name_row.set_title("Name (optional)")
        hour = Adw.SpinRow.new_with_range(0, 23, 1)
        hour.set_title("Hour")
        hour.set_value(alarm.hour if alarm else 7)
        minute = Adw.SpinRow.new_with_range(0, 59, 1)
        minute.set_title("Minute")
        minute.set_value(alarm.minute if alarm else 0)

        repeat_row = Adw.SwitchRow()
        repeat_row.set_title("Repeat")
        repeat_row.set_subtitle("Ring daily or on chosen weekdays. Off means a one-shot alarm.")
        repeat_row.set_active(alarm.repeat if alarm else False)

        day_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        day_box.set_margin_top(10)
        day_box.set_margin_bottom(4)
        day_box.set_halign(Gtk.Align.CENTER)
        day_toggles: list[Gtk.ToggleButton] = []
        for day in WEEKDAY_SHORT:
            toggle = Gtk.ToggleButton(label=day)
            toggle.add_css_class("timey-daybtn")
            toggle.set_tooltip_text(f"Repeat every {day}")
            toggle.set_active(True)
            day_box.append(toggle)
            day_toggles.append(toggle)

        if alarm and alarm.repeat:
            for toggle, day in zip(day_toggles, range(7)):
                toggle.set_active(day in alarm.weekdays)

        def sync_day_visibility(*_args) -> None:
            day_box.set_visible(repeat_row.get_active())

        day_box.set_visible(repeat_row.get_active())
        repeat_row.connect("notify::active", sync_day_visibility)

        group = Adw.PreferencesGroup()
        group.add(name_row)
        group.add(hour)
        group.add(minute)
        group.add(repeat_row)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.append(group)
        outer.append(day_box)

        dialog = Adw.AlertDialog()
        dialog.set_heading("Edit alarm" if alarm else "New alarm")
        dialog.set_body("Alarms use your local timezone.")
        dialog.set_extra_child(outer)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response",
            self._on_alarm_editor_response,
            alarm, name_row, hour, minute, repeat_row, day_toggles,
        )
        return dialog

    def _on_alarm_editor_response(
        self,
        _dialog: Adw.AlertDialog,
        response: str,
        existing: Alarm | None,
        name_row: Adw.EntryRow,
        hour_row: Adw.SpinRow,
        minute_row: Adw.SpinRow,
        repeat_row: Adw.SwitchRow,
        day_toggles: list[Gtk.ToggleButton],
    ) -> None:
        if response != "save":
            return
        hour = int(hour_row.get_value())
        minute = int(minute_row.get_value())
        repeat = repeat_row.get_active()
        weekdays = {index for index, toggle in enumerate(day_toggles) if toggle.get_active()}
        name = name_row.get_text()

        if existing is not None:
            existing.name = name
            existing.hour = hour
            existing.minute = minute
            if repeat:
                existing.repeat = True
                existing.weekdays = weekdays if weekdays else set(range(7))
                if existing.enabled:
                    existing.arm()
            else:
                existing.repeat = False
                if existing.enabled:
                    existing.arm()
            self._on_alarm_changed()
            return

        alarm = Alarm(
            hour,
            minute,
            name=name,
            repeat=repeat,
            weekdays=weekdays if repeat and weekdays else None,
            enabled=True,
        )
        self.state.alarms.append(alarm)
        self._on_alarm_changed()

    def _rebuild_alarm_list(self) -> None:
        """Re-render alarm cards in their sorted order."""
        self.state.sort_alarms()
        while (child := self.alarms_box.get_first_child()) is not None:
            self.alarms_box.remove(child)
        if not self.state.alarms:
            self.alarms_empty.set_margin_top(80)
            self.alarms_box.append(self.alarms_empty)
            return
        self.alarms_empty.set_margin_top(0)
        self.alarms_empty.set_margin_bottom(0)
        for alarm in self.state.alarms:
            self.alarms_box.append(_AlarmCard(self, alarm).card)

    # ── timers logic ─────────────────────────────────────────────────
    def _new_add_dialog(self) -> Adw.AlertDialog:
        name_row = Adw.EntryRow()
        name_row.set_title("Name (optional)")

        minutes = Adw.SpinRow.new_with_range(0, 1440, 1)
        minutes.set_title("Minutes")
        minutes.set_value(5)

        seconds = Adw.SpinRow.new_with_range(0, 59, 1)
        seconds.set_title("Seconds")
        seconds.set_value(0)

        group = Adw.PreferencesGroup()
        group.add(name_row)
        group.add(minutes)
        group.add(seconds)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(group)

        dialog = Adw.AlertDialog()
        dialog.set_heading("New countdown")
        dialog.set_body("Set a duration. Add as many timers as you need.")
        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add Timer")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response", self._on_add_timer_response, name_row, minutes, seconds
        )
        return dialog

    def _on_add_timer(self, *_args) -> None:
        self._new_add_dialog().present(self)

    def _on_add_timer_response(
        self,
        _dialog: Adw.AlertDialog,
        response: str,
        name_row: Adw.EntryRow,
        minutes: Adw.SpinRow,
        seconds: Adw.SpinRow,
    ) -> None:
        if response != "add":
            return
        total = int(minutes.get_value()) * 60 + int(seconds.get_value())
        if total < 1:
            return
        self.add_timer(total, name=name_row.get_text())

    def add_timer(self, duration_s: float, name: str = "") -> _TimerCard:
        """Create a new countdown card (used by the UI and tests)."""
        countdown = Countdown(duration_s, name=name)
        self.state.timers.append(countdown)
        card = _TimerCard(self, countdown)
        self.timer_cards.append(card)

        # Keep the empty-state label first, cards after it.
        self.timers_box.insert_child_after(card.card, self.timers_empty)
        self._refresh_timers_empty_state()
        self._save()
        return card

    def remove_timer(self, card: _TimerCard) -> None:
        if card not in self.timer_cards:
            return
        self.timer_cards.remove(card)
        if card.countdown in self.state.timers:
            self.state.timers.remove(card.countdown)
        self.timers_box.remove(card.card)
        self._refresh_timers_empty_state()
        self._save()

    def _refresh_timers_empty_state(self) -> None:
        self.timers_empty.set_visible(not bool(self.timer_cards))

    # ── world clock logic ────────────────────────────────────────────
    def _on_add_zone(self, *_args) -> None:
        self._zone_picker().present(self)

    def _zone_picker(self) -> Adw.AlertDialog:
        options = [("This computer (local timezone)", "Local")]
        options.extend(worldclock.CITIES)

        dropdown = Gtk.DropDown.new_from_strings([label for label, _zone in options])
        dropdown.set_selected(0)
        dropdown.set_hexpand(True)
        dropdown.set_valign(Gtk.Align.CENTER)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(4)
        label = Gtk.Label(label="Pick a city to add to your World clock:")
        label.add_css_class("timey-hint")
        label.set_halign(Gtk.Align.START)
        box.append(label)
        box.append(dropdown)

        dialog = Adw.AlertDialog()
        dialog.set_heading("Add a clock")
        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_add_zone_response, dropdown, options)
        return dialog

    def _on_add_zone_response(
        self,
        _dialog: Adw.AlertDialog,
        response: str,
        dropdown: Gtk.DropDown,
        options: list[tuple[str, str]],
    ) -> None:
        if response != "add":
            return
        index = dropdown.get_selected()
        if index < 0 or index >= len(options):
            return
        zone = options[index][1]
        if zone in self.state.zones:
            return
        self.state.zones.append(zone)
        self._save()
        self._rebuild_world_list()

    def _remove_zone(self, zone: str) -> None:
        if zone not in self.state.zones:
            return
        self.state.zones.remove(zone)
        if not self.state.zones:
            # Always keep the local clock available.
            self.state.zones = ["Local"]
        self._save()
        self._rebuild_world_list()

    def _rebuild_world_list(self) -> None:
        while (child := self.world_box.get_first_child()) is not None:
            self.world_box.remove(child)
        self.world_cards = []
        for zone in self.state.zones:
            card = _WorldCard(self, zone)
            self.world_cards.append(card)
            self.world_box.append(card.card)

    # ── settings dialog ──────────────────────────────────────────────
    def _on_settings(self, *_args) -> None:
        self._build_settings_dialog().present(self)

    def _build_settings_dialog(self) -> Adw.AlertDialog:
        group = Adw.PreferencesGroup()

        background_row = Adw.SwitchRow()
        background_row.set_title("Keep running in the background")
        background_row.set_subtitle(
            "Alarms and timers keep going — with desktop notifications and "
            "sound — even when the window is closed. Starts automatically at login."
        )
        background_row.set_active(self.state.background)
        background_row.connect("notify::active", self._on_background_toggled, background_row)
        group.add(background_row)

        sound_row = Adw.SwitchRow()
        sound_row.set_title("Play alert sounds")
        sound_row.set_subtitle("Play a sound when an alarm or a timer finishes.")
        sound_row.set_active(self.state.sound)
        sound_row.connect("notify::active", self._on_sound_toggled, sound_row)
        group.add(sound_row)

        theme_row = Adw.ActionRow()
        theme_row.set_title("Color scheme")
        theme_row.set_subtitle("Dark or light.")
        theme_button = Gtk.Button(label="Switch")
        theme_button.add_css_class("timey-btn")
        theme_button.add_css_class("timey-sm")
        theme_button.connect("clicked", self._on_settings_theme_clicked)
        theme_row.add_suffix(theme_button)
        group.add(theme_row)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.append(group)

        dialog = Adw.AlertDialog()
        dialog.set_heading("Settings")
        dialog.set_body("Preferences are remembered between launches.")
        dialog.set_extra_child(box)
        if self.state.background:
            dialog.add_response("quit", "Quit Timey")
            dialog.set_response_appearance("quit", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        dialog.connect("response", self._on_settings_response)
        return dialog

    def _on_background_toggled(self, row: Adw.SwitchRow, _param, _data=None) -> None:
        self.app.set_background_enabled(row.get_active())

    def _on_sound_toggled(self, row: Adw.SwitchRow, _param, _data=None) -> None:
        self.state.sound = row.get_active()
        self._save()

    def _on_settings_theme_clicked(self, _button: Gtk.Button) -> None:
        self._apply_theme("light" if self._theme == "dark" else "dark", persist=True)

    def _on_settings_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "quit":
            self.app.quit()

    # ── theming ──────────────────────────────────────────────────────
    def _apply_theme(self, theme: str, *, persist: bool = False) -> None:
        self._theme = theme
        self.state.theme = theme
        manager = Adw.StyleManager.get_default()
        scheme = (
            Adw.ColorScheme.FORCE_DARK if theme == "dark" else Adw.ColorScheme.FORCE_LIGHT
        )
        manager.set_color_scheme(scheme)

        # Refresh the stylesheet from the new palette.
        self._provider.load_from_string(style.build_css(theme))

        if persist:
            self._save()

        # Icon shows the *target* mode: sun (light) in dark, moon in light.
        image = self.theme_button.get_child()
        image.set_from_icon_name(
            "weather-clear-symbolic" if theme == "dark" else "weather-clear-night-symbolic"
        )
        self.theme_button.set_tooltip_text(
            "Switch to light mode" if theme == "dark" else "Switch to dark mode"
        )

    def _on_realize(self, *_args) -> None:
        if not self._css_installed:
            self._css_installed = True
            self._provider.load_from_string(style.build_css(self._theme))
            Gtk.StyleContext.add_provider_for_display(
                self.get_display(), self._provider, _CSS_PRIORITY
            )

    def _on_destroy(self, *_args) -> None:
        self._save()

    def _on_close_request(self, *_args) -> bool:
        """Close hides the window instead of quitting when in background mode."""
        if self.state.background:
            self._save()
            self.hide()
            return True
        return False

    def _save(self) -> None:
        self.app.save_state()

    # ── per-tick view refresh (driven by the application tick) ───────
    def on_tick(self) -> None:
        if not self.is_visible():
            return
        if self.stopwatch.is_running():
            self.time_label.set_text(format_elapsed(self.stopwatch.elapsed()))
        for card in self.timer_cards:
            if card.countdown.is_running():
                card.update_time()
        for card in self.world_cards:
            card.tick()

    def on_timer_finished(self, countdown: Countdown) -> None:
        for card in self.timer_cards:
            if card.countdown is countdown:
                card.refresh()

    def on_alarm_fired(self, alarm: Alarm) -> None:
        self._on_alarm_changed()

    # ── stopwatch actions ────────────────────────────────────────────
    def _on_toggle_start(self, *_args) -> None:
        sw = self.stopwatch
        if sw.is_running():
            sw.pause()
        else:
            sw.start()
        self._save()
        self._refresh_stopwatch()

    def _on_lap(self, *_args) -> None:
        record = self.stopwatch.lap()
        if record is None:
            return
        self._append_lap_row(record)
        self._refresh_stopwatch()
        self._save()

    def _on_reset(self, *_args) -> None:
        self.stopwatch.reset()
        self.time_label.set_text(format_elapsed(0.0))
        while (row := self.laps_list.get_first_child()) is not None:
            self.laps_list.remove(row)
        self._refresh_stopwatch()
        self._save()

    def _refresh_stopwatch(self) -> None:
        sw = self.stopwatch
        state = sw.state

        self.state_label.remove_css_class("running")
        self.state_label.remove_css_class("paused")
        if state == "running":
            self.state_label.set_text("RUNNING")
            self.state_label.add_css_class("running")
        elif state == "paused":
            self.state_label.set_text("PAUSED")
            self.state_label.add_css_class("paused")
        else:
            self.state_label.set_text("STANDBY")

        if state == "running":
            self.start_button.set_label("Pause")
        elif state == "paused":
            self.start_button.set_label("Resume")
        else:
            self.start_button.set_label("Start")
            self.time_label.set_text(format_elapsed(0.0))

        has_time = sw.elapsed() > 0 or sw.lap_count > 0
        self.reset_button.set_sensitive(has_time)
        self.lap_button.set_sensitive(state == "running")

        # Restore persisted laps, if any.
        if sw.lap_count and self.laps_list.get_first_child() is None:
            for record in sw.laps:
                self._append_lap_row(record, scroll=False)

        has_laps = sw.lap_count > 0
        self.laps_empty.set_visible(not has_laps)
        self.laps_list.set_visible(has_laps)

    def _append_lap_row(self, record: dict, *, scroll: bool = True) -> None:
        row = Gtk.ListBoxRow()
        row.add_css_class("timey-laprow")

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        content.set_margin_start(12)
        content.set_margin_end(12)

        index = Gtk.Label(label=f"LAP {record['index']:02d}")
        index.add_css_class("timey-lapid")
        index.set_halign(Gtk.Align.START)
        index.set_hexpand(True)
        index.set_valign(Gtk.Align.CENTER)
        content.append(index)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        right.set_halign(Gtk.Align.END)

        total = Gtk.Label(label=format_elapsed(record["total"]))
        total.add_css_class("timey-laptotal")
        total.set_halign(Gtk.Align.END)
        right.append(total)

        split = Gtk.Label(label=f"+{record['split']:.2f}s this lap")
        split.add_css_class("timey-lapsplit")
        split.set_halign(Gtk.Align.END)
        right.append(split)

        content.append(right)
        row.set_child(content)
        self.laps_list.append(row)

        if scroll:
            adjustment = self.scroller.get_vadjustment()
            GLib.idle_add(adjustment.set_value, adjustment.get_upper())

    # ── keyboard ─────────────────────────────────────────────────────
    def _on_key_pressed(self, _controller, keyval: int, _keycode: int, state) -> bool:
        if state & Gdk.ModifierType.CONTROL_MASK:
            return False  # leave Ctrl shortcuts alone
        # Countdown timers have their own controls; shortcuts belong to
        # the stopwatch page.
        if self.stack.get_visible_child_name() != "stopwatch":
            return False

        if keyval == Gdk.KEY_space:
            focus = self.get_focus()
            if isinstance(focus, Gtk.Button):
                return False
            self._on_toggle_start()
            return True
        if keyval in (Gdk.KEY_l, Gdk.KEY_L):
            self._on_lap()
            return True
        if keyval in (Gdk.KEY_r, Gdk.KEY_R):
            self._on_reset()
            return True
        return False

    # ── header actions ───────────────────────────────────────────────
    def _on_mode_toggled(self, button: Gtk.ToggleButton, page: str) -> None:
        if button.get_active():
            self.stack.set_visible_child_name(page)

    def _on_toggle_theme(self, *_args) -> None:
        self._apply_theme("light" if self._theme == "dark" else "dark", persist=True)

    def _on_about(self, *_args) -> None:
        about = Adw.AboutWindow(transient_for=self)
        about.set_application_name(APP_NAME)
        about.set_version(VERSION)
        about.set_developer_name("PixlPixlPixl")
        about.set_comments(
            "A grayscale stopwatch, countdown timers, alarms and world "
            "clock for the Linux desktop."
        )
        about.set_website(WEBSITE)
        about.add_credit_section("Built with", ["Python", "GTK 4", "Libadwaita"])
        about.present()
        self.about_window = about
        self._relabel_about_website(about)

    def _relabel_about_website(self, about: Adw.AboutWindow) -> None:
        """AboutWindow's built-in row is hard-coded as “Website”.

        There is no public API to rename it, so walk the window's widget
        tree after it is mapped and relabel the button to “Github”.
        """

        def walk(widget: Gtk.Widget) -> None:
            if isinstance(widget, Gtk.Label) and widget.get_text() == "Website":
                widget.set_text("Github")
            child = widget.get_first_child()
            while child is not None:
                walk(child)
                child = child.get_next_sibling()

        def once() -> bool:
            walk(about)
            return False

        # The link row may not be built yet right after present() — retry
        # a few times during the first frames.
        for attempt in (0, 100, 300):
            GLib.timeout_add(attempt, once)


# ─────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────
class TimeyApplication(Adw.Application):
    def __init__(self, *, start_hidden: bool = False) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._start_hidden = start_hidden
        self.state = statemod.State()
        self.window: TimeyWindow | None = None
        self._tick_source: int | None = None
        self._tick_count = 0
        self._autostart_checked = False

        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

        # Lets notification clicks raise the window.
        open_action = Gio.SimpleAction.new(
            "open-window", GLib.VariantType.new("s")
        )
        open_action.connect("activate", self._on_open_window)
        self.add_action(open_action)

    # ── lifecycle ────────────────────────────────────────────────────
    def _on_activate(self, app: Adw.Application) -> None:
        if self.window is None:
            # First activation: build everything, honour --hidden.
            self.state = statemod.State.load()
            self._ensure_autostart_consistent()
            self.window = TimeyWindow(self)
            self._start_tick()
            if self._start_hidden:
                self.window.hide()
                return
        # Any later activation means the user asked for Timey — raise it,
        # even if it was running hidden in the background.
        self.window.present()
        self.window._refresh_stopwatch()

    def _on_open_window(self, _action, _parameter) -> None:
        window = self.window
        if window is None:
            self._on_activate(self)
            return
        window.present()
        window._refresh_stopwatch()

    def _on_shutdown(self, *_args) -> None:
        if self._tick_source is not None:
            GLib.source_remove(self._tick_source)
            self._tick_source = None
        self.save_state()

    def _start_tick(self) -> None:
        if self._tick_source is None:
            self._tick_source = GLib.timeout_add(TICK_MS, self._tick)

    def _tick(self) -> bool:
        state = self.state
        self._tick_count += 1

        # Countdowns that finished this tick.
        finished = [cd for cd in state.timers if cd.is_running() and cd.update()]
        for countdown in finished:
            self._alert_timer_finished(countdown)
            if self.window is not None:
                self.window.on_timer_finished(countdown)

        # Alarms that went off this tick.
        armed = [a for a in state.alarms if a.enabled and a.next_fire is not None]
        if armed:
            moment = alarm_now()
            for alarm in armed:
                if alarm.check(moment):
                    self._alert_alarm_fired(alarm)
                    state.sort_alarms()
                    if self.window is not None:
                        self.window.on_alarm_fired(alarm)

        if self.window is not None:
            self.window.on_tick()

        # Persist running engines a few times per minute so a crash or
        # reboot loses at most a few seconds of progress.
        running = state.stopwatch.is_running() or any(
            cd.is_running() for cd in state.timers
        )
        if running and self._tick_count % AUTOSAVE_TICKS == 0:
            self.save_state()
        return True

    # ── alerts ───────────────────────────────────────────────────────
    def _alert_timer_finished(self, countdown: Countdown) -> None:
        label = countdown.name if countdown.name else "Timer"
        alerts.timer_alert(self, f"timey-timer-{label}", countdown.name, self.state.sound)

    def _alert_alarm_fired(self, alarm: Alarm) -> None:
        alerts.alarm_alert(self, f"timey-alarm-{alarm.uid}", alarm.name, self.state.sound)

    # ── persistence / background ─────────────────────────────────────
    def save_state(self) -> None:
        self.state.save()

    def set_background_enabled(self, enabled: bool) -> None:
        self.state.background = bool(enabled)
        self.save_state()
        self._sync_autostart()

    def _ensure_autostart_consistent(self) -> None:
        if self._autostart_checked:
            return
        self._autostart_checked = True
        self._sync_autostart()

    def _sync_autostart(self) -> None:
        if self.state.background:
            self._write_autostart()
        else:
            self._remove_autostart()

    def _autostart_dir(self) -> Path:
        return env.xdg_config_home() / "autostart"

    def _resolve_background_command(self) -> list[str]:
        """Command line that launches Timey hidden at login.

        Prefers the launcher installed by install.sh (which exports
        ``TIMEY_LAUNCHER``), falls back to a checkout wrapper script so
        development installs work too.
        """
        launcher = os.environ.get("TIMEY_LAUNCHER")
        if launcher and Path(launcher).is_file():
            return [launcher, "--hidden"]

        pkg = Path(__file__).resolve()
        # Installed layout: <prefix>/lib/timey/timey/app.py
        if len(pkg.parents) > 3 and pkg.parents[2].name == "lib":
            candidate = pkg.parents[3] / "bin" / "timey"
            if candidate.is_file():
                return [str(candidate), "--hidden"]

        checked = shutil.which("timey")
        if checked:
            return [checked, "--hidden"]

        # Development checkout: generate a small wrapper we control.
        wrapper = env.config_dir() / "run-hidden.sh"
        repo = pkg.parents[1]
        try:
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            wrapper.write_text(
                "#!/bin/sh\n"
                f"cd {shlex.quote(str(repo))} || exit 1\n"
                "export PYTHONPATH="
                f"{shlex.quote(str(repo))}${{PYTHONPATH:+:$PYTHONPATH}}\n"
                f"exec {shlex.quote(sys.executable)} -m timey --hidden\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            return [str(wrapper)]
        except OSError:
            return [sys.executable, "-m", "timey", "--hidden"]

    def _write_autostart(self) -> None:
        directory = self._autostart_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        command = " ".join(shlex.quote(part) for part in self._resolve_background_command())
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Timey (background)\n"
            "Comment=Keeps Timey alarms and timers running at login\n"
            f"Exec={command}\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        try:
            (directory / "timey-background.desktop").write_text(entry, encoding="utf-8")
        except OSError:
            pass

    def _remove_autostart(self) -> None:
        try:
            (self._autostart_dir() / "timey-background.desktop").unlink(missing_ok=True)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    """Entry point: load local environment and run the GTK application."""
    args = list(argv if argv is not None else sys.argv)
    env.load_env_files()
    start_hidden = "--hidden" in args
    if start_hidden:
        args.remove("--hidden")
    app = TimeyApplication(start_hidden=start_hidden)
    return app.run(args)
