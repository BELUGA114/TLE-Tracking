"""xpropagator gRPC 客户端插件式封装

依赖：grpcio grpcio-tools
Proto 定义参见 api/v1/ 目录。"""

from __future__ import annotations

import logging
import math
import time
from datetime import UTC, datetime
from typing import NamedTuple

log = logging.getLogger(__name__)

# ── 懒加载 gRPC 存根 ─────────────────────────────────────────────────────────────
# 未安装 grpcio 或未编译 proto 时，主脚本仍可正常运行（降级到简单 5km 规则）
_GRPC_AVAILABLE = False
try:
    import grpc
    from google.protobuf import empty_pb2
    from google.protobuf.timestamp_pb2 import Timestamp

    from api.v1 import common_pb2  # Satellite, EphemerisData
    from api.v1 import main_pb2_grpc as pb2_grpc
    from api.v1.core import prop_pb2  # PropRequest, PropTask, TimeType
    _GRPC_AVAILABLE = True
    log.debug("xpropagator gRPC 存根加载成功")
except ImportError as _e:
    _GRPC_AVAILABLE = False
    log.debug("xpropagator 存根未就绪（%s），残差分析不可用", _e)


# ── 默认连接参数 ──────────────────────────────────────────────────────────────────
XPROP_HOST: str   = "localhost"
XPROP_PORT: int   = 50051
_CONNECT_TIMEOUT: float = 3.0    # gRPC 连接超时（秒）
_CALL_TIMEOUT:    float = 10.0   # 单次 RPC 调用超时（秒）

# 尝试从 config.yaml 加载 xpropagator 地址（若存在则覆盖默认值）
try:
    import os as _os

    import yaml as _yaml
    _script_dir = _os.path.dirname(_os.path.abspath(__file__))
    _cfg_path = _os.path.join(_script_dir, "config.yaml")
    if _os.path.exists(_cfg_path):
        with open(_cfg_path, encoding="utf-8") as _f:
            _cfg_data = _yaml.safe_load(_f) or {}
        _xprop_cfg = _cfg_data.get("xpropagator", {})
        if _xprop_cfg.get("host"):
            XPROP_HOST = str(_xprop_cfg["host"])
        if _xprop_cfg.get("port"):
            XPROP_PORT = int(_xprop_cfg["port"])
except Exception:
    pass


class StateVector(NamedTuple):
    """ECI 笛卡尔状态向量（km, km/s）"""
    x:  float
    y:  float
    z:  float
    vx: float
    vy: float
    vz: float


# ── 内部工具函数 ──────────────────────────────────────────────────────────────────

def _parse_epoch_utc(epoch_str: str) -> datetime | None:
    """
    解析 ISO 时间字符串为 UTC datetime 对象。
    
    支持格式：
    - 带/不带微秒："%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"
    - 空格分隔："%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"
    - 带时区："%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"
    
    如果输入无时区信息，假设为 UTC；如果有时区，转换为 UTC。
    解析失败返回 None。
    """
    if not epoch_str or not isinstance(epoch_str, str):
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        # 带时区的格式
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            dt = datetime.strptime(epoch_str, fmt)
            # 如果有时区信息，转换为 UTC；否则假设为 UTC
            if dt.tzinfo is not None:
                return dt.astimezone(UTC)
            else:
                return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    log.warning("xprop: 无法解析历元字符串: %s", epoch_str)
    return None


def _dt_to_pb_timestamp(dt: datetime) -> Timestamp:
    # 将 Python datetime（带 tzinfo）转换为 protobuf Timestamp
    ts = Timestamp()
    ts.FromDatetime(dt.astimezone(UTC))
    return ts


# ── 核心 API ──────────────────────────────────────────────────────────────────────

