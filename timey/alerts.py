"""Desktop notifications & audible alerts for Timey.

Notifications go through the :class:`Gio.Application` so they are routed
correctly whether the window is open, hidden or in the background.

Audio is synthesized as small WAV files with the Python standard library
(no extra dependencies) and played with ``canberra-gtk-play`` when
available, falling back to ``paplay``. Failures are always silent.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave

_SAMPLE_RATE = 44100

#: Built-in sounds: token -> (label, list of (freq Hz, seconds, volume)).
#: A ``freq`` of 0 inserts a silence gap between notes.
BUILTIN_SOUNDS: dict[str, tuple[str, tuple]] = {
    "default": (
        "Default",
        ((660, 0.45, 0.9),),
    ),
    "bell": (
        "Bell",
        ((880, 0.9, 0.8),),
    ),
    "chime": (
        "Chime",
        (
            (523.25, 0.28, 1.0),
            (0, 0.04, 0.0),
            (659.25, 0.28, 1.0),
            (0, 0.04, 0.0),
            (783.99, 0.5, 1.0),
        ),
    ),
    "ping": (
        "Ping",
        ((1318.51, 0.24, 0.85),),
    ),
    "alarm": (
        "Alarm",
        (
            (987.77, 0.22, 1.0),
            (0, 0.14, 0.0),
            (987.77, 0.22, 1.0),
            (0, 0.14, 0.0),
            (987.77, 0.22, 1.0),
        ),
    ),
}

#: Spec prefix stored for user-picked sound files.
FILE_PREFIX = "file:"

_canberra: str | None | bool = None
_paplay: str | None | bool = None
_wav_cache: dict[str, str] = {}


def sound_options() -> list[tuple[str, str]]:
    """Built-in sound choices as ``(spec, label)`` pairs."""
    return [(key, label) for key, (label, _notes) in BUILTIN_SOUNDS.items()]


def spec_is_file(spec: str) -> bool:
    return bool(spec) and spec.startswith(FILE_PREFIX)


def spec_label(spec: str) -> str:
    """Human label for a sound spec (``'bell'``, ``'file:…'``, ...)."""
    if spec_is_file(spec):
        return os.path.basename(spec[len(FILE_PREFIX):])
    if spec in BUILTIN_SOUNDS:
        return BUILTIN_SOUNDS[spec][0]
    return "Default"


# ── synthesis ─────────────────────────────────────────────────────────
def _tone_path(tone: str) -> str | None:
    if tone not in BUILTIN_SOUNDS:
        return None
    if tone in _wav_cache:
        return _wav_cache[tone]
    try:
        directory = tempfile.gettempdir()
        path = os.path.join(directory, f"timey-{tone}.wav")
        _write_wav(path, BUILTIN_SOUNDS[tone][1])
        _wav_cache[tone] = path
        return path
    except OSError:
        return None


def _write_wav(path: str, notes: tuple) -> None:
    """Write a 16-bit mono WAV made of the given notes."""
    frames: list[float] = []
    for freq, seconds, volume in notes:
        count = max(0, int(seconds * _SAMPLE_RATE))
        for index in range(count):
            if freq <= 0:
                sample = 0.0
            else:
                t = index / _SAMPLE_RATE
                envelope = min(1.0, t / 0.008)  # fade in (avoid click)
                envelope *= min(1.0, (seconds - t) / 0.04)  # fade out
                sample = volume * envelope * math.sin(2.0 * math.pi * freq * t)
            frames.append(sample)

    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        data = b"".join(
            struct.pack("<h", max(-32768, min(32767, int(sample * 32767))))
            for sample in frames
        )
        handle.writeframes(data)


def _run(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _canberra_bin() -> str | None:
    global _canberra
    if _canberra is None:
        _canberra = shutil.which("canberra-gtk-play")
    return _canberra if _canberra else None


def _paplay_bin() -> str | None:
    global _paplay
    if _paplay is None:
        _paplay = shutil.which("paplay")
    return _paplay if _paplay else None


def _play_file(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    canberra = _canberra_bin()
    if canberra is not None and _run([canberra, "--file", path]):
        return True
    paplay = _paplay_bin()
    if paplay is not None and _run([paplay, path]):
        return True
    return False


def play_spec(spec: str, enabled: bool = True) -> bool:
    """Play one alert, given a sound spec (builtin name or ``file:…``)."""
    if not enabled:
        return False
    if spec_is_file(spec):
        return _play_file(spec[len(FILE_PREFIX):])
    tone = spec if spec in BUILTIN_SOUNDS else "default"
    path = _tone_path(tone)
    return bool(path) and _play_file(path)


def play_alarm_tone(enabled: bool = True) -> bool:
    """Play the ringing alarm sound once (callers repeat it)."""
    return play_spec("alarm", enabled)


# ── notifications ─────────────────────────────────────────────────────
def notify(
    app,
    key: str,
    title: str,
    body: str,
    *,
    urgent: bool = True,
    stop_action: bool = False,
) -> None:
    """Send a desktop notification from ``app`` (a Gio.Application)."""
    from gi.repository import Gio

    notification = Gio.Notification.new(title)
    notification.set_body(body)
    if urgent:
        notification.set_priority(Gio.NotificationPriority.URGENT)
    try:
        if stop_action:
            notification.set_default_action("app.stop-alarm")
            notification.add_button("Stop", "app.stop-alarm")
            notification.add_button("Open Timey", "app.open-window")
        else:
            notification.set_default_action_and_target("app.open-window", None)
    except Exception:
        pass
    try:
        app.send_notification(key, notification)
    except Exception:
        pass


def timer_alert(app, key: str, name: str, spec: str, sound: bool) -> None:
    """Notify + play the timer's chosen sound when a countdown finishes."""
    title = f"{name} finished" if name else "Timer finished"
    body = "Countdown complete."
    notify(app, key, title, body)
    play_spec(spec, sound)


def alarm_started(app, key: str, name: str) -> None:
    """Notify that an alarm is ringing (sound is handled separately)."""
    title = f"Alarm — {name}" if name else "Alarm"
    body = "Tap Stop to silence it."
    notify(app, key, title, body, stop_action=True)
