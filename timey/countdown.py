"""Countdown timer engine — pure Python, no GUI dependencies.

Designed to be driven by a periodic UI tick: call :meth:`update` while a
timer is running; it returns ``True`` exactly once when the timer hits
zero, so a UI layer can react (notification, flash, sound, ...) without
double-firing.

Timers survive restarts. While a timer is running its *remaining* time is
measured with the monotonic clock (immune to wall-clock adjustments), but
every save also records a wall-clock anchor (:meth:`save_state`). A later
:meth:`from_state` restores the timer and accounts for the time that
passed while the app was closed, so a running timer keeps counting down
across launches.
"""

from __future__ import annotations

import time

IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"
FINISHED = "finished"

STATES = (IDLE, RUNNING, PAUSED, FINISHED)


class Countdown:
    """A single countdown from ``duration`` seconds down to zero."""

    def __init__(self, duration_s: float, name: str = "") -> None:
        if duration_s <= 0:
            raise ValueError("Countdown duration must be positive")
        self.duration = float(duration_s)
        self.name = str(name).strip()
        self._state = IDLE
        self._remaining = self.duration
        self._started_at = 0.0

    # ── queries ──────────────────────────────────────────────────────
    @property
    def state(self) -> str:
        return self._state

    def is_idle(self) -> bool:
        return self._state == IDLE

    def is_running(self) -> bool:
        return self._state == RUNNING

    def is_paused(self) -> bool:
        return self._state == PAUSED

    def is_finished(self) -> bool:
        return self._state == FINISHED

    def remaining(self) -> float:
        """Seconds left on the clock (clamped at zero)."""
        if self._state == RUNNING:
            return max(0.0, self._remaining - self._running_time())
        return max(0.0, self._remaining)

    def progress(self) -> float:
        """Fraction elapsed in ``0.0 .. 1.0``."""
        if self.duration <= 0:
            return 1.0
        return max(0.0, min(1.0, (self.duration - self.remaining()) / self.duration))

    # ── controls ─────────────────────────────────────────────────────
    def start(self) -> None:
        """Start or resume counting down."""
        if self._state in (IDLE, PAUSED):
            self._started_at = self._now()
            self._state = RUNNING

    def pause(self) -> None:
        """Pause a running countdown, remembering the remaining time."""
        if self._state == RUNNING:
            self._remaining = self.remaining()
            self._state = PAUSED

    def reset(self) -> None:
        """Return to a full, idle countdown."""
        self._state = IDLE
        self._remaining = self.duration
        self._started_at = 0.0

    def update(self) -> bool:
        """Advance the clock; returns ``True`` the moment time runs out."""
        if self._state != RUNNING:
            return False
        if self.remaining() <= 0:
            self._remaining = 0.0
            self._started_at = 0.0
            self._state = FINISHED
            return True
        return False

    # ── persistence ──────────────────────────────────────────────────
    def save_state(self, wall: float | None = None) -> dict[str, object]:
        """Serializable snapshot, as of now.

        ``wall`` is a wall-clock ``time.time()`` stamp and is stored only
        while the countdown is running, so a restore can tell how much of
        the remaining time elapsed while the app was closed.
        """
        if wall is None:
            wall = time.time()
        data: dict[str, object] = {
            "name": self.name,
            "duration": self.duration,
            "state": self._state,
            "remaining": self.remaining(),
        }
        if self._state == RUNNING:
            data["wall"] = wall
        return data

    @classmethod
    def from_state(cls, data: dict, wall: float | None = None) -> "Countdown":
        """Rebuild a countdown from :meth:`save_state`.

        A running countdown continues counting down across the gap: any
        time that passed while the app was closed is subtracted from the
        stored remaining time. If it ran out while away, the restored
        timer is ``FINISHED``.
        """
        if wall is None:
            wall = time.time()
        name = str(data.get("name", ""))
        duration = float(data.get("duration", 0))
        if duration <= 0:
            raise ValueError("Countdown duration must be positive")
        countdown = cls(duration, name=name)

        state = data.get("state", IDLE)
        if state == FINISHED:
            countdown._state = FINISHED
            countdown._remaining = 0.0
            return countdown
        if state == PAUSED:
            countdown._state = PAUSED
            countdown._remaining = max(0.0, float(data.get("remaining", duration)))
            return countdown
        if state == IDLE:
            # Already constructed idle at full duration.
            return countdown

        # Running (or corrupt state): treat as running.
        remaining = max(0.0, float(data.get("remaining", duration)))
        anchor = float(data.get("wall") or wall)
        remaining = max(0.0, remaining - (wall - anchor))
        countdown._remaining = remaining
        if remaining <= 0:
            countdown._state = FINISHED
            countdown._remaining = 0.0
        else:
            # Start from here with the reduced remaining time so the
            # monotonic clock keeps measuring inside this process.
            countdown._state = IDLE
            countdown.start()
        return countdown

    # ── internals ────────────────────────────────────────────────────
    def _running_time(self) -> float:
        return self._now() - self._started_at

    def _now(self) -> float:
        return time.monotonic()