def propagate_tle(
    norad_id:    int,
    name:        str,
    tle1:        str,
    tle2:        str,
    target_time: datetime,
    host:        str = XPROP_HOST,
    port:        int = XPROP_PORT,
) -> StateVector | None:
    """
    调用 xpropagator Prop RPC，将 TLE 传播到 target_time（UTC）。
    返回：ECI 状态向量（km / km·s⁻¹），失败时返回 None。
    每次调用都创建新 channel（满足插件式/无状态设计，避免长连接管理）。
    """
    if not _GRPC_AVAILABLE:
        return None

    try:
        channel = grpc.insecure_channel(
            f"{host}:{port}",
            options=[("grpc.connect_timeout_ms", int(_CONNECT_TIMEOUT * 1000))],
        )
        stub = pb2_grpc.PropagatorStub(channel)

        # 生成伪 NORAD ID：80000-99999 区间无已分配卫星编号，不会与真实卫星冲突
        # hash() 进程级加盐确保重启后 ID 不同，绕过 xpropagator 服务端 TLE 缓存
        fake_id = 80000 + (hash(f"{norad_id}:{tle1}:{tle2}") % 20000)

        spoof_tle1, spoof_tle2 = _spoof_catalog_id(tle1, tle2, fake_id)

        # req_id：微秒时间戳为高位 + norad_id + fake_id，三值打包确保 int64 内唯一
        req_id = int(time.time() * 1000000) + norad_id * 100000 + fake_id
        
        request = prop_pb2.PropRequest(
            req_id=req_id,
            time_type=prop_pb2.TimeMse,  # SGP4 内部使用 MSE 时间系统（Space-Track Report #3），不能替换为 UTC
            task=prop_pb2.PropTask(
                time_utc=_dt_to_pb_timestamp(target_time),
                sat=common_pb2.Satellite(  # ← 从 common_pb2 取
                    norad_id=fake_id,  # 使用伪 ID 绕过缓存
                    name=name,
                    tle_ln1=spoof_tle1,   # 使用替换后的 TLE
                    tle_ln2=spoof_tle2,
                ),
            ),
        )
        resp = stub.Prop(request, timeout=_CALL_TIMEOUT)
        r = resp.result
        return StateVector(r.x, r.y, r.z, r.vx, r.vy, r.vz)

    except Exception as exc:
        log.warning("xpropagator RPC 失败 [NORAD %d @ %s]: %s",
                    norad_id, target_time.isoformat(), exc)
        return None
    finally:
        try:
            channel.close()
        except Exception:
            pass


def position_residual_km(sv_a: StateVector, sv_b: StateVector) -> float:
    """计算两个状态向量间的位置残差（欧氏距离，km）"""
    return math.sqrt(
        (sv_a.x - sv_b.x) ** 2
        + (sv_a.y - sv_b.y) ** 2
        + (sv_a.z - sv_b.z) ** 2
    )

def _resolve_tle(orbit_dict: dict) -> tuple[str, str] | None:
    """从 orbit dict 获取 TLE，优先使用现成数据，缺失时从 _raw_elements 合成。"""
    tle1, tle2 = orbit_dict.get("tle1", ""), orbit_dict.get("tle2", "")
    if tle1 and tle2:  # 完整性校验
        return tle1, tle2

    raw = orbit_dict.get("_raw_elements")
    if not raw:
        log.warning("xprop: 无 TLE 且无 _raw_elements [NORAD %d]", orbit_dict.get("norad"))
        return None

    log.debug("xprop: 无 TLE，从 _raw_elements 合成 [NORAD %d]", orbit_dict.get("norad"))
    try:
        result = gp_json_to_tle_lines(raw)
        return result
    except Exception as e:
        log.error("xprop: TLE 合成失败 [NORAD %d]: %s", orbit_dict.get("norad"), e)
        return None

