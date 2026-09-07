"""Unit tests for the Alarm engine (no GUI required).

Tests drive a fake clock by patching ``timey.alarm.now`` so alarm
construction, arming and firing are fully deterministic.
"""

import unittest
from datetime import datetime

import timey.alarm as alarm_module
from timey.alarm import (
    FRIDAY,
    MONDAY,
    SATURDAY,
    SUNDAY,
    Alarm,
    format_time,
)

MON_0600 = datetime(2026, 9, 7, 6, 0, 0)  # a Monday morning


class FakeClock:
    """Mutable stand-in for timey.alarm.now()."""

    def __init__(self, start: datetime) -> None:
        self.value = start

    def __call__(self) -> datetime:
        return self.value

    def set(self, value: datetime) -> None:
        self.value = value


class AlarmTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock(MON_0600)
        self._original = alarm_module.now
        alarm_module.now = self.clock

    def tearDown(self) -> None:
        alarm_module.now = self._original

    def advance(self, to: datetime) -> None:
        self.clock.set(to)


class FormatTests(AlarmTestCase):
    def test_format_time(self) -> None:
        self.assertEqual(format_time(7, 5), "07:05")
        self.assertEqual(format_time(23, 59), "23:59")

    def test_invalid_values_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Alarm(24, 0)
        with self.assertRaises(ValueError):
            Alarm(7, 60)
        with self.assertRaises(ValueError):
            Alarm(-1, 0)


class OneShotTests(AlarmTestCase):
    def test_arms_for_today_when_time_ahead(self) -> None:
        alarm = Alarm(7, 30)
        self.assertEqual(alarm.next_fire, datetime(2026, 9, 7, 7, 30))

    def test_arms_for_tomorrow_when_time_passed(self) -> None:
        self.advance(datetime(2026, 9, 7, 8, 0))  # past 07:30 today
        alarm = Alarm(7, 30)
        self.assertEqual(alarm.next_fire, datetime(2026, 9, 8, 7, 30))

    def test_fires_once_then_goes_quiet_but_stays(self) -> None:
        alarm = Alarm(7, 30)
        self.advance(datetime(2026, 9, 7, 7, 29, 59))
        self.assertFalse(alarm.check())
        self.advance(datetime(2026, 9, 7, 7, 30, 1))
        self.assertTrue(alarm.check())  # fires exactly once
        self.assertFalse(alarm.check())
        self.assertFalse(alarm.enabled)
        self.assertIsNone(alarm.next_fire)
        self.assertEqual(alarm.last_fired, datetime(2026, 9, 7, 7, 30))

    def test_disabled_alarm_never_fires(self) -> None:
        alarm = Alarm(7, 30, enabled=False)
        alarm.arm()  # schedule without enabling
        self.assertIsNotNone(alarm.next_fire)
        self.advance(datetime(2026, 9, 7, 7, 30, 5))
        self.assertFalse(alarm.check())

    def test_re_enabling_arms_again(self) -> None:
        alarm = Alarm(7, 30)
        self.advance(datetime(2026, 9, 7, 7, 30, 1))
        self.assertTrue(alarm.check())
        self.assertFalse(alarm.enabled)
        alarm.set_enabled(True)
        self.assertTrue(alarm.enabled)
        self.assertIsNotNone(alarm.next_fire)


