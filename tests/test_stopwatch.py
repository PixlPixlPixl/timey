"""Unit tests for the Stopwatch engine (no GUI required)."""

import unittest

from timey.stopwatch import (
    IDLE,
    PAUSED,
    RUNNING,
    Stopwatch,
    format_elapsed,
)


class FakeStopwatch(Stopwatch):
    """Stopwatch with a controllable clock for deterministic tests."""

    def __init__(self, clock: list[float]) -> None:
        super().__init__()
        self._clock = clock

    def _now(self) -> float:
        return self._clock[0]

    def _advance(self, seconds: float) -> None:
        self._clock[0] += seconds


class FormatElapsedTests(unittest.TestCase):
    def test_zero(self) -> None:
        self.assertEqual(format_elapsed(0.0), "00:00:00.00")

    def test_subsecond(self) -> None:
        self.assertEqual(format_elapsed(1.234), "00:00:01.23")

    def test_rollover_to_minutes_and_hours(self) -> None:
        self.assertEqual(format_elapsed(3599.99), "00:59:59.99")
        self.assertEqual(format_elapsed(3600.0), "01:00:00.00")

    def test_no_centis(self) -> None:
        self.assertEqual(format_elapsed(61.99, with_centis=False), "00:01:01")

    def test_floor_never_shows_60(self) -> None:
        # 0.999 seconds must floor to 00.99, never jump to 01.00 early.
        self.assertEqual(format_elapsed(0.999), "00:00:00.99")

    def test_negative_is_clamped(self) -> None:
        self.assertEqual(format_elapsed(-5), "00:00:00.00")


class StopwatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = [0.0]
        self.sw = FakeStopwatch(self.clock)

    def test_initial_state(self) -> None:
        self.assertTrue(self.sw.is_idle())
        self.assertEqual(self.sw.state, IDLE)
        self.assertEqual(self.sw.elapsed(), 0.0)
        self.assertEqual(self.sw.lap_count, 0)

    def test_start_and_elapsed(self) -> None:
        self.sw.start()
        self.assertTrue(self.sw.is_running())
        self.sw._advance(10.0)
        self.assertAlmostEqual(self.sw.elapsed(), 10.0)

    def test_pause_keeps_time_and_resume_continues(self) -> None:
        self.sw.start()
        self.sw._advance(5.0)
        self.sw.pause()
        self.assertTrue(self.sw.is_paused())
        self.assertAlmostEqual(self.sw.elapsed(), 5.0)

        # Time must NOT advance while paused.
        self.sw._advance(100.0)
        self.assertAlmostEqual(self.sw.elapsed(), 5.0)

        self.sw.start()  # resume
        self.sw._advance(3.0)
        self.assertAlmostEqual(self.sw.elapsed(), 8.0)

    def test_lap_records_split_and_total(self) -> None:
        self.sw.start()
        self.sw._advance(3.0)
        first = self.sw.lap()
        assert first is not None
        self.assertAlmostEqual(first["total"], 3.0)
        self.assertAlmostEqual(first["split"], 3.0)

        self.sw._advance(2.0)
        second = self.sw.lap()
        assert second is not None
        self.assertAlmostEqual(second["total"], 5.0)
        self.assertAlmostEqual(second["split"], 2.0)
        self.assertEqual(self.sw.lap_count, 2)

    def test_lap_returns_none_when_not_running(self) -> None:
        self.assertIsNone(self.sw.lap())
        self.sw.start()
        self.sw.pause()
        self.assertIsNone(self.sw.lap())

    def test_reset(self) -> None:
        self.sw.start()
        self.sw._advance(7.0)
        self.sw.lap()
        self.sw.reset()
        self.assertTrue(self.sw.is_idle())
        self.assertEqual(self.sw.elapsed(), 0.0)
        self.assertEqual(self.sw.lap_count, 0)
        self.assertEqual(self.sw.laps, [])

    def test_starting_from_idle_zeroes_accumulated(self) -> None:
        self.sw.start()
        self.sw._advance(9.0)
        self.sw.reset()
        self.sw.start()
        self.sw._advance(1.0)
        self.assertAlmostEqual(self.sw.elapsed(), 1.0)


class PersistenceTests(unittest.TestCase):
    def test_idle_round_trip(self) -> None:
        watch = Stopwatch()
        restored = Stopwatch.from_state(watch.save_state(wall=1000.0), wall=1010.0)
        self.assertTrue(restored.is_idle())
        self.assertEqual(restored.elapsed(), 0.0)
        self.assertEqual(restored.lap_count, 0)

    def test_paused_keeps_elapsed_and_laps(self) -> None:
        data = {
            "state": "paused",
            "elapsed": 42.5,
            "laps": [
                {"index": 1, "total": 20.0, "split": 20.0},
                {"index": 2, "total": 42.5, "split": 22.5},
            ],
        }
        restored = Stopwatch.from_state(data, wall=1.0)
        self.assertTrue(restored.is_paused())
        self.assertAlmostEqual(restored.elapsed(), 42.5)
        self.assertEqual(restored.lap_count, 2)

    def test_left_running_keeps_counting_across_restart(self) -> None:
        # Saved at wall=1000 with 10 s elapsed; reopened 15 s later.
        data = {"state": "running", "elapsed": 10.0, "laps": [], "wall": 1000.0}
        restored = Stopwatch.from_state(data, wall=1015.0)
        self.assertTrue(restored.is_running())
        self.assertAlmostEqual(restored.elapsed(), 25.0, delta=0.01)

    def test_laps_survive_round_trip(self) -> None:
        data = {
            "state": "paused",
            "elapsed": 5.0,
            "laps": [{"index": 1, "total": 5.0, "split": 5.0}],
        }
        restored = Stopwatch.from_state(data)
        self.assertEqual(restored.laps, [{"index": 1, "total": 5.0, "split": 5.0}])


if __name__ == "__main__":
    unittest.main()