def classify_change_xprop(
    orbit:                  dict,
    prev:                   dict,
    maneuver_threshold_km:  float = 5.0,
    host:                   str   = XPROP_HOST,
    port:                   int   = XPROP_PORT,
) -> str | None:
    """
    使用 xpropagator（USSF SGP4/SGP4-XP）做残差分析判断 TLE 变化性质。

    比较时刻选取：新 TLE 的历元（两 TLE 最接近的公共参考时刻）

    残差含义：
      Δr ≥ maneuver_threshold_km  →  "maneuver"   （疑似真实机动）
      Δr <  maneuver_threshold_km  →  "correction" （疑似解算修正/噪声）

    返回 None 表示 xpropagator 服务不可用，主脚本应降级到简单规则。

    当 orbit/prev 的 tle1/tle2 字段为空时（5 位编号耗尽后），
    自动从 _raw_elements 合成 TLE 两行后再调用 xpropagator
    """

    if not _GRPC_AVAILABLE:
        return None

    # 以新 TLE 历元作为公共比较时刻
    epoch_dt = _parse_epoch_utc(orbit.get("epoch", ""))
    if epoch_dt is None:
        return None

    prev_tles  = _resolve_tle(prev)
    orbit_tles = _resolve_tle(orbit)
    if prev_tles is None or orbit_tles is None:
        return None

    prev_tle1,  prev_tle2  = prev_tles
    new_tle1,   new_tle2   = orbit_tles

    # 旧 TLE 预报到新历元 → "如果没有机动，卫星应在哪里"
    # 使用 prev 的卫星标识（NORAD ID 和名称）
    prev_norad = prev["norad"]
    prev_name = prev.get("name", "")
    sv_predicted = propagate_tle(
        prev_norad, prev_name,
        prev_tle1, prev_tle2,  # 使用解析后的 TLE（可能从 _raw_elements 合成）
        epoch_dt, host, port,
    )
    if sv_predicted is None:
        return None

    # 新 TLE 在其历元时刻的初始状态（MSE=0 点，即 TLE 定义的参考状态）
    # 使用 orbit 的卫星标识（NORAD ID 和名称）
    orbit_norad = orbit["norad"]
    orbit_name = orbit.get("name", "")
    sv_new_epoch = propagate_tle(
        orbit_norad, orbit_name,
        new_tle1, new_tle2,  # 使用解析后的 TLE（可能从 _raw_elements 合成）
        epoch_dt, host, port,
    )
    if sv_new_epoch is None:
        return None

    delta_km = position_residual_km(sv_predicted, sv_new_epoch)
    verdict  = "maneuver" if delta_km >= maneuver_threshold_km else "correction"

    log.info(
        "xprop 残差 @ %s：Δr = %.3f km（阈值 %.1f km）→ %s",
        epoch_dt.strftime("%Y-%m-%dT%H:%MZ"),
        delta_km,
        maneuver_threshold_km,
        verdict.upper(),
    )
    return verdict


def is_service_alive(host: str = XPROP_HOST, port: int = XPROP_PORT) -> bool:
    """
    探活：检查 xpropagator 服务是否响应（调用 Info RPC）
    可在启动时调用一次，用于日志提示。
    """
    if not _GRPC_AVAILABLE:
        return False
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        stub = pb2_grpc.PropagatorStub(channel)
        resp = stub.Info(empty_pb2.Empty(), timeout=_CONNECT_TIMEOUT)
        channel.close()
        log.debug("xpropagator 已连接：%s %s", resp.name, resp.version)
        return True
    except Exception as exc:
        log.warning("xpropagator 服务探活失败: %s", exc)
        return False

def _tle_checksum(line: str) -> int:
    """计算 TLE 行校验位（末位数字）
    
    注意：line 应为完整的 69 字符 TLE 行（含占位符校验位），
    函数会对前 68 个字符计算校验和。
    """
    total = 0
    for ch in line[:-1]:  # 不含最后一位（占位符或旧校验位）
        if ch.isdigit():
            total += int(ch)
        elif ch == '-':
            total += 1
    return total % 10


"""
服务端的 satKey 就是 TLE 第一行的卫星编号，不是 TLE 内容的哈希
同一编号第一次加载后就常驻缓存，后续传入再不同的 TLE 都被忽略
这个设计对长期追踪同一颗卫星合理，但对用两组不同 TLE 做残差比较完全不可用
"""

