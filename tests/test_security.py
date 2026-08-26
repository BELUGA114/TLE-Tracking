from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.routers.config import toggle_discovery, update_config
from backend.security import (
    SlidingWindowRateLimiter,
    enforce_config_write_rate_limit,
    inject_cesium_token,
    require_dashboard_auth,
    serialize_javascript_string,
)


def test_serialization_cannot_close_script_element() -> None:
    value = 'token"\\</script><script>alert(1)</script>&\u2028\u2029'

    serialized = serialize_javascript_string(value)

    assert "</script" not in serialized.lower()
    assert "<" not in serialized
    assert ">" not in serialized
    assert "&" not in serialized
    assert "\u2028" not in serialized
    assert "\u2029" not in serialized
    assert r"\u003c/script\u003e" in serialized
    assert serialized.startswith('"')
    assert serialized.endswith('"')


def test_html_injection_replaces_only_the_token_placeholder() -> None:
    html = '<script>window.CESIUM_ION_TOKEN="";</script>'

    injected = inject_cesium_token(html, "client-token")

    assert injected == '<script>window.CESIUM_ION_TOKEN="client-token";</script>'


def test_missing_server_key_disables_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)

    with pytest.raises(HTTPException) as caught:
        require_dashboard_auth(None)

    assert caught.value.status_code == 503


def test_missing_or_wrong_client_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_API_KEY", "expected")
    wrong = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")

    for credentials in (None, wrong):
        with pytest.raises(HTTPException) as caught:
            require_dashboard_auth(credentials)
        assert caught.value.status_code == 401


def test_matching_client_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_API_KEY", "expected")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expected")

    require_dashboard_auth(credentials)


def test_requests_over_burst_are_rejected_until_window_expires() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10, max_identities=10)

    limiter.check("client", now=100.0)
    limiter.check("client", now=101.0)
    with pytest.raises(HTTPException) as caught:
        limiter.check("client", now=102.0)

    assert caught.value.status_code == 429
    limiter.check("client", now=111.1)


def test_identity_cache_is_bounded() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10, max_identities=2)

    limiter.check("first", now=100.0)
    limiter.check("second", now=101.0)
    limiter.check("third", now=102.0)

    assert limiter.identity_count <= 2


@pytest.mark.parametrize("endpoint", [update_config, toggle_discovery])
def test_all_config_write_routes_use_auth_and_rate_limit_dependencies(endpoint) -> None:
    dependency_calls = [
        parameter.default.dependency
        for parameter in inspect.signature(endpoint).parameters.values()
        if hasattr(parameter.default, "dependency")
    ]

    assert require_dashboard_auth in dependency_calls
    assert enforce_config_write_rate_limit in dependency_calls
    assert dependency_calls.index(enforce_config_write_rate_limit) < dependency_calls.index(
        require_dashboard_auth
    )
