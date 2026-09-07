"""Unit tests for the persistent State store (no GUI required)."""

import configparser
import os
import tempfile
import unittest
from pathlib import Path

from timey import state as statemod
from timey.alarm import Alarm
from timey.countdown import Countdown


class StateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(self._root)
        os.environ.pop("TIMEY_BACKGROUND_DEFAULT", None)
        os.environ.pop("TIMEY_THEME", None)

    def tearDown(self) -> None:
        if self._old_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old_xdg
        os.environ.pop("TIMEY_BACKGROUND_DEFAULT", None)
        os.environ.pop("TIMEY_THEME", None)
        self._tmp.cleanup()

    def _path(self) -> Path:
        return self._root / "timey" / "state.json"

    def test_fresh_defaults(self) -> None:
        loaded = statemod.State.load()
        self.assertEqual(loaded.theme, "dark")
        self.assertFalse(loaded.background)
        self.assertTrue(loaded.sound)
        self.assertEqual(loaded.zones, ["Local"])

    def test_background_default_env(self) -> None:
        os.environ["TIMEY_BACKGROUND_DEFAULT"] = "1"
        loaded = statemod.State.load()
        self.assertTrue(loaded.background)

    def test_round_trip_full_state(self) -> None:
        saved = statemod.State(
            theme="light",
            background=True,
            sound=False,
            zones=["Local", "Europe/London", "Asia/Tokyo"],
        )
        saved.alarms.append(Alarm(6, 30, name="Wake", repeat=True))
        saved.timers.append(
            Countdown.from_state(
                {"name": "Tea", "duration": 90, "state": "idle", "remaining": 90}
            )
        )
        saved.save()

        loaded = statemod.State.load()
        self.assertEqual(loaded.theme, "light")
        self.assertTrue(loaded.background)
        self.assertFalse(loaded.sound)
        self.assertEqual(loaded.zones, ["Local", "Europe/London", "Asia/Tokyo"])
        self.assertEqual(len(loaded.alarms), 1)
        alarm = loaded.alarms[0]
        self.assertEqual(alarm.name, "Wake")
        self.assertTrue(alarm.repeat)
        self.assertTrue(alarm.enabled)
        self.assertEqual(len(loaded.timers), 1)
        self.assertEqual(loaded.timers[0].name, "Tea")
        self.assertTrue(loaded.timers[0].is_idle())
        self.assertAlmostEqual(loaded.timers[0].remaining(), 90.0)
        self.assertTrue(loaded.stopwatch.is_idle())

    def test_legacy_config_ini_theme_migrated(self) -> None:
        legacy = self._root / "timey" / "config.ini"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        parser = configparser.ConfigParser()
        parser["preferences"] = {"theme": "light"}
        with open(legacy, "w", encoding="utf-8") as handle:
            parser.write(handle)
        loaded = statemod.State.load()
        self.assertEqual(loaded.theme, "light")

    def test_corrupt_state_falls_back_to_defaults(self) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        loaded = statemod.State.load()
        self.assertEqual(loaded.theme, "dark")
        self.assertEqual(loaded.zones, ["Local"])

    def test_sort_alarms_groups_enabled_first(self) -> None:
        late = Alarm(9, 0, name="Late", enabled=False)
        early = Alarm(6, 0, name="Early", enabled=True)
        st = statemod.State()
        st.alarms = [late, early]
        st.sort_alarms()
        self.assertEqual([a.name for a in st.alarms], ["Early", "Late"])

    def test_missing_zones_falls_back_to_local(self) -> None:
        st = statemod.State.from_dict({"zones": []})
        self.assertEqual(st.zones, ["Local"])


if __name__ == "__main__":
    unittest.main()