# 没有办法的办法：使用 fake_id 创建一个临时的 TLE
def _spoof_catalog_id(tle1: str, tle2: str, fake_id: int) -> tuple[str, str]:
    """
    替换 TLE 中的卫星编号为 fake_id 并重算校验位，用于绕过 xpropagator 缓存。
    """
    # 防御：去除首尾空白
    tle1 = tle1.strip()
    tle2 = tle2.strip()
    
    # 确保长度至少 7 字符（容纳编号替换），不足填充，超出截断
    if len(tle1) < 7 or len(tle1) < 69:
        tle1 = tle1.ljust(69)
    elif len(tle1) > 69:
        tle1 = tle1[:69]
        
    if len(tle2) < 7 or len(tle2) < 69:
        tle2 = tle2.ljust(69)
    elif len(tle2) > 69:
        tle2 = tle2[:69]

    id_str = f"{fake_id:5d}"  # 5位右对齐

    # 替换 line1 卫星编号（列2-6，0-indexed）并重算校验位
    l1 = list(tle1)
    l1[2:7] = list(id_str)
    l1[68] = str(_tle_checksum("".join(l1)))
    new_tle1 = "".join(l1)

    # 替换 line2 卫星编号（列2-6，0-indexed）并重算校验位
    l2 = list(tle2)
    l2[2:7] = list(id_str)
    l2[68] = str(_tle_checksum("".join(l2)))
    new_tle2 = "".join(l2)

    return new_tle1, new_tle2

# TLE 合成辅助函数
# 用于在 TLE_LINE1/TLE_LINE2 缺失时（5位编号耗尽后 ~2026-07-20）从 GP JSON 根数重建 TLE 两行。
# xpropagator gRPC 接口只接受 TLE 文本，合成在客户端完成，服务端完全透明。

# Alpha-5 编目号编码表：100000-339999 映射到 5 字符字母数字格式
# A=10, B=11, ..., Z=33，跳过 I 和 O（避免与 1 和 0 混淆）
_ALPHA5_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # 24 个字母，不含 I/O


def _encode_alpha5(norad_id: int) -> str:
    """将 NORAD 编目号编码为 TLE 5 字符格式（≥100000 时使用 Alpha-5）。"""
    if norad_id < 100000:
        return f"{norad_id:5d}"
    tens = norad_id // 10000 - 10  # 10→0, 11→1, ..., 33→23
    if 0 <= tens < len(_ALPHA5_LETTERS):
        return f"{_ALPHA5_LETTERS[tens]}{norad_id % 10000:04d}"
    # 超出 Alpha-5 范围（>339999），回退到截断
    return f"{min(norad_id, 99999):5d}"

def _epoch_to_tle_str(epoch_str: str) -> str:
    """将 ISO 历元字符串转换为 TLE 历元格式 YYDDD.DDDDDDDD"""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        # 带时区的格式
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            dt = datetime.strptime(epoch_str, fmt)
            break
        except ValueError:
            continue
    else:
        log.warning("gp_json_to_tle_lines: 无法解析历元 '%s'，使用零值", epoch_str)
        return "00000.00000000"
    year_2d = dt.year % 100
    doy = dt.timetuple().tm_yday
    frac = (dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1e6) / 86400.0
    return f"{year_2d:02d}{doy + frac:012.8f}"


def _format_ndot(value: float) -> str:
    """格式化平均运动一阶导数为 TLE 格式（10字符: S.NNNNNNNN）"""
    sign = '-' if value < 0 else ' '
    # f"{abs:.8f}" → "0.NNNNNNNN"，去掉整数部分的 "0"
    frac_str = f"{abs(value):.8f}"[1:]   # ".NNNNNNNN"
    return f"{sign}{frac_str}"            # 共 10 字符


def _format_tle_decimal(value: float) -> str:
    """
    格式化为 TLE 空格科学计数法（8字符: SMMMMME±D）。
    约定：隐含小数点在最高位前，如 20347-3 表示 0.20347×10⁻³。
    """
    if value == 0.0:
        return " 00000-0"
    sign = '-' if value < 0 else ' '
    abs_val = abs(value)
    exp = math.floor(math.log10(abs_val)) + 1
    mantissa = abs_val / (10.0 ** exp)
    mantissa_int = min(round(mantissa * 100000), 99999)
    exp_sign = '+' if exp >= 0 else '-'
    return f"{sign}{mantissa_int:05d}{exp_sign}{abs(exp):1d}"


def _format_intl_designator(object_id: str) -> str:
    """将国际编号 '1998-067A' 转换为 TLE 格式 '98067A  '（8字符）"""
    try:
        if '-' in object_id:
            year_part, rest = object_id.split('-', 1)
            result = year_part[-2:] + rest.replace('-', '')
        else:
            result = object_id
        return result[:8].ljust(8)
    except Exception:
        return "        "

