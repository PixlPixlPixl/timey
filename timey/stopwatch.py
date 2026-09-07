"""Stopwatch timing engine — pure Python, no GUI dependencies.

Kept deliberately independent from the UI so the timing logic can be
unit-tested in isolation and reused by other front-ends later.
"""

from __future__ import annotations

import time

IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"

#: State constants used across the UI.
STATES = (IDLE, RUNNING, PAUSED)


def format_elapsed(seconds: float, *, with_centis: bool = True) -> str:
    """Format fractional seconds as ``HH:MM:SS.cc`` (optionally bare time)."""
    seconds = max(0.0, float(seconds))
    total_cs = int(seconds * 100)  # floor, so the display never shows 60
    centis = total_cs % 100
    total_seconds = total_cs // 100
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    body = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{body}.{centis:02d}" if with_centis else body


class Stopwatch:
    """Monotonic-clock based stopwatch with lap support.

    The elapsed time is measured from ``time.monotonic()`` so it is
    immune to wall-clock adjustments (NTP, manual changes, ...).
    """

    def __init__(self) -> None:
        self._state = IDLE
        self._started_at = 0.0
        self._accumulated = 0.0
        self._laps: list[dict[str, float | int]] = []
        self._last_lap_total = 0.0

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

    @property
    def laps(self) -> list[dict[str, float | int]]:
        return list(self._laps)

    @property
    def lap_count(self) -> int:
        return len(self._laps)

    # ── controls ─────────────────────────────────────────────────────
    def start(self) -> None:
        """Start or resume the stopwatch."""
        if self._state == IDLE:
            self._accumulated = 0.0
            self._last_lap_total = 0.0
        if self._state in (IDLE, PAUSED):
            self._started_at = self._now()
            self._state = RUNNING

    def pause(self) -> None:
        """Pause a running stopwatch, keeping accumulated time."""
        if self._state == RUNNING:
            self._accumulated += self._running_time()
            self._state = PAUSED

    def elapsed(self) -> float:
        """Total elapsed seconds so far."""
        if self._state == RUNNING:
            return self._accumulated + self._running_time()
        return self._accumulated

    def lap(self) -> dict[str, float | int] | None:
        """Record a lap. Returns the lap record, or ``None`` if not running."""
        if self._state != RUNNING:
            return None
        total = self.elapsed()
        split = total - self._last_lap_total
        self._last_lap_total = total
        record = {"index": len(self._laps) + 1, "total": total, "split": split}
        self._laps.append(record)
        return record

    def reset(self) -> None:
        """Stop everything and clear the accumulated time and laps."""
        self._state = IDLE
        self._started_at = 0.0
        self._accumulated = 0.0
        self._last_lap_total = 0.0
        self._laps.clear()

    # ── persistence ──────────────────────────────────────────────────
    def save_state(self, wall: float | None = None) -> dict[str, object]:
        """Serializable snapshot, as of now.

        ``wall`` is a wall-clock ``time.time()`` stamp, stored while the
        stopwatch is running so a restore can keep counting across an app
        restart (laps are included in the snapshot).
        """
        if wall is None:
            wall = time.time()
        data: dict[str, object] = {
            "state": self._state,
            "elapsed": self.elapsed(),
            "laps": [dict(lap) for lap in self._laps],
        }
        if self._state == RUNNING:
            data["wall"] = wall
        return data

    @classmethod
    def from_state(cls, data: dict, wall: float | None = None) -> "Stopwatch":
        """Rebuild a stopwatch from :meth:`save_state`.

        A stopwatch that was left running keeps running: the time elapsed
        while the app was closed is added before it resumes from now.
        """
        if wall is None:
            wall = time.time()
        watch = cls()
        state = data.get("state", IDLE)
        elapsed = max(0.0, float(data.get("elapsed", 0.0)))
        laps_raw = data.get("laps") or []
        laps = [
            {
                "index": int(lap["index"]),
                "total": float(lap["total"]),
                "split": float(lap["split"]),
            }
            for lap in laps_raw
            if isinstance(lap, dict)
        ]
        watch._laps = laps
        watch._last_lap_total = laps[-1]["total"] if laps else 0.0
        watch._accumulated = elapsed
        if state == RUNNING:
            anchor = float(data.get("wall") or wall)
            watch._accumulated += max(0.0, wall - anchor)
            watch._state = RUNNING
            watch._started_at = watch._now()  # carry on from here
        elif state == PAUSED:
            watch._state = PAUSED
        return watch

    # ── internals ────────────────────────────────────────────────────
    def _running_time(self) -> float:
        return self._now() - self._started_at

    def _now(self) -> float:
        return time.monotonic()
