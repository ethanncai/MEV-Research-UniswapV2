"""Multi-key token-bucket rate limiter for Etherscan API (thread-safe)."""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class DailyLimitExhaustedError(RuntimeError):
    """Raised when all API keys have exhausted their daily call limits."""

    pass


@dataclass
class _KeyState:
    """Tracks per-key usage counters."""

    key: str
    calls_today: int = 0
    today: date = field(default_factory=date.today)
    last_call_ts: float = 0.0

    def reset_if_new_day(self) -> None:
        """Reset daily counter when the date rolls over."""
        current = date.today()
        if current != self.today:
            logger.info("Daily counter reset for key ...%s", self.key[-6:])
            self.calls_today = 0
            self.today = current


class RateLimiter:
    """Round-robin rate limiter across multiple API keys.

    Enforces:
      - Per-key calls/second limit (token-bucket style with fixed window).
      - Per-key daily call budget.
      - Automatic rotation when a key is exhausted for the day.
    """

    def __init__(
        self,
        api_keys: list[str],
        calls_per_second: int = 3,
        daily_limit: int = 100_000,
    ) -> None:
        if not api_keys:
            raise ValueError("At least one API key is required.")
        self._keys: list[_KeyState] = [_KeyState(key=k) for k in api_keys]
        self._calls_per_second = calls_per_second
        self._daily_limit = daily_limit
        self._current_idx = 0
        self._lock = threading.Lock()
        # Use full quota (no safety margin) for maximum throughput
        self._min_interval = 1.0 / calls_per_second

    @property
    def total_keys(self) -> int:
        """Return the number of registered API keys."""
        return len(self._keys)

    def _find_available_key(self) -> Optional[_KeyState]:
        """Find the next key that has not exhausted its daily budget."""
        checked = 0
        while checked < len(self._keys):
            ks = self._keys[self._current_idx]
            ks.reset_if_new_day()
            if ks.calls_today < self._daily_limit:
                return ks
            logger.warning(
                "Key ...%s exhausted daily limit (%d). Rotating.",
                ks.key[-6:], self._daily_limit,
            )
            self._current_idx = (self._current_idx + 1) % len(self._keys)
            checked += 1
        return None

    def acquire(self) -> str:
        """Block until a call slot is available and return the API key to use.
        Thread-safe: each key is used by at most one caller per min_interval.

        Raises:
            DailyLimitExhaustedError: If all keys have exhausted their daily budgets.
        """
        with self._lock:
            ks = self._find_available_key()
            if ks is None:
                raise DailyLimitExhaustedError(
                    "All API keys have exhausted their daily call limits."
                )
            now = time.monotonic()
            wait_time = max(0.0, self._min_interval - (now - ks.last_call_ts))
            ks.last_call_ts = now + wait_time
            ks.calls_today += 1
            if ks.calls_today % 10_000 == 0:
                logger.info(
                    "Key ...%s: %d / %d daily calls used.",
                    ks.key[-6:], ks.calls_today, self._daily_limit,
                )
            self._current_idx = (self._current_idx + 1) % len(self._keys)
            key = ks.key

        if wait_time > 0:
            time.sleep(wait_time)
        return key

    def stats(self) -> list[dict]:
        """Return usage statistics for all keys."""
        return [
            {
                "key_suffix": ks.key[-6:],
                "calls_today": ks.calls_today,
                "daily_limit": self._daily_limit,
                "remaining": self._daily_limit - ks.calls_today,
            }
            for ks in self._keys
        ]
