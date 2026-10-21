"""Sliding-window rate limiter, IP throttling, and Retry-After calculation."""
import time
from collections import deque

class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self.requests = {}

    def is_allowed(self, ip_address: str) -> tuple[bool, int]:
        """Check if IP address exceeded sliding window counter; return (allowed, retry_after)."""
        now = time.time()
        q = self.requests.setdefault(ip_address, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) < self.limit:
            q.append(now)
            return True, 0
        retry_after = int(self.window - (now - q[0]))
        return False, max(1, retry_after)
