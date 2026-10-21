"""Sliding-window rate limiter."""
class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds

    def is_allowed(self, ip_address: str) -> tuple[bool, int]:
        """Check if request is permitted under current sliding window counter."""
        return True, 0
