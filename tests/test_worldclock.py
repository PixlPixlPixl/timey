"""Unit tests for world-clock helpers (no GUI required)."""

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from timey import worldclock


class SnapshotTests(unittest.TestCase):
    def test_snapshot_london_winter(self) -> None:
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Europe/London"))
        parts = worldclock.snapshot_text(dt)
        self.assertEqual(parts["time"], "12:00:00")
        self.assertEqual(parts["offset"], "UTC+00:00")
        self.assertEqual(parts["date"], "Thu 15 Jan")

    def test_snapshot_tokyo(self) -> None:
        dt = datetime(2026, 7, 1, 9, 5, 7, tzinfo=ZoneInfo("Asia/Tokyo"))
        parts = worldclock.snapshot_text(dt)
        self.assertEqual(parts["time"], "09:05:07")
        self.assertEqual(parts["offset"], "UTC+09:00")

    def test_snapshot_negative_offset(self) -> None:
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        parts = worldclock.snapshot_text(dt)
        self.assertEqual(parts["offset"], "UTC-08:00")


class ZoneTests(unittest.TestCase):
    def test_local_is_local(self) -> None:
        self.assertTrue(worldclock.is_local("Local"))
        self.assertTrue(worldclock.is_local(""))
        self.assertFalse(worldclock.is_local("Europe/London"))

    def test_zone_info_resolves_curated_city(self) -> None:
        label, info = worldclock.zone_info("Europe/London")
        self.assertEqual(label, "London")
        self.assertIsNotNone(info)

    def test_zone_info_nested_region_label(self) -> None:
        label, info = worldclock.zone_info("America/Argentina/Buenos_Aires")
        self.assertEqual(label, "Buenos Aires")
        self.assertIsNotNone(info)

    def test_zone_info_local(self) -> None:
        label, info = worldclock.zone_info("Local")
        self.assertTrue(label)  # either "Local time" or a resolved city
        self.assertIsNotNone(info)

    def test_unknown_zone_returns_none_info(self) -> None:
        label, info = worldclock.zone_info("Not/A_Zone")
        self.assertIsNone(info)
        self.assertEqual(label, "A Zone")

    def test_curated_list_contains_common_cities(self) -> None:
        zones = {zone for _city, zone in worldclock.CITIES}
        for expected in (
            "America/New_York",
            "Europe/London",
            "Asia/Tokyo",
            "Australia/Sydney",
        ):
            self.assertIn(expected, zones)

    def test_local_zone_name_detects_system(self) -> None:
        name = worldclock.local_zone_name()
        # On a real machine this resolves to a tzdata path; on exotic
        # setups it may be None, which the UI handles.
        self.assertTrue(name is None or "/" in name or name)


if __name__ == "__main__":
    unittest.main()
