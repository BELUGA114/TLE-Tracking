"""Telegram Bot 双向控制脚本

独立进程，长轮询 getUpdates，处理 slash 命令和 Inline Keyboard 回调。
所有配置读写通过 localhost HTTP API，不直接操作 config.yaml。

命令：
  /start              欢迎语 + 主菜单
  /status             状态摘要 + 主菜单
  /watchlist          关注列表面板
  /addwatch <前缀> [备注]  直接添加关注
  /rmwatch <前缀>     直接移除关注
  /help               帮助

Inline Keyboard：
  主菜单: [总开关] [关注列表 (N)] [添加关注] [刷新状态]
  关注列表: [🗑 前缀·备注] 每行，点即删
  ForceReply: 点 [添加关注] 后回复消息输入前缀和备注

用法:
    .venv/Scripts/python.exe telegram_bot.py
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
from common.logging_config import setup_logging
setup_logging("bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_BASE = "http://localhost:8000"
_runtime_api_key = os.getenv("DASHBOARD_API_KEY", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# 复用 TCP 连接
_session = requests.Session()

# 只响应指定 chat_id 的消息，防止未授权访问
_ALLOWED_CHAT_ID = int(CHAT_ID) if CHAT_ID.lstrip("-").isdigit() else 0

# ForceReply 提示文本，用于识别用户的 ForceReply 回复
_FORCE_REPLY_PROMPT = "请回复本消息，格式：国际编号前缀 备注"


def _api_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if _runtime_api_key:
        headers["Authorization"] = f"Bearer {_runtime_api_key}"
    return headers


def _set_api_key(value: str) -> bool:
    global _runtime_api_key
    normalized = value.strip()
    if not normalized:
        return False
    _runtime_api_key = normalized
    return True


def _get_config() -> Optional[dict]:
    try:
        resp = _session.get(f"{API_BASE}/api/config", headers=_api_headers(), timeout=10)
        if resp.status_code == 200:
            return resp.json()
        log.warning("GET /api/config 返回 %d: %s", resp.status_code, resp.text[:200])
        return None
    except requests.RequestException as e:
        log.warning("GET /api/config 失败: %s", e)
        return None


def _put_config(updates: dict) -> bool:
    try:
        resp = _session.put(
            f"{API_BASE}/api/config", headers=_api_headers(), json=updates, timeout=10
        )
        if resp.status_code == 200:
            return True
        log.warning("PUT /api/config 返回 %d: %s", resp.status_code, resp.text[:200])
        return False
    except requests.RequestException as e:
        log.warning("PUT /api/config 失败: %s", e)
        return False


def _toggle_discovery() -> Optional[bool]:
    """原子翻转 enabled，返回新值。避免读-改-写竞态。"""
    try:
        resp = _session.post(
            f"{API_BASE}/api/config/toggle-discovery",
            headers=_api_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("enabled")
        log.warning("POST /toggle-discovery 返回 %d: %s", resp.status_code, resp.text[:200])
        return None
    except requests.RequestException as e:
        log.warning("POST /toggle-discovery 失败: %s", e)
        return None


def _get_status() -> Optional[dict]:
    try:
        resp = _session.get(
            f"{API_BASE}/api/discovery/status", headers=_api_headers(), timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        log.warning("GET /api/discovery/status 返回 %d", resp.status_code)
        return None
    except requests.RequestException as e:
        log.warning("GET /api/discovery/status 失败: %s", e)
        return None


def _setup_commands() -> None:
    """在 Bot 启动时调用 setMyCommands，配置左下角菜单按钮的命令列表"""
    commands = [
        {"command": "start", "description": "欢迎语 + 主菜单"},
        {"command": "status", "description": "状态摘要 + 开关"},
        {"command": "watchlist", "description": "关注列表面板"},
        {"command": "addwatch", "description": "添加关注前缀"},
        {"command": "rmwatch", "description": "移除关注前缀"},
        {"command": "setapikey", "description": "临时设置仪表盘 API 密钥"},
        {"command": "help", "description": "显示帮助"},
    ]
    try:
        resp = _session.post(
            f"{TELEGRAM_API}/setMyCommands",
            json={"commands": commands},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            log.debug("setMyCommands 已配置 %d 条命令", len(commands))
        else:
            log.warning("setMyCommands 返回: %s", resp.text[:200])
    except requests.RequestException as e:
        log.warning("setMyCommands 失败: %s", e)


def _send_message(text: str, reply_markup: Optional[dict] = None) -> bool:
    payload: dict = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = _session.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            time.sleep(retry_after)
            resp = _session.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)
        return resp.status_code == 200
    except requests.RequestException as e:
        log.warning("sendMessage 失败: %s", e)
        return False


def _delete_message(chat_id: int, message_id: int) -> bool:
    try:
        resp = _session.post(
            f"{TELEGRAM_API}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException as e:
        log.warning("deleteMessage 失败: %s", e)
        return False


def _edit_message_text(
    chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None
) -> bool:
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
        resp = _session.post(f"{TELEGRAM_API}/editMessageText", json=payload, timeout=15)
        return resp.status_code == 200
    except requests.RequestException as e:
        log.warning("editMessageText 失败: %s", e)
        return False


def _answer_callback(callback_query_id: str, text: str = "") -> None:
    try:
        _session.post(
            f"{TELEGRAM_API}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=10,
        )
    except requests.RequestException:
        pass


# ── 键盘构建 ──

def _build_main_keyboard(enabled: bool, watched_count: int) -> dict:
    """主菜单键盘：总开关 / 关注列表 / 添加 / 刷新"""
    toggle_text = "已开" if enabled else "已关"
    return {
        "inline_keyboard": [
            [{"text": f"🔔 总开关：{toggle_text}", "callback_data": "toggle"}],
            [{"text": f"📋 关注列表 ({watched_count})", "callback_data": "watchlist"}],
            [{"text": "➕ 添加关注", "callback_data": "addwatch"}],
            [{"text": "🔄 刷新状态", "callback_data": "refresh"}],
        ]
    }


def _build_watched_keyboard(watched: list) -> dict:
    """关注列表面板键盘：每项一个删除按钮 + 返回主菜单"""
    buttons = []
    for item in watched:
        if isinstance(item, dict):
            prefix = item.get("intldes_prefix", "")
            label = item.get("label", "")
        else:
            prefix = str(item)
            label = ""
        display = f"{prefix} · {label}" if label else prefix
        buttons.append([{"text": f"🗑 {display}", "callback_data": f"remove:{prefix}"}])
    buttons.append([{"text": "⬅️ 返回主菜单", "callback_data": "refresh"}])
    return {"inline_keyboard": buttons}


def _build_watched_text(watched: list) -> str:
    """关注列表消息文本"""
    if not watched:
        return "<b>📋 关注列表</b>\n\n暂无关注项。\n使用 /addwatch 命令或 [➕ 添加关注] 按钮添加。"
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
    lines.append("")
    lines.append("<i>点击任一 🗑 行直接删除，无需确认。</i>")
    return "\n".join(lines)


def _build_status_text(status: dict) -> str:
    """状态消息文本"""
    enabled = status.get("enabled", False)
    state_text = "已启用 🟢" if enabled else "已关闭 ⚫"
    return "\n".join([
        f"<b>📡 新对象发现</b>  {state_text}",
        "",
        f"<b>上次检查:</b> {status.get('last_check_ts', '?')}",
        f"<b>最新编目:</b> {status.get('last_debut_ts', '?')}",
        f"<b>累计发现:</b> {status.get('total_processed', 0)} 个",
        f"<b>关注数量:</b> {status.get('watched_launches_count', 0)} 个",
        f"<b>下次检查:</b> {status.get('next_check_at', '?')}",
    ])


def _build_help_text() -> str:
    return (
        "<b>📡 新对象发现 Bot</b>\n"
        "\n"
        "<b>命令:</b>\n"
        "/start - 欢迎语 + 主菜单\n"
        "/status - 状态摘要\n"
        "/watchlist - 关注列表\n"
        "/addwatch <code>前缀</code> <code>备注</code> - 添加关注\n"
        "/rmwatch <code>前缀</code> - 移除关注\n"
        "/setapikey <code>密钥</code> - 临时设置仪表盘 API 密钥\n"
        "/help - 显示此帮助\n"
        "\n"
        "<i>主菜单按钮也可完成大部分操作。</i>"
    )


# ── watched_launches 辅助操作 ──

def _read_watched() -> list:
    """读取当前关注列表"""
    config = _get_config()
    if config is None:
        return []
    nod = config.get("new_object_discovery", {})
    watched = nod.get("watched_launches", [])
    return watched if isinstance(watched, list) else []


def _write_watched(watched: list) -> bool:
    """写入关注列表"""
    return _put_config({"new_object_discovery": {"watched_launches": watched}})


def _find_watched_prefix(watched: list, prefix: str) -> Optional[dict]:
    """在关注列表中查找指定前缀，返回匹配项和其在列表中的 dict 形态"""
    upper = prefix.strip().upper()
    for item in watched:
        existing = (
            item.get("intldes_prefix", "") if isinstance(item, dict) else str(item)
        )
        if existing.strip().upper() == upper:
            return item
    return None


# ── 命令处理 ──

def _cmd_start(msg: dict) -> None:
    """处理 /start 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    _send_message(
        "<b>📡 新对象发现 Bot</b>\n"
        "\n"
        "监控 Space-Track SATCAT 新编目 PAYLOAD 对象。\n"
        "使用下方菜单管理总开关和关注列表。\n"
        "\n"
        "<i>输入 /help 查看所有命令。</i>"
    )
    _cmd_status(msg)


