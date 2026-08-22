from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

import telegram_bot as bot


@pytest.fixture()
def bot_state() -> Iterator[None]:
    """保存并恢复模块级状态，避免用例间串扰。"""
    original_allowed_chat_id = bot._ALLOWED_CHAT_ID
    original_api_key = bot._runtime_api_key
    bot._ALLOWED_CHAT_ID = 12345
    bot._set_api_key("environment-key")
    yield
    bot._ALLOWED_CHAT_ID = original_allowed_chat_id
    bot._set_api_key(original_api_key)


def test_authorized_command_updates_runtime_header_without_echoing_key(bot_state: None) -> None:
    secret = "rotated-secret"
    message = {
        "chat": {"id": 12345},
        "message_id": 77,
        "text": f"/setapikey {secret}",
    }

    with patch.object(bot, "_send_message") as send_message, patch.object(
        bot, "_delete_message"
    ) as delete_message, patch.object(bot, "_get_status") as get_status:
        bot._handle_message(message)

    assert bot._api_headers()["Authorization"] == f"Bearer {secret}"
    response_text = " ".join(str(call) for call in send_message.call_args_list)
    assert secret not in response_text
    delete_message.assert_called_once_with(12345, 77)
    get_status.assert_not_called()


def test_unauthorized_chat_cannot_update_runtime_key(bot_state: None) -> None:
    message = {
        "chat": {"id": 99999},
        "message_id": 78,
        "text": "/setapikey stolen",
    }

    bot._handle_message(message)

    assert bot._api_headers()["Authorization"] == "Bearer environment-key"


def test_empty_command_keeps_existing_key(bot_state: None) -> None:
    message = {"chat": {"id": 12345}, "message_id": 79, "text": "/setapikey"}

    with patch.object(bot, "_send_message") as send_message:
        bot._handle_message(message)

    assert bot._api_headers()["Authorization"] == "Bearer environment-key"
    assert "用法" in send_message.call_args.args[0]


def test_delete_failure_warns_user_without_echoing_key(bot_state: None) -> None:
    secret = "rotated-secret"
    message = {
        "chat": {"id": 12345},
        "message_id": 80,
        "text": f"/setapikey {secret}",
    }

    with patch.object(bot, "_send_message") as send_message, patch.object(
        bot, "_delete_message", return_value=False
    ):
        bot._handle_message(message)

    response = send_message.call_args.args[0]
    assert "手动删除" in response
    assert secret not in response
