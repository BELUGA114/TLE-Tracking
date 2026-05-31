#!/usr/bin/env python3
"""
Space-Track.org TLE 轨道监控脚本

脚本严格遵守 Space-Track API 使用规范

功能：
- 监控单颗或多颗卫星的 TLE 更新
- 自动检测轨道变化（基于哈希比对）
- 输出轨道参数变化（近地点 / 远地点等）
- 附带一个极其简化的再入时间估算（仅供参考）

"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

import requests
import yaml

# CelesTrak 拉取模块（可选，主源为 celestrak 时启用）
if TYPE_CHECKING:
    import celestrak_fetcher as ct

try:
    import celestrak_fetcher as ct
    _CT_MODULE_OK = True
except ImportError:
    _CT_MODULE_OK = False

# 初始化日志系统（必须在配置加载之前）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

load_dotenv()

# 密钥（来自 .env）
USERNAME = os.getenv("SPACETRACK_USER")
PASSWORD = os.getenv("SPACETRACK_PASS")

# 业务配置（来自 config.yaml）

# 配置文件路径（由 _load_config() 解析后保存，供热重载使用）
_CONFIG_PATH: str = ""


def _load_config() -> dict:
    """加载 YAML 配置文件，文件不存在时返回空 dict（全部使用默认值）。

    查找优先级：
      1. CONFIG_PATH 环境变量指定的完整路径
      2. 当前工作目录下的 config.yaml（Docker 挂载场景）
      3. 脚本所在目录下的 config.yaml（本地开发场景）
    """
    global _CONFIG_PATH

    candidates = []
    env_path = os.environ.get("CONFIG_PATH")
    if env_path:
        candidates.append(("CONFIG_PATH", env_path))
    candidates.append(("CWD", os.path.join(os.getcwd(), "config.yaml")))
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(("script dir", os.path.join(script_dir, "config.yaml")))

    for source, path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            logging.getLogger(__name__).debug("已加载配置文件(%s):%s", source, path)
            _CONFIG_PATH = path
            return cfg
        except FileNotFoundError:
            continue
        except (yaml.YAMLError, OSError) as e:
            logging.getLogger(__name__).error("配置文件加载失败 %s: %s", path, e)
            raise SystemExit(1)

    logging.getLogger(__name__).warning("未找到配置文件，所有参数使用默认值")
    _CONFIG_PATH = ""
    return {}

_cfg = _load_config()

NORAD_IDS: list[int] = _cfg.get("targets", {}).get("norad_ids", [25544])
SCHEDULED_MINUTE: int = _cfg.get("schedule", {}).get("minute", 12)  # 每小时请求的分钟数（建议 12 或 48，避开整点/半点高峰）
DATA_DIR: str = (
    os.environ.get("DATA_DIR")
    or _cfg.get("files", {}).get("data_dir")
    or ("." if os.name == "nt" else "/data")
)  # 数据文件根目录（Windows 默认当前目录，Linux/Docker 默认 /data）

def _data_path(filename: str) -> str:
    """返回数据目录下的完整路径，自动创建目录"""
    path = os.path.join(DATA_DIR, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

DATA_FILE: str = _data_path(_cfg.get("files", {}).get("data_file", "tle_data.jsonl"))    # 轨道数据文件（带轮转保护）
CACHE_FILE: str = _data_path(_cfg.get("files", {}).get("cache",    "tle_cache.json"))   # 临时缓存，自动覆盖
LOG_FILE: str = _data_path(_cfg.get("files", {}).get("run_log",  "tle_log.jsonl"))  # 运行日志（带轮转保护）
REENTRY_WARNING_KM: int  = _cfg.get("alerts", {}).get("reentry_warning_km",   200)  # 近地点低于此值时发出再入预警
ONLY_PRINT_ON_UPDATE: bool = _cfg.get("alerts", {}).get("only_print_on_update", True)  # 仅在 TLE 变化时打印输出
LOGIN_MAX_FAILURES: int = _cfg.get("retry", {}).get("login_max_failures",  5)  # 登录最大失败次数
LOGIN_PAUSE_SECONDS: int = _cfg.get("retry", {}).get("login_pause_seconds", 1800)  # 登录失败后等待时间（秒）
REQUEST_MAX_RETRIES: int = _cfg.get("retry", {}).get("request_max_retries", 3)  # 请求最大重试次数
REQUEST_RETRY_BASE: int = _cfg.get("retry", {}).get("request_retry_base",  5)  # 指数退避基数（秒）：5, 10, 20 ...
_xprop_cfg = _cfg.get("xpropagator", {})
XPROP_ENABLED: bool = _xprop_cfg.get("enabled", True)
XPROP_HOST: str = _xprop_cfg.get("host", "localhost")
XPROP_PORT: int = _xprop_cfg.get("port", 50051)
XPROP_MANEUVER_THRESHOLD_KM: float = _xprop_cfg.get("maneuver_threshold_km", 5.0)
# 降级策略配置（当 xpropagator 不可用时使用）
FALLBACK_MANEUVER_THRESHOLD_KM: float = _cfg.get("alerts", {}).get("fallback_maneuver_threshold_km", 5.0)
# 双源配置
_ds_cfg = _cfg.get("data_source", {})
PRIMARY_SOURCE: str    = _ds_cfg.get("primary",                   "spacetrack")
FALLBACK_SOURCE: str   = _ds_cfg.get("fallback",                  "none")
FALLBACK_THRESHOLD: int = _ds_cfg.get("fallback_threshold",        3)
CELESTRAK_INTERVAL: int = _ds_cfg.get("celestrak_interval_seconds", 7200)
USE_SUPPLEMENTAL: bool  = _ds_cfg.get("use_supplemental",          False)

# 以下参数涉及 API 合规，不暴露在 config.yaml 中，避免用户误改导致封号
# Space-Track 规定 gp 端点每小时最多 1 次请求（3600s），登录会话约 2 小时过期（5400s 留 30 分钟余量）
MIN_REQUEST_INTERVAL: int = 3600
SESSION_MAX_AGE: int = 5400

# 日志文件最大大小（字节），超过后自动轮转（10 MB）
MAX_LOG_SIZE: int = _cfg.get("files", {}).get(
    "max_log_size_mb", 10
) * 1024 * 1024

# 安全的回退时间值（用于排序）
_EPOCH_MIN = datetime(2000, 1, 1, tzinfo=timezone.utc)

# Space-Track API 地址
BASE_URL = "https://www.space-track.org"
LOGIN_URL = f"{BASE_URL}/ajaxauth/login"
LOGOUT_URL = f"{BASE_URL}/ajaxauth/logout"

# User-Agent（可选，用于标识应用身份）
# 如果用户在 config.yaml 中配置了 user_agent，则使用该值；否则不设置 UA
SPACE_TRACK_USER_AGENT: Optional[str] = _cfg.get("user_agent") or None

# 批量查询 URL：获取最近 1 小时内发布的所有 TLE
# 这是 Space-Track 官方推荐的查询方式，符合 API 使用规范
#   decay_date/null-val          - 排除已衰减的卫星
#   CREATION_DATE/%3Enow-0.042   - 最近 1 小时（略大于 1/24=0.04167，避免服务器浮点舍入漏掉边界记录）
#   format/json                  - JSON 格式输出
BULK_TLE_URL = (
    f"{BASE_URL}/basicspacedata/query/class/gp"
    "/decay_date/null-val"
    "/CREATION_DATE/%3Enow-0.042"
    "/format/json"
)

# 确保 xpropagator_client 模块的 logger 也能输出 INFO 级别日志
logging.getLogger("xpropagator_client").setLevel(logging.INFO)

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from xpropagator_client import classify_change_xprop, is_service_alive, _parse_epoch_utc

# xpropagator 客户端（插件式，找不到模块时自动禁用）
try:
    from xpropagator_client import classify_change_xprop, is_service_alive, _parse_epoch_utc
    _XPROP_MODULE_OK = True
except ImportError:
    _XPROP_MODULE_OK = False

# 实际是否可用 = 配置开启 + 模块导入成功
XPROP_ACTIVE: bool = XPROP_ENABLED and _XPROP_MODULE_OK


def rotate_file_if_needed(filepath: str, max_size: int = MAX_LOG_SIZE) -> None:
    """如果文件超过 max_size，将其重命名为 .bak 实现轮转"""
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) > max_size:
            backup = filepath + ".bak"
            # 如果备份已存在，先删除旧备份
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(filepath, backup)
            log.info("日志文件 %s 已轮转（>%d MB）", filepath, max_size // (1024 * 1024))
    except OSError as e:
        log.error("日志轮转失败: %s", e)


def parse_datetime_utc(value: object) -> Optional[datetime]:
    """
    将 Space-Track 返回的 ISO 时间字符串转换为 UTC datetime 对象。
    
    复用 xpropagator_client._parse_epoch_utc，保持行为一致。
    如果 xpropagator_client 模块不可用，使用本地实现作为回退。
    """
    if _XPROP_MODULE_OK and _parse_epoch_utc is not None:
        # 优先使用统一的时间解析函数
        # 注意：None 值需要特殊处理，避免 str(None) 变成 "None" 字符串
        return _parse_epoch_utc(str(value) if value is not None else "")
    
    # 回退实现（当 xpropagator_client 不可用时）
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    # 如果没有时区信息，假设为 UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# 本地缓存管理

class LocalCache:
    """持久化缓存，保存上次请求时间和全量原始 TLE 数据"""

    def __init__(self, path: str) -> None:
        self._path = path
        self._data: dict = {"last_fetch_ts": None, "raw_records": [], "pending": False}
        if path:
            self._load()

    def _load(self) -> None:
        """从 JSON 文件加载缓存数据"""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("缓存格式错误")
            self._data["last_fetch_ts"] = raw.get("last_fetch_ts", None)
            raw_records = raw.get("raw_records", [])
            if not isinstance(raw_records, list):
                log.warning("缓存 raw_records 字段类型异常，已重置")
                raw_records = []
            self._data["raw_records"] = raw_records
            # 加载待处理标记（用于断点恢复）
            self._data["pending"] = raw.get("pending", False)
            log.info("已加载本地缓存：%s", self._path)
        except FileNotFoundError:
            log.debug("缓存文件 %s 不存在，将从头开始", self._path)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            log.warning("缓存文件损坏或读取失败（将从头开始）: %s", e)

    def _save(self) -> None:
        """将缓存数据保存到 JSON 文件（覆盖模式）"""
        if not self._path:
            return
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.error("缓存写入失败: %s", e)

    @property
    def last_fetch_ts(self) -> Optional[datetime]:
        """获取上次请求的时间戳"""
        ts = parse_datetime_utc(self._data.get("last_fetch_ts"))
        if ts is None:
            raw = self._data.get("last_fetch_ts")
            if raw:
                log.warning("缓存时间戳格式异常，已忽略: %s", raw)
        return ts

    def seconds_since_last_fetch(self) -> float:
        """计算距离上次请求的秒数"""
        ts = self.last_fetch_ts
        if ts is None:
            return float("inf")  # 从未请求过，返回无穷大
        now = datetime.now(timezone.utc)
        return (now - ts).total_seconds()

    def mark_fetched(self) -> None:
        """更新请求时间戳（请求成功时使用）"""
        self._data["last_fetch_ts"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def save_raw_records(self, records: list[dict]) -> None:
        """保存全量原始记录（覆盖旧数据），并标记为待处理"""
        self._data["last_fetch_ts"] = datetime.now(timezone.utc).isoformat()
        self._data["raw_records"] = records
        self._data["pending"] = True  # 标记有未处理的数据
        self._save()

    def clear_pending(self) -> None:
        """清除待处理标记（数据处理完成后调用）"""
        self._data["pending"] = False
        self._save()

    @property
    def has_pending_data(self) -> bool:
        """检查是否有待处理的全量数据（用于断点恢复）"""
        return self._data.get("pending", False)

    def get_raw_records(self) -> list[dict]:
        """获取缓存中的全量原始记录"""
        return self._data.get("raw_records", [])


# 调度器

def next_scheduled_time(minute: int = SCHEDULED_MINUTE) -> datetime:
    """计算下一个调度时刻（每小时的 :MM 分）"""
    now = datetime.now(timezone.utc)
    target = now.replace(minute=minute, second=0, microsecond=0)
    # 如果当前时间已超过目标时间，则推到下一小时
    if target <= now:
        target += timedelta(hours=1)
    return target


def wait_until(target: datetime) -> None:
    """阻塞等待到指定时刻（每分钟唤醒一次，便于响应 Ctrl-C）"""
    # 只在首次打印等待信息
    first_log = True
    while True:
        secs = (target - datetime.now(timezone.utc)).total_seconds()
        if secs <= 0:
            return
        # 首次或剩余时间少于 10 分钟时打印日志
        if first_log or secs < 600:
            log.info(
                "下次查询：%s UTC（%.0f 分钟后）",
                target.strftime("%H:%M"),
                secs / 60,
            )
            first_log = False
        time.sleep(min(secs, 60))


def compute_next_wake(cache: LocalCache, minute: int = SCHEDULED_MINUTE) -> datetime:
    """
    计算下次唤醒时间，同时满足两个约束：
    1. 下一个调度时刻（每小时的 :MM 分）
    2. 距上次请求满 MIN_REQUEST_INTERVAL（3600秒）
    取两者中较晚的时刻
    """
    sched = next_scheduled_time(minute)

    # 检查速率限制
    secs_since = cache.seconds_since_last_fetch()
    if secs_since < MIN_REQUEST_INTERVAL:
        rate_ok_at = datetime.now(timezone.utc) + timedelta(
            seconds=MIN_REQUEST_INTERVAL - secs_since
        )
        # 如果速率限制时刻明显晚于调度时刻（超过1分钟），才需要推迟到下一个小时
        # 使用1分钟的容差，避免因为时间精度问题导致不必要的推迟
        if (rate_ok_at - sched).total_seconds() > 60:
            while sched <= rate_ok_at:
                sched += timedelta(hours=1)

    return sched


# Space-Track 会话管理

class FetchStatus(Enum):
    """请求状态枚举"""
    RELOGIN = auto()  # 401 错误，需要重新登录
    SKIP = auto()     # 临时错误，本轮跳过


class SpaceTrackSession:
    """封装 Space-Track 登录、重试和会话管理逻辑"""

    def __init__(self) -> None:
        self._session = requests.Session()
        if SPACE_TRACK_USER_AGENT:
            self._session.headers.update({"User-Agent": SPACE_TRACK_USER_AGENT})
        self._login_failures = 0
        self._logged_in_at: Optional[float] = None

    def _check_login_response(self, resp: requests.Response) -> bool:
        if resp.status_code != 200:
            return False
        if "chocolatechip" not in self._session.cookies:
            return False
        try:
            body = resp.json()
            if isinstance(body, dict) and body.get("Login") == "Failed":
                return False
        except ValueError:
            pass
        return True

    def login_once(self) -> bool:
        """尝试登录一次，成功返回 True"""
        try:
            resp = self._session.post(
                LOGIN_URL,
                data={"identity": USERNAME, "password": PASSWORD},
                timeout=15,
            )
        except requests.RequestException as e:
            log.error("登录网络错误: %s", e)
            return False

        if self._check_login_response(resp):
            log.debug("登录成功")
            self._login_failures = 0
            self._logged_in_at = time.monotonic()
            return True

        log.error("登录失败 (HTTP %d)", resp.status_code)
        try:
            log.error("响应: %s", resp.json())
        except ValueError:
            log.error("响应: %s", resp.text[:200])
        return False

    def login_with_retry(self) -> bool:
        """带重试的登录，最多尝试 LOGIN_MAX_FAILURES 次"""
        for attempt in range(1, LOGIN_MAX_FAILURES + 1):
            if self.login_once():
                return True
            self._login_failures += 1
            if attempt < LOGIN_MAX_FAILURES:
                wait = REQUEST_RETRY_BASE * (2 ** (attempt - 1))
                log.warning(
                    "登录失败（第 %d/%d 次），%d 秒后重试",
                    attempt, LOGIN_MAX_FAILURES, wait,
                )
                time.sleep(wait)
            else:
                log.error(
                    "连续登录失败 %d 次，放弃本轮（建议等待 %d 分钟后再试）",
                    LOGIN_MAX_FAILURES,
                    LOGIN_PAUSE_SECONDS // 60,
                )
        return False

    def ensure_fresh_session(self) -> bool:
        """确保会话有效，如果超过 SESSION_MAX_AGE 则重新登录"""
        if self._logged_in_at is None:
            return self.login_with_retry()
        age = time.monotonic() - self._logged_in_at
        if age > SESSION_MAX_AGE:
            log.info("会话已存在 %.0f 分钟，主动刷新登录...", age / 60)
            self.logout()
            self._session = requests.Session()
            if SPACE_TRACK_USER_AGENT:
                self._session.headers.update({"User-Agent": SPACE_TRACK_USER_AGENT})
            return self.login_with_retry()
        return True

    def logout(self) -> None:
        try:
            self._session.get(LOGOUT_URL, timeout=10)
        except Exception:
            pass
        self._session.cookies.clear()
        self._logged_in_at = None

    def relogin(self) -> bool:
        self.logout()
        self._session = requests.Session()
        if SPACE_TRACK_USER_AGENT:
            self._session.headers.update({"User-Agent": SPACE_TRACK_USER_AGENT})
        return self.login_with_retry()

    def get(self, url: str) -> "requests.Response | FetchStatus":
        """发送 GET 请求，带重试和错误处理"""
        for attempt in range(1, REQUEST_MAX_RETRIES + 1):
            try:
                resp = self._session.get(url, timeout=30)
                if resp.status_code == 401:
                    return FetchStatus.RELOGIN
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                if resp.status_code != 200:
                    log.warning("非预期状态码 %d", resp.status_code)
                    return FetchStatus.SKIP
                return resp
            except requests.RequestException as e:
                wait = REQUEST_RETRY_BASE * (2 ** (attempt - 1))
                if attempt < REQUEST_MAX_RETRIES:
                    log.warning(
                        "请求错误（第 %d/%d 次）: %s，%d 秒后重试",
                        attempt, REQUEST_MAX_RETRIES, e, wait,
                    )
                    time.sleep(wait)
                else:
                    log.error("请求失败，已重试 %d 次，本轮跳过: %s", REQUEST_MAX_RETRIES, e)
                    return FetchStatus.SKIP
        return FetchStatus.SKIP

    def __enter__(self) -> "SpaceTrackSession":
        return self

    def __exit__(self, *_) -> None:
        self.logout()
        self._session.close()


# 批量拉取和本地筛选

def fetch_bulk_tle(st: SpaceTrackSession) -> "list[dict] | FetchStatus":
    """批量拉取最近 1 小时内发布的所有 TLE（消耗 1 次 gp 配额）"""
    log.info("请求批量 TLE（最近 1 小时发布）...")
    result = st.get(BULK_TLE_URL)
    if isinstance(result, FetchStatus):
        return result
    try:
        data = result.json()
    except ValueError as e:
        log.warning("JSON 解析失败: %s", e)
        return FetchStatus.SKIP
    log.debug("收到 %d 条记录", len(data))
    return data


def fetch_bulk_with_relogin(st: SpaceTrackSession) -> Optional[list[dict]]:
    """
    带重登录保护的批量拉取
    如果遇到 401 错误，重新登录后不会立即重试 gp 请求
    而是返回 None，由主循环在下一个调度周期再试
    """
    result = fetch_bulk_tle(st)
    if result is FetchStatus.RELOGIN:
        # 会话过期，重新登录后不立即重试（避免同一小时内第 2 次 gp 请求）
        log.info("会话过期，重新登录...")
        st.relogin()
        return None
    if isinstance(result, FetchStatus):
        return None
    return result


def _record_sort_key(rec: dict) -> tuple[datetime, int]:
    """记录排序键：优先按 CREATION_DATE，其次按 FILE 号"""
    creation = parse_datetime_utc(rec.get("CREATION_DATE")) or _EPOCH_MIN
    try:
        file_no = int(rec.get("FILE") or 0)
    except (ValueError, TypeError):
        file_no = 0
    return (creation, file_no)


def filter_by_norad(records: list[dict], norad_ids: list[int]) -> dict[int, dict]:
    """
    筛选目标 NORAD ID，每个卫星只返回最新一条（CREATION_DATE 最大）。
    同一小时内多条记录属于“解算修正覆盖”，不是轨道演化序列。
    返回结构：{norad_id: latest_record_with_batch_count}
    """
    target_set = set(norad_ids)

    # 按 NORAD ID 分组
    grouped: dict[int, list[dict]] = {}
    for rec in records:
        try:
            nid = int(rec.get("NORAD_CAT_ID") or 0)
        except (ValueError, TypeError):
            continue  # 跳过无效记录
        if nid in target_set:
            grouped.setdefault(nid, []).append(rec)

    # 对每个卫星，只保留最新的一条记录
    found: dict[int, dict] = {}
    for nid, recs in grouped.items():
        # 按时间排序（从旧到新）
        sorted_recs = sorted(recs, key=_record_sort_key)
        latest = sorted_recs[-1]
        
        # 注入本批次记录数量，供 process_records 打日志用
        latest["_batch_count"] = len(sorted_recs)
        found[nid] = latest
    
    return found


# 轨道数据处理

def _calculate_orbital_params(mean_motion: float, eccentricity: float) -> dict:
    """
    从平均运动和离心率计算轨道参数。
    
    Args:
        mean_motion: 平均运动（圈/天）
        eccentricity: 离心率
    
    Returns:
        dict: 包含 periapsis (km), apoapsis (km), period (min)
    """
    if mean_motion <= 0:
        return {"periapsis": 0.0, "apoapsis": 0.0, "period": 0.0}
    
    # 地球引力常数 (km^3/s^2)
    mu = 398600.4418
    # 地球半径 (km)
    R_E = 6378.137
    
    # 周期（分钟）= 1440 / mean_motion
    period_min = 1440.0 / mean_motion
    
    # 半长轴（km）：a = (mu / n^2)^(1/3)，其中 n 为角速度（rad/s）
    # mean_motion 单位为 圈/天，需要转换为 rad/s
    n_rad_s = mean_motion * 2.0 * math.pi / 86400.0
    semi_major_axis = (mu / (n_rad_s ** 2)) ** (1.0 / 3.0)
    
    # 近地点和远地点（km）
    periapsis = semi_major_axis * (1.0 - eccentricity) - R_E
    apoapsis = semi_major_axis * (1.0 + eccentricity) - R_E
    
    return {
        "periapsis": max(0.0, periapsis),  # 确保非负
        "apoapsis": max(0.0, apoapsis),
        "period": period_min,
    }


def classify_change(orbit: dict, prev: Optional[dict]) -> str:
    """
    判断 TLE 变化是真实机动还是解算修正。
    优先策略（当 xpropagator 已启用且在线）：
      残差分析，将旧 TLE 传播到新历元，对比 ECI 位置差
      Δr ≥ XPROP_MANEUVER_THRESHOLD_KM km → maneuver
      Δr <  XPROP_MANEUVER_THRESHOLD_KM km → correction

      降级策略（xpropagator 不可用时）：
      近地点/远地点变化 > 5 km → maneuver，否则 → correction
    """
    if prev is None:
        return "initial"

    # 近地点低于再入预警阈值时，SGP4 传播不可靠（大气阻力主导），
    # 残差分析和简单阈值均可能误判 → 跳过分类，标记为轨道衰降
    if orbit.get("periapsis", 0) < REENTRY_WARNING_KM:
        return "decaying"

    # 高精度路径：xpropagator 残差分析
    if XPROP_ACTIVE:
        result = classify_change_xprop(orbit, prev,
            maneuver_threshold_km=XPROP_MANEUVER_THRESHOLD_KM,
            host=XPROP_HOST, port=XPROP_PORT,)
        if result is not None:
            return result
        # RPC 调用失败（服务暂时不可用），降级处理
        log.debug("[%d] xpropagator 本次调用失败，降级到简单阈值", orbit["norad"])

    # 降级路径：简单近地点/远地点阈值
    delta_peri = abs(orbit["periapsis"] - prev["periapsis"])
    delta_apo = abs(orbit["apoapsis"] - prev["apoapsis"])
    if delta_peri > FALLBACK_MANEUVER_THRESHOLD_KM or delta_apo > FALLBACK_MANEUVER_THRESHOLD_KM:
        return "maneuver"
    return "correction"


def format_change_type(change_type: str) -> str:
    # 将变化类型转换为中英文对照格式
    type_map = {
        "initial": "首次记录 (Initial)",
        "correction": "解算修正 (Correction)",
        "maneuver": "真实机动 (Maneuver)",
        "decaying": "轨道衰降 (Decaying)",
    }
    return type_map.get(change_type, f"未知 ({change_type})")


def parse_orbit(record: dict) -> dict:
    """
    从 Space-Track/CelesTrak 记录中提取轨道参数并计算哈希值。
    
    Hash 计算策略：
    1. 优先使用 TLE_LINE1 + TLE_LINE2（传统方式）
    2. 回退：当 TLE 为空时，使用 _raw_elements 序列化为 JSON 后计算 hash
       （5位编号耗尽后 ~2026-07-20 的主要方式）
    3. 如果两者均缺失，抛出 ValueError（数据不完整，无法继续处理）
    
    轨道参数计算策略：
    - 如果 API 直接提供 PERIAPSIS/APOAPSIS/PERIOD，直接使用
    - 否则从 MEAN_MOTION 和 ECCENTRICITY 计算（CelesTrak GP 接口场景）
    """
    name = (record.get("OBJECT_NAME") or "").strip()
    tle1 = str(record.get("TLE_LINE1") or "")
    tle2 = str(record.get("TLE_LINE2") or "")
    norad_id = int(record.get("NORAD_CAT_ID") or 0)
    
    # 计算 TLE 哈希：优先使用 TLE 文本，如果为空则使用原始根数
    # 取前 16 字符（64 位）足以避免跟踪卫星间的哈希碰撞
    if tle1 and tle2:
        tle_hash = hashlib.sha256((tle1 + tle2).encode("utf-8")).hexdigest()[:16]
    else:
        # 5位编号耗尽后（~2026-07-20），TLE_LINE1/2 不再提供，改用 _raw_elements 计算 hash
        raw_elements = record.get("_raw_elements", {})
        if raw_elements:
            raw_str = json.dumps(raw_elements, sort_keys=True, ensure_ascii=False)
            tle_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]
            log.debug("[NORAD %d] TLE 文本为空，使用 _raw_elements 计算 hash", norad_id)
        else:
            # 数据不完整：既无 TLE 也无原始根数，无法继续处理
            raise ValueError(
                f"[NORAD {norad_id}] 轨道数据不完整：既无 TLE_LINE1/TLE_LINE2，"
                f"也无 _raw_elements。无法计算 hash，请检查数据源返回格式。"
            )
    
    # 提取或计算轨道参数
    periapsis_raw = record.get("PERIAPSIS")
    apoapsis_raw = record.get("APOAPSIS")
    period_raw = record.get("PERIOD")
    
    # 如果 API 未提供这些字段（如 CelesTrak GP），则从轨道根数计算
    if not periapsis_raw or not apoapsis_raw or not period_raw:
        mean_motion = float(record.get("MEAN_MOTION") or 0)
        eccentricity = float(record.get("ECCENTRICITY") or 0)
        
        if mean_motion > 0:
            calculated = _calculate_orbital_params(mean_motion, eccentricity)
            periapsis = calculated["periapsis"]
            apoapsis = calculated["apoapsis"]
            period = calculated["period"]
            log.debug(
                "[NORAD %d] API 未提供完整轨道参数，已从根数计算: "
                "近地点=%.1f km, 远地点=%.1f km, 周期=%.3f min",
                norad_id, periapsis, apoapsis, period,
            )
        else:
            # 无法计算，使用默认值
            periapsis = float(periapsis_raw or 0)
            apoapsis = float(apoapsis_raw or 0)
            period = float(period_raw or 0)
    else:
        # API 已提供，直接使用
        periapsis = float(periapsis_raw)
        apoapsis = float(apoapsis_raw)
        period = float(period_raw)
    
    return {
        "norad": norad_id,
        "name": name or "TBA",
        "intl_id": record.get("OBJECT_ID", ""),
        "epoch": record.get("EPOCH", ""),
        "periapsis": periapsis,
        "apoapsis": apoapsis,
        "incl": float(record.get("INCLINATION") or 0),
        "period": period,
        "ecc": float(record.get("ECCENTRICITY") or 0),
        "bstar": float(record.get("BSTAR") or 0),
        "tle1": tle1,
        "tle2": tle2,
        "tle_hash": tle_hash,
        # 原始根数，供以下场景使用：
        # 1. 5位编号耗尽后（~2026-07-20），TLE_LINE1/2 不再提供时，用于重建 TLE
        # 2. xpropagator_client.gp_json_to_tle_lines() 在 tle1/tle2 为空时合成 TLE
        "_raw_elements": {
            "NORAD_CAT_ID": record.get("NORAD_CAT_ID"),
            "OBJECT_ID": record.get("OBJECT_ID"),
            "OBJECT_NAME": record.get("OBJECT_NAME"),
            "EPOCH": record.get("EPOCH"),
            "CLASSIFICATION_TYPE": record.get("CLASSIFICATION_TYPE"),
            "ELEMENT_SET_NO": record.get("ELEMENT_SET_NO"),
            "EPHEMERIS_TYPE": record.get("EPHEMERIS_TYPE"),
            "INCLINATION": record.get("INCLINATION"),
            "RA_OF_ASC_NODE": record.get("RA_OF_ASC_NODE"),
            "ECCENTRICITY": record.get("ECCENTRICITY"),
            "ARG_OF_PERICENTER": record.get("ARG_OF_PERICENTER"),
            "MEAN_ANOMALY": record.get("MEAN_ANOMALY"),
            "MEAN_MOTION": record.get("MEAN_MOTION"),
            "MEAN_MOTION_DOT": record.get("MEAN_MOTION_DOT"),
            "MEAN_MOTION_DDOT": record.get("MEAN_MOTION_DDOT"),
            "BSTAR": record.get("BSTAR"),
            "REV_AT_EPOCH": record.get("REV_AT_EPOCH"),
        },
    }


def estimate_reentry_days(orbit: dict) -> Optional[float]:
    """
    基于 BSTAR 和简化大气模型估算剩余再入天数（仅供参考）
    原理：通过大气阻力引起的平均运动变化率推算轨道衰减速度
    """
    peri, bstar, period = orbit["periapsis"], orbit["bstar"], orbit["period"]
    # 近地点过高或 BSTAR 无效时无法估算
    if peri > 400.0 or bstar <= 0.0 or period <= 0:
        return None
    # 简化的大气密度模型（经验参数拟合自 US Standard Atmosphere 1976）
    rho_area = 2e-10 * math.exp(-(peri - 200.0) / 60.0) * 60000.0
    rho0 = 2.461e-5
    n = 1440.0 / period  # 平均运动（圈/天）
    # 平均运动变化率（BSTAR 阻力模型）
    dn_dt = 3.0 * math.pi * (n ** 2) * bstar * (rho_area / rho0)
    if dn_dt <= 1e-12:
        return None
    # 16 圈/天 ≈ 90 分钟为低轨理论最低稳定周期，以此作为再入判定阈值
    n_reentry = 16.0
    if n <= n_reentry:
        return 0.0
    return (n - n_reentry) / dn_dt


def format_reentry_estimate(days: float) -> str:
    if days == 0.0:
        return "即将再入"
    if days < 1.0:
        return f"约 {days * 24:.0f} 小时内（粗估）"
    if days < 30.0:
        return f"约 {days:.1f} 天内（粗估）"
    return f"约 {days:.0f} 天（粗估，误差较大）"


def print_orbit(orbit: dict, prev: Optional[dict]) -> None:
    """格式化打印轨道信息"""
    peri, apo = orbit["periapsis"], orbit["apoapsis"]
    delta = ""
    if prev:
        delta = f"  （近地点变化 {peri - prev['periapsis']:+.1f} km，远地点变化 {apo - prev['apoapsis']:+.1f} km）"
    log.info(f"""
  ===============================================
    {orbit['name']:<20} NORAD {orbit['norad']}
    国际编号: {orbit['intl_id']}
    历元:     {orbit['epoch']}
    近地点:   {peri:.1f} km    远地点: {apo:.1f} km
    倾角:     {orbit['incl']:.4f}°   周期: {orbit['period']:.3f} min
    离心率:   {orbit['ecc']:.7f}   BSTAR: {orbit['bstar']:.4e}
    TLE Hash: {orbit['tle_hash']}
  ==============================================={delta}
  {orbit['tle1']}
  {orbit['tle2']}""")
    # 再入预警
    if REENTRY_WARNING_KM > 0 and peri < REENTRY_WARNING_KM:
        days = estimate_reentry_days(orbit)
        if days is not None:
            log.info(f"   再入高风险：近地点 {peri:.1f} km，预计 {format_reentry_estimate(days)}，实际误差可达数倍")
        else:
            log.info(f"   再入高风险：近地点 {peri:.1f} km")
            if orbit["bstar"] <= 0:
                log.info("     BSTAR=0，寿命无法估算（可能为初始定轨解，阻力项尚未计算）")
            else:
                log.info("     近地点 > 400 km 或周期无效，不满足估算条件")
    elif peri < 300:
        log.info(f"     注意：近地点 {peri:.1f} km，大气阻力明显，轨道将持续衰减")


def log_record(orbit: dict, change_type: str = "unknown", source: str = "spacetrack") -> None:
    """将轨道数据写入 DATA_FILE（核心业务数据）"""
    if not DATA_FILE:
        return
    rotate_file_if_needed(DATA_FILE)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "change_type": change_type,  # 变化类型：initial/correction/maneuver
        "source": source,            # 数据来源：spacetrack / celestrak / celestrak_sup
        **orbit
    }
    try:
        with open(DATA_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        log.error("轨道数据写入失败: %s", e)


def write_log_message(message: str) -> None:
    """将运行日志写入 LOG_FILE"""
    if not LOG_FILE:
        return
    rotate_file_if_needed(LOG_FILE)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "message": message}
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        log.error("运行日志写入失败: %s", e)


# 状态恢复

def _iter_jsonl_reversed(path: str, chunk: int = 65536):
    """
    从文件末尾逐块反向读取 JSONL
    """
    with open(path, "rb") as f:
        f.seek(0, 2)
        remaining = f.tell()
        
        if remaining == 0:
            return
        
        buf = b""
        while remaining > 0:
            read_size = min(chunk, remaining)
            remaining -= read_size
            f.seek(remaining)
            buf = f.read(read_size) + buf
            lines = buf.split(b"\n")
            # 最左边的块可能是不完整行，留到下次拼接
            buf = lines[0]
            for line in reversed(lines[1:]):
                line = line.strip()
                if line:
                    yield line.decode("utf-8", errors="replace")
        # 处理文件开头剩余内容
        if buf.strip():
            yield buf.strip().decode("utf-8", errors="replace")


def restore_from_log(norad_ids: list[int]) -> dict[int, dict]:
    """从 DATA_FILE 末尾反向扫描，恢复每个目标的最新轨道状态。"""
    prev_data: dict[int, dict] = {}
    if not DATA_FILE:
        return prev_data
    
    target_set = set(norad_ids)
    seen: set[int] = set()
    
    try:
        for line in _iter_jsonl_reversed(DATA_FILE):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            norad = entry.get("norad")
            if norad not in target_set or norad in seen:
                continue
            
            prev_data[norad] = entry
            seen.add(norad)
            
            # 找到所有目标，立即退出
            if len(seen) == len(target_set):
                break
        
        if prev_data:
            log.info("已从轨道数据文件恢复 %d 个目标的历史状态", len(prev_data))
    
    except OSError as e:
        log.warning("轨道数据文件读取失败: %s", e)
    
    return prev_data


# 数据处理

def process_records(
    raw_records: dict[int, dict],
    prev_data: dict[int, dict],
    last_hash: dict[int, str],
    cache: LocalCache,
) -> None:
    """
    比对 TLE 哈希值，检测变化并记录日志
    每个卫星只处理最新一条记录（解算修正后的最终版）
    无论是否命中目标都更新缓存时间戳，防止速率保护卡死
    """
    # 遍历所有监控目标
    for norad_id in NORAD_IDS:
        # 获取该卫星的最新记录（已包含 _batch_count）
        record = raw_records.get(norad_id)
        if not record:
            continue
        
        # 提取来源标识（确认 record 不为 None 后读取）
        record_source = record.get("_source", "spacetrack")

        # 提取批次记录数（元数据，不进入 orbit）
        batch_count = record.pop("_batch_count", 1)
        
        # 解析轨道参数并计算 Hash
        try:
            orbit = parse_orbit(record)
        except ValueError as e:
            log.error("[%d] 轨道数据解析失败，跳过该记录: %s", norad_id, e)
            continue
        
        prev = prev_data.get(norad_id)
        cur_hash = orbit["tle_hash"]

        if batch_count > 1:
            write_log_message(f"[{norad_id}] 本批次共 {batch_count} 条解算记录，取最新一条")

        if cur_hash != last_hash.get(norad_id):
            change_type = classify_change(orbit, prev)
            change_type_cn = format_change_type(change_type)  # 中英文对照
            
            msg = f"[{norad_id}] 检测到 TLE 变化！(hash: {last_hash.get(norad_id, '无')} → {cur_hash}, 类型: {change_type_cn})"
            log.info(msg)
            write_log_message(msg)

            print_orbit(orbit, prev)

            log_record(orbit, change_type, source=record_source)
            
            # 更新内存中的状态（供下次比较使用）
            prev_data[norad_id] = orbit  # 更新最新轨道数据
            last_hash[norad_id] = cur_hash  # 更新最新 Hash
        elif not ONLY_PRINT_ON_UPDATE:
            # Hash 相同，但配置为打印所有数据
            print_orbit(orbit, None)  # TLE 未变化，不显示 delta

    # 更新缓存时间戳（全量数据已在 save_raw_records 中保存）
    # 即使没有命中目标，也要更新时间戳，避免下次启动时重复请求
    cache.mark_fetched()

def cold_start_if_needed(norad_ids: list[int], prev_data: dict[int, dict]) -> None:
    """
    冷启动检查：对 tle_data 中无记录的卫星，通过 CelesTrak 获取初始基准数据
    无论 PRIMARY_SOURCE 为何值均执行，因为冷启动始终优先走 CelesTrak（无需认证）
    """
    missing = [nid for nid in norad_ids if nid not in prev_data]
    if not missing:
        return

    if not _CT_MODULE_OK:
        log.warning("冷启动：以下卫星无历史记录，但 celestrak_fetcher 模块未找到，跳过初始化: %s",
                    missing)
        return

    log.info("冷启动：以下卫星无历史记录，将通过 CelesTrak 获取初始基准: %s", missing)
    for nid in missing:
        record = ct.fetch_single(
            nid, 
            use_supplemental=USE_SUPPLEMENTAL,
            user_agent=SPACE_TRACK_USER_AGENT,  # 统一从 config.yaml 传入 UA
        )
        if record is None:
            log.warning("[冷启动][%d] CelesTrak 查询失败，本轮跳过", nid)
            continue
        try:
            orbit = parse_orbit(record)
        except ValueError as e:
            log.error("[冷启动][%d] 轨道数据解析失败，跳过: %s", nid, e)
            continue
        log.info("[冷启动][%d] %s 初始基准已入库", nid, orbit["name"])
        log_record(orbit, change_type="initial", source=record.get("_source", "celestrak"))
        prev_data[nid] = orbit
    log.info("冷启动完成")


def run_celestrak_cycle(
    prev_data: dict[int, dict],
    last_hash: dict[int, str],
    consecutive_failures: dict,
) -> bool:
    """
    以 CelesTrak 为主源执行一轮监控。
    返回 True 表示本轮至少有一次成功的网络请求，False 表示全部失败或全部跳过。
    consecutive_failures 为可变 dict，内含 "count" 字段，由调用方维护。
    """
    any_success = False  # 是否有至少一次请求成功
    
    for nid in NORAD_IDS:
        secs = ct.seconds_since_last_query(nid)
        if secs < CELESTRAK_INTERVAL:
            log.debug("[CelesTrak][%d] 距上次查询 %.0f 分钟，跳过本轮", nid, secs / 60)
            continue  # 跳过不算成功也不算失败

        record = ct.fetch_single(
            nid,
            use_supplemental=USE_SUPPLEMENTAL,
            user_agent=SPACE_TRACK_USER_AGENT,  # 统一从 config.yaml 传入 UA
        )
        if record is None:
            log.warning("[CelesTrak][%d] 查询失败", nid)
            continue

        any_success = True
        try:
            orbit = parse_orbit(record)
        except ValueError as e:
            log.error("[CelesTrak][%d] 轨道数据解析失败，跳过: %s", nid, e)
            continue
        
        cur_hash = orbit["tle_hash"]
        record_source = record.get("_source", "celestrak")

        prev = prev_data.get(nid)
        if cur_hash != last_hash.get(nid):
            change_type = classify_change(orbit, prev)
            change_type_cn = format_change_type(change_type)
            msg = (f"[{nid}] 检测到 TLE 变化！"
                   f"(hash: {last_hash.get(nid, '无')} → {cur_hash}, "
                   f"类型: {change_type_cn}, 来源: {record_source})")
            log.info(msg)
            write_log_message(msg)
            print_orbit(orbit, prev)
            log_record(orbit, change_type, source=record_source)
            prev_data[nid] = orbit
            last_hash[nid] = cur_hash
        elif not ONLY_PRINT_ON_UPDATE:
            print_orbit(orbit, None)

    return any_success


# ── 配置热重载 ──────────────────────────────────────────────────────────────────────

_config_mtime: float = 0.0

ALLOWED_RELOAD_KEYS = {
    "targets.norad_ids",
    "alerts.reentry_warning_km",
    "alerts.only_print_on_update",
    "alerts.fallback_maneuver_threshold_km",
    "xpropagator.enabled",
    "xpropagator.maneuver_threshold_km",
    "data_source.fallback_threshold",
}


def _check_config_reload(prev_data: dict[int, dict], last_hash: dict[int, str]) -> bool:
    """检测 config.yaml 变更并热重载允许的字段，返回 True 表示有变更"""
    global _config_mtime
    global NORAD_IDS, REENTRY_WARNING_KM, ONLY_PRINT_ON_UPDATE
    global FALLBACK_MANEUVER_THRESHOLD_KM, XPROP_ENABLED, XPROP_MANEUVER_THRESHOLD_KM
    global XPROP_ACTIVE, FALLBACK_THRESHOLD

    if not _CONFIG_PATH:
        return False

    try:
        current_mtime = os.path.getmtime(_CONFIG_PATH)
    except OSError:
        return False
    if current_mtime == _config_mtime:
        return False
    _config_mtime = current_mtime

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            new_cfg = yaml.safe_load(f) or {}
    except Exception:
        log.warning("[config-reload] 读取 config.yaml 失败，跳过")
        return False

    changed = []

    # norad_ids 变更
    new_ids = new_cfg.get("targets", {}).get("norad_ids", [25544])
    if not isinstance(new_ids, list) or not all(isinstance(v, int) for v in new_ids):
        new_ids = [25544]
    if sorted(new_ids) != sorted(NORAD_IDS):
        old_set = set(NORAD_IDS)
        new_set = set(new_ids)
        added = new_set - old_set
        removed = old_set - new_set
        changed.append(f"norad_ids: {NORAD_IDS} → {new_ids}")
        NORAD_IDS = new_ids
        # 新增卫星 → 冷启动
        if added:
            cold_start_if_needed(list(added), prev_data)
            for nid in added:
                orbit = prev_data.get(nid)
                if orbit:
                    last_hash[nid] = orbit.get("tle_hash", "")
                    print_orbit(orbit, None)
        # 删除卫星 → 清理状态
        for nid in removed:
            prev_data.pop(nid, None)
            last_hash.pop(nid, None)

    # 告警字段
    alerts = new_cfg.get("alerts", {})
    new_reentry = int(alerts.get("reentry_warning_km", 200))
    if new_reentry != REENTRY_WARNING_KM:
        changed.append(f"reentry_warning_km: {REENTRY_WARNING_KM} → {new_reentry}")
        REENTRY_WARNING_KM = new_reentry

    new_only_update = bool(alerts.get("only_print_on_update", True))
    if new_only_update != ONLY_PRINT_ON_UPDATE:
        changed.append(f"only_print_on_update: {ONLY_PRINT_ON_UPDATE} → {new_only_update}")
        ONLY_PRINT_ON_UPDATE = new_only_update

    new_fallback_thr = float(alerts.get("fallback_maneuver_threshold_km", 5.0))
    if new_fallback_thr != FALLBACK_MANEUVER_THRESHOLD_KM:
        changed.append(f"fallback_maneuver_threshold_km: {FALLBACK_MANEUVER_THRESHOLD_KM} → {new_fallback_thr}")
        FALLBACK_MANEUVER_THRESHOLD_KM = new_fallback_thr

    # xpropagator 字段
    xprop = new_cfg.get("xpropagator", {})
    new_xprop_enabled = bool(xprop.get("enabled", True))
    if new_xprop_enabled != XPROP_ENABLED:
        changed.append(f"xpropagator.enabled: {XPROP_ENABLED} → {new_xprop_enabled}")
        XPROP_ENABLED = new_xprop_enabled
        XPROP_ACTIVE = XPROP_ENABLED and _XPROP_MODULE_OK

    new_xprop_thr = float(xprop.get("maneuver_threshold_km", 5.0))
    if new_xprop_thr != XPROP_MANEUVER_THRESHOLD_KM:
        changed.append(f"xpropagator.maneuver_threshold_km: {XPROP_MANEUVER_THRESHOLD_KM} → {new_xprop_thr}")
        XPROP_MANEUVER_THRESHOLD_KM = new_xprop_thr

    # 数据源
    ds = new_cfg.get("data_source", {})
    new_fb_thr = int(ds.get("fallback_threshold", 3))
    if new_fb_thr != FALLBACK_THRESHOLD:
        changed.append(f"fallback_threshold: {FALLBACK_THRESHOLD} → {new_fb_thr}")
        FALLBACK_THRESHOLD = new_fb_thr

    if changed:
        log.info("[config-reload] 检测到配置变更: %s", "; ".join(changed))
        write_log_message(f"[config-reload] {len(changed)} 项变更已生效")
        return True
    return False


# 主程序

def main() -> None:
    """主函数：启动 TLE 监控循环（支持双源协同）"""

    # 仅在 Space-Track 为主源或备源时才强制要求凭据
    _st_required = (PRIMARY_SOURCE == "spacetrack" or FALLBACK_SOURCE == "spacetrack")
    if _st_required and (not USERNAME or not PASSWORD):
        log.error("当前配置需要 Space-Track 凭据（主源或备源为 spacetrack），但 .env 中未找到！")
        log.error("请设置 SPACETRACK_USER / SPACETRACK_PASS，或将 data_source.primary 改为 celestrak")
        raise SystemExit(1)

    if PRIMARY_SOURCE == "celestrak" and not _CT_MODULE_OK:
        log.error("data_source.primary=celestrak，但 celestrak_fetcher.py 未找到，请确认文件存在")
        raise SystemExit(1)

    log.info("TLE-Tracking 轨道监控  主源: %s  备源: %s", PRIMARY_SOURCE, FALLBACK_SOURCE)
    log.info("目标: %s", ", ".join(str(i) for i in NORAD_IDS))

    if XPROP_ACTIVE:
        alive = is_service_alive(XPROP_HOST, XPROP_PORT)
        if not alive:
            log.warning("xpropagator 配置已启用但服务未响应（%s:%d），将自动降级", XPROP_HOST, XPROP_PORT)
    else:
        if XPROP_ENABLED and not _XPROP_MODULE_OK:
            log.warning("xpropagator 已启用但模块未找到")
        elif not XPROP_ENABLED:
            log.info("xpropagator 已禁用，使用简单阈值")

    log.info(
        "调度: 每小时第 %02d 分 | 再入预警: <%d km | 数据: %s | 日志: %s",
        SCHEDULED_MINUTE, REENTRY_WARNING_KM, DATA_FILE or "关闭", LOG_FILE or "关闭",
    )
    print()

    write_log_message("程序启动")

    # 加载 Space-Track 缓存（仅 spacetrack 模式使用，celestrak 模式中闲置）
    cache = LocalCache(CACHE_FILE)

    # 从 tle_data 恢复历史状态
    prev_data = restore_from_log(NORAD_IDS)
    last_hash: dict[int, str] = {
        nid: orbit.get("tle_hash", "") for nid, orbit in prev_data.items()
    }

    # 冷启动：对无记录的卫星通过 CelesTrak 填充初始基准（与主源无关）
    cold_start_if_needed(NORAD_IDS, prev_data)
    # 冷启动后更新 last_hash
    for nid, orbit in prev_data.items():
        if nid not in last_hash:
            last_hash[nid] = orbit.get("tle_hash", "")

    # Space-Track 断点恢复（仅当缓存中有待处理数据时）
    if PRIMARY_SOURCE == "spacetrack" and cache.has_pending_data:
        write_log_message("检测到未处理的全量数据，尝试断点恢复...")
        all_records = cache.get_raw_records()
        if all_records:
            raw_records = filter_by_norad(all_records, NORAD_IDS)
            # 注入来源标识
            for rec in raw_records.values():
                rec.setdefault("_source", "spacetrack")
            found_ids = list(raw_records.keys())
            missing_ids = [nid for nid in NORAD_IDS if nid not in raw_records]
            if found_ids:
                write_log_message(f"断点恢复：命中 {', '.join(str(i) for i in found_ids)}")
            if missing_ids:
                write_log_message(f"断点恢复：未包含 {', '.join(str(i) for i in missing_ids)}")
            process_records(raw_records, prev_data, last_hash, cache)
            cache.clear_pending()
            write_log_message("断点恢复完成")

    # 打印当前轨道状态
    for nid in NORAD_IDS:
        orbit = prev_data.get(nid)
        if orbit:
            print_orbit(orbit, None)

    # 主循环
    consecutive_failures = {"count": 0}  # 主源连续失败计数
    active_source = PRIMARY_SOURCE       # 当前实际使用的数据源

    if PRIMARY_SOURCE == "spacetrack":
        with SpaceTrackSession() as st:
            first_run = True
            while True:
                if first_run:
                    first_run = False
                    secs_since = cache.seconds_since_last_fetch()
                    if secs_since == float("inf"):
                        log.info("无历史记录，将立即执行首次查询")
                    elif secs_since < MIN_REQUEST_INTERVAL:
                        wait_seconds = MIN_REQUEST_INTERVAL - secs_since
                        log.warning(
                            "距上次请求 %.0f 分钟，需等待 %.0f 分钟（速率限制保护）",
                            secs_since / 60,
                            wait_seconds / 60,
                        )
                        time.sleep(wait_seconds)
                else:
                    wake_at = compute_next_wake(cache, SCHEDULED_MINUTE)
                    wait_until(wake_at)

                _check_config_reload(prev_data, last_hash)

                write_log_message(
                    f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 开始批量拉取（主源: spacetrack）"
                )

                # 主源请求
                success = False
                if active_source == "spacetrack":
                    if not st.ensure_fresh_session():
                        log.error("登录失败")
                        consecutive_failures["count"] += 1
                    else:
                        all_records = fetch_bulk_with_relogin(st)
                        if all_records is None:
                            consecutive_failures["count"] += 1
                        else:
                            consecutive_failures["count"] = 0
                            success = True
                            cache.save_raw_records(all_records)
                            raw_records = filter_by_norad(all_records, NORAD_IDS)
                            # 注入来源标识
                            for rec in raw_records.values():
                                rec.setdefault("_source", "spacetrack")
                            process_records(raw_records, prev_data, last_hash, cache)
                            cache.clear_pending()

                elif active_source == "celestrak" and _CT_MODULE_OK:
                    # 备源模式（Space-Track 故障期间）
                    ok = run_celestrak_cycle(prev_data, last_hash, consecutive_failures)
                    if ok:
                        consecutive_failures["count"] = 0
                        # 尝试恢复主源
                        if st.ensure_fresh_session():
                            write_log_message("主源 Space-Track 已恢复，切回主源")
                            active_source = "spacetrack"
                    else:
                        consecutive_failures["count"] += 1

                # 备源切换判断
                if (consecutive_failures["count"] >= FALLBACK_THRESHOLD
                        and active_source != FALLBACK_SOURCE
                        and FALLBACK_SOURCE != "none"):
                    log.warning(
                        "主源 %s 连续失败 %d 次，切换到备源 %s",
                        PRIMARY_SOURCE, consecutive_failures["count"], FALLBACK_SOURCE,
                    )
                    write_log_message(f"备源切换：{PRIMARY_SOURCE} → {FALLBACK_SOURCE}（连续失败 {consecutive_failures['count']} 次）")
                    active_source = FALLBACK_SOURCE

    else:
        # CelesTrak 主源路径（仅需速率限制，无需调度时刻）
        write_log_message(f"以 CelesTrak 为主源启动，轮询间隔 {CELESTRAK_INTERVAL // 60} 分钟")
        
        # 加载 CelesTrak 轮询时间戳缓存（用于速率保护）
        # 使用 time.time()（Unix 时间戳）存储，确保跨重启有效
        celestrak_cache_path = _data_path("celestrak_poll_cache.json")
        celestrak_last_poll: Optional[float] = None
        try:
            if os.path.exists(celestrak_cache_path):
                with open(celestrak_cache_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    raw_ts = cache_data.get("last_poll_ts")
                    now = time.time()
                    # 校验时间戳范围：拒绝损坏或未初始化的值（0、负数），防止速率保护因错误数据卡死
                    if raw_ts is not None and raw_ts > 1e8 and raw_ts <= now:
                        celestrak_last_poll = raw_ts
                        log.debug("已加载 CelesTrak 轮询缓存，上次轮询时间戳: %s", celestrak_last_poll)
                    else:
                        log.warning("CelesTrak 轮询缓存时间戳无效（%s），将忽略", raw_ts)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("CelesTrak 轮询缓存加载失败: %s", e)

        while True:
            # 检查距上次轮询的时间间隔，确保满足最小速率限制
            if celestrak_last_poll is not None:
                secs_since = time.time() - celestrak_last_poll
                if secs_since < CELESTRAK_INTERVAL:
                    wait_seconds = CELESTRAK_INTERVAL - secs_since
                    log.warning(
                        "距上次 CelesTrak 轮询 %.0f 分钟，需等待 %.0f 分钟（速率限制保护）",
                        secs_since / 60,
                        wait_seconds / 60,
                    )
                    write_log_message(
                        f"距上次 CelesTrak 轮询 {secs_since / 60:.0f} 分钟，需等待 {wait_seconds / 60:.0f} 分钟"
                    )
                    # 分片等待，每 60s 检查配置变更
                    _waited = 0
                    while _waited < wait_seconds:
                        chunk = min(wait_seconds - _waited, 60)
                        time.sleep(chunk)
                        _waited += chunk
                        _check_config_reload(prev_data, last_hash)
                else:
                    write_log_message(f"距上次 CelesTrak 轮询 {secs_since / 60:.0f} 分钟，满足速率限制")
            else:
                log.info("无 CelesTrak 轮询历史记录，将立即执行首次查询")
                write_log_message("无 CelesTrak 轮询历史记录，将立即执行首次查询")

            _check_config_reload(prev_data, last_hash)

            write_log_message(
                f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 开始 CelesTrak 轮询"
            )

            ok = run_celestrak_cycle(prev_data, last_hash, consecutive_failures)
            if ok:
                consecutive_failures["count"] = 0
                active_source = "celestrak"
            else:
                consecutive_failures["count"] += 1
                write_log_message(f"CelesTrak 本轮全部失败，连续失败 {consecutive_failures['count']} 次")

                # 备源切换
                if (consecutive_failures["count"] >= FALLBACK_THRESHOLD
                        and FALLBACK_SOURCE == "spacetrack"
                        and _st_required):
                    if active_source != "spacetrack":
                        write_log_message("切换到备源 Space-Track")
                        write_log_message(f"备源切换：celestrak → spacetrack（连续失败 {consecutive_failures['count']} 次）")
                    active_source = "spacetrack"
                    # Space-Track 备源：单次批量拉取
                    with SpaceTrackSession() as st_tmp:
                        if st_tmp.ensure_fresh_session():
                            all_records = fetch_bulk_with_relogin(st_tmp)
                            if all_records:
                                consecutive_failures["count"] = 0
                                active_source = "celestrak"  # 下轮尝试回主源
                                cache.save_raw_records(all_records)
                                raw_records = filter_by_norad(all_records, NORAD_IDS)
                                # 注入来源标识
                                for rec in raw_records.values():
                                    rec.setdefault("_source", "spacetrack")
                                process_records(raw_records, prev_data, last_hash, cache)
                                cache.clear_pending()
                            else:
                                log.error("备源 Space-Track 登录失败或请求失败，请检查凭据是否过期")
                        else:
                            log.error("备源 Space-Track 登录失败，请检查凭据是否过期")
            
            # 更新轮询时间戳（每次轮询完成后记录，使用 time.time() 跨重启有效）
            celestrak_last_poll = time.time()
            try:
                with open(celestrak_cache_path, "w", encoding="utf-8") as f:
                    json.dump({"last_poll_ts": celestrak_last_poll}, f)
            except OSError as e:
                log.warning("CelesTrak 轮询时间戳保存失败: %s", e)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已停止监控")