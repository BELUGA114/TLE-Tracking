"""共享日志配置

用法:
    from common.logging_config import setup_logging
    setup_logging("monitor")   # 或 "bot" / "backend"

环境变量:
    LOG_LEVEL              全局日志级别，默认 INFO
    LOG_LEVEL_<MODULE>     覆盖特定 logger 级别，如 LOG_LEVEL_xpropagator_client=DEBUG
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

# 第三方库日志静默列表
_THIRD_PARTY_LOGGERS = ("httpx", "urllib3", "asyncio", "aiohttp")

# 有效的日志级别名
_LEVEL_NAMES = {"DEBUG", "INFO", "WARNING", "ERROR"}


def _parse_level(name: str) -> int:
    """将字符串级别名转为 logging 级别常量，无效时降级 INFO 并报警。"""
    name = name.upper().strip()
    if name in _LEVEL_NAMES:
        return getattr(logging, name)
    # 回退：输出版权信息到 stderr 后降级 INFO
    print(
        f"[logging_config] 无效的日志级别 '{name}'，已降级为 INFO",
        file=sys.stderr,
    )
    return logging.INFO


def _silence_third_party() -> None:
    """将第三方库 logger 级别设为 WARNING，防止噪音日志污染输出。"""
    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _apply_module_overrides(default_level: int) -> None:
    """遍历环境变量，匹配 LOG_LEVEL_<MODULE>=LEVEL 模式并覆盖。"""
    prefix = "LOG_LEVEL_"
    applied: list[str] = []
    for key, value in os.environ.items():
        if not key.startswith(prefix) or key == "LOG_LEVEL":
            continue
        module_name = key[len(prefix):].lower()
        if not module_name:
            continue
        level = _parse_level(value)
        logging.getLogger(module_name).setLevel(level)
        applied.append(f"{module_name}={value}")
    if applied:
        # 用根 logger 输出（尚未配置 format，使用 basicConfig 默认格式）
        logging.getLogger(__name__).debug(
            "模块级别覆盖已应用: %s", ", ".join(applied),
        )


def setup_logging(module_tag: str = "") -> None:
    """初始化日志系统，必须在入口模块中显式调用。

    module_tag 会出现在每行日志的时间戳后面，用于区分多进程日志来源。
    """
    load_dotenv()

    level_name = os.getenv("LOG_LEVEL", "INFO")
    level = _parse_level(level_name)

    # 格式: 2026-07-16 14:30:05 [INFO] [monitor] 消息内容
    tag_part = f"[{module_tag}] " if module_tag else ""
    logging.basicConfig(
        level=level,
        format=f"%(asctime)s [%(levelname)s] {tag_part}%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _silence_third_party()
    _apply_module_overrides(level)
