"""Small in-process sliding-window rate limiter for authentication endpoints."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from ..config import settings


class SlidingWindowLimiter:
    """Limit attempts in one process.

    This limiter is intentionally dependency-free and per-process, so limits
    are approximate when the API runs behind multiple worker processes.
    """

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, *keys: str) -> None:
        config = settings()
        limit = max(1, config.auth_rate_limit_attempts)
        window = max(1, config.auth_rate_limit_window_seconds)
        now = time.monotonic()
        retry_after = 0
        with self._lock:
            for key in keys:
                attempts = self._attempts[key]
                while attempts and attempts[0] <= now - window:
                    attempts.popleft()
                if len(attempts) >= limit:
                    retry_after = max(
                        retry_after, max(1, int(attempts[0] + window - now + 0.999))
                    )
            if retry_after == 0:
                for key in keys:
                    self._attempts[key].append(now)
                return
        raise HTTPException(
            status_code=429,
            detail="too many authentication attempts",
            headers={"Retry-After": str(retry_after)},
        )

    def clear(self) -> None:
        """Clear recorded attempts, primarily for isolated application tests."""
        with self._lock:
            self._attempts.clear()


auth_limiter = SlidingWindowLimiter()
