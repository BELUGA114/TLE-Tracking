from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

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


@pytest.fixture()
def tmp_data_dir(tmp_path) -> str:
    """隔离的游标文件目录，避免用例间游标串扰。"""
    return str(tmp_path)


def _make_watcher(tmp_data_dir: str, enabled: bool, watched: list) -> NewObjectWatcher:
    cfg = {"enabled": enabled, "watched_launches": watched}
    return NewObjectWatcher(cfg, tmp_data_dir)


def test_disabled_without_watchlist_never_due(tmp_data_dir: str) -> None:
    watcher = _make_watcher(tmp_data_dir, False, [])
    fixed = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)  # 已过 17:10 UTC
    with patch("new_object_watcher._utc_now", return_value=fixed):
        assert watcher.is_due is False


def test_disabled_with_watchlist_is_due_after_schedule(tmp_data_dir: str) -> None:
    watcher = _make_watcher(tmp_data_dir, False, ["2026-085"])
    fixed = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
    with patch("new_object_watcher._utc_now", return_value=fixed):
        assert watcher.is_due is True


def test_disabled_with_watchlist_not_due_before_schedule(tmp_data_dir: str) -> None:
    watcher = _make_watcher(tmp_data_dir, False, ["2026-085"])
    fixed = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)  # 17:10 之前
    with patch("new_object_watcher._utc_now", return_value=fixed):
        assert watcher.is_due is False


def _run_check(watcher: NewObjectWatcher, notifier: FakeNotifier, records: list[dict]) -> int:
    """在 mock 掉查询/持久化/睡眠的情况下执行一次 check()。"""
    watcher._cursor["last_debut_ts"] = "2026-08-23 16:00:00+00:00"
    fixed = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
    with patch("new_object_watcher._utc_now", return_value=fixed):
        with patch.object(watcher, "_query_debut", return_value=records):
            with patch.object(watcher, "_save_cursor"):
                with patch("new_object_watcher.time.sleep"):
                    return watcher.check(None, notifier)


def test_watchlist_only_pushes_matched_and_skips_unmatched(tmp_data_dir: str) -> None:
    watcher = _make_watcher(tmp_data_dir, False, ["2026-085"])
    notifier = FakeNotifier()
    records = [
        {"NORAD_CAT_ID": "60001", "OBJECT_ID": "2026-085A", "DEBUT": "2026-08-23 17:00:00"},
        {"NORAD_CAT_ID": "60002", "OBJECT_ID": "2026-100B", "DEBUT": "2026-08-23 17:05:00"},
    ]

    pushed = _run_check(watcher, notifier, records)

    assert pushed == 1
    assert len(notifier.debuts) == 1
    assert notifier.debuts[0][0]["NORAD_CAT_ID"] == "60001"
    assert notifier.debuts[0][1] is True  # watched=True
    assert notifier.summaries == []  # watchlist-only 不发摘要


def test_enabled_pushes_all_records(tmp_data_dir: str) -> None:
    watcher = _make_watcher(tmp_data_dir, True, [])
    notifier = FakeNotifier()
    records = [
        {"NORAD_CAT_ID": "60001", "OBJECT_ID": "2026-085A", "DEBUT": "2026-08-23 17:00:00"},
        {"NORAD_CAT_ID": "60002", "OBJECT_ID": "2026-100B", "DEBUT": "2026-08-23 17:05:00"},
    ]

    pushed = _run_check(watcher, notifier, records)

    assert pushed == 2
    assert len(notifier.debuts) == 2


def test_legacy_list_of_str_parsing(tmp_data_dir: str) -> None:
    w = NewObjectWatcher(
        {"enabled": True, "watched_launches": ["2026-085", "2026-092"]},
        tmp_data_dir,
    )
    assert isinstance(w._watched, dict)
    assert set(w._watched.keys()) == {"2026-085", "2026-092"}
    assert w._watched["2026-085"] == ""


def test_dict_format_labels_parsing(tmp_data_dir: str) -> None:
    w = NewObjectWatcher(
        {
            "enabled": True,
            "watched_launches": [
                {"intldes_prefix": "2026-085", "label": "Starlink"},
                {"intldes_prefix": "2026-092"},
            ],
        },
        tmp_data_dir,
    )
    assert w._watched["2026-085"] == "Starlink"
    assert w._watched["2026-092"] == ""


def test_prefix_matching(tmp_data_dir: str) -> None:
    w = NewObjectWatcher(
        {
            "enabled": True,
            "watched_launches": [{"intldes_prefix": "2026-085", "label": "Starlink"}],
        },
        tmp_data_dir,
    )
    w._cursor["last_debut_ts"] = "2020-01-01T00:00:00+00:00"
    matched, unmatched = w._process(
        [
            {"DEBUT": "2026-07-14T17:05:00+00:00", "OBJECT_ID": "2026-085A", "NORAD_CAT_ID": 1, "OBJECT_NAME": "A"},
            {"DEBUT": "2026-07-14T17:06:00+00:00", "OBJECT_ID": "2026-085B", "NORAD_CAT_ID": 2, "OBJECT_NAME": "B"},
            {"DEBUT": "2026-07-14T17:07:00+00:00", "OBJECT_ID": "2026-086A", "NORAD_CAT_ID": 3, "OBJECT_NAME": "C"},
        ]
    )
    assert len(matched) == 2
    assert len(unmatched) == 1
    assert matched[0].get("_matched_label") == "Starlink"


def test_prefix_matching_prefers_longest(tmp_data_dir: str) -> None:
    # 长前缀优先，防止 "2026-08" 误匹配 "2026-085A"
    w = NewObjectWatcher(
        {
            "enabled": True,
            "watched_launches": [
                "2026-08",
                {"intldes_prefix": "2026-085", "label": "Long"},
            ],
        },
        tmp_data_dir,
    )
    w._cursor["last_debut_ts"] = "2020-01-01T00:00:00+00:00"
    matched, _ = w._process(
        [
            {"DEBUT": "2026-07-14T17:05:00+00:00", "OBJECT_ID": "2026-085A", "NORAD_CAT_ID": 1, "OBJECT_NAME": "A"},
        ]
    )
    assert len(matched) == 1
    assert matched[0].get("_matched_label") == "Long"
