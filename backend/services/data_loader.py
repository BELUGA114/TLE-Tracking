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
from datetime import datetime, timezone
from typing import Optional

import yaml

log = logging.getLogger(__name__)


def _project_root() -> str:
    """返回项目根目录（backend/services/ 向上三级）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _find_file(filename: str) -> Optional[str]:
    """在数据目录下查找文件"""

    root = _project_root()

    # 项目根下的 data/ 目录（本地开发 / Windows 场景）
    local = os.path.join(root, "data", filename)
    if os.path.exists(local):
        return local

    # config.yaml 中的 data_dir（Docker 场景，值为 /data）
    try:
        cfg_path = os.path.join(root, "config.yaml")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            data_dir = cfg.get("files", {}).get("data_dir")
            if data_dir:
                p = os.path.join(data_dir, filename)
                if os.path.exists(p):
                    return p
    except Exception as exc:
        log.debug("config.yaml 读取失败: %s", exc)

    return None


def load_latest_satellites() -> list[dict]:

    #读取所有卫星的最新轨道记录，每个 NORAD ID 只取最新一条。
    path = _find_file("tle_data.jsonl")
    if not path:
        return []

    latest: dict[int, dict] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                norad = entry.get("norad")
                if norad is not None:
                    # 后面的行比前面的新（追加写入），覆盖即取最新
                    latest[norad] = entry
    except OSError as e:
        log.error("读取 %s 失败: %s", path, e)
        return []

    return list(latest.values())


def load_satellite_history(norad_id: int, limit: int = 100) -> list[dict]:
    """
    读取指定卫星的完整 TLE 变化历史（从旧到新）。
    """
    path = _find_file("tle_data.jsonl")
    if not path:
        return []

    records: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("norad") == norad_id:
                    records.append(entry)
    except OSError as e:
        log.error("读取 %s 失败: %s", path, e)
        return []

    # 按时间升序排列
    records.sort(key=lambda r: r.get("timestamp", ""))
    return records[-limit:] if len(records) > limit else records


def load_change_history(limit: int = 50) -> list[dict]:
    """
    读取所有卫星的 TLE 变化事件（从新到旧）。
    """
    path = _find_file("tle_data.jsonl")
    if not path:
        return []

    records: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records.append(entry)
    except OSError as e:
        log.error("读取 %s 失败: %s", path, e)
        return []

    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records[:limit]


def load_decay_state() -> dict:
    """
    读取衰降状态文件。若文件不存在返回空 dict。
    """
    path = _find_file("decay_state.json")
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
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
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records.append(entry)
    except OSError as e:
        log.error("读取 %s 失败: %s", path, e)
        return []

    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records[:limit]
