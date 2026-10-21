import time
import pytest
from rate_limiter import TokenBucket, RateLimiterManager


def test_token_bucket_initial():
    tb = TokenBucket(capacity=5, refill_rate=1)
    assert tb.tokens == 5
    assert tb.acquire(3) is True
    assert tb.tokens == 2
    assert tb.acquire(3) is False
    assert tb.tokens == 2


def test_token_bucket_refill():
    tb = TokenBucket(capacity=5, refill_rate=10)
    tb.acquire(5)
    assert tb.tokens == 0
    time.sleep(0.15)
    tb.refill()
    assert tb.tokens >= 1


def test_rate_limiter_manager_burst():
    mgr = RateLimiterManager()
    ip = "10.0.0.1"
    # First 10 requests should be allowed (capacity = 10)
    for _ in range(10):
        assert mgr.is_allowed(ip) is True
    # 11th request should be blocked
    assert mgr.is_allowed(ip) is False


def test_rate_limiter_different_ips():
    mgr = RateLimiterManager()
    ip1 = "10.0.0.10"
    ip2 = "10.0.0.20"
    # Exhaust ip1
    for _ in range(10):
        mgr.is_allowed(ip1)
    assert mgr.is_allowed(ip1) is False
    # ip2 should still have fresh quota
    assert mgr.is_allowed(ip2) is True