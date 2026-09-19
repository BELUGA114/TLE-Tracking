from __future__ import annotations

import json
import os

import pytest

from backend.services import data_loader


def _write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture
def tle_file(tmp_path, monkeypatch):
    """将 data_loader 的 tle_data.jsonl 定位重定向到临时文件，并重置解析缓存。"""
    path = str(tmp_path / "tle_data.jsonl")

    def fake_find(filename: str) -> str | None:
        if filename == "tle_data.jsonl":
            return path if os.path.exists(path) else None
        return None

    monkeypatch.setattr(data_loader, "_find_file", fake_find)
    # 重置模块级缓存，避免跨用例污染
    monkeypatch.setattr(data_loader, "_tle_cache_key", None)
    monkeypatch.setattr(data_loader, "_tle_cache_records", [])
    return path


def test_latest_satellites_picks_newest_per_norad(tle_file) -> None:
    _write_jsonl(
        tle_file,
        [
            {"norad": 100, "timestamp": "2026-01-01T00:00:00", "epoch": "old"},
            {"norad": 200, "timestamp": "2026-01-01T01:00:00", "epoch": "a"},
            {"norad": 100, "timestamp": "2026-01-02T00:00:00", "epoch": "new"},
        ],
    )

    sats = data_loader.load_latest_satellites()

    by_norad = {s["norad"]: s for s in sats}
    assert by_norad[100]["epoch"] == "new"
    assert by_norad[200]["epoch"] == "a"


def test_change_history_newest_first_and_limited(tle_file) -> None:
    _write_jsonl(
        tle_file,
        [
            {"norad": 1, "timestamp": "2026-01-01T00:00:00"},
            {"norad": 1, "timestamp": "2026-01-02T00:00:00"},
            {"norad": 1, "timestamp": "2026-01-03T00:00:00"},
        ],
    )

    records = data_loader.load_change_history(limit=2)

    assert [r["timestamp"] for r in records] == [
        "2026-01-03T00:00:00",
        "2026-01-02T00:00:00",
    ]


def test_satellite_history_ascending_and_filtered(tle_file) -> None:
    _write_jsonl(
        tle_file,
        [
            {"norad": 1, "timestamp": "2026-01-01T00:00:00"},
            {"norad": 2, "timestamp": "2026-01-01T00:30:00"},
            {"norad": 1, "timestamp": "2026-01-02T00:00:00"},
        ],
    )

    records = data_loader.load_satellite_history(1)

    assert [r["timestamp"] for r in records] == [
        "2026-01-01T00:00:00",
        "2026-01-02T00:00:00",
    ]


def test_merge_raw_elements_does_not_pollute_cache(tle_file) -> None:
    """回归：调用方 pop _raw_elements 不得剥掉缓存里的字段。"""
    _write_jsonl(
        tle_file,
        [{"norad": 1, "timestamp": "2026-01-01T00:00:00", "_raw_elements": {"OBJECT_ID": "X"}}],
    )

    first = data_loader.load_latest_satellites()
    data_loader.merge_raw_elements(first)  # 就地 pop，若返回引用会污染缓存
    assert first[0]["OBJECT_ID"] == "X"

    # 文件未变，第二次仍应拿到完整的 _raw_elements
    second = data_loader.load_latest_satellites()
    assert second[0].get("_raw_elements") == {"OBJECT_ID": "X"}


def test_cache_invalidates_on_file_change(tle_file) -> None:
    _write_jsonl(tle_file, [{"norad": 1, "timestamp": "2026-01-01T00:00:00"}])
    assert len(data_loader.load_change_history()) == 1

    # 追加一条并将 mtime 明显前移，确保 (mtime, size) 变化被识别
    _write_jsonl(
        tle_file,
        [
            {"norad": 1, "timestamp": "2026-01-01T00:00:00"},
            {"norad": 2, "timestamp": "2026-01-02T00:00:00"},
        ],
    )
    future = os.stat(tle_file).st_mtime + 10
    os.utime(tle_file, (future, future))

    assert len(data_loader.load_change_history()) == 2


def test_merge_raw_elements_coerces_omm_strings_to_float() -> None:
    """回归：Space-Track OMM 的字符串数值字段必须转为 float，
    否则前端 number 契约落空（string 无 .toFixed，整页崩溃）。"""
    records = [
        {
            "norad": 25544,
            "_raw_elements": {
                "RA_OF_ASC_NODE": "293.8866",
                "MEAN_MOTION": "15.5022",
                "MEAN_MOTION_DOT": "7.229e-05",
            },
        }
    ]
    data_loader.merge_raw_elements(records)
    r = records[0]
    assert r["RA_OF_ASC_NODE"] == 293.8866
    assert isinstance(r["RA_OF_ASC_NODE"], float)
    assert isinstance(r["MEAN_MOTION"], float)
    assert isinstance(r["MEAN_MOTION_DOT"], float)


def test_merge_raw_elements_keeps_number_and_bad_values() -> None:
    """已是数字的保持不变；无法解析的保留原值，不丢弃、不抛异常。"""
    records = [
        {
            "norad": 1,
            "_raw_elements": {"RA_OF_ASC_NODE": 90.19, "MEAN_ANOMALY": "N/A"},
        }
    ]
    data_loader.merge_raw_elements(records)
    r = records[0]
    assert r["RA_OF_ASC_NODE"] == 90.19
    assert r["MEAN_ANOMALY"] == "N/A"  # 转换失败保留原值
