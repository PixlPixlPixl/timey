"""Timey — a grayscale stopwatch built with Python + GTK 4 + Libadwaita."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import env, style  # noqa: E402
from .prefs import Prefs  # noqa: E402
from .stopwatch import Stopwatch, format_elapsed  # noqa: E402

APP_ID = "io.github.pixlpixlpixl.Timey"
APP_NAME = "Timey"
VERSION = "0.1.0"
WEBSITE = "https://github.com/PixlPixlPixl/Timey"

TICK_MS = 10  # refresh rate of the centisecond display

_CSS_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION


class TimeyWindow(Adw.ApplicationWindow):
    """Main application window."""

    def __init__(self, app: Adw.Application, prefs: Prefs) -> None:
        super().__init__(
            application=app,
            title=APP_NAME,
            default_width=430,
            default_height=640,
            resizable=True,
        )
        self.prefs = prefs
        self.stopwatch = Stopwatch()

        self._theme = prefs.theme if prefs.theme in ("dark", "light") else "dark"
        self._provider = Gtk.CssProvider()
        self._css_installed = False
        self._tick_source: int | None = None

        self._build_ui()
        self.connect("destroy", self._on_destroy)
        self.connect("realize", self._on_realize)

        # Apply the initial theme right away; it is reapplied on realize
        # once a display is available.
        self._apply_theme(self._theme)
        self._refresh()

    # ── UI construction ──────────────────────────────────────────────
    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=APP_NAME, subtitle=""))
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

        toolbar.set_content(self._build_body())

        # Keyboard shortcuts.
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)

    def _build_body(self) -> Gtk.Widget:
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body.set_margin_top(18)
        body.set_margin_bottom(18)
        body.set_margin_start(28)
        body.set_margin_end(28)

        # ── time readout ──
        self.state_label = Gtk.Label(label="STANDBY")
        self.state_label.add_css_class("timey-state")
        body.append(self.state_label)

        self.time_label = Gtk.Label(label=format_elapsed(0.0))
        self.time_label.add_css_class("timey-main")
        self.time_label.set_valign(Gtk.Align.CENTER)
        body.append(self.time_label)

        hint_label = Gtk.Label(label="Space start/pause   ·   L lap   ·   R reset")
        hint_label.add_css_class("timey-hint")
        body.append(hint_label)

        # ── buttons ──
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

        # ── laps panel ──
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

    @staticmethod
    def _make_button(label: str, kind: str) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.add_css_class("timey-btn")
        button.add_css_class(f"timey-{kind}")
        return button

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
        # Start the centisecond ticker once we have a real clock running.
        if self._tick_source is None:
            self._tick_source = GLib.timeout_add(TICK_MS, self._tick)

    def _tick(self) -> bool:
        if self.stopwatch.is_running():
            self.time_label.set_text(format_elapsed(self.stopwatch.elapsed()))
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
        self._refresh()

    def _on_lap(self, *_args) -> None:
        record = self.stopwatch.lap()
        if record is None:
            return
        self._append_lap_row(record)
        self._refresh()

    def _on_reset(self, *_args) -> None:
        self.stopwatch.reset()
        self.time_label.set_text(format_elapsed(0.0))
        while (row := self.laps_list.get_first_child()) is not None:
            self.laps_list.remove(row)
        self._refresh()

    def _refresh(self) -> None:
        sw = self.stopwatch
        state = sw.state

        # Status text and colour.
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

        # Buttons.
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

        # Empty-laps placeholder.
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

        # Keep the newest lap in view.
        adjustment = self.scroller.get_vadjustment()
        GLib.idle_add(adjustment.set_value, adjustment.get_upper())

    # ── keyboard ─────────────────────────────────────────────────────
    def _on_key_pressed(self, _controller, keyval: int, _keycode: int, state) -> bool:
        if state & Gdk.ModifierType.CONTROL_MASK:
            return False  # leave Ctrl shortcuts alone

        if keyval == Gdk.KEY_space:
            # A focused Gtk.Button already activates on Space — don't double-fire.
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
        about.set_comments("A grayscale stopwatch for the Linux desktop.")
        about.set_website(WEBSITE)
        about.add_credit_section("Built with", ["Python", "GTK 4", "Libadwaita"])
        about.present()


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
