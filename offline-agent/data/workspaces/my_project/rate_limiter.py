import time


class TokenBucket:
    def __init__(self, capacity, refill_rate):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()

    def acquire(self, tokens=1):
        if tokens > self.tokens:
            return False
        self.tokens -= tokens
        return True

    def refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens += elapsed * self.refill_rate
        self.tokens = min(self.tokens, self.capacity)
        self.last_refill = now

    def reset(self):
        self.tokens = self.capacity
        self.last_refill = time.time()


class RateLimiterManager:
    def __init__(self):
        self.ip_limits = {}

    def get_limiter(self, ip):
        if ip not in self.ip_limits:
            self.ip_limits[ip] = TokenBucket(capacity=10, refill_rate=1)
        return self.ip_limits[ip]

    def is_allowed(self, ip, tokens=1):
        limiter = self.get_limiter(ip)
        limiter.refill()
        return limiter.acquire(tokens)


if __name__ == "__main__":
    manager = RateLimiterManager()
    client_ip = "192.168.1.42"
    print(f"Testing RateLimiter for client: {client_ip}")
    for i in range(12):
        allowed = manager.is_allowed(client_ip)
        status = "ALLOWED" if allowed else "BLOCKED (rate limit exceeded)"
        print(f"Request #{i + 1:02d}: {status}")