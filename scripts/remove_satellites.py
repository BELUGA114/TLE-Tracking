"""按 NORAD ID 删除 tle_data.jsonl 中的卫星数据。

用法:
    python scripts/remove_satellites.py 25544 44713 44714

    # --dry-run 仅预览，不实际写入
    python scripts/remove_satellites.py --dry-run 25544

    如果 .venv 未激活，用 .venv/bin/python (Linux) 或 .venv\Scripts\python.exe (Windows)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(norad_ids: set[int], *, dry_run: bool = False) -> None:
    data_path = Path(__file__).resolve().parent.parent / "data" / "tle_data.jsonl"

    if not data_path.exists():
        print(f"文件不存在: {data_path}")
        sys.exit(1)

    kept: list[str] = []
    removed_count = 0
    total = 0

    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if record.get("norad") in norad_ids:
                removed_count += 1
            else:
                kept.append(line)

    if dry_run:
        print(f"总行数: {total}")
        print(f"将删除: {removed_count} 行")
        print(f"保留: {len(kept)} 行")
        for nid in norad_ids:
            print(f"  NORAD {nid}")
        return

    with open(data_path, "w", encoding="utf-8") as f:
        for line in kept:
            f.write(line + "\n")

    print(f"完成: {total} -> {len(kept)} 行, 删除 {removed_count} 行")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="按 NORAD ID 删除 TLE 数据")
    parser.add_argument("norad_ids", nargs="+", type=int, help="要删除的 NORAD ID")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际写入")
    args = parser.parse_args()

    main(set(args.norad_ids), dry_run=args.dry_run)
