from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections import OrderedDict, deque

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def serialize_javascript_string(value: str) -> str:
    """序列化可安全嵌入 script 元素的 JavaScript 字符串。"""
    serialized = json.dumps(value, ensure_ascii=False)
    return (
        serialized.replace("&", r"\u0026")
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("\u2028", r"\u2028")
        .replace("\u2029", r"\u2029")
    )


def inject_cesium_token(index_html: str, token: str) -> str:
    marker = 'window.CESIUM_ION_TOKEN=""'
    assignment = f"window.CESIUM_ION_TOKEN={serialize_javascript_string(token)}"
    return index_html.replace(marker, assignment, 1)


def require_dashboard_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    server_key = os.environ.get("DASHBOARD_API_KEY", "")
    if not server_key:
        raise HTTPException(
            503,
            "服务端未配置 DASHBOARD_API_KEY，配置写入已禁用",
        )
    if credentials is None or not secrets.compare_digest(
        credentials.credentials,
        server_key,
    ):
        raise HTTPException(401, "未授权：需要有效的仪表盘 API 密钥")


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        max_identities: int,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._max_identities = max_identities
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def identity_count(self) -> int:
        with self._lock:
            return len(self._requests)

    def check(self, identity: str, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        cutoff = current - self._window_seconds
        with self._lock:
            timestamps = self._requests.pop(identity, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self._max_requests:
                self._requests[identity] = timestamps
                raise HTTPException(
                    429,
                    "配置写入请求过于频繁，请稍后重试",
                    headers={"Retry-After": str(int(self._window_seconds))},
                )

            timestamps.append(current)
            self._requests[identity] = timestamps
            while len(self._requests) > self._max_identities:
                self._requests.popitem(last=False)


_config_write_limiter = SlidingWindowRateLimiter(
    max_requests=30,
    window_seconds=60,
    max_identities=1024,
)


def enforce_config_write_rate_limit(request: Request) -> None:
    identity = request.client.host if request.client else "unknown"
    _config_write_limiter.check(identity)
