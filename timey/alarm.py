"""Time-of-day alarm engine — pure Python, no GUI dependencies.

Alarms are evaluated against the **local** wall clock. Each alarm is one
of two kinds:

* **one-shot** — fires once at its next occurrence (today if that time
  is still ahead, otherwise tomorrow), then disables itself. It stays in
  the list (``enabled`` becomes ``False``) and can be re-armed by simply
  enabling it again.
* **repeating** — fires on the chosen weekdays (all seven == daily) and
  automatically re-arms itself for the next allowed occurrence.

A periodic UI/daemon tick calls :meth:`Alarm.check`, which returns
``True`` exactly once when the alarm is due, so the caller can notify /
play a sound without double-firing.

Times are naive ``datetime`` values meaning local wall-clock time. For
deterministic tests every method accepts an optional ``now``.
"""

from __future__ import annotations

import datetime as _dt
import uuid

#: Weekday constants in ``datetime.weekday()`` terms.
MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

WEEKDAYS = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY)
WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAY_LONG = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

#: How far past its time an alarm is still considered "on time" when the
#: app (re)starts, rather than a missed occurrence.
ON_TIME_GRACE_S = 60.0


def now() -> _dt.datetime:
    """Current local wall-clock time (naive)."""
    return _dt.datetime.now().replace(microsecond=0)


def format_time(hour: int, minute: int) -> str:
    """``HH:MM`` (24 h) for an alarm's stored time."""
    return f"{int(hour):02d}:{int(minute):02d}"


def _round(day: _dt.date, hour: int, minute: int) -> _dt.datetime:
    return _dt.datetime.combine(day, _dt.time(hour, minute, 0))


