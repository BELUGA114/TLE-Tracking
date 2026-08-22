"""Telegram Bot HTTP 端点集成测试脚本

验证 REST 接口的读写一致性和输入校验，需要 FastAPI 服务运行。
纯逻辑测试（键盘/状态文本构建、chat_id 授权）已移至 tests/test_telegram_bot_ui.py，
NewObjectWatcher 解析测试已移至 tests/test_new_object_watcher.py。

用法:
    .venv/Scripts/python.exe scripts/test_telegram_bot.py

前置条件:
    uvicorn 在 localhost:8000 运行
    .env 中已配置 DASHBOARD_API_KEY（可选，配置后请求携带 Authorization 头）
"""

from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

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


def test_http_endpoints() -> None:
    """HTTP API 端点：验证 REST 接口的读写一致性和输入校验。"""
    print("\n── HTTP API 端点 ──")

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


def main() -> None:
    print("Telegram Bot HTTP 端点测试")

    if not API_KEY:
        print("警告: DASHBOARD_API_KEY 未配置，请求不带 Authorization 头")

    test_http_endpoints()

    print(f"\n结果: {PASSED} 通过, {FAILED} 失败, {PASSED + FAILED} 总计")
    if FAILED:
        print("有测试失败")
        sys.exit(1)
    else:
        print("全部通过")


if __name__ == "__main__":
    main()
