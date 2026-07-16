"""配置读写 API — 允许 Web 修改部分 config.yaml 字段"""

from __future__ import annotations

import asyncio
import os

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/api/config", tags=["config"])
security = HTTPBearer(auto_error=False)

# 可选 API 密钥：设置 DASHBOARD_API_KEY 环境变量即可启用认证
_DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "")

# 防止前端和 Telegram Bot 并发 read-modify-write 导致互相覆盖
_config_lock = asyncio.Lock()


def _require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if not _DASHBOARD_API_KEY:
        return  # 未配置密钥时允许所有请求
    if credentials is None or credentials.credentials != _DASHBOARD_API_KEY:
        raise HTTPException(401, "未授权：需要有效的 API 密钥")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
CONFIG_PATH = os.path.abspath(CONFIG_PATH)

# 允许 Web 修改的字段路径（YAML 路径）
ALLOWED_PATHS = {
    "targets.norad_ids",
    "alerts.reentry_warning_km",
    "alerts.sgp4_reliable_floor_km",
    "alerts.only_print_on_update",
    "alerts.fallback_maneuver_threshold_km",
    "xpropagator.enabled",
    "xpropagator.maneuver_threshold_km",
    "data_source.fallback_threshold",
    "new_object_discovery.enabled",
    "new_object_discovery.daily_summary",
    "new_object_discovery.watched_launches",
}


def _read_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _extract_allowed(cfg: dict) -> dict:
    """从完整配置中提取允许返回的字段"""
    result: dict = {}
    for path in sorted(ALLOWED_PATHS):
        parts = path.split(".")
        node = cfg
        ok = True
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                ok = False
                break
        if ok:
            # 构建嵌套结构
            target = result
            for p in parts[:-1]:
                target = target.setdefault(p, {})
            target[parts[-1]] = node
    return result


def _merge_allowed(cfg: dict, updates: dict) -> None:
    """将允许的更新合并到配置字典中，递归处理嵌套"""
    for key, value in updates.items():
        if isinstance(value, dict):
            if key not in cfg:
                cfg[key] = {}
            _merge_allowed(cfg[key], value)
        else:
            cfg[key] = value


def _validate_updates(updates: dict, prefix: str = "") -> list[str]:
    """递归校验，返回非法字段路径列表"""
    illegal: list[str] = []
    for key, value in updates.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            illegal.extend(_validate_updates(value, path))
        elif path not in ALLOWED_PATHS:
            illegal.append(path)
        else:
            # 类型校验
            if key in ("norad_ids",):
                if not isinstance(value, list) or not all(isinstance(v, int) for v in value):
                    illegal.append(f"{path} (必须是整数列表)")
            elif key in ("reentry_warning_km", "sgp4_reliable_floor_km",
                        "fallback_maneuver_threshold_km",
                        "maneuver_threshold_km", "fallback_threshold"):
                if not isinstance(value, (int, float)):
                    illegal.append(f"{path} (必须是数字)")
            elif key in ("enabled", "only_print_on_update", "daily_summary"):
                if not isinstance(value, bool):
                    illegal.append(f"{path} (必须是布尔值)")
            elif key in ("watched_launches",):
                if not isinstance(value, list):
                    illegal.append(f"{path} (必须是列表)")
                else:
                    for i, item in enumerate(value):
                        if isinstance(item, str):
                            if not item.strip():
                                illegal.append(f"{path}[{i}] (前缀不能为空)")
                        elif isinstance(item, dict):
                            pfx = item.get("intldes_prefix", "")
                            if not pfx or not isinstance(pfx, str) or not pfx.strip():
                                illegal.append(f"{path}[{i}].intldes_prefix (必填且不能为空)")
                            lbl = item.get("label")
                            if lbl is not None and not isinstance(lbl, str):
                                illegal.append(f"{path}[{i}].label (必须是字符串)")
                        else:
                            illegal.append(f"{path}[{i}] (必须是字符串或对象)")
    return illegal


def _write_config(cfg: dict) -> None:
    """直接写入（不 rename，兼容 Docker bind mount）"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


@router.get("")
async def get_config():
    """返回允许在 Web 上修改的配置字段"""
    cfg = _read_config()
    return _extract_allowed(cfg)


@router.put("")
async def update_config(updates: dict, _auth=Depends(_require_auth)):
    """更新允许的配置字段，合并写入 config.yaml"""
    if not updates:
        raise HTTPException(400, "请求体为空")

    illegal = _validate_updates(updates)
    if illegal:
        raise HTTPException(400, f"不允许修改的字段: {', '.join(illegal)}")

    # read-modify-write 加锁，防止前端和 bot 并发写导致互相覆盖
    async with _config_lock:
        cfg = _read_config()
        if not cfg:
            raise HTTPException(500, "无法读取配置文件")

        _merge_allowed(cfg, updates)

        try:
            _write_config(cfg)
        except OSError as e:
            raise HTTPException(500, f"配置文件写入失败: {e}")

    return {"status": "ok", "message": "配置已保存，将在下一轮询周期生效"}


@router.post("/toggle-discovery")
async def toggle_discovery(_auth=Depends(_require_auth)):
    """原子翻转 new_object_discovery.enabled，返回新值。

    独立端点而非让客户端读-改-写 PUT，防止 bot 和前端并发 toggle 时
    一方覆盖另一方（两次 toggle 理应相消，但先后读同值导致回到原点）。
    """
    async with _config_lock:
        cfg = _read_config()
        if not cfg:
            raise HTTPException(500, "无法读取配置文件")
        nod = cfg.setdefault("new_object_discovery", {})
        current = nod.get("enabled", False)
        new_val = not current
        nod["enabled"] = new_val
        try:
            _write_config(cfg)
        except OSError as e:
            raise HTTPException(500, f"配置文件写入失败: {e}")

    return {"enabled": new_val}