class Alarm:
    """A single time-of-day alarm.

    ``hour``/``minute`` are the wall-clock time (24 h). With ``repeat``
    disabled the alarm is one-shot; with it enabled the alarm repeats on
    the days listed in ``weekdays`` (0 = Monday ... 6 = Sunday).
    """

    def __init__(
        self,
        hour: int,
        minute: int = 0,
        *,
        name: str = "",
        repeat: bool = False,
        weekdays: set[int] | None = None,
        enabled: bool = True,
        uid: str | None = None,
    ) -> None:
        if not 0 <= int(hour) <= 23:
            raise ValueError("hour must be in 0..23")
        if not 0 <= int(minute) <= 59:
            raise ValueError("minute must be in 0..59")
        self.hour = int(hour)
        self.minute = int(minute)
        self.name = str(name).strip()
        self.repeat = bool(repeat)
        self.weekdays = {
            int(d) for d in (weekdays if weekdays is not None else set(WEEKDAYS))
        }
        # Repeat with no weekdays chosen means "every day".
        if not self.weekdays:
            self.weekdays = set(WEEKDAYS)
        self.enabled = bool(enabled)
        self.uid = uid or uuid.uuid4().hex

        #: True while the alarm is ringing and waiting to be stopped.
        self.ringing = False
        #: Next due occurrence (naive local), or None when not armed.
        self.next_fire: _dt.datetime | None = None
        #: When it last went off (naive local), if ever.
        self.last_fired: _dt.datetime | None = None
        if self.enabled:
            self.arm(now())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "enabled" if self.enabled else "off"
        return (
            f"Alarm({format_time(self.hour, self.minute)!r}, name={self.name!r}, "
            f"{state}, repeat={self.repeat!r}, weekdays={sorted(self.weekdays)!r})"
        )

    # ── queries ──────────────────────────────────────────────────────
    @property
    def fires_daily(self) -> bool:
        """True when repeating on every weekday."""
        return self.repeat and self.weekdays == set(WEEKDAYS)

    def describe_repeat(self) -> str:
        """Short human summary of the repeat rule ('' when one-shot)."""
        if not self.repeat:
            return ""
        if self.fires_daily:
            return "Daily"
        if self.weekdays == {MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY}:
            return "Weekdays"
        if self.weekdays == {SATURDAY, SUNDAY}:
            return "Weekends"
        ordered = [WEEKDAY_SHORT[d] for d in WEEKDAYS if d in self.weekdays]
        return " · ".join(ordered) if len(ordered) <= 3 else f"{len(ordered)} days a week"

    def describe_next(self, moment: _dt.datetime | None = None) -> str:
        """e.g. ``"next Tue 07:30"`` for the next due occurrence."""
        fire = self.effective_next_fire(moment)
        if fire is None:
            return ""
        today = (moment or now()).date()
        if fire.date() == today:
            day_word = "today"
        else:
            day_word = f"on {WEEKDAY_LONG[fire.weekday()]}"
        return f"{day_word} at {format_time(fire.hour, fire.minute)}"

    def effective_next_fire(self, moment: _dt.datetime | None = None) -> _dt.datetime | None:
        """The occurrence ``check`` will fire at (or None if disabled)."""
        if not self.enabled:
            return None
        return self.next_fire

    # ── scheduling ───────────────────────────────────────────────────
    def occurrence_after(self, moment: _dt.datetime) -> _dt.datetime:
        """Next future occurrence of this alarm strictly after ``moment``."""
        if not self.repeat:
            candidate = _round(moment.date(), self.hour, self.minute)
            if candidate > moment:
                return candidate
            return _round(moment.date() + _dt.timedelta(days=1), self.hour, self.minute)

        allowed = self.weekdays or set(WEEKDAYS)
        for offset in range(0, 8):  # at most a full week ahead
            day = moment.date() + _dt.timedelta(days=offset)
            if day.weekday() not in allowed:
                continue
            candidate = _round(day, self.hour, self.minute)
            if candidate > moment:
                return candidate
        # Unreachable: the loop covers every weekday within a week.
        raise AssertionError("no occurrence found")  # pragma: no cover

    def arm(self, moment: _dt.datetime | None = None) -> None:
        """Schedule the next occurrence after ``moment`` (default: now).

        Scheduling is independent of ``enabled`` so a restored alarm can
        be re-armed before it is switched on; ``check`` only fires when
        the alarm is enabled.
        """
        self.ringing = False
        self.next_fire = self.occurrence_after(moment or now())

    def set_enabled(self, enabled: bool) -> None:
        """Toggle the alarm. (Re-)enabling arms it for its next occurrence."""
        self.enabled = bool(enabled)
        if self.enabled:
            self.arm()
        else:
            self.ringing = False
            self.next_fire = None

    def check(self, moment: _dt.datetime | None = None) -> bool:
        """Signal that the alarm's time has come. Returns True exactly once.

        The alarm enters the :attr:`ringing` state and stays there until
        :meth:`dismiss` (or :meth:`set_enabled`) is called, so the sound
        can keep playing continuously until the user stops it.
        """
        if not self.enabled or self.next_fire is None:
            return False
        current = moment or now()
        if current < self.next_fire:
            return False
        if self.ringing:
            return False  # already ringing; not due again

        self.ringing = True
        self.last_fired = self.next_fire
        return True

    def dismiss(self, moment: _dt.datetime | None = None) -> None:
        """Stop a ringing alarm.

        A repeating alarm re-arms for its next occurrence; a one-shot
        alarm goes quiet (``enabled`` False) but stays in the list.
        """
        if not self.ringing:
            return
        self.ringing = False
        if self.repeat:
            self.next_fire = self.occurrence_after(moment or now())
        else:
            self.next_fire = None
            self.enabled = False

    # ── restore handling ─────────────────────────────────────────────
    def reconcile(self, moment: _dt.datetime | None = None) -> None:
        """Bring a restored alarm up to date with the present.

        Called after loading persisted state. An occurrence that was
        *missed* while the app was fully closed is skipped: repeating
        alarms re-arm for the next allowed day, one-shot alarms that
        missed their slot by more than the grace period are marked as
        fired (so they don't ring embarrassingly late). Occurrences
        within the grace window are left armed and fire immediately on
        the first ``check``.
        """
        current = moment or now()
        if not self.enabled:
            self.next_fire = None
            return
        if self.next_fire is None:
            # Persisted without a schedule (e.g. corrupt/old data): arm now.
            self.next_fire = self.occurrence_after(current)
            return
        if self.next_fire >= current:
            return
        late_by = current - self.next_fire
        if late_by <= _dt.timedelta(seconds=ON_TIME_GRACE_S):
            return  # effectively on time — first check() will fire it
        # Missed while away.
        if self.repeat:
            self.next_fire = self.occurrence_after(current)
        else:
            self.last_fired = self.next_fire
            self.next_fire = None
            self.enabled = False

    # ── persistence ──────────────────────────────────────────────────
    def to_dict(self) -> dict[str, object]:
        def iso(value: _dt.datetime | None) -> str | None:
            return value.isoformat() if value is not None else None

        return {
            "uid": self.uid,
            "name": self.name,
            "hour": self.hour,
            "minute": self.minute,
            "repeat": self.repeat,
            "weekdays": sorted(self.weekdays),
            "enabled": self.enabled,
            "next_fire": iso(self.next_fire),
            "last_fired": iso(self.last_fired),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Alarm":
        def parse(value: object) -> _dt.datetime | None:
            if not value:
                return None
            try:
                return _dt.datetime.fromisoformat(str(value))
            except ValueError:
                return None

        alarm = cls(
            hour=int(data.get("hour", 7)),
            minute=int(data.get("minute", 0)),
            name=str(data.get("name", "")),
            repeat=bool(data.get("repeat", False)),
            weekdays={int(d) for d in data.get("weekdays", [])},
            enabled=bool(data.get("enabled", True)),
            uid=str(data.get("uid") or None),
        )
        alarm.next_fire = parse(data.get("next_fire"))
        alarm.last_fired = parse(data.get("last_fired"))
        return alarm