def gp_json_to_tle_lines(gp: dict) -> tuple[str, str]:
    """
    从 GP JSON 根数合成标准 TLE 两行（各 69 字符）

    ≥100000 的编目号使用 Alpha-5 编码（如 100000→A0000）。
    xpropagator 路径后续会通过 _spoof_catalog_id 替换为伪 ID，编码格式不影响传播。
    """
    norad_id = int(gp.get("NORAD_CAT_ID") or 0)
    cat_str = _encode_alpha5(norad_id)
    classification = str(gp.get("CLASSIFICATION_TYPE") or "U")[0]
    intl_desig = _format_intl_designator(str(gp.get("OBJECT_ID") or ""))
    epoch_tle = _epoch_to_tle_str(str(gp.get("EPOCH") or ""))
    ndot = float(gp.get("MEAN_MOTION_DOT") or 0.0)
    nddot = float(gp.get("MEAN_MOTION_DDOT") or 0.0)
    bstar = float(gp.get("BSTAR") or 0.0)
    ephem_type = int(gp.get("EPHEMERIS_TYPE") or 0)
    elem_set_no = int(gp.get("ELEMENT_SET_NO") or 0)
    incl = float(gp.get("INCLINATION") or 0.0)
    raan = float(gp.get("RA_OF_ASC_NODE") or 0.0)
    ecc = float(gp.get("ECCENTRICITY") or 0.0)
    argp = float(gp.get("ARG_OF_PERICENTER") or 0.0)
    ma = float(gp.get("MEAN_ANOMALY") or 0.0)
    mm = float(gp.get("MEAN_MOTION") or 0.0)
    rev = int(gp.get("REV_AT_EPOCH") or 0)

    # 离心率：去掉 "0." → 7位纯数字
    ecc_str = f"{ecc:.7f}"[2:]

    # ── Line 1（68字符正文 + 1字符校验）──
    # 列位（0-indexed）: [0]'1' [1]' ' [2:7]编号 [7]分类 [8]' ' [9:17]国际编号
    # [17]' ' [18:32]历元 [32]' ' [33:43]ndot [43]' ' [44:52]nddot
    # [52]' ' [53:61]bstar [61]' ' [62]星历类型 [63]' ' [64:68]根数集号 [68]校验
    line1_body = (
        f"1 "
        f"{cat_str}{classification} "
        f"{intl_desig} "
        f"{epoch_tle} "
        f"{_format_ndot(ndot)} "
        f"{_format_tle_decimal(nddot)} "
        f"{_format_tle_decimal(bstar)} "
        f"{ephem_type} "
        f"{elem_set_no:4d}"
    )
    if len(line1_body) != 68:
        raise ValueError(
            f"TLE Line 1 长度异常: 期望 68 字符，实际 {len(line1_body)} 字符。"
            f"可能原因：根数字段格式化错误或输入数据不完整。"
        )
    # "0"是占位符凑足69字符，_tle_checksum内部取前68字符忽略末位
    line1 = line1_body + str(_tle_checksum(line1_body + "0"))

    # ── Line 2（68字符正文 + 1字符校验）──
    # 列位（0-indexed）: [0]'2' [1]' ' [2:7]编号 [7]' ' [8:16]倾角 [16]' '
    # [17:25]升交点赤经 [25]' ' [26:33]离心率 [33]' ' [34:42]近地点辐角
    # [42]' ' [43:51]平近点角 [51]' ' [52:63]平均运动 [63:68]圈号 [68]校验
    line2_body = (
        f"2 "
        f"{cat_str} "
        f"{incl:8.4f} "
        f"{raan:8.4f} "
        f"{ecc_str} "
        f"{argp:8.4f} "
        f"{ma:8.4f} "
        f"{mm:11.8f}"  # 平均运动（11字符），直接拼接圈号
        f"{rev:5d}"
    )
    if len(line2_body) != 68:
        raise ValueError(
            f"TLE Line 2 长度异常: 期望 68 字符，实际 {len(line2_body)} 字符。"
            f"可能原因：根数字段格式化错误或输入数据不完整。"
        )
    # "0"是占位符凑足69字符，_tle_checksum内部取前68字符忽略末位
    line2 = line2_body + str(_tle_checksum(line2_body + "0"))

    return line1, line2