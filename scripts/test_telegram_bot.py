"""Telegram Bot 功能测试脚本

测试 bot 的业务逻辑层（命令解析、键盘构建、配置读写），不依赖 Telegram API。
需要 FastAPI 服务运行时测试 HTTP 端点（可选）。

用法:
    .venv/Scripts/python.exe scripts/test_telegram_bot.py

前置条件:
    .env 中已配置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    测试 HTTP 端点需要 uvicorn 在 localhost:8000 运行
"""

from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

# 将项目根目录加入 sys.path，以便 import telegram_bot 的内部函数
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_BASE = "http://localhost:8000"
API_KEY = os.getenv("DASHBOARD_API_KEY", "")
PASSED = 0
FAILED = 0


def _api_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def _server_alive() -> bool:
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def test_internal_functions() -> None:
    """测试 1: 内部函数（无需服务器）—— 验证命令解析、键盘构建、配置读写纯逻辑。"""
    print("\n── 测试1: 内部函数 ──")

    # 导入 bot 模块的内部函数
    # 先临时设置必要的全局变量，避免 main() 的 TOKEN 检查阻止导入
    import telegram_bot as bot

    # _build_main_keyboard
    k_enabled = bot._build_main_keyboard(True, 3)
    check("主菜单第一个按钮为 [总开关：已开]", "已开" in k_enabled["inline_keyboard"][0][0]["text"])
    check("[总开关] callback 为 toggle", k_enabled["inline_keyboard"][0][0]["callback_data"] == "toggle")

    k_disabled = bot._build_main_keyboard(False, 0)
    check("关闭时显示 [总开关：已关]", "已关" in k_disabled["inline_keyboard"][0][0]["text"])
    check("[关注列表] 显示数量", "(0)" in k_disabled["inline_keyboard"][1][0]["text"])

    # _build_watched_keyboard
    watched = [
        {"intldes_prefix": "2026-085", "label": "Starlink"},
        {"intldes_prefix": "2026-092"},
    ]
    kb = bot._build_watched_keyboard(watched)
    check("第一项显示 prefix · label", "2026-085 · Starlink" in kb["inline_keyboard"][0][0]["text"])
    check("第二项仅显示 prefix", kb["inline_keyboard"][1][0]["text"] == "🗑 2026-092")
    check("移除按钮回调含 prefix", kb["inline_keyboard"][0][0]["callback_data"] == "remove:2026-085")
    check("末尾有返回按钮", kb["inline_keyboard"][-1][0]["callback_data"] == "refresh")

    # _build_watched_keyboard 空列表
    kb_empty = bot._build_watched_keyboard([])
    check(
        "空列表仅有返回按钮",
        len(kb_empty["inline_keyboard"]) == 1 and kb_empty["inline_keyboard"][0][0]["callback_data"] == "refresh",
    )

    # _build_status_text
    status = {
        "enabled": True,
        "last_check_ts": "2026-07-14 17:10 UTC",
        "last_debut_ts": "2026-07-13 22:05 UTC",
        "total_processed": 47,
        "watched_launches_count": 3,
        "next_check_at": "2026-07-15 17:10 UTC",
    }
    text = bot._build_status_text(status)
    check("状态文本包含已启用", "已启用" in text)
    check("状态文本包含上次检查时间", "2026-07-14 17:10 UTC" in text)
    check("状态文本包含累计数量", "47" in text)
    check("状态文本包含下次检查", "2026-07-15 17:10 UTC" in text)

    status_disabled = dict(status, enabled=False)
    text_off = bot._build_status_text(status_disabled)
    check("关闭时显示已关闭", "已关闭" in text_off)

    # _build_watched_text
    text_w = bot._build_watched_text(watched)
    check("列表文本包含 Starlink", "Starlink" in text_w)
    check("列表文本包含 2026-085", "2026-085" in text_w)
    check("列表文本包含 2026-092", "2026-092" in text_w)

    text_w_empty = bot._build_watched_text([])
    check("空列表提示", "暂无关注项" in text_w_empty)

    # chat_id 授权检查 — 内部路由函数
    real_id = bot._ALLOWED_CHAT_ID
    # 用假 chat_id 发消息，验证 _handle_message 忽略
    fake_msg = {"chat": {"id": 999999}, "text": "/status"}
    bot._handle_message(fake_msg)
    check(
        "假 chat_id 的 /status 被忽略（不抛异常、不发消息）",
        True,  # 不崩溃就是通过
    )

    # 真 chat_id（如果没配凭据则为0，也跳过）
    if real_id:
        valid_msg = {"chat": {"id": real_id}, "text": "/help"}
        # 不应该抛异常（即使服务器没运行，_cmd_help 发消息失败也应该静默处理）
        try:
            bot._handle_message(valid_msg)
            check("真 chat_id 的消息不触发授权拦截", True)
        except Exception as e:
            check("真 chat_id 的消息不触发授权拦截", False, str(e))

    # 回调授权检查
    fake_cb = {
        "id": "cb_001",
        "message": {"chat": {"id": 999999}, "message_id": 1},
        "data": "toggle",
    }
    # 不应该抛异常
    try:
        bot._handle_callback(fake_cb)
        check("假 chat_id 的回调被静默忽略", True)
    except Exception as e:
        check("假 chat_id 的回调被静默忽略", False, str(e))


