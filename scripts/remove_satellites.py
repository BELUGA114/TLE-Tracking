r"""按 NORAD ID 删除 tle_data.jsonl 中的卫星数据。

用法:
    python remove_satellites.py -f /path/to/tle_data.jsonl 25544 44713
    python remove_satellites.py --dry-run -f /path/to/tle_data.jsonl 25544

    不指定 -f 时，默认使用脚本所在项目目录下的 data/tle_data.jsonl。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def default_data_path() -> Path:
    """返回脚本所在项目的 data/tle_data.jsonl 默认路径。"""
    return Path(__file__).resolve().parent.parent / "data" / "tle_data.jsonl"


def main(norad_ids: set[int], file_path: str, *, dry_run: bool = False) -> None:
    data_path = Path(file_path)

    if not data_path.exists():
        print(f"[错误] 文件不存在: {data_path}")
        sys.exit(1)
    if data_path.is_dir():
        print(f"[错误] 路径是目录，需要指定到文件: {data_path}")
        sys.exit(1)

    kept: list[str] = []
    removed_count = 0
    total = 0
    matched_ids: set[int] = set()

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
                matched_ids.add(record["norad"])
            else:
                kept.append(line)

    if dry_run:
        print(f"文件: {data_path}")
        print(f"总行数: {total}")
        print(f"将删除: {removed_count} 行")
        print(f"保留: {len(kept)} 行")
        for nid in sorted(norad_ids):
            status = "[匹配]" if nid in matched_ids else "[无数据]"
            print(f"  NORAD {nid} {status}")
        return

    with open(data_path, "w", encoding="utf-8") as f:
        for line in kept:
            f.write(line + "\n")

    print(f"完成: {total} -> {len(kept)} 行, 删除 {removed_count} 行")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="按 NORAD ID 删除 TLE 数据 (JSONL 格式)"
    )
    parser.add_argument(
        "-f", "--file",
        default=str(default_data_path()),
        help=f"TLE 数据文件路径 (默认: {default_data_path()})",
    )
    parser.add_argument("norad_ids", nargs="+", type=int, help="要删除的 NORAD ID")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际写入")
    args = parser.parse_args()

    main(set(args.norad_ids), args.file, dry_run=args.dry_run)
