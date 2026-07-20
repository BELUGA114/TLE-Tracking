"""新编目对象发现模块

通过 Space-Track satcat_debut API 检测新编目 PAYLOAD 类型航天器，
通过 Telegram Bot 推送通知。

速率限制：1 次/天（SATCAT 数据每天 1700 UTC 更新）
查询谓词：DEBUT/%3Enow-1（Space-Track 官方推荐方式）
游标本地去重：防止重叠查询窗口内重复推送

用法:
    from new_object_watcher import NewObjectWatcher
    watcher = NewObjectWatcher(config, data_dir)
    if watcher.is_due:
        watcher.check(session, notifier)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# satcat_debut 查询 URL 模板
# now-1 模式获取过去约 24 小时的数据，窗口重叠由本地游标去重
SATCAT_DEBUT_URL = (
    "https://www.space-track.org/basicspacedata/query/class/satcat_debut"
    "/OBJECT_TYPE/PAYLOAD"
    "/DEBUT/%3Enow-1"
    "/orderby/DEBUT asc"
    "/format/json"
)

# 游标文件名
CURSOR_FILENAME = "new_object_cursor.json"


def _utc_now() -> datetime:
    """返回当前 UTC 时间（可 mock 的工厂函数）"""
    return datetime.now(timezone.utc)


class NewObjectWatcher:
    """新编目对象检测器。

    每次 .check() 查询 satcat_debut 过去 ~24h 数据，
    通过游标去重后，按过滤规则通过 TelegramNotifier 推送。
    """

    def __init__(self, config: dict, data_dir: str) -> None:
        """
        Args:
            config: config.yaml 中 new_object_discovery 段的 dict，
                    缺失时使用默认值（enabled=False）
            data_dir: 数据文件目录，游标文件保存于此
        """
        self._enabled = bool(config.get("enabled", False))
        self._schedule_hour = int(config.get("schedule_hour", 17))
        self._schedule_minute = int(config.get("schedule_minute", 10))
        self._backtrack_hours = int(config.get("backtrack_hours", 72))
        self._daily_summary = bool(config.get("daily_summary", False))

        # 关注列表：prefix → label 映射。兼容旧 list[str] 和新 list[dict] 两种格式
        raw_watched = config.get("watched_launches", [])
        self._watched: dict[str, str] = {}
        if isinstance(raw_watched, list):
            for item in raw_watched:
                if isinstance(item, str):
                    prefix = item.strip().upper()
                    if prefix:
                        self._watched[prefix] = ""
                elif isinstance(item, dict):
                    prefix = str(item.get("intldes_prefix", "")).strip().upper()
                    if prefix:
                        label = str(item.get("label", "")).strip()
                        self._watched[prefix] = label

        self._cursor_path = os.path.join(data_dir, CURSOR_FILENAME)
        # 确保目录存在——Docker 下 /data 由 volume mount 创建，其他场景可能不存在
        os.makedirs(data_dir, exist_ok=True)
        self._last_check_date: str = ""  # ISO date (YYYY-MM-DD)，当天已检查过则跳过

        # 加载或初始化游标
        self._cursor: dict = self._load_cursor()

        # 从游标直接恢复上次检查日期，进程重启后当天不再重复请求
        self._last_check_date = self._cursor.get("last_check_date", "")

        if self._enabled:
            log.info(
                "新对象发现已启用  调度: %02d:%02d UTC  关注列表: %d 个前缀",
                self._schedule_hour,
                self._schedule_minute,
                len(self._watched),
            )
        else:
            log.debug("新对象发现未启用")

    # 游标文件的加载与原子写入，防止进程崩溃导致游标丢失或重复推送

    def _load_cursor(self) -> dict:
        """加载游标文件，文件不存在或损坏时返回默认值（从当前时刻开始）"""
        try:
            with open(self._cursor_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            log.info("游标文件 %s 不存在，将从当前时刻开始", self._cursor_path)
            return self._default_cursor()
        except (OSError, json.JSONDecodeError) as e:
            log.warning("游标文件读取失败或损坏，将从当前时刻开始: %s", e)
            return self._default_cursor()

        if not isinstance(data, dict):
            log.warning("游标文件格式异常，将从当前时刻开始")
            return self._default_cursor()

        # 验证 last_debut_ts 是否为合法 ISO 8601 字符串
        last_debut = data.get("last_debut_ts")
        if isinstance(last_debut, str):
            try:
                datetime.fromisoformat(last_debut)
            except ValueError:
                log.warning("游标时间戳格式异常 (%s)，将从当前时刻开始", last_debut)
                return self._default_cursor()

        # 补全缺失字段
        data.setdefault("last_debut_ts", _utc_now().isoformat())
        data.setdefault("last_check_ts", _utc_now().isoformat())
        data.setdefault("total_processed", 0)
        return data

    @staticmethod
    def _default_cursor() -> dict:
        now = _utc_now()
        return {
            # last_debut_ts=now 确保首次查询不推送历史数据（DEBUT > now 无记录）
            # last_check_date="" 确保首次 is_due 不跳过当天（"" != today）
            "last_debut_ts": now.isoformat(),
            "last_check_date": "",
            "last_check_ts": now.isoformat(),
            "total_processed": 0,
        }

    def _save_cursor(self) -> None:
        """原子写入游标文件（fsync + os.replace 防止半写）"""
        tmp = self._cursor_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._cursor, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._cursor_path)
        except OSError as e:
            log.warning("游标文件写入失败: %s", e)
            # 清理临时文件
            try:
                os.remove(tmp)
            except OSError:
                pass

    # 每天只检查一次，避免重复查询 satcat_debut API（速率限制 1次/天）

    @property
    def is_enabled(self) -> bool:
        """总开关是否启用"""
        return self._enabled

    @property
    def is_due(self) -> bool:
        """今天是否已到检查时间且尚未检查过。

        判断逻辑：
        1. 未启用 → 永远 False
        2. 当前 UTC 时间已过今天的 schedule 时刻
        3. 且今天的日期 != 上次检查日期
        """
        if not self._enabled:
            return False

        now = _utc_now()
        today_str = now.strftime("%Y-%m-%d")

        # 同一天不重复检查
        if today_str == self._last_check_date:
            return False

        # 检查当前时间是否已过调度时刻
        schedule_minutes = self._schedule_hour * 60 + self._schedule_minute
        now_minutes = now.hour * 60 + now.minute
        if now_minutes < schedule_minutes:
            return False

        return True

    # 通过已登录的 SpaceTrackSession 查询 satcat_debut，返回原始记录列表

    def _query_debut(self, session) -> list[dict] | None:
        """查询 satcat_debut API，返回记录列表。失败返回 None。

        session 为 SpaceTrackSession 实例（需已登录）。
        """
        log.debug("查询 satcat_debut")
        result = session.get(SATCAT_DEBUT_URL)

        # session.get 可能返回 FetchStatus 枚举或 requests.Response
        # 延迟导入避免循环依赖（此模块被 spacetrack_monitor 导入）
        from spacetrack_monitor import FetchStatus

        if isinstance(result, FetchStatus):
            log.warning("satcat_debut 查询失败 (FetchStatus): %s", result)
            return None

        try:
            data = result.json()
        except ValueError as e:
            log.warning("satcat_debut JSON 解析失败: %s (body前200字: %s)", e, result.text[:200])
            return None

        log.debug("satcat_debut 返回 %d 条记录", len(data))
        log.debug("satcat_debut 原始响应: %s", json.dumps(data, ensure_ascii=False))
        return data

    # 按 DEBUT 时间戳去重（游标之前的不推送），按 watched_launches 列表分拣

    def _process(self, records: list[dict]) -> tuple[list[dict], list[dict]]:
        """去重 + 过滤，返回 (matched, unmatched) 两个列表。

        matched: 命中 watched_launches 的记录
        unmatched: 未命中 watched_launches 的记录

        去重依据：DEBUT > last_debut_ts（游标值）
        INTLDES 匹配：优先用 OBJECT_ID，为空时回退 INTLDES
        """
        last_ts_str = self._cursor.get("last_debut_ts", "")
        try:
            last_ts = datetime.fromisoformat(last_ts_str)
        except (ValueError, TypeError):
            last_ts = _utc_now()

        matched: list[dict] = []
        unmatched: list[dict] = []
        newest_ts = last_ts  # 记录本批次最新的 DEBUT 时间

        for rec in records:
            # 解析 DEBUT 时间。Space-Track 返回格式为 "2026-07-07 17:33:19"（无时区）
            debut_str = str(rec.get("DEBUT", ""))
            try:
                debut_ts = datetime.fromisoformat(debut_str)
            except ValueError:
                debut_ts = None
            if debut_ts is None:
                try:
                    debut_ts = datetime.strptime(debut_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    log.debug("无法解析 DEBUT 时间: %s，跳过", debut_str)
                    continue
            # fromisoformat 对空格分隔的字符串可能返回不带时区的 datetime，统一补 UTC
            if debut_ts.tzinfo is None:
                debut_ts = debut_ts.replace(tzinfo=timezone.utc)

            # 去重：DEBUT 不晚于游标时间 → 跳过
            if debut_ts <= last_ts:
                continue

            # 更新最新时间戳
            if debut_ts > newest_ts:
                newest_ts = debut_ts

            # 获取国际编号：优先 OBJECT_ID，回退 INTLDES
            intldes = str(rec.get("OBJECT_ID") or rec.get("INTLDES") or "").strip().upper()

            # startswith 匹配：关注 "2026-085" 命中 "2026-085A"/"2026-085B"
            # 按 key 长度降序遍历，长前缀优先（防止 "2026-08" 误匹配 "2026-085A"）
            matched_prefix = ""
            for prefix in sorted(self._watched.keys(), key=len, reverse=True):
                if intldes.startswith(prefix):
                    matched_prefix = prefix
                    break
            if matched_prefix:
                rec["_matched_label"] = self._watched[matched_prefix]
                matched.append(rec)
            else:
                unmatched.append(rec)

        # 更新游标
        if newest_ts > last_ts:
            self._cursor["last_debut_ts"] = newest_ts.isoformat()

        return matched, unmatched

    # 每次调用执行完整的检查-去重-过滤-推送流程，返回实际推送的消息数

    def check(self, session, notifier, write_log_fn=None) -> int:
        """执行一次完整的检查-去重-过滤-推送流程。

        Args:
            session: 已登录的 SpaceTrackSession 实例
            notifier: TelegramNotifier 实例
            write_log_fn: 可选，写入运行日志的回调函数（签名: fn(message: str) -> None）

        Returns:
            推送的消息数量（0 表示无新对象或全部失败）
        """
        if not self._enabled:
            return 0

        now = _utc_now()

        # 回溯窗口检查：必须在覆盖 last_check_ts 之前读取旧值
        old_last_check_ts = self._cursor.get("last_check_ts", now.isoformat())
        self._last_check_date = now.strftime("%Y-%m-%d")
        self._cursor["last_check_date"] = self._last_check_date
        self._cursor["last_check_ts"] = now.isoformat()

        # 立即持久化"今天已检查"，防止进程在后续网络请求中崩溃导致重启后重复查询
        # satcat_debut 速率限制 1次/天，重复请求可能导致封号
        self._save_cursor()

        try:
            last_check = datetime.fromisoformat(old_last_check_ts)
        except (ValueError, TypeError):
            last_check = now
        hours_since = (now - last_check).total_seconds() / 3600

        backtrack_note = ""
        if hours_since > self._backtrack_hours:
            backtrack_note = (
                f"上次检查于 {last_check.strftime('%m-%d %H:%M')} UTC，"
                f"距今 {hours_since:.0f} 小时。可能遗漏此期间编目事件。"
            )
            log.warning("新对象发现回溯超限: %s", backtrack_note)

        # 查询
        records = self._query_debut(session)
        if records is None:
            self._save_cursor()
            return 0

        # 去重 + 过滤
        matched, unmatched = self._process(records)

        total_new = len(matched) + len(unmatched)
        pushed = 0

        # 如果没有任何新对象
        if total_new == 0:
            if self._daily_summary and notifier.active:
                notifier.send_summary(0)
                pushed = 1
            msg = f"[新对象发现] {now.strftime('%Y-%m-%d')} 无新 PAYLOAD 编目"
            log.info(msg)
            if write_log_fn:
                write_log_fn(msg)
            self._save_cursor()
            return pushed

        # 汇总日志
        msg = (
            f"[新对象发现] {now.strftime('%Y-%m-%d')} "
            f"发现 {total_new} 个新 PAYLOAD（关注: {len(matched)}, 常规: {len(unmatched)}）"
        )
        log.info(msg)
        if write_log_fn:
            write_log_fn(msg)

        if backtrack_note and notifier.active:
            notifier.send_summary(total_new, note=backtrack_note)
            pushed += 1

        # 推送：命中关注列表的优先
        for rec in matched:
            label = rec.get("_matched_label", "")
            rec.pop("_matched_label", None)
            if notifier.send_debut(rec, watched=True, label=label):
                pushed += 1
                if write_log_fn:
                    label_suffix = f" — {label}" if label else ""
                    write_log_fn(
                        f"[新对象发现] 已推送（关注{label_suffix}）: NORAD {rec.get('NORAD_CAT_ID')} "
                        f"{rec.get('OBJECT_NAME', '?')} ({rec.get('OBJECT_ID', '?')})"
                    )
            time.sleep(0.5)  # Telegram 限流保护

        for i, rec in enumerate(unmatched):
            if notifier.send_debut(rec, watched=False):
                pushed += 1
                if write_log_fn:
                    write_log_fn(
                        f"[新对象发现] 已推送: NORAD {rec.get('NORAD_CAT_ID')} "
                        f"{rec.get('OBJECT_NAME', '?')} ({rec.get('OBJECT_ID', '?')})"
                    )
            # burst 限流：每 5 条暂停 2 秒
            if (i + 1) % 5 == 0 and i + 1 < len(unmatched):
                time.sleep(2)
            else:
                time.sleep(0.5)

        self._cursor["total_processed"] += total_new
        self._save_cursor()

        msg_end = f"[新对象发现] 本轮推送完成，共 {pushed} 条消息"
        log.info(msg_end)
        if write_log_fn:
            write_log_fn(msg_end)

        return pushed
