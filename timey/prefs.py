"""User preferences for Timey.

Preferences are stored as a simple INI file under the user's XDG
config directory (``~/.config/timey/config.ini``), so no GSettings
schema install is required to run the app from a checkout.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from . import env

GROUP = "preferences"
KEY_THEME = "theme"

VALID_THEMES = ("dark", "light")


def _normalize_theme(value: str | None) -> str:
    return value if value in VALID_THEMES else "dark"


def default_theme() -> str:
    """Theme for the first launch: TIMEY_THEME env, else ``dark``."""
    return _normalize_theme(env.get("TIMEY_THEME"))


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "timey" / "config.ini"


class Prefs:
    """Small persisted-preferences holder for Timey."""

    def __init__(self, theme: str = "dark") -> None:
        self.theme = _normalize_theme(theme)

    @classmethod
    def load(cls) -> "Prefs":
        theme = default_theme()
        path = config_path()
        if path.is_file():
            try:
                parser = configparser.ConfigParser()
                parser.read(path, encoding="utf-8")
                if parser.has_option(GROUP, KEY_THEME):
                    theme = _normalize_theme(parser.get(GROUP, KEY_THEME))
            except (configparser.Error, OSError):
                pass
        return cls(theme)

    def save(self) -> None:
        path = config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            parser = configparser.ConfigParser()
            parser[GROUP] = {KEY_THEME: self.theme}
            with open(path, "w", encoding="utf-8") as handle:
                parser.write(handle)
        except OSError:
            # Non-fatal: the app keeps working, the choice just isn't
            # persisted if the config directory is not writable.
            pass