def _cmd_set_api_key(msg: dict) -> None:
    text = msg.get("text", "")
    _, separator, value = text.partition(" ")
    if not separator or not value.strip():
        _send_message("用法: /setapikey <code>密钥</code>")
        return

    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")
    message_deleted = False
    if isinstance(chat_id, int) and isinstance(message_id, int):
        message_deleted = _delete_message(chat_id, message_id)

    _set_api_key(value)
    response = "仪表盘 API 密钥已在当前 Bot 进程中更新。"
    if not message_deleted:
        response += " Telegram 未能删除原命令，请手动删除含密钥的消息。"
    _send_message(response)


def _cmd_status(msg: dict) -> None:
    """处理 /status 命令：状态摘要 + 主菜单"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    status = _get_status()
    if status is None:
        _send_message("无法获取状态，请稍后重试。")
        return
    watched = _read_watched()
    text = _build_status_text(status)
    keyboard = _build_main_keyboard(status.get("enabled", False), len(watched))
    _send_message(text, reply_markup=keyboard)


def _cmd_watchlist(msg: dict) -> None:
    """处理 /watchlist 命令：关注列表面板"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    watched = _read_watched()
    text = _build_watched_text(watched)
    keyboard = _build_watched_keyboard(watched)
    _send_message(text, reply_markup=keyboard)


