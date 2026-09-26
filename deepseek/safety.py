"""Account-safety controls for the DeepSeek Web client.

These controls intentionally fail closed. They are designed to avoid request
bursts and repeated authentication attempts; they do not bypass provider
limits, CAPTCHAs, WAFs, or account controls.
"""

from __future__ import annotations

import threading
import time


class SafetyTrip(RuntimeError):
    """Raised when the client must stop instead of retrying automatically."""


class RequestGuard:
    def __init__(self, min_interval: float = 3.0):
        self.min_interval = max(1.0, float(min_interval))
        self._lock = threading.Lock()
        self._last_request = 0.0
        self.tripped = False
        self.reason = ""

    def wait(self) -> None:
        with self._lock:
            if self.tripped:
                raise SafetyTrip(self.reason or "DeepSeek safety guard is active.")
            now = time.monotonic()
            delay = self.min_interval - (now - self._last_request)
            if delay > 0:
                time.sleep(delay)
            self._last_request = time.monotonic()

    def trip(self, reason: str) -> None:
        with self._lock:
            self.tripped = True
            self.reason = reason

    def reset(self) -> None:
        with self._lock:
            self.tripped = False
            self.reason = ""
            self._last_request = time.monotonic()


def is_account_protection_response(status: int, body: str = "") -> bool:
    if status in (401, 403, 429):
        return True
    text = (body or "").lower()
    markers = (
        "captcha", "recaptcha", "verify you are human", "human verification",
        "too many requests", "rate limit", "forbidden", "account suspended",
        "account disabled", "risk control", "security verification",
    )
    return any(m in text for m in markers)