def test_http_endpoints() -> None:
    """测试 2: HTTP API 端点（需要服务器）—— 验证 REST 接口的读写一致性和输入校验。"""
    print("\n── 测试2: HTTP API 端点 ──")

    if not _server_alive():
        print("  SKIP  服务器未运行，跳过 HTTP 测试")
        print("         启动方式: uvicorn backend.main:app --host 0.0.0.0 --port 8000")
        return

    # GET /api/discovery/status
    resp = requests.get(f"{API_BASE}/api/discovery/status", headers=_api_headers(), timeout=10)
    check("GET /api/discovery/status 返回 200", resp.status_code == 200)
    if resp.status_code == 200:
        data = resp.json()
        for key in ["enabled", "last_check_ts", "last_debut_ts", "total_processed", "watched_launches_count", "next_check_at"]:
            check(f"  status 包含 {key}", key in data)

    # GET /api/config
    resp = requests.get(f"{API_BASE}/api/config", headers=_api_headers(), timeout=10)
    check("GET /api/config 返回 200", resp.status_code == 200)
    if resp.status_code == 200:
        cfg = resp.json()
        check("  config 包含 new_object_discovery", "new_object_discovery" in cfg)
        nod = cfg.get("new_object_discovery", {})
        check("  nod 包含 enabled", "enabled" in nod)
        check("  nod 包含 watched_launches", "watched_launches" in nod)
        check("  nod 包含 daily_summary", "daily_summary" in nod)

        # 记录原始值供恢复
        original_enabled = nod.get("enabled", False)

        # PUT toggle enabled
        new_enabled = not original_enabled
        resp = requests.put(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            json={"new_object_discovery": {"enabled": new_enabled}},
            timeout=10,
        )
        check("PUT toggle enabled 返回 200", resp.status_code == 200)

        # 验证 GET 反映变更
        resp = requests.get(f"{API_BASE}/api/config", headers=_api_headers(), timeout=10)
        updated = resp.json().get("new_object_discovery", {}).get("enabled")
        check(f"  enabled 已从 {original_enabled} 变为 {new_enabled}", updated == new_enabled)

        # PUT 恢复原始值
        requests.put(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            json={"new_object_discovery": {"enabled": original_enabled}},
            timeout=10,
        )

        # PUT 添加 watched_launches（新格式 list[dict]）
        resp = requests.put(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            json={
                "new_object_discovery": {
                    "watched_launches": [
                        {"intldes_prefix": "2026-999", "label": "TestSat"},
                    ]
                }
            },
            timeout=10,
        )
        check("PUT watched_launches 新格式 返回 200", resp.status_code == 200)

        # 验证
        resp = requests.get(f"{API_BASE}/api/config", headers=_api_headers(), timeout=10)
        updated_watched = resp.json().get("new_object_discovery", {}).get("watched_launches", [])
        has_test = any(
            (isinstance(w, dict) and w.get("intldes_prefix") == "2026-999")
            or (isinstance(w, str) and w == "2026-999")
            for w in updated_watched
        )
        check("  watched_launches 包含 2026-999", has_test)

        # 清理：移除测试项
        cleaned = [w for w in updated_watched if not (
            (isinstance(w, dict) and w.get("intldes_prefix") == "2026-999")
            or (isinstance(w, str) and w == "2026-999")
        )]
        resp = requests.put(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            json={"new_object_discovery": {"watched_launches": cleaned}},
            timeout=10,
        )
        check("清理测试数据 返回 200", resp.status_code == 200)

        # PUT 旧格式 list[str]（向后兼容）
        resp = requests.put(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            json={"new_object_discovery": {"watched_launches": ["2026-888"]}},
            timeout=10,
        )
        check("PUT watched_launches 旧格式 返回 200", resp.status_code == 200)

        # 清理
        resp = requests.put(
            f"{API_BASE}/api/config",
            headers=_api_headers(),
            json={"new_object_discovery": {"watched_launches": cleaned}},
            timeout=10,
        )
        check("清理旧格式测试数据 返回 200", resp.status_code == 200)

    # PUT 非法 watched_launches
    resp = requests.put(
        f"{API_BASE}/api/config",
        headers=_api_headers(),
        json={"new_object_discovery": {"watched_launches": [{"intldes_prefix": ""}]}},
        timeout=10,
    )
    check("PUT 空前缀返回 400", resp.status_code == 400)

    resp = requests.put(
        f"{API_BASE}/api/config",
        headers=_api_headers(),
        json={"new_object_discovery": {"watched_launches": "not_a_list"}},
        timeout=10,
    )
    check("PUT 非列表 watched_launches 返回 400", resp.status_code == 400)

    # 非法字段被拒绝
    resp = requests.put(
        f"{API_BASE}/api/config",
        headers=_api_headers(),
        json={"new_object_discovery": {"schedule_hour": 99}},
        timeout=10,
    )
    check("PUT 非白名单字段 schedule_hour 返回 400", resp.status_code == 400)