def _cmd_addwatch(msg: dict) -> None:
    """处理 /addwatch <前缀> [备注] 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    text = msg.get("text", "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        _send_message(
            "用法: /addwatch &lt;前缀&gt; [备注]\n\n"
            "示例:\n  /addwatch 2026-085\n  /addwatch 2026-085 Starlink G12-3"
        )
        return

    prefix = parts[1].strip().upper()
    label = parts[2].strip() if len(parts) > 2 else ""

    watched = _read_watched()
    if _find_watched_prefix(watched, prefix):
        _send_message(f"前缀 <code>{prefix}</code> 已在关注列表中。")
        return

    new_item: dict = {"intldes_prefix": prefix}
    if label:
        new_item["label"] = label
    watched.append(new_item)

    if _write_watched(watched):
        response = f"已添加关注: <code>{prefix}</code>"
        if label:
            response += f" — {label}"
        _send_message(response)
    else:
        _send_message("保存配置失败，请稍后重试。")


def _cmd_rmwatch(msg: dict) -> None:
    """处理 /rmwatch <前缀> 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    text = msg.get("text", "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        _send_message("用法: /rmwatch &lt;前缀&gt;\n\n示例: /rmwatch 2026-085")
        return

    prefix = parts[1].strip().upper()
    watched = _read_watched()
    removed_item = _find_watched_prefix(watched, prefix)

    if removed_item is None:
        _send_message(f"前缀 <code>{prefix}</code> 不在关注列表中。")
        return

    new_watched = [item for item in watched if item is not removed_item]
    if _write_watched(new_watched):
        label = removed_item.get("label", "") if isinstance(removed_item, dict) else ""
        response = f"已移除: <code>{prefix}</code>"
        if label:
            response += f" — {label}"
        _send_message(response)
    else:
        _send_message("保存配置失败，请稍后重试。")


def _cmd_help(msg: dict) -> None:
    """处理 /help 命令"""
    if msg.get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return
    _send_message(_build_help_text())


# ── Inline Keyboard 回调处理 ──

def _is_cb_authorized(cb: dict) -> bool:
    return cb.get("message", {}).get("chat", {}).get("id") == _ALLOWED_CHAT_ID


def _handle_toggle(cb: dict) -> None:
    """处理主菜单 [🔔 总开关] 按钮

    使用服务端原子 toggle 端点，无需读-改-写，杜绝 bot 与前端并发翻转
    时互相覆盖（两次 toggle 理应相消为原值）。
    """
    if not _is_cb_authorized(cb):
        _answer_callback(cb["id"]); return

    # 先应答按钮，用户立刻看到反馈（即使 API 调用尚未返回）
    _answer_callback(cb["id"], "正在切换...")

    new_enabled = _toggle_discovery()
    if new_enabled is None:
        _answer_callback(cb["id"], "切换失败，请重试"); return

    _answer_callback(cb["id"], f"总开关已{'开启' if new_enabled else '关闭'}")

    # 读取状态和配置，刷新键盘
    status = _get_status()
    config = _get_config()
    if status and config:
        nod = config.get("new_object_discovery", {})
        watched_list: list = nod.get("watched_launches", [])
        if not isinstance(watched_list, list):
            watched_list = []
        status["enabled"] = new_enabled
        status["watched_launches_count"] = len(watched_list)
        text = _build_status_text(status)
        keyboard = _build_main_keyboard(new_enabled, len(watched_list))
        m = cb.get("message", {})
        _edit_message_text(
            m.get("chat", {}).get("id", 0), m.get("message_id", 0),
            text, reply_markup=keyboard,
        )


def _handle_watchlist_panel(cb: dict) -> None:
    """处理主菜单 [📋 关注列表] 按钮：切换到关注列表面板"""
    if not _is_cb_authorized(cb):
        _answer_callback(cb["id"]); return
    watched = _read_watched()
    text = _build_watched_text(watched)
    keyboard = _build_watched_keyboard(watched)
    m = cb.get("message", {})
    _edit_message_text(
        m.get("chat", {}).get("id", 0), m.get("message_id", 0),
        text, reply_markup=keyboard,
    )
    _answer_callback(cb["id"])


def _handle_remove(cb: dict, prefix: str) -> None:
    """处理关注列表中的 [🗑] 按钮：直接删除，刷新面板"""
    if not _is_cb_authorized(cb):
        _answer_callback(cb["id"]); return
    watched = _read_watched()
    removed_item = _find_watched_prefix(watched, prefix)
    if removed_item is None:
        _answer_callback(cb["id"], "该前缀已不存在"); return

    new_watched = [item for item in watched if item is not removed_item]
    if not _write_watched(new_watched):
        _answer_callback(cb["id"], "保存失败"); return

    label = removed_item.get("label", "") if isinstance(removed_item, dict) else ""
    toast = f"已移除 {prefix}" + (f" — {label}" if label else "")
    _answer_callback(cb["id"], toast)

    # 刷新列表面板
    text = _build_watched_text(new_watched)
    keyboard = _build_watched_keyboard(new_watched)
    m = cb.get("message", {})
    _edit_message_text(
        m.get("chat", {}).get("id", 0), m.get("message_id", 0),
        text, reply_markup=keyboard,
    )


def _handle_addwatch_button(cb: dict) -> None:
    """处理主菜单 [➕ 添加关注] 按钮：发送 ForceReply 消息"""
    if not _is_cb_authorized(cb):
        _answer_callback(cb["id"]); return
    _answer_callback(cb["id"])
    _send_message(
        f"{_FORCE_REPLY_PROMPT}\n\n"
        "示例: <code>2026-085 Starlink G12-3</code>\n"
        "仅前缀也可以: <code>2026-085</code>",
        reply_markup={"force_reply": True},
    )


def _handle_refresh(cb: dict) -> None:
    """处理 [🔄 刷新状态] / [⬅️ 返回主菜单] 按钮"""
    if not _is_cb_authorized(cb):
        _answer_callback(cb["id"]); return
    status = _get_status()
    if status is None:
        _answer_callback(cb["id"], "无法获取状态"); return
    config = _get_config()
    if config:
        nod = config.get("new_object_discovery", {})
        watched_list: list = nod.get("watched_launches", [])
        if not isinstance(watched_list, list):
            watched_list = []
        status["enabled"] = nod.get("enabled", False)
        status["watched_launches_count"] = len(watched_list)
    else:
        status.setdefault("enabled", False)
        status.setdefault("watched_launches_count", 0)

    text = _build_status_text(status)
    keyboard = _build_main_keyboard(
        status.get("enabled", False),
        status.get("watched_launches_count", 0),
    )
    m = cb.get("message", {})
    _edit_message_text(
        m.get("chat", {}).get("id", 0), m.get("message_id", 0),
        text, reply_markup=keyboard,
    )
    _answer_callback(cb["id"])


# ── ForceReply 处理 ──

def _handle_force_reply(msg: dict) -> bool:
    """检查消息是否为 ForceReply 回复，是则解析并添加关注。
    返回 True 表示已处理（无需再走命令路由）。
    """
    reply_to = msg.get("reply_to_message")
    if not reply_to:
        return False

    # 检查回复的是否为 bot 的 ForceReply 提示消息
    replied_text = reply_to.get("text", "")
    if _FORCE_REPLY_PROMPT not in replied_text:
        return False

    text = msg.get("text", "").strip()
    if not text:
        _send_message("未收到文本，请重新点击 [➕ 添加关注] 再试。")
        return True

    # 解析：第一个空格前为 prefix，之后为 label
    parts = text.split(maxsplit=1)
    prefix = parts[0].strip().upper()
    label = parts[1].strip() if len(parts) > 1 else ""

    if not prefix:
        _send_message("前缀不能为空，请重新点击 [➕ 添加关注] 再试。")
        return True

    watched = _read_watched()
    if _find_watched_prefix(watched, prefix):
        _send_message(f"前缀 <code>{prefix}</code> 已在关注列表中。")
        return True

    new_item: dict = {"intldes_prefix": prefix}
    if label:
        new_item["label"] = label
    watched.append(new_item)

    if _write_watched(watched):
        response = f"已添加关注: <code>{prefix}</code>"
        if label:
            response += f" — {label}"
        _send_message(response)
    else:
        _send_message("保存配置失败，请稍后重试。")

    return True


# ── 消息路由 ──

def _handle_message(msg: dict) -> None:
    """路由消息到对应处理函数"""
    chat = msg.get("chat", {})
    if chat.get("id") != _ALLOWED_CHAT_ID:
        log.info("忽略未授权 chat_id=%s", chat.get("id"))
        return

    # 优先检查 ForceReply 回复
    if _handle_force_reply(msg):
        return

    text = msg.get("text", "").strip()
    if not text:
        return

    if text.startswith("/start"):
        _cmd_start(msg)
    elif text.startswith("/status"):
        _cmd_status(msg)
    elif text.startswith("/watchlist"):
        _cmd_watchlist(msg)
    elif text.startswith("/addwatch"):
        _cmd_addwatch(msg)
    elif text.startswith("/rmwatch"):
        _cmd_rmwatch(msg)
    elif text.startswith("/setapikey"):
        _cmd_set_api_key(msg)
    elif text.startswith("/help"):
        _cmd_help(msg)
    else:
        _send_message("未知命令。使用 /help 查看可用命令。")


def _handle_callback(cb: dict) -> None:
    """路由 Inline Keyboard 回调"""
    if cb.get("message", {}).get("chat", {}).get("id") != _ALLOWED_CHAT_ID:
        return

    data = cb.get("data", "")

    if data == "toggle":
        _handle_toggle(cb)
    elif data == "watchlist":
        _handle_watchlist_panel(cb)
    elif data.startswith("remove:"):
        _handle_remove(cb, data[7:])
    elif data == "addwatch":
        _handle_addwatch_button(cb)
    elif data == "refresh":
        _handle_refresh(cb)


# ── 主循环 ──

def main() -> None:
    if not TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未配置，Bot 无法启动")
        return
    if not _ALLOWED_CHAT_ID:
        log.error("TELEGRAM_CHAT_ID 格式无效: %s", CHAT_ID)
        return

    log.info("Telegram Bot 已启动  chat_id=%d  API=%s", _ALLOWED_CHAT_ID, API_BASE)
    _setup_commands()

    offset = 0
    consecutive_errors = 0

    try:
        _run_loop(offset, consecutive_errors)
    except KeyboardInterrupt:
        log.info("Telegram Bot 已停止")


def _run_loop(offset: int, consecutive_errors: int) -> None:
    while True:
        try:
            resp = _session.get(
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

        time.sleep(1)


if __name__ == "__main__":
    main()
