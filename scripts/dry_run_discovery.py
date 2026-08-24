"""新对象发现干跑测试

用真实的 Space-Track 查询，执行完整去重+过滤流程，但不发 Telegram。
用于验证字段格式和匹配逻辑是否正确。

用法:
    uv run python scripts/dry_run_discovery.py

前置条件:
    .env 中已配置 SPACETRACK_USER / SPACETRACK_PASS
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timezone

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from new_object_watcher import NewObjectWatcher
from spacetrack_monitor import SpaceTrackSession, FetchStatus

SATCAT_DEBUT_URL = (
    "https://www.space-track.org/basicspacedata/query/class/satcat_debut"
    "/OBJECT_TYPE/PAYLOAD"
    "/DEBUT/%3Enow-7"          # 过去 7 天，比 now-1 更宽
    "/orderby/DEBUT asc"
    "/format/json"
)


def main() -> None:
    print("新对象发现干跑测试")
    print("=" * 60)

    # 1. 登录
    st = SpaceTrackSession()
    if not st.ensure_fresh_session():
        print("[错误] Space-Track 登录失败")
        return

    # 2. 查询（过去 7 天）
    print("\n[1] 查询 satcat_debut（过去 7 天）...")
    result = st.get(SATCAT_DEBUT_URL)
    if isinstance(result, FetchStatus):
        print(f"[错误] 查询失败: {result}")
        return

    records = result.json()
    print(f"    返回 {len(records)} 条 PAYLOAD 记录")

    if not records:
        print("    无记录，无法验证。等待下次发射编目后重试。")
        return

    # 3. 打印第一条记录的完整字段
    print(f"\n[2] 第一条记录完整字段:")
    print(json.dumps(records[0], indent=2, ensure_ascii=False))

    # 4. 打印所有记录的概要
    print(f"\n[3] 所有记录概要:")
    print(f"    {'NORAD':<10} {'OBJECT_ID':<14} {'DEBUT':<22} {'NAME'}")
    print(f"    {'-'*10} {'-'*14} {'-'*22} {'-'*20}")
    for rec in records:
        norad = str(rec.get("NORAD_CAT_ID", "?"))
        obj_id = str(rec.get("OBJECT_ID", rec.get("INTLDES", "?")))
        debut = str(rec.get("DEBUT", "?"))
        name = str(rec.get("OBJECT_NAME", "?"))[:25]
        print(f"    {norad:<10} {obj_id:<14} {debut:<22} {name}")

    # 5. 用当前配置跑 _process。数据目录与生产环境一致
    data_dir = os.environ.get("DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    os.makedirs(data_dir, exist_ok=True)
    watcher = NewObjectWatcher({"enabled": True}, data_dir)
    watched_list = list(watcher._watched.keys())
    print(f"\n[4] 当前关注列表: {watched_list if watched_list else '(空)'}")

    # 重置游标，让所有记录都通过去重
    watcher._cursor["last_debut_ts"] = "2020-01-01T00:00:00+00:00"
    matched, unmatched = watcher._process(records)

    print(f"    关注命中: {len(matched)} 条")
    for rec in matched:
        label = rec.get("_matched_label", "")
        label_str = f" — {label}" if label else ""
        print(f"      {rec.get('OBJECT_ID','?')} → {rec.get('OBJECT_NAME','?')}{label_str}")

    print(f"    常规对象: {len(unmatched)} 条")
    if unmatched:
        for rec in unmatched[:5]:
            print(f"      {rec.get('OBJECT_ID','?')} → {rec.get('OBJECT_NAME','?')}")
        if len(unmatched) > 5:
            print(f"      ... 还有 {len(unmatched) - 5} 条")

    # 6. 检查 OBJECT_ID 格式
    print(f"\n[5] OBJECT_ID 格式检查:")
    for rec in records[:10]:
        obj_id = str(rec.get("OBJECT_ID", ""))
        intldes = str(rec.get("INTLDES", ""))
        has_suffix = any(c.isalpha() for c in obj_id)
        print(f"    OBJECT_ID={obj_id!r}  {'含后缀' if has_suffix else '纯编号'}    INTLDES={intldes!r}")

    st.logout()
    print(f"\n{'='*60}")
    print("干跑完成。请确认:")
    print("  1. OBJECT_ID 格式（纯编号 vs 含后缀字母）")
    print("  2. 前缀匹配是否正确（关注列表 vs 实际数据）")
    print("  3. 如有匹配项，label 是否正确传递")


if __name__ == "__main__":
    main()