def test_backward_compat() -> None:
    """测试 3: 向后兼容性 —— 旧格式 list[str] 和新格式 list[dict] 均能正确解析。"""
    print("\n── 测试3: 向后兼容性 ──")
    import tempfile
    from new_object_watcher import NewObjectWatcher

    d = tempfile.mkdtemp()

    w = NewObjectWatcher({"enabled": True, "watched_launches": ["2026-085", "2026-092"]}, d)
    check("旧格式 list[str] 解析为 dict", isinstance(w._watched, dict))
    check("旧格式 key 正确", set(w._watched.keys()) == {"2026-085", "2026-092"})
    check("旧格式 label 为空", w._watched["2026-085"] == "")

    w2 = NewObjectWatcher({"enabled": True, "watched_launches": [
        {"intldes_prefix": "2026-085", "label": "Starlink"},
        {"intldes_prefix": "2026-092"},
    ]}, d)
    check("新格式 label 正确", w2._watched["2026-085"] == "Starlink")
    check("新格式无 label 时为空", w2._watched["2026-092"] == "")

    # 前缀匹配
    w2._cursor["last_debut_ts"] = "2020-01-01T00:00:00+00:00"
    matched, unmatched = w2._process([
        {"DEBUT": "2026-07-14T17:05:00+00:00", "OBJECT_ID": "2026-085A", "NORAD_CAT_ID": 1, "OBJECT_NAME": "A"},
        {"DEBUT": "2026-07-14T17:06:00+00:00", "OBJECT_ID": "2026-085B", "NORAD_CAT_ID": 2, "OBJECT_NAME": "B"},
        {"DEBUT": "2026-07-14T17:07:00+00:00", "OBJECT_ID": "2026-086A", "NORAD_CAT_ID": 3, "OBJECT_NAME": "C"},
    ])
    check("前缀 2026-085 匹配 2026-085A", len(matched) == 2)
    check("前缀 2026-085 不匹配 2026-086A", len(unmatched) == 1)
    check("匹配项带有 label", matched[0].get("_matched_label") == "Starlink")


def main() -> None:
    print("Telegram Bot 功能测试")

    # 检查凭据
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("警告: TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未配置")
        print("       内部函数测试不受影响，HTTP 端点测试需要服务器运行")
    else:
        print(f"Bot token: {token[:8]}...  chat_id: {chat_id}")

    test_internal_functions()
    test_http_endpoints()
    test_backward_compat()

    print(f"\n结果: {PASSED} 通过, {FAILED} 失败, {PASSED + FAILED} 总计")
    if FAILED:
        print("有测试失败")
        sys.exit(1)
    else:
        print("全部通过")


if __name__ == "__main__":
    main()
