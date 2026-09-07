"""Unit tests for the Countdown engine (no GUI required)."""

import unittest

from timey.countdown import (
    FINISHED,
    IDLE,
    PAUSED,
    RUNNING,
    Countdown,
)


class FakeCountdown(Countdown):
    """Countdown with a controllable clock."""

    def __init__(self, duration_s: float, clock: list[float], name: str = "") -> None:
        super().__init__(duration_s, name=name)
        self._clock = clock

    def _now(self) -> float:
        return self._clock[0]

    def _advance(self, seconds: float) -> None:
        self._clock[0] += seconds


class CountdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = [0.0]
        self.timer = FakeCountdown(60.0, self.clock, name="Tea")

    def test_initial_state(self) -> None:
        self.assertTrue(self.timer.is_idle())
        self.assertEqual(self.timer.remaining(), 60.0)
        self.assertEqual(self.timer.progress(), 0.0)
        self.assertEqual(self.timer.name, "Tea")

    def test_requires_positive_duration(self) -> None:
        with self.assertRaises(ValueError):
            Countdown(0)
        with self.assertRaises(ValueError):
            Countdown(-5)

    def test_running_counts_down(self) -> None:
        self.timer.start()
        self.assertTrue(self.timer.is_running())
        self.timer._advance(10.0)
        self.assertAlmostEqual(self.timer.remaining(), 50.0)
        self.assertAlmostEqual(self.timer.progress(), 10.0 / 60.0)

    def test_pause_freezes_and_resume_continues(self) -> None:
        self.timer.start()
        self.timer._advance(20.0)
        self.timer.pause()
        self.assertTrue(self.timer.is_paused())
        self.assertAlmostEqual(self.timer.remaining(), 40.0)

        self.timer._advance(999.0)  # no time passes while paused
        self.assertAlmostEqual(self.timer.remaining(), 40.0)

        self.timer.start()
        self.timer._advance(5.0)
        self.assertAlmostEqual(self.timer.remaining(), 35.0)

    def test_finishes_exactly_once(self) -> None:
        self.timer.start()
        self.timer._advance(59.5)
        self.assertFalse(self.timer.update())
        self.timer._advance(0.6)  # now past zero
        self.assertTrue(self.timer.update())  # fires once
        self.assertFalse(self.timer.update())  # and only once
        self.assertTrue(self.timer.is_finished())
        self.assertEqual(self.timer.remaining(), 0.0)
        self.assertEqual(self.timer.progress(), 1.0)

    def test_remaining_never_goes_negative_while_running(self) -> None:
        self.timer.start()
        self.timer._advance(10_000.0)
        self.assertFalse(self.timer.is_finished())  # update() not called yet
        self.assertEqual(self.timer.remaining(), 0.0)

    def test_cannot_start_finished_timer_without_reset(self) -> None:
        short = FakeCountdown(1.0, self.clock)
        short.start()
        short._advance(2.0)
        self.assertTrue(short.update())
        short.start()  # ignored while finished
        self.assertTrue(short.is_finished())
        short.reset()
        short.start()
        self.assertTrue(short.is_running())

    def test_reset_restores_full_time(self) -> None:
        self.timer.start()
        self.timer._advance(45.0)
        self.timer.reset()
        self.assertTrue(self.timer.is_idle())
        self.assertEqual(self.timer.remaining(), 60.0)
        self.assertEqual(self.timer.progress(), 0.0)

    def test_name_stripped(self) -> None:
        t = Countdown(5, name="   Focus  ")
        self.assertEqual(t.name, "Focus")


class PersistenceTests(unittest.TestCase):
    def test_idle_round_trip(self) -> None:
        t = Countdown(90, name="Tea")
        restored = Countdown.from_state(t.save_state(wall=1000.0), wall=1010.0)
        self.assertTrue(restored.is_idle())
        self.assertEqual(restored.remaining(), 90.0)
        self.assertEqual(restored.name, "Tea")

    def test_paused_round_trip(self) -> None:
        data = {"name": "P", "duration": 60, "state": "paused", "remaining": 40}
        restored = Countdown.from_state(data, wall=2000.0)
        self.assertTrue(restored.is_paused())
        self.assertAlmostEqual(restored.remaining(), 40.0)

    def test_running_keeps_counting_across_restart(self) -> None:
        # Saved at wall=1000 with 50 s left, reopened 10 s later.
        data = {
            "name": "Run",
            "duration": 60,
            "state": "running",
            "remaining": 50,
            "wall": 1000.0,
        }
        restored = Countdown.from_state(data, wall=1010.0)
        self.assertTrue(restored.is_running())
        self.assertAlmostEqual(restored.remaining(), 40.0, delta=0.01)

    def test_running_that_expired_while_away_is_finished(self) -> None:
        data = {
            "name": "Run",
            "duration": 60,
            "state": "running",
            "remaining": 5,
            "wall": 1000.0,
        }
        restored = Countdown.from_state(data, wall=2000.0)
        self.assertTrue(restored.is_finished())
        self.assertEqual(restored.remaining(), 0.0)

    def test_finished_round_trip(self) -> None:
        data = {"name": "Done", "duration": 10, "state": "finished", "remaining": 0}
        restored = Countdown.from_state(data, wall=1.0)
        self.assertTrue(restored.is_finished())
        self.assertEqual(restored.remaining(), 0.0)


if __name__ == "__main__":
    unittest.main()
