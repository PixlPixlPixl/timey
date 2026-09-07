"""Timey — a grayscale stopwatch & multi-countdown app.

Built with Python + GTK 4 + Libadwaita.
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import env, style  # noqa: E402
from .countdown import Countdown  # noqa: E402
from .prefs import Prefs  # noqa: E402
from .stopwatch import Stopwatch, format_elapsed  # noqa: E402

APP_ID = "io.github.pixlpixlpixl.Timey"
APP_NAME = "Timey"
VERSION = "0.2.0"
WEBSITE = "https://github.com/PixlPixlPixl/Timey"

TICK_MS = 10  # refresh rate of the centisecond displays

_CSS_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION


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
        self.refresh()

    def _on_reset(self, _button: Gtk.Button) -> None:
        self.countdown.reset()
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
# Main window
# ─────────────────────────────────────────────────────────────────────
class TimeyWindow(Adw.ApplicationWindow):
    """Main application window."""

    def __init__(self, app: Adw.Application, prefs: Prefs) -> None:
        super().__init__(
            application=app,
            title=APP_NAME,
            default_width=440,
            default_height=680,
            resizable=True,
        )
        self.prefs = prefs
        self.stopwatch = Stopwatch()
        self.timer_cards: list[_TimerCard] = []

        self._theme = prefs.theme if prefs.theme in ("dark", "light") else "dark"
        self._provider = Gtk.CssProvider()
        self._css_installed = False
        self._tick_source: int | None = None
        self.about_window: Adw.AboutWindow | None = None

        self._build_ui()
        self.connect("destroy", self._on_destroy)
        self.connect("realize", self._on_realize)

        # Apply the initial theme right away; it is reapplied on realize
        # once a display is available.
        self._apply_theme(self._theme)
        self._refresh_stopwatch()

    # ── UI construction ──────────────────────────────────────────────
    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()

        # Two tools: the stopwatch and the (multi) countdown timers.
        self.stack = Adw.ViewStack()
        self.stack.add_titled(self._build_stopwatch_page(), "stopwatch", "Stopwatch")
        self.stack.add_titled(self._build_timers_page(), "timers", "Timer")

        switcher = Adw.ViewSwitcher(stack=self.stack)
        header.set_title_widget(switcher)
        toolbar.add_top_bar(header)

        # Theme toggle (dark ⇄ light) + about button.
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

        return page

    @staticmethod
    def _make_button(label: str, kind: str) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.add_css_class("timey-btn")
        button.add_css_class(f"timey-{kind}")
        return button

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
        card = _TimerCard(self, countdown)
        self.timer_cards.append(card)

        # Keep the empty-state label first, cards after it.
        self.timers_box.insert_child_after(card.card, self.timers_empty)
        self._refresh_timers_empty_state()
        return card

    def remove_timer(self, card: _TimerCard) -> None:
        if card not in self.timer_cards:
            return
        self.timer_cards.remove(card)
        self.timers_box.remove(card.card)
        self._refresh_timers_empty_state()

    def _refresh_timers_empty_state(self) -> None:
        self.timers_empty.set_visible(not bool(self.timer_cards))

    def _notify_timer_finished(self, countdown: Countdown) -> None:
        app = self.get_application()
        if app is None:
            return
        label = countdown.name if countdown.name else "Timer finished"
        notification = Gio.Notification.new(f"{APP_NAME} - {label}")
        notification.set_body("Countdown complete")
        app.send_notification("timey-countdown-finished", notification)

    # ── theming ──────────────────────────────────────────────────────
    def _apply_theme(self, theme: str, *, persist: bool = False) -> None:
        self._theme = theme
        manager = Adw.StyleManager.get_default()
        scheme = (
            Adw.ColorScheme.FORCE_DARK if theme == "dark" else Adw.ColorScheme.FORCE_LIGHT
        )
        manager.set_color_scheme(scheme)

        # Refresh the stylesheet from the new palette.
        self._provider.load_from_string(style.build_css(theme))

        if persist:
            self.prefs.theme = theme
            self.prefs.save()

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
        # Start the ticker once we have a real clock running.
        if self._tick_source is None:
            self._tick_source = GLib.timeout_add(TICK_MS, self._tick)

    def _tick(self) -> bool:
        if self.stopwatch.is_running():
            self.time_label.set_text(format_elapsed(self.stopwatch.elapsed()))

        for card in self.timer_cards:
            countdown = card.countdown
            if not countdown.is_running():
                continue
            if countdown.update():
                card.refresh()
                self._notify_timer_finished(countdown)
            else:
                card.update_time()
        return True  # keep ticking

    def _on_destroy(self, *_args) -> None:
        if self._tick_source is not None:
            GLib.source_remove(self._tick_source)
            self._tick_source = None

    # ── stopwatch actions ────────────────────────────────────────────
    def _on_toggle_start(self, *_args) -> None:
        if self.stopwatch.is_running():
            self.stopwatch.pause()
        else:
            self.stopwatch.start()
        self._refresh_stopwatch()

    def _on_lap(self, *_args) -> None:
        record = self.stopwatch.lap()
        if record is None:
            return
        self._append_lap_row(record)
        self._refresh_stopwatch()

    def _on_reset(self, *_args) -> None:
        self.stopwatch.reset()
        self.time_label.set_text(format_elapsed(0.0))
        while (row := self.laps_list.get_first_child()) is not None:
            self.laps_list.remove(row)
        self._refresh_stopwatch()

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

        has_laps = sw.lap_count > 0
        self.laps_empty.set_visible(not has_laps)
        self.laps_list.set_visible(has_laps)

    def _append_lap_row(self, record: dict) -> None:
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
    def _on_toggle_theme(self, *_args) -> None:
        self._apply_theme("light" if self._theme == "dark" else "dark", persist=True)

    def _on_about(self, *_args) -> None:
        about = Adw.AboutWindow(transient_for=self)
        about.set_application_name(APP_NAME)
        about.set_version(VERSION)
        about.set_developer_name("PixlPixlPixl")
        about.set_comments("A grayscale stopwatch and countdown timer for the Linux desktop.")
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


class TimeyApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)

    def _on_activate(self, app: Adw.Application) -> None:
        window = self.props.active_window
        if window is None:
            window = TimeyWindow(app=app, prefs=Prefs.load())
        window.present()


def main(argv: list[str] | None = None) -> int:
    """Entry point: load local environment and run the GTK application."""
    env.load_env_files()
    app = TimeyApplication()
    return app.run(argv if argv is not None else sys.argv)
