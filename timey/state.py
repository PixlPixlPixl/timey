"""Persistent state for Timey — settings and every model.

Everything that must survive a restart lives in one JSON document under
``~/.config/timey/state.json`` (writes are atomic). That includes the
theme, background/sound preferences, alarms, countdown timers (a running
timer keeps counting down across launches), the stopwatch (history, laps
and whether it was left running) and the world-clock timezone list.

The very first run migrates the theme from the legacy ``config.ini`` if
one exists, so existing installs keep their choice.
"""

from __future__ import annotations

import json
import os
import tempfile
import time as _time
from pathlib import Path

from . import env
from .alarm import Alarm, now as _alarm_now
from .countdown import Countdown
from .stopwatch import Stopwatch

SCHEMA_VERSION = 1

VALID_THEMES = ("dark", "light")

#: env vars read on first launch
ENV_THEME = "TIMEY_THEME"
ENV_BACKGROUND_DEFAULT = "TIMEY_BACKGROUND_DEFAULT"

STATE_FILE = "state.json"
LEGACY_FILE = "config.ini"


def normalize_theme(value: str | None) -> str:
    return value if value in VALID_THEMES else "dark"


def state_path() -> Path:
    return env.config_dir() / STATE_FILE


def legacy_config_path() -> Path:
    return env.config_dir() / LEGACY_FILE


def default_background_enabled() -> bool:
    """First-launch "run in the background" preference.

    ``install.sh`` exports ``TIMEY_BACKGROUND_DEFAULT=1`` from its
    generated launcher, so an *installed* Timey keeps running in the
    background by default while a development checkout does not.
    """
    return os.environ.get(ENV_BACKGROUND_DEFAULT) == "1"


def default_launch_on_login() -> bool:
    """First-launch "start Timey at login" preference.

    Follows the same install-default as the background setting so an
    installed Timey keeps its historic behaviour of starting at login.
    """
    return default_background_enabled()


def default_theme() -> str:
    """First-launch theme: TIMEY_THEME env, legacy config.ini, then dark."""
    value = normalize_theme(os.environ.get(ENV_THEME))
    if value != "dark":
        return value
    legacy = _read_legacy_theme()
    return legacy if legacy else "dark"


def _read_legacy_theme() -> str | None:
    path = legacy_config_path()
    if not path.is_file():
        return None
    try:
        import configparser

        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        if parser.has_option("preferences", "theme"):
            return normalize_theme(parser.get("preferences", "theme"))
    except Exception:
        pass
    return None


class State:
    """One loaded/saved snapshot of everything Timey remembers."""

    def __init__(
        self,
        *,
        theme: str = "dark",
        background: bool = False,
        launch_on_login: bool = False,
        sound: bool = True,
        alarms: list[Alarm] | None = None,
        timers: list[Countdown] | None = None,
        stopwatch: Stopwatch | None = None,
        zones: list[str] | None = None,
    ) -> None:
        self.theme = normalize_theme(theme)
        self.background = bool(background)
        self.launch_on_login = bool(launch_on_login)
        self.sound = bool(sound)
        self.alarms = alarms if alarms is not None else []
        self.timers = timers if timers is not None else []
        self.stopwatch = stopwatch if stopwatch is not None else Stopwatch()
        self.zones = zones if zones is not None else ["Local"]

    # ── loading ──────────────────────────────────────────────────────
    @classmethod
    def load(cls) -> "State":
        """Load persisted state, falling back to first-launch defaults."""
        path = state_path()
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return cls.from_dict(raw)
            except (OSError, ValueError):
                pass
        return cls(
            theme=default_theme(),
            background=default_background_enabled(),
            launch_on_login=default_launch_on_login(),
        )

    @classmethod
    def from_dict(cls, raw: object) -> "State":
        if not isinstance(raw, dict):
            return cls()
        settings = raw.get("settings")
        settings = settings if isinstance(settings, dict) else {}

        alarms = [
            alarm
            for item in (raw.get("alarms") or [])
            if isinstance(item, dict)
            if (alarm := _alarm_from_dict(item)) is not None
        ]
        timers = [
            timer
            for item in (raw.get("timers") or [])
            if isinstance(item, dict)
            if (timer := _timer_from_dict(item)) is not None
        ]

        stopwatch = Stopwatch()
        sw_raw = raw.get("stopwatch")
        if isinstance(sw_raw, dict):
            try:
                stopwatch = Stopwatch.from_state(sw_raw)
            except (TypeError, ValueError, KeyError):
                pass

        zones = [z for z in (raw.get("zones") or []) if isinstance(z, str) and z]
        if not zones:
            zones = ["Local"]

        background = bool(settings.get("background", False))
        # Migrate older configs: autostart used to follow the background
        # setting, so default the new toggle to whatever it was.
        launch_on_login = bool(
            settings.get("launch_on_login", background)
        )

        state = cls(
            theme=normalize_theme(settings.get("theme")),
            background=background,
            launch_on_login=launch_on_login,
            sound=settings.get("sound", True) if "sound" in settings else True,
            alarms=alarms,
            timers=timers,
            stopwatch=stopwatch,
            zones=zones,
        )

        # Bring restored alarms up to date with the present (a missed
        # occurrence while the app was closed is skipped, not fired late).
        current = _alarm_now()
        for alarm in state.alarms:
            alarm.reconcile(current)
        return state

    # ── saving ───────────────────────────────────────────────────────
    def to_dict(self, wall: float | None = None) -> dict[str, object]:
        if wall is None:
            wall = _time.time()
        return {
            "version": SCHEMA_VERSION,
            "settings": {
                "theme": self.theme,
                "background": self.background,
                "launch_on_login": self.launch_on_login,
                "sound": self.sound,
            },
            "alarms": [alarm.to_dict() for alarm in self.alarms],
            "timers": [timer.save_state(wall) for timer in self.timers],
            "stopwatch": self.stopwatch.save_state(wall),
            "zones": self.zones,
        }

    def save(self) -> None:
        """Persist atomically; failures are non-fatal."""
        path = state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.to_dict(), indent=2)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".timey-state-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError:
            # Non-fatal: the app keeps working if config is unwritable.
            pass

    # ── helpers for the UI ───────────────────────────────────────────
    def sort_alarms(self) -> None:
        """Keep the alarm list ordered by when they fire next."""
        self.alarms.sort(key=_alarm_sort_key)

    def alarm_index(self, alarm: Alarm) -> int:
        for i, candidate in enumerate(self.alarms):
            if candidate.uid == alarm.uid:
                return i
        return -1

    def timer_index(self, countdown: Countdown) -> int:
        for i, candidate in enumerate(self.timers):
            if candidate is countdown:
                return i
        return -1

    def zone_index(self, zone: str) -> int:
        for i, candidate in enumerate(self.zones):
            if candidate == zone:
                return i
        return -1


# ── serialization helpers ────────────────────────────────────────────
def _alarm_from_dict(data: dict) -> Alarm | None:
    try:
        return Alarm.from_dict(data)
    except (ValueError, TypeError, KeyError):
        return None


def _timer_from_dict(data: dict) -> Countdown | None:
    try:
        return Countdown.from_state(data)
    except (ValueError, TypeError, KeyError):
        return None


def _alarm_sort_key(alarm: Alarm) -> tuple:
    """Disabled / one-shot-rung alarms sort after armed ones; otherwise
    by time of day, then name (stable, predictable list)."""
    if not alarm.enabled:
        return (1, alarm.hour, alarm.minute, alarm.name.lower())
    return (0, alarm.hour, alarm.minute, alarm.name.lower())
