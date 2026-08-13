from __future__ import annotations

import os
import inspect
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.security import (
    SlidingWindowRateLimiter,
    enforce_config_write_rate_limit,
    inject_cesium_token,
    require_dashboard_auth,
    serialize_javascript_string,
)
from backend.routers.config import toggle_discovery, update_config


class JavascriptSerializationTests(unittest.TestCase):
    def test_serialization_cannot_close_script_element(self) -> None:
        value = 'token"\\</script><script>alert(1)</script>&\u2028\u2029'

        serialized = serialize_javascript_string(value)

        self.assertNotIn("</script", serialized.lower())
        self.assertNotIn("<", serialized)
        self.assertNotIn(">", serialized)
        self.assertNotIn("&", serialized)
        self.assertNotIn("\u2028", serialized)
        self.assertNotIn("\u2029", serialized)
        self.assertIn(r"\u003c/script\u003e", serialized)
        self.assertTrue(serialized.startswith('"'))
        self.assertTrue(serialized.endswith('"'))

    def test_html_injection_replaces_only_the_token_placeholder(self) -> None:
        html = '<script>window.CESIUM_ION_TOKEN="";</script>'

        injected = inject_cesium_token(html, "client-token")

        self.assertEqual(
            injected,
            '<script>window.CESIUM_ION_TOKEN="client-token";</script>',
        )


class DashboardAuthenticationTests(unittest.TestCase):
    def test_missing_server_key_disables_writes(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                require_dashboard_auth(None)

        self.assertEqual(caught.exception.status_code, 503)

    def test_missing_or_wrong_client_key_is_rejected(self) -> None:
        wrong = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "expected"}, clear=True):
            for credentials in (None, wrong):
                with self.subTest(credentials=credentials):
                    with self.assertRaises(HTTPException) as caught:
                        require_dashboard_auth(credentials)
                    self.assertEqual(caught.exception.status_code, 401)

    def test_matching_client_key_is_accepted(self) -> None:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expected")
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "expected"}, clear=True):
            require_dashboard_auth(credentials)


class ConfigWriteRateLimiterTests(unittest.TestCase):
    def test_requests_over_burst_are_rejected_until_window_expires(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10, max_identities=10)

        limiter.check("client", now=100.0)
        limiter.check("client", now=101.0)
        with self.assertRaises(HTTPException) as caught:
            limiter.check("client", now=102.0)

        self.assertEqual(caught.exception.status_code, 429)
        limiter.check("client", now=111.1)

    def test_identity_cache_is_bounded(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10, max_identities=2)

        limiter.check("first", now=100.0)
        limiter.check("second", now=101.0)
        limiter.check("third", now=102.0)

        self.assertLessEqual(limiter.identity_count, 2)


class ConfigRouteSecurityTests(unittest.TestCase):
    def test_all_config_write_routes_use_auth_and_rate_limit_dependencies(self) -> None:
        for endpoint in (update_config, toggle_discovery):
            dependency_calls = [
                parameter.default.dependency
                for parameter in inspect.signature(endpoint).parameters.values()
                if hasattr(parameter.default, "dependency")
            ]
            with self.subTest(endpoint=endpoint.__name__):
                self.assertIn(require_dashboard_auth, dependency_calls)
                self.assertIn(enforce_config_write_rate_limit, dependency_calls)
                self.assertLess(
                    dependency_calls.index(enforce_config_write_rate_limit),
                    dependency_calls.index(require_dashboard_auth),
                )


if __name__ == "__main__":
    unittest.main()
