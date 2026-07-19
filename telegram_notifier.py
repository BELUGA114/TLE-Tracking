"""Telegram Bot 消息推送模块

通过 Telegram Bot API sendMessage 发送新编目通知。
缺失 token/chat_id 时静默降级（不推送，不影响主循环）。

用法:
    from telegram_notifier import TelegramNotifier
    notifier = TelegramNotifier(token="...", chat_id="...")
    notifier.send("<b>Hello</b>")
    notifier.send_debut(record, watched=True)
"""

from __future__ import annotations

import html
import logging
import time

import requests

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Telegram Bot 消息推送器。token/chat_id 缺失时静默降级。"""

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token.strip() if token else ""
        self._chat_id = chat_id.strip() if chat_id else ""
        self._active = bool(self._token and self._chat_id)
        self._session = requests.Session()
        if not self._active:
            log.warning(
                "Telegram 通知未配置：缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，"
                "新编目对象将不会推送"
            )

    @property
    def active(self) -> bool:
        """是否已配置凭据，可以发送消息"""
        return self._active

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        """发送一条消息到配置的 chat_id，失败自动重试。

        Args:
            text: 消息正文（已格式化，需调用方自行做 HTML 转义或标签拼接）
            parse_mode: Telegram parse_mode，默认 "HTML"

        Returns:
            True 发送成功，False 全部重试失败（已打 WARNING 日志）
        """
        if not self._active:
            log.debug("Telegram 未配置，跳过发送")
            return False

        url = TELEGRAM_API.format(token=self._token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }

        for attempt in range(1, 4):
            try:
                resp = self._session.post(url, json=payload, timeout=15)
            except requests.RequestException as e:
                wait = 2 ** (attempt - 1)
                log.warning(
                    "Telegram 发送失败（第 %d/3 次）: %s，%d 秒后重试",
                    attempt, e, wait,
                )
                if attempt < 3:
                    time.sleep(wait)
                continue

            if resp.status_code == 429:
                # 频率限制：严格遵循 Retry-After 响应头
                retry_after = resp.headers.get("Retry-After", "30")
                try:
                    wait = int(retry_after)
                except ValueError:
                    wait = 30
                log.warning(
                    "Telegram 429 频率限制（第 %d/3 次），等待 %d 秒",
                    attempt, wait,
                )
                if attempt < 3:
                    time.sleep(wait)
                continue

            if resp.status_code == 400:
                # 格式错误：不重试，打 ERROR 日志包含消息内容
                body = resp.text[:500]
                log.error(
                    "Telegram 400 格式错误，消息被拒绝。响应: %s，消息内容: %s",
                    body, text[:300],
                )
                return False

            if resp.status_code != 200:
                wait = 2 ** (attempt - 1)
                log.warning(
                    "Telegram HTTP %d（第 %d/3 次）: %s，%d 秒后重试",
                    resp.status_code, attempt, resp.text[:200], wait,
                )
                if attempt < 3:
                    time.sleep(wait)
                continue

            # 成功
            return True

        log.warning("Telegram 消息发送失败，已达最大重试次数")
        return False

    @staticmethod
    def escape(text: str) -> str:
        """转义 HTML 特殊字符，用于 Telegram HTML parse mode"""
        return html.escape(str(text), quote=False)

    def send_debut(self, record: dict, watched: bool = False, label: str = "") -> bool:
        """格式化并发送一条新编目通知。

        satcat_debut 返回的字段参考（modeldef 确认）：
          身份: NORAD_CAT_ID, OBJECT_NAME, OBJECT_ID, INTLDES, DEBUT
          轨道: PERIOD, INCLINATION, APOGEE, PERIGEE
          发射: LAUNCH, SITE, COUNTRY, LAUNCH_YEAR, LAUNCH_NUM, LAUNCH_PIECE
        """
        e = self.escape
        name = e(str(record.get("OBJECT_NAME") or "?"))
        norad_id = str(record.get("NORAD_CAT_ID") or "?")
        intldes = e(str(record.get("OBJECT_ID") or record.get("INTLDES") or "?"))
        debut = e(str(record.get("DEBUT") or "?"))

        perigee = record.get("PERIGEE")
        apogee = record.get("APOGEE")
        period = record.get("PERIOD")
        incl = record.get("INCLINATION")
        launch = record.get("LAUNCH")
        site = record.get("SITE")
        country = record.get("COUNTRY")

        if watched and label:
            watched_label = f"  <i>🔍 关注中 — {e(label)}</i>"
        elif watched:
            watched_label = "  <i>🔍 关注中</i>"
        else:
            watched_label = ""

        # 轨道参数行：只在有数据时才显示
        orbit_parts: list[str] = []
        if perigee is not None and apogee is not None:
            orbit_parts.append(f"<b>近地点:</b> {e(str(perigee))} km  <b>远地点:</b> {e(str(apogee))} km")
        elif perigee is not None:
            orbit_parts.append(f"<b>近地点:</b> {e(str(perigee))} km")
        elif apogee is not None:
            orbit_parts.append(f"<b>远地点:</b> {e(str(apogee))} km")
        if incl is not None:
            orbit_parts.append(f"<b>倾角:</b> {e(str(incl))}°")
        if period is not None:
            orbit_parts.append(f"<b>周期:</b> {e(str(period))} min")

        # 发射信息行
        launch_parts: list[str] = []
        if launch:
            launch_parts.append(f"<b>发射:</b> {e(str(launch))}")
        if site:
            launch_parts.append(f"<b>发射场:</b> {e(str(site))}")
        if country:
            launch_parts.append(f"<b>国家:</b> {e(str(country))}")

        lines = [
            f"<b>🛰 新编目 PAYLOAD</b>{watched_label}",
            "",
            f"<b>名称:</b> {name}",
            f"<b>NORAD ID:</b> <code>{e(norad_id)}</code>",
            f"<b>国际编号:</b> {intldes}",
            f"<b>编目时间:</b> {debut} UTC",
        ]
        if orbit_parts:
            lines.append("  ".join(orbit_parts))
        if launch_parts:
            lines.append("  ".join(launch_parts))
        lines += [
            "",
            f'<a href="https://www.n2yo.com/satellite/?s={e(norad_id)}">N2YO</a>'
            f"  |  "
            f'<a href="https://celestrak.org/satcat/records.php?CATNR={e(norad_id)}">CelesTrak</a>',
        ]

        return self.send("\n".join(lines))

    def send_summary(self, count: int, note: str = "") -> bool:
        """发送摘要消息（无新对象的静默确认或宕机恢复说明）。

        Args:
            count: 新发现对象数量
            note: 附加说明，如宕机恢复提示
        """
        e = self.escape
        if note:
            text = (
                f"<b>📡 SATCAT 每日检查</b>\n"
                f"\n"
                f"本日新编目 PAYLOAD: <b>{count}</b> 个\n"
                f"\n"
                f"<i>{e(note)}</i>"
            )
        else:
            text = (
                f"<b>📡 SATCAT 每日检查</b>\n"
                f"\n"
                f"本日新编目 PAYLOAD: <b>{count}</b> 个"
            )
        return self.send(text)
