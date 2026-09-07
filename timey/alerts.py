"""Desktop notifications & audible alerts for Timey.

Notifications go through the :class:`Gio.Application` so they are routed
correctly whether the window is open, hidden or in the background.
Audio is attempted via ``canberra-gtk-play`` when available (no extra
Python dependencies); any failure is silent.
"""

from __future__ import annotations

import shutil
import subprocess

#: Event ids tried for each alert kind, in order (from the freedesktop
#: sound naming spec / common themes).
_SOUND_EVENTS: dict[str, tuple[str, ...]] = {
    "alarm": ("alarm-clock-elapsed", "alarm", "complete"),
    "timer": ("complete", "message-new-instant"),
}

#: Cache of command availability so we only stat once.
_canberra: str | None | bool = None


def _canberra_path() -> str | None:
    global _canberra
    if _canberra is None:
        _canberra = shutil.which("canberra-gtk-play")
    return _canberra if _canberra else None


def play_sound(kind: str, enabled: bool = True) -> bool:
    """Play the alert sound for ``kind`` (``"alarm"`` or ``"timer"``).

    Returns True when an audible alert was actually produced. Never
    raises and never blocks the UI for long.
    """
    if not enabled:
        return False
    binary = _canberra_path()
    if binary is None:
        return False
    for event in _SOUND_EVENTS.get(kind, ("complete",)):
        try:
            result = subprocess.run(
                [binary, "--id", event],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
                check=False,
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            return False
    return False


def notify(
    app,
    key: str,
    title: str,
    body: str,
    *,
    urgent: bool = True,
    open_action: bool = True,
) -> None:
    """Send a desktop notification from ``app`` (a Gio.Application)."""
    from gi.repository import Gio, GLib

    notification = Gio.Notification.new(title)
    notification.set_body(body)
    if urgent:
        notification.set_priority(Gio.NotificationPriority.URGENT)
    if open_action:
        try:
            notification.set_default_action_and_target("app.open-window", GLib.Variant("s", "main"))
        except Exception:
            pass
    try:
        app.send_notification(key, notification)
    except Exception:
        pass


def alarm_alert(app, key: str, name: str, sound: bool) -> None:
    """Notify + play sound that an alarm went off."""
    title = f"Alarm — {name}" if name else "Alarm"
    body = "Your alarm is going off."
    notify(app, key, title, body)
    play_sound("alarm", sound)


def timer_alert(app, key: str, name: str, sound: bool) -> None:
    """Notify + play sound that a countdown finished."""
    title = f"{name} finished" if name else "Timer finished"
    body = "Countdown complete."
    notify(app, key, title, body)
    play_sound("timer", sound)
