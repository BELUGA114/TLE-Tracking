"""Telegram Bot 双向控制脚本

独立进程，长轮询 getUpdates，处理 slash 命令和 Inline Keyboard 回调。
所有配置读写通过 localhost HTTP API，不直接操作 config.yaml。

命令：
  /start, /status  - 状态摘要 + Inline Keyboard [启用/禁用] [关注列表]
  /watch <前缀> <标签>  - 添加关注（标签可选）
  /unwatch <前缀>  - 移除关注
  /help            - 帮助

Inline Keyboard：
  [启用] / [禁用]  - toggle 总开关
  [关注列表]       - 列出所有关注项，每项带 [移除] 按钮
  [➕ 添加关注]   - 提示使用 /watch 命令

用法:
    .venv/Scripts/python.exe telegram_bot.py
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Bot] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_BASE = "http://localhost:8000"
API_KEY = os.getenv("DASHBOARD_API_KEY", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# 只响应指定 chat_id 的消息，防止未授权访问
_ALLOWED_CHAT_ID = int(CHAT_ID) if CHAT_ID.lstrip("-").isdigit() else 0


def _api_headers() -> dict[str, str]:
    """构建 API 请求头，DASHBOARD_API_KEY 存在时带 Bearer token"""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


def _get_config() -> Optional[dict]:
    """读取当前可修改的配置字段"""
    try:
        resp = requests.get(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        log.warning("GET /api/config 返回 %d: %s", resp.status_code, resp.text[:200])
        return None
    except requests.RequestException as e:
        log.warning("GET /api/config 失败: %s", e)
        return None


def _put_config(updates: dict) -> bool:
    """合并写入配置"""
    try:
        resp = requests.put(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            json=updates,
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        log.warning("PUT /api/config 返回 %d: %s", resp.status_code, resp.text[:200])
        return False
    except requests.RequestException as e:
        log.warning("PUT /api/config 失败: %s", e)
        return False


def _get_status() -> Optional[dict]:
    """读取运行时状态"""
    try:
        resp = requests.get(
            f"{API_BASE}/api/discovery/status",
            headers=_api_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        log.warning("GET /api/discovery/status 返回 %d", resp.status_code)
        return None
    except requests.RequestException as e:
        log.warning("GET /api/discovery/status 失败: %s", e)
        return None


def _send_message(text: str, reply_markup: Optional[dict] = None) -> bool:
    """发送或编辑消息。reply_markup 用于 Inline Keyboard"""
    payload: dict = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json=payload,
            timeout=15,
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            time.sleep(retry_after)
            resp = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)
        return resp.status_code == 200
    except requests.RequestException as e:
        log.warning("sendMessage 失败: %s", e)
        return False


def _edit_message_text(chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None) -> bool:
    """编辑已有消息，用于 Inline Keyboard 响应后更新"""
    payload: dict = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/editMessageText",
            json=payload,
            timeout=15,
        )
        return resp.status_code == 200
    except requests.RequestException as e:
        log.warning("editMessageText 失败: %s", e)
        return False


def _answer_callback(callback_query_id: str, text: str = "") -> None:
    """回复 callback query，关闭按钮 loading 状态"""
    try:
        requests.post(
            f"{TELEGRAM_API}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=10,
        )
    except requests.RequestException:
        pass


def _build_status_keyboard(enabled: bool) -> dict:
    """构建 /status 的 Inline Keyboard"""
    toggle_label = "禁用" if enabled else "启用"
    return {
        "inline_keyboard": [
            [{"text": toggle_label, "callback_data": "toggle"}],
            [{"text": "关注列表", "callback_data": "list"}],
        ]
    }


def _build_watched_keyboard(watched: list) -> dict:
    """构建关注列表的 Inline Keyboard，每项带移除按钮"""
    buttons = []
    for item in watched:
        if isinstance(item, dict):
            prefix = item.get("intldes_prefix", "")
            label = item.get("label", "")
        else:
            prefix = str(item)
            label = ""
        display = f"{label} ({prefix})" if label else prefix
        buttons.append([
            {"text": display, "callback_data": "noop"},
            {"text": "❌", "callback_data": f"remove:{prefix}"},
        ])
    buttons.append([{"text": "➕ 添加关注", "callback_data": "add"}])
    buttons.append([{"text": "« 返回", "callback_data": "status"}])
    return {"inline_keyboard": buttons}


def _build_status_text(status: dict, config: dict) -> str:
    """构建 /status 消息文本"""
    enabled = status.get("enabled", False)
    state_icon = "🟢" if enabled else "⚫"
    state_text = "已启用" if enabled else "已关闭"

    lines = [
        f"<b>📡 新对象发现</b>  {state_icon} {state_text}",
        "",
        f"<b>上次检查:</b> {status.get('last_check_ts', '?')}",
        f"<b>最新编目:</b> {status.get('last_debut_ts', '?')}",
        f"<b>累计发现:</b> {status.get('total_processed', 0)} 个",
        f"<b>关注数量:</b> {status.get('watched_launches_count', 0)} 个",
        f"<b>下次检查:</b> {status.get('next_check_at', '?')}",
    ]
    return "\n".join(lines)


def _build_watched_text(watched: list) -> str:
    """构建关注列表消息文本"""
    if not watched:
        return "<b>📋 关注列表</b>\n\n暂无关注项。使用 /watch 命令添加。"

    lines = ["<b>📋 关注列表</b>", ""]
    for item in watched:
        if isinstance(item, dict):
            prefix = item.get("intldes_prefix", "?")
            label = item.get("label", "")
        else:
            prefix = str(item)
            label = ""
        if label:
            lines.append(f"• <b>{label}</b>  <code>{prefix}</code>")
        else:
            lines.append(f"• <code>{prefix}</code>")
    return "\n".join(lines)


def _build_help_text() -> str:
    """构建 /help 消息文本"""
    return (
        "<b>📡 新对象发现 Bot</b>\n"
        "\n"
        "<b>命令:</b>\n"
        "/status - 查看状态和开关\n"
        "/watch <code>前缀</code> <code>标签</code> - 添加关注（标签可选）\n"
        "/unwatch <code>前缀</code> - 移除关注\n"
        "/help - 显示此帮助\n"
        "\n"
        "<i>Inline 按钮也可用于切换开关和管理列表。</i>"
    )


# 命令处理

def _cmd_status(msg: dict) -> None:
    """处理 /start 和 /status 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    status = _get_status()
    config = _get_config()
    if status is None or config is None:
        _send_message("无法获取状态，请稍后重试。")
        return

    enabled = status.get("enabled", False)
    text = _build_status_text(status, config)
    keyboard = _build_status_keyboard(enabled)
    _send_message(text, reply_markup=keyboard)


