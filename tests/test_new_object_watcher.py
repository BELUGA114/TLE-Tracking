from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from new_object_watcher import NewObjectWatcher


class FakeNotifier:
    """记录推送调用的测试替身，代替 TelegramNotifier"""

    def __init__(self) -> None:
        self.active = True
        self.debuts: list[tuple[dict, bool, str]] = []
        self.summaries: list[tuple[int, str]] = []

    def send_debut(self, record: dict, watched: bool = False, label: str = "") -> bool:
        self.debuts.append((record, watched, label))
        return True

    def send_summary(self, count: int, note: str = "") -> bool:
        self.summaries.append((count, note))
        return True


class NewObjectWatcherModeTests(unittest.TestCase):
    """验证总开关与关注列表的组合语义"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_watcher(self, enabled: bool, watched: list) -> NewObjectWatcher:
        cfg = {"enabled": enabled, "watched_launches": watched}
        return NewObjectWatcher(cfg, self._tmpdir.name)

    def test_disabled_without_watchlist_never_due(self) -> None:
        watcher = self._make_watcher(False, [])
        fixed = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)  # 已过 17:10 UTC
        with patch("new_object_watcher._utc_now", return_value=fixed):
            self.assertFalse(watcher.is_due)

    def test_disabled_with_watchlist_is_due_after_schedule(self) -> None:
        watcher = self._make_watcher(False, ["2026-085"])
        fixed = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
        with patch("new_object_watcher._utc_now", return_value=fixed):
            self.assertTrue(watcher.is_due)

    def test_disabled_with_watchlist_not_due_before_schedule(self) -> None:
        watcher = self._make_watcher(False, ["2026-085"])
        fixed = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)  # 17:10 之前
        with patch("new_object_watcher._utc_now", return_value=fixed):
            self.assertFalse(watcher.is_due)

    def test_watchlist_only_pushes_matched_and_skips_unmatched(self) -> None:
        watcher = self._make_watcher(False, ["2026-085"])
        notifier = FakeNotifier()
        records = [
            {"NORAD_CAT_ID": "60001", "OBJECT_ID": "2026-085A", "DEBUT": "2026-08-23 17:00:00"},
            {"NORAD_CAT_ID": "60002", "OBJECT_ID": "2026-100B", "DEBUT": "2026-08-23 17:05:00"},
        ]
        watcher._cursor["last_debut_ts"] = "2026-08-23 16:00:00+00:00"
        fixed = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
        with patch("new_object_watcher._utc_now", return_value=fixed):
            with patch.object(watcher, "_query_debut", return_value=records):
                with patch.object(watcher, "_save_cursor"):
                    with patch("new_object_watcher.time.sleep"):
                        pushed = watcher.check(None, notifier)

        self.assertEqual(pushed, 1)
        self.assertEqual(len(notifier.debuts), 1)
        self.assertEqual(notifier.debuts[0][0]["NORAD_CAT_ID"], "60001")
        self.assertTrue(notifier.debuts[0][1])  # watched=True
        self.assertEqual(notifier.summaries, [])  # watchlist-only 不发摘要

    def test_enabled_pushes_all_records(self) -> None:
        watcher = self._make_watcher(True, [])
        notifier = FakeNotifier()
        records = [
            {"NORAD_CAT_ID": "60001", "OBJECT_ID": "2026-085A", "DEBUT": "2026-08-23 17:00:00"},
            {"NORAD_CAT_ID": "60002", "OBJECT_ID": "2026-100B", "DEBUT": "2026-08-23 17:05:00"},
        ]
        watcher._cursor["last_debut_ts"] = "2026-08-23 16:00:00+00:00"
        fixed = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
        with patch("new_object_watcher._utc_now", return_value=fixed):
            with patch.object(watcher, "_query_debut", return_value=records):
                with patch.object(watcher, "_save_cursor"):
                    with patch("new_object_watcher.time.sleep"):
                        pushed = watcher.check(None, notifier)

        self.assertEqual(pushed, 2)
        self.assertEqual(len(notifier.debuts), 2)


if __name__ == "__main__":
    unittest.main()
