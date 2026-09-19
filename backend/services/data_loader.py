"""
JSON 数据加载模块

从 tle_data.jsonl / decay_state.json / tle_log.jsonl 读取数据，
供 FastAPI 路由层使用

与 spacetrack_monitor.py 相同的文件路径解析逻辑。
"""

from __future__ import annotations

import json
import logging
import os
import threading

import yaml

log = logging.getLogger(__name__)


# tle_data.jsonl 解析缓存。
# 后端多个 REST 端点与 WebSocket（3s 轮询）会反复读取同一份数据，
# 若每次都全量扫描+解析，成本随历史行数线性增长。此处按 (mtime, size)
# 失效：文件未变则复用上次解析结果，三个读函数共用同一次解析。
_TLE_CACHE_LOCK = threading.Lock()
_tle_cache_key: tuple[float, int] | None = None
_tle_cache_records: list[dict] = []


def _load_tle_records() -> list[dict]:
    """解析 tle_data.jsonl 全部记录（按写入顺序，即时间升序）。

    返回的列表为缓存共享对象，调用方只读、不得就地修改。
    """
    global _tle_cache_key, _tle_cache_records

    path = _find_file("tle_data.jsonl")
    if not path:
        return []

    try:
        st = os.stat(path)
        key = (st.st_mtime, st.st_size)
    except OSError as e:
        log.error("读取 %s 状态失败: %s", path, e)
        return []

    with _TLE_CACHE_LOCK:
        if key == _tle_cache_key:
            return _tle_cache_records

        records: list[dict] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning("JSONL 行解析失败 [%s]: %.80s", path, line)
                        continue
        except OSError as e:
            log.error("读取 %s 失败: %s", path, e)
            return _tle_cache_records

        _tle_cache_key = key
        _tle_cache_records = records
        return records


def _project_root() -> str:
    """返回项目根目录（backend/services/ 向上三级）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_data_dir() -> str:
    """返回数据文件所在目录，优先 congfig.yaml 中的 data_dir，其次项目根下的 data/"""

    root = _project_root()

    local = os.path.join(root, "data")
    if os.path.isdir(local):
        return local

    try:
        cfg_path = os.path.join(root, "config.yaml")
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            data_dir = cfg.get("files", {}).get("data_dir")
            if data_dir:
                return data_dir
    except (OSError, yaml.YAMLError) as exc:
        log.debug("config.yaml 读取失败: %s", exc)

    return local


def _find_file(filename: str) -> str | None:
    """在数据目录下查找文件"""

    data_dir = get_data_dir()
    p = os.path.join(data_dir, filename)
    return p if os.path.exists(p) else None


# Space-Track OMM 中应为数值、但会以带引号字符串下发的字段。
# CelesTrak 路径存的是数字，两源混用会让前端 number 契约落空
# （字符串没有 .toFixed，直接渲染即抛异常）。在合并入顶层时统一转为 float。
_OMM_NUMERIC_FIELDS = (
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "MEAN_MOTION",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
    "ECCENTRICITY",
    "INCLINATION",
    "BSTAR",
    "REV_AT_EPOCH",
)


def merge_raw_elements(records: list[dict]) -> None:
    """将 _raw_elements 中的字段合并到顶层，就地修改。

    合并时把 OMM 数值字段规范成 float，兑现 API 声明的 number 契约；
    转换失败（缺失或非数值）保留原值，不猜测、不丢弃。
    """

    for r in records:
        if raw := r.pop("_raw_elements", None):
            r.update(raw)
        for field in _OMM_NUMERIC_FIELDS:
            value = r.get(field)
            if isinstance(value, str):
                try:
                    r[field] = float(value)
                except ValueError:
                    log.warning("OMM 字段 %s 无法转为数值: %.40s", field, value)


def load_latest_satellites() -> list[dict]:
    # 读取所有卫星的最新轨道记录，每个 NORAD ID 只取最新一条。
    latest: dict[int, dict] = {}
    for entry in _load_tle_records():
        norad = entry.get("norad")
        if norad is not None:
            # 后面的行比前面的新（追加写入），覆盖即取最新
            latest[norad] = entry
    # 返回浅拷贝：调用方（merge_raw_elements）会就地 pop/update，不能污染缓存
    return [dict(v) for v in latest.values()]


def load_satellite_history(norad_id: int, limit: int = 100) -> list[dict]:
    """
    读取指定卫星的完整 TLE 变化历史（从旧到新）。
    """
    # _load_tle_records 已按写入顺序（时间升序）返回，无需再排序
    records = [dict(e) for e in _load_tle_records() if e.get("norad") == norad_id]
    return records[-limit:] if len(records) > limit else records


def load_change_history(limit: int = 50) -> list[dict]:
    """
    读取所有卫星的 TLE 变化事件（从新到旧）。
    """
    # 写入顺序为时间升序，取末尾 limit 条即最新，再反转为从新到旧
    records = _load_tle_records()
    tail = records[-limit:] if len(records) > limit else records
    return [dict(e) for e in reversed(tail)]


def load_decay_state() -> dict:
    """
    读取衰降状态文件。若文件不存在返回空 dict。
    """
    path = _find_file("decay_state.json")
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError) as e:
        log.debug("decay_state.json 读取失败: %s", e)
        return {}


def load_run_log(limit: int = 100) -> list[dict]:
    """
    从 tle_log.jsonl 读取运行日志（从新到旧）。
    """
    path = _find_file("tle_log.jsonl")
    if not path:
        return []

    records: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("JSONL 行解析失败 [%s]: %.80s", path, line)
                    continue
                records.append(entry)
    except OSError as e:
        log.error("读取 %s 失败: %s", path, e)
        return []

    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records[:limit]