def _cmd_watch(msg: dict) -> None:
    """处理 /watch <前缀> [标签] 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    text = msg.get("text", "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        _send_message(
            "用法: /watch &lt;前缀&gt; [标签]\n\n"
            "示例:\n  /watch 2026-085\n  /watch 2026-085 Starlink G12-3"
        )
        return

    prefix = parts[1].strip().upper()
    label = parts[2].strip() if len(parts) > 2 else ""

    config = _get_config()
    if config is None:
        _send_message("无法读取配置，请稍后重试。")
        return

    nod = config.get("new_object_discovery", {})
    watched: list = nod.get("watched_launches", [])
    if not isinstance(watched, list):
        watched = []

    # 检查是否已存在相同前缀
    for item in watched:
        existing_prefix = (
            item.get("intldes_prefix", "") if isinstance(item, dict) else str(item)
        )
        if existing_prefix.strip().upper() == prefix:
            _send_message(f"前缀 <code>{prefix}</code> 已在关注列表中。")
            return

    new_item: dict = {"intldes_prefix": prefix}
    if label:
        new_item["label"] = label
    watched.append(new_item)

    ok = _put_config({"new_object_discovery": {"watched_launches": watched}})
    if ok:
        response = f"已添加关注: <code>{prefix}</code>"
        if label:
            response += f" — {label}"
        _send_message(response)
    else:
        _send_message("保存配置失败，请稍后重试。")


def _cmd_unwatch(msg: dict) -> None:
    """处理 /unwatch <前缀> 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    text = msg.get("text", "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        _send_message("用法: /unwatch &lt;前缀&gt;\n\n示例: /unwatch 2026-085")
        return

    prefix = parts[1].strip().upper()

    config = _get_config()
    if config is None:
        _send_message("无法读取配置，请稍后重试。")
        return

    nod = config.get("new_object_discovery", {})
    watched: list = nod.get("watched_launches", [])
    if not isinstance(watched, list):
        watched = []

    removed = False
    new_watched = []
    for item in watched:
        existing_prefix = (
            item.get("intldes_prefix", "") if isinstance(item, dict) else str(item)
        )
        if existing_prefix.strip().upper() == prefix:
            removed = True
        else:
            new_watched.append(item)

    if not removed:
        _send_message(f"前缀 <code>{prefix}</code> 不在关注列表中。")
        return

    ok = _put_config({"new_object_discovery": {"watched_launches": new_watched}})
    if ok:
        _send_message(f"已移除关注: <code>{prefix}</code>")
    else:
        _send_message("保存配置失败，请稍后重试。")


def _cmd_help(msg: dict) -> None:
    """处理 /help 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    _send_message(_build_help_text())


# Inline Keyboard 回调处理

def _handle_toggle(cb: dict) -> None:
    """处理 [启用]/[禁用] 按钮"""
    if cb.get("message", {}).get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        _answer_callback(cb["id"])
        return
    config = _get_config()
    if config is None:
        _answer_callback(cb["id"], "无法读取配置")
        return

    nod = config.get("new_object_discovery", {})
    current = nod.get("enabled", False)
    new_enabled = not current

    ok = _put_config({"new_object_discovery": {"enabled": new_enabled}})
    if not ok:
        _answer_callback(cb["id"], "保存失败")
        return

    _answer_callback(cb["id"], f"已{'启用' if new_enabled else '禁用'}")

    # 刷新状态消息
    status = _get_status()
    config_new = _get_config()
    if status and config_new:
        text = _build_status_text(status, config_new)
        keyboard = _build_status_keyboard(new_enabled)
        msg = cb.get("message", {})
        _edit_message_text(
            msg.get("chat", {}).get("id", 0),
            msg.get("message_id", 0),
            text,
            reply_markup=keyboard,
        )


def _handle_list(cb: dict) -> None:
    """处理 [关注列表] 按钮"""
    if cb.get("message", {}).get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        _answer_callback(cb["id"])
        return
    config = _get_config()
    if config is None:
        _answer_callback(cb["id"], "无法读取配置")
        return

    nod = config.get("new_object_discovery", {})
    watched: list = nod.get("watched_launches", [])
    if not isinstance(watched, list):
        watched = []

    text = _build_watched_text(watched)
    keyboard = _build_watched_keyboard(watched)
    msg = cb.get("message", {})
    _edit_message_text(
        msg.get("chat", {}).get("id", 0),
        msg.get("message_id", 0),
        text,
        reply_markup=keyboard,
    )
    _answer_callback(cb["id"])


def _handle_remove(cb: dict, prefix: str) -> None:
    """处理关注项的 [❌] 移除按钮"""
    if cb.get("message", {}).get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        _answer_callback(cb["id"])
        return
    config = _get_config()
    if config is None:
        _answer_callback(cb["id"], "无法读取配置")
        return

    nod = config.get("new_object_discovery", {})
    watched: list = nod.get("watched_launches", [])
    if not isinstance(watched, list):
        watched = []

    new_watched = []
    removed_label = prefix
    for item in watched:
        existing_prefix = (
            item.get("intldes_prefix", "") if isinstance(item, dict) else str(item)
        )
        if existing_prefix.strip().upper() == prefix.upper():
            if isinstance(item, dict) and item.get("label"):
                removed_label = item["label"]
        else:
            new_watched.append(item)

    ok = _put_config({"new_object_discovery": {"watched_launches": new_watched}})
    if not ok:
        _answer_callback(cb["id"], "保存失败")
        return

    _answer_callback(cb["id"], f"已移除 {removed_label}")

    # 刷新列表
    config_new = _get_config()
    if config_new:
        nod_new = config_new.get("new_object_discovery", {})
        watched_new: list = nod_new.get("watched_launches", [])
        if not isinstance(watched_new, list):
            watched_new = []
        text = _build_watched_text(watched_new)
        keyboard = _build_watched_keyboard(watched_new)
        msg = cb.get("message", {})
        _edit_message_text(
            msg.get("chat", {}).get("id", 0),
            msg.get("message_id", 0),
            text,
            reply_markup=keyboard,
        )


def _handle_add(cb: dict) -> None:
    """处理 [➕ 添加关注] 按钮"""
    if cb.get("message", {}).get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        _answer_callback(cb["id"])
        return
    _answer_callback(cb["id"], "使用 /watch 命令添加")


def _handle_status_callback(cb: dict) -> None:
    """处理 [« 返回] 按钮，回到状态页"""
    if cb.get("message", {}).get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        _answer_callback(cb["id"])
        return
    status = _get_status()
    config = _get_config()
    if status and config:
        enabled = status.get("enabled", False)
        text = _build_status_text(status, config)
        keyboard = _build_status_keyboard(enabled)
        msg = cb.get("message", {})
        _edit_message_text(
            msg.get("chat", {}).get("id", 0),
            msg.get("message_id", 0),
            text,
            reply_markup=keyboard,
        )
    _answer_callback(cb["id"])


# 消息路由

def _handle_message(msg: dict) -> None:
    """路由消息到对应命令处理函数"""
    # 权限检查：只响应配置的 chat_id
    chat = msg.get("chat", {})
    if chat.get("id") != _ALLOWED_CHAT_ID:
        log.info("忽略来自 chat_id=%s 的未授权消息", chat.get("id"))
        return

    text = msg.get("text", "").strip()
    if not text:
        return

    if text.startswith("/start") or text.startswith("/status"):
        _cmd_status(msg)
    elif text.startswith("/watch"):
        _cmd_watch(msg)
    elif text.startswith("/unwatch"):
        _cmd_unwatch(msg)
    elif text.startswith("/help"):
        _cmd_help(msg)
    else:
        _send_message("未知命令。使用 /help 查看可用命令。")


def _handle_callback(cb: dict) -> None:
    """路由 Inline Keyboard 回调"""
    msg = cb.get("message", {})
    chat = msg.get("chat", {})
    # 权限检查
    if chat.get("id") != _ALLOWED_CHAT_ID:
        return

    data = cb.get("data", "")

    if data == "toggle":
        _handle_toggle(cb)
    elif data == "list":
        _handle_list(cb)
    elif data.startswith("remove:"):
        _handle_remove(cb, data[7:])
    elif data == "add":
        _handle_add(cb)
    elif data == "status":
        _handle_status_callback(cb)
    elif data == "noop":
        _answer_callback(cb["id"])


# 主循环

def main() -> None:
    """长轮询 getUpdates，处理消息和回调"""
    if not TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未配置，Bot 无法启动")
        return

    if not _ALLOWED_CHAT_ID:
        log.error("TELEGRAM_CHAT_ID 格式无效: %s", CHAT_ID)
        return

    log.info("Telegram Bot 已启动  chat_id=%d  API=%s", _ALLOWED_CHAT_ID, API_BASE)

    offset = 0
    consecutive_errors = 0

    while True:
        try:
            resp = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
        except requests.RequestException as e:
            consecutive_errors += 1
            wait = min(2 ** consecutive_errors, 60)
            log.warning("getUpdates 失败（第 %d 次）: %s，%d 秒后重试", consecutive_errors, e, wait)
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "30"))
            log.warning("getUpdates 429，等待 %d 秒", retry_after)
            time.sleep(retry_after)
            continue

        if resp.status_code != 200:
            consecutive_errors += 1
            wait = min(2 ** consecutive_errors, 60)
            log.warning("getUpdates HTTP %d，%d 秒后重试", resp.status_code, wait)
            time.sleep(wait)
            continue

        consecutive_errors = 0

        try:
            body = resp.json()
        except ValueError:
            log.warning("getUpdates JSON 解析失败")
            time.sleep(5)
            continue

        if not body.get("ok"):
            log.warning("getUpdates 返回 not ok: %s", body)
            time.sleep(5)
            continue

        for update in body.get("result", []):
            update_id = update.get("update_id", 0)
            if update_id >= offset:
                offset = update_id + 1

            if "message" in update:
                _handle_message(update["message"])
            elif "callback_query" in update:
                _handle_callback(update["callback_query"])

        # Telegram 建议轮询间隔 1-2 秒
        time.sleep(1)


if __name__ == "__main__":
    main()
