from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

import telegram_bot as bot


@pytest.fixture()
def bot_state() -> Iterator[None]:
    """保存并恢复 _ALLOWED_CHAT_ID，避免用例间串扰。"""
    original = bot._ALLOWED_CHAT_ID
    yield
    bot._ALLOWED_CHAT_ID = original


def test_main_keyboard_enabled() -> None:
    kb = bot._build_main_keyboard(True, 3)
    assert "已开" in kb["inline_keyboard"][0][0]["text"]
    assert kb["inline_keyboard"][0][0]["callback_data"] == "toggle"


def test_main_keyboard_disabled() -> None:
    kb = bot._build_main_keyboard(False, 0)
    assert "已关" in kb["inline_keyboard"][0][0]["text"]
    assert "(0)" in kb["inline_keyboard"][1][0]["text"]


def test_watched_keyboard_with_label_and_plain() -> None:
    watched = [
        {"intldes_prefix": "2026-085", "label": "Starlink"},
        {"intldes_prefix": "2026-092"},
    ]
    kb = bot._build_watched_keyboard(watched)
    assert "2026-085 · Starlink" in kb["inline_keyboard"][0][0]["text"]
    assert kb["inline_keyboard"][1][0]["text"] == "🗑 2026-092"
    assert kb["inline_keyboard"][0][0]["callback_data"] == "remove:2026-085"
    assert kb["inline_keyboard"][-1][0]["callback_data"] == "refresh"


def test_watched_keyboard_supports_legacy_string() -> None:
    kb = bot._build_watched_keyboard(["2026-085"])
    assert kb["inline_keyboard"][0][0]["text"] == "🗑 2026-085"
    assert kb["inline_keyboard"][0][0]["callback_data"] == "remove:2026-085"


def test_watched_keyboard_empty() -> None:
    kb = bot._build_watched_keyboard([])
    assert len(kb["inline_keyboard"]) == 1
    assert kb["inline_keyboard"][0][0]["callback_data"] == "refresh"


def test_status_text_enabled() -> None:
    status = {
        "enabled": True,
        "last_check_ts": "2026-07-14 17:10 UTC",
        "last_debut_ts": "2026-07-13 22:05 UTC",
        "total_processed": 47,
        "watched_launches_count": 3,
        "next_check_at": "2026-07-15 17:10 UTC",
    }
    text = bot._build_status_text(status)
    assert "已启用" in text
    assert "2026-07-14 17:10 UTC" in text
    assert "47" in text
    assert "2026-07-15 17:10 UTC" in text


def test_status_text_disabled() -> None:
    assert "已关闭" in bot._build_status_text({"enabled": False})


def test_watched_text_with_items() -> None:
    watched = [
        {"intldes_prefix": "2026-085", "label": "Starlink"},
        {"intldes_prefix": "2026-092"},
    ]
    text = bot._build_watched_text(watched)
    assert "Starlink" in text
    assert "2026-085" in text
    assert "2026-092" in text


def test_watched_text_empty() -> None:
    assert "暂无关注项" in bot._build_watched_text([])


def test_unauthorized_message_ignored(bot_state: None) -> None:
    bot._ALLOWED_CHAT_ID = 12345
    with patch.object(bot, "_send_message") as send_message:
        bot._handle_message({"chat": {"id": 999999}, "text": "/status"})
    send_message.assert_not_called()


def test_authorized_help_sends_message(bot_state: None) -> None:
    bot._ALLOWED_CHAT_ID = 12345
    with patch.object(bot, "_send_message") as send_message:
        bot._handle_message({"chat": {"id": 12345}, "text": "/help"})
    send_message.assert_called_once()
    assert "/help" in send_message.call_args.args[0]


def test_unauthorized_callback_ignored(bot_state: None) -> None:
    bot._ALLOWED_CHAT_ID = 12345
    cb = {
        "id": "cb_001",
        "message": {"chat": {"id": 999999}, "message_id": 1},
        "data": "toggle",
    }
    with patch.object(bot, "_answer_callback") as answer, patch.object(
        bot, "_toggle_discovery"
    ) as toggle:
        bot._handle_callback(cb)
    answer.assert_not_called()
    toggle.assert_not_called()
