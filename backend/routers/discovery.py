"""新对象发现运行时状态 — 只读 endpoint

数据来源：new_object_cursor.json + config.yaml。
Bot /status 命令调用此接口展示状态，不依赖 watcher 进程。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

import yaml
from fastapi import APIRouter

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

# 项目根目录（backend/routers/ 向上三级）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.yaml")


# 模块级配置缓存，供 DATA_DIR 解析使用
def _load_config_cached() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return {}


_cfg = _load_config_cached()

DATA_DIR: str = (
    os.environ.get("DATA_DIR")
    or _cfg.get("files", {}).get("data_dir")
    or os.path.join(_PROJECT_ROOT, "data")
)
CURSOR_PATH = os.path.join(DATA_DIR, "new_object_cursor.json")


def _read_cursor() -> dict:
    """读取游标文件，不存在或损坏时返回空 dict"""
    try:
        with open(CURSOR_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _read_config() -> dict:
    """读取 config.yaml"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return {}


@router.get("/status")
async def get_status():
    """返回新对象发现的运行时状态（只读）"""
    cursor = _read_cursor()
    cfg = _read_config()
    nod = cfg.get("new_object_discovery", {}) if cfg else {}

    enabled = nod.get("enabled", False)
    schedule_hour = nod.get("schedule_hour", 17)
    schedule_minute = nod.get("schedule_minute", 10)
    watched = nod.get("watched_launches", [])
    watched_count = len(watched) if isinstance(watched, list) else 0

    # 计算下次检查时间
    now = datetime.now(timezone.utc)
    next_check = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
    if next_check <= now:
        next_check += timedelta(days=1)

    last_debut_ts = cursor.get("last_debut_ts")
    last_check_ts = cursor.get("last_check_ts")
    total_processed = cursor.get("total_processed", 0)

    # 格式化时间戳，缺失时显示 "从未"
    if isinstance(last_check_ts, str):
        try:
            last_dt = datetime.fromisoformat(last_check_ts)
            last_check_display = last_dt.strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            last_check_display = last_check_ts
    else:
        last_check_display = "从未"

    if isinstance(last_debut_ts, str):
        try:
            debut_dt = datetime.fromisoformat(last_debut_ts)
            last_debut_display = debut_dt.strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            last_debut_display = last_debut_ts
    else:
        last_debut_display = "从未"

    return {
        "enabled": enabled,
        "last_check_ts": last_check_display,
        "last_debut_ts": last_debut_display,
        "total_processed": total_processed,
        "watched_launches_count": watched_count,
        "next_check_at": next_check.strftime("%Y-%m-%d %H:%M UTC"),
    }
