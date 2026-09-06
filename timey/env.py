"""Tiny, dependency-free ``.env`` loader.

Loads local override files *without* overriding variables that already
exist in the process environment. Timey currently exposes no network
features, but this gives a safe place for future secrets / local config
while keeping them out of version control.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["load_env_files", "get", "env_file_paths"]


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "timey"


def env_file_paths() -> list[Path]:
    """Locations probed for ``.env`` files, in load order."""
    candidates = [Path.cwd() / ".env", _config_dir() / ".env"]
    seen: set[Path] = set()
    paths: list[Path] = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            paths.append(path)
    return paths


def load_env_files() -> None:
    """Load every discovered ``.env`` file into ``os.environ``.

    Existing environment variables always win.
    """
    for path in env_file_paths():
        _load_file(path)


def _load_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key.isidentifier():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def get(name: str, default: str | None = None) -> str | None:
    """Read a value from the environment after ``.env`` files are loaded."""
    return os.environ.get(name, default)
