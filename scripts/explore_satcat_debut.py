"""验证 satcat_debut API schema — modeldef 自省 + 实际查询

用法:
    uv run python scripts/explore_satcat_debut.py

前置条件:
    .env 中已配置 SPACETRACK_USER / SPACETRACK_PASS
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv("SPACETRACK_USER")
PASSWORD = os.getenv("SPACETRACK_PASS")

BASE_URL = "https://www.space-track.org"
LOGIN_URL = f"{BASE_URL}/ajaxauth/login"
LOGOUT_URL = f"{BASE_URL}/ajaxauth/logout"


def login() -> requests.Session | None:
    """登录 Space-Track，返回已认证的 Session"""
    session = requests.Session()
    try:
        resp = session.post(
            LOGIN_URL,
            data={"identity": USERNAME, "password": PASSWORD},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"[错误] 登录网络错误: {e}")
        return None

    if resp.status_code != 200:
        print(f"[错误] 登录失败 HTTP {resp.status_code}")
        return None

    if "chocolatechip" not in session.cookies:
        print("[错误] 登录失败：未获取到认证 cookie")
        return None

    print("[OK] 登录成功")
    return session


def check_modeldef(session: requests.Session) -> None:
    """通过 modeldef 自省获取 satcat_debut 的完整字段 schema"""
    url = f"{BASE_URL}/basicspacedata/modeldef/class/satcat_debut/format/json"
    print(f"\n{'='*60}")
    print("查询 modeldef schema...")
    print(f"URL: {url}")

    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        print(f"[错误] modeldef 请求失败: {e}")
        return

    if resp.status_code != 200:
        print(f"[警告] modeldef 返回 HTTP {resp.status_code}")
        print(f"响应: {resp.text[:500]}")
        return

    data = resp.json()
    print(f"[OK] modeldef 返回 {len(data)} 个字段定义")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def check_actual_data(session: requests.Session) -> None:
    """实际查询最近 24h 的 satcat_debut 数据，验证字段名和值格式"""
    url = (
        f"{BASE_URL}/basicspacedata/query/class/satcat_debut"
        "/OBJECT_TYPE/PAYLOAD"
        "/DEBUT/%3Enow-1"
        "/orderby/DEBUT asc"
        "/limit/5"
        "/format/json"
    )
    print(f"\n{'='*60}")
    print("查询实际数据（最近 24h，限 5 条）...")
    print(f"URL: {url}")

    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        print(f"[错误] 查询请求失败: {e}")
        return

    if resp.status_code != 200:
        print(f"[错误] 查询返回 HTTP {resp.status_code}")
        print(f"响应: {resp.text[:500]}")
        return

    data = resp.json()
    print(f"[OK] 查询成功，返回 {len(data)} 条记录")

    if not data:
        print("[信息] 过去 24h 无新编目 PAYLOAD")
        return

    # 打印第一条记录的所有字段，用于验证
    print("\n第一条记录的全部字段:")
    print(json.dumps(data[0], indent=2, ensure_ascii=False))

    # 重点关注的字段
    first = data[0]
    print("\n关键字段验证:")
    for key in ["NORAD_CAT_ID", "OBJECT_NAME", "OBJECT_ID", "OBJECT_TYPE", "DEBUT", "COUNTRY"]:
        value = first.get(key, "<缺失>")
        print(f"  {key}: {value}")

    # 验证 DEBUT 日期格式
    debut_val = first.get("DEBUT", "")
    if debut_val:
        print(f"\nDEBUT 原始值: {debut_val!r}")
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                # 本脚本的目的正是探测 naive 格式能否解析，故忽略 DTZ007
                parsed = datetime.strptime(str(debut_val), fmt)  # noqa: DTZ007
                print(f"  → 可解析为 {fmt}: {parsed}")
            except ValueError:
                pass

    # 验证 INTLDES 格式（是否含后缀字母）
    intldes_val = first.get("OBJECT_ID", "")
    print(f"\nINTLDES (OBJECT_ID) 原始值: {intldes_val!r}")
    has_alpha = intldes_val and any(c.isalpha() for c in str(intldes_val))
    print(f"  格式: {'含后缀字母' if has_alpha else '纯发射编号'}")


def main() -> None:
    if not USERNAME or not PASSWORD:
        print("[错误] .env 中未找到 SPACETRACK_USER / SPACETRACK_PASS")
        sys.exit(1)

    session = login()
    if session is None:
        sys.exit(1)

    try:
        check_modeldef(session)
        check_actual_data(session)
    finally:
        # 登出属于收尾动作，失败不影响脚本结论
        with contextlib.suppress(requests.RequestException):
            session.get(LOGOUT_URL, timeout=10)
        session.close()

    print(f"\n{'='*60}")
    print("侦查完成。请根据上述输出确认字段名后继续实现。")
    print("重点关注：")
    print("  1. DEBUT 字段名是否确认为 'DEBUT'")
    print("  2. DEBUT 日期格式")
    print("  3. OBJECT_ID 是否只含发射编号，还是带后缀字母")
    print("  4. OBJECT_TYPE 枚举值拼写（是否确认为 'PAYLOAD')")


if __name__ == "__main__":
    main()


"""
真实返回:
{
  "INTLDES": "2026-150E",
  "NORAD_CAT_ID": "69743",
  "OBJECT_TYPE": "PAYLOAD",
  "SATNAME": "STARLINK-38087",
  "DEBUT": "2026-07-07 17:33:19",
  "COUNTRY": "US",
  "LAUNCH": "2026-07-02",
  "SITE": "AFWTR",
  "DECAY": null,
  "PERIOD": null,
  "INCLINATION": null,
  "APOGEE": null,
  "PERIGEE": null,
  "COMMENT": null,
  "COMMENTCODE": null,
  "RCSVALUE": "0",
  "RCS_SIZE": "LARGE",
  "FILE": "9537",
  "LAUNCH_YEAR": "2026",
  "LAUNCH_NUM": "150",
  "LAUNCH_PIECE": "E",
  "CURRENT": "Y",
  "OBJECT_NAME": "STARLINK-38087",
  "OBJECT_ID": "2026-150E",
  "OBJECT_NUMBER": "69743"
}
"""