class RepeatTests(AlarmTestCase):
    def test_daily_re_arms_for_tomorrow(self) -> None:
        alarm = Alarm(7, 30, repeat=True)
        self.advance(datetime(2026, 9, 7, 7, 30, 1))
        self.assertTrue(alarm.check())
        self.assertTrue(alarm.enabled)
        self.assertEqual(alarm.next_fire, datetime(2026, 9, 8, 7, 30))

    def test_single_weekday_skips_to_next_occurrence(self) -> None:
        self.advance(datetime(2026, 9, 11, 6, 0))  # Friday
        alarm = Alarm(7, 30, repeat=True, weekdays={MONDAY})
        self.assertEqual(alarm.next_fire, datetime(2026, 9, 14, 7, 30))  # next Mon

    def test_weekend_only(self) -> None:
        alarm = Alarm(9, 0, repeat=True, weekdays={SUNDAY})
        self.assertEqual(alarm.next_fire, datetime(2026, 9, 13, 9, 0))  # Sunday

    def test_empty_weekdays_mean_daily(self) -> None:
        alarm = Alarm(7, 30, repeat=True, weekdays=set())
        self.assertTrue(alarm.fires_daily)
        self.assertEqual(alarm.describe_repeat(), "Daily")

    def test_repeat_descriptions(self) -> None:
        two_days = Alarm(7, 0, repeat=True, weekdays={MONDAY, FRIDAY})
        self.assertEqual(two_days.describe_repeat(), "Mon · Fri")
        weekends = Alarm(7, 0, repeat=True, weekdays={SUNDAY, FRIDAY, SATURDAY})
        self.assertEqual(weekends.describe_repeat(), "Fri · Sat · Sun")


class ReconcileTests(AlarmTestCase):
    def test_missed_repeat_skips_to_next_occurrence(self) -> None:
        # Armed for Sunday 07:30, but the app reopens Monday 10:00.
        alarm = Alarm(7, 30, repeat=True)
        alarm.arm(datetime(2026, 9, 6, 6, 0))
        self.advance(datetime(2026, 9, 7, 10, 0))
        alarm.reconcile()
        self.assertTrue(alarm.enabled)
        self.assertEqual(alarm.next_fire, datetime(2026, 9, 8, 7, 30))

    def test_missed_one_shot_is_marked_off_not_rung_late(self) -> None:
        alarm = Alarm(7, 30)
        alarm.arm(datetime(2026, 9, 6, 6, 0))  # Sunday 07:30
        self.advance(datetime(2026, 9, 7, 10, 0))
        alarm.reconcile()
        self.assertFalse(alarm.enabled)
        self.assertIsNone(alarm.next_fire)
        self.assertIsNotNone(alarm.last_fired)

    def test_grace_window_fires_immediately(self) -> None:
        alarm = Alarm(7, 30)
        self.advance(datetime(2026, 9, 7, 7, 30, 40))  # 40 s late
        alarm.reconcile()
        self.assertTrue(alarm.enabled)
        self.assertTrue(alarm.check())  # fires straight away

    def test_disabled_stays_off(self) -> None:
        alarm = Alarm(7, 30, enabled=False)
        alarm.reconcile()
        self.assertFalse(alarm.enabled)
        self.assertIsNone(alarm.next_fire)


class SerializationTests(AlarmTestCase):
    def test_round_trip_preserves_everything(self) -> None:
        original = Alarm(
            6,
            15,
            name="Wake up",
            repeat=True,
            weekdays={0, 1, 2, 3, 4},
        )
        restored = Alarm.from_dict(original.to_dict())
        self.assertEqual(restored.uid, original.uid)
        self.assertEqual(restored.name, "Wake up")
        self.assertEqual(restored.hour, 6)
        self.assertEqual(restored.minute, 15)
        self.assertTrue(restored.repeat)
        self.assertEqual(restored.weekdays, {0, 1, 2, 3, 4})
        self.assertTrue(restored.enabled)
        self.assertEqual(restored.next_fire, original.next_fire)

    def test_round_trip_keeps_fire_history(self) -> None:
        alarm = Alarm(7, 30)
        self.advance(datetime(2026, 9, 7, 7, 30, 1))
        alarm.check()
        restored = Alarm.from_dict(alarm.to_dict())
        self.assertIsNotNone(restored.last_fired)
        self.assertFalse(restored.enabled)
        self.assertIsNone(restored.next_fire)


if __name__ == "__main__":
    unittest.main()
