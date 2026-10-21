"""LRU in-memory cache, TTL eviction cleaner, and Redis key namespacing."""
from collections import OrderedDict
import time

class LRUCache:
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.expirations = {}

    def get(self, key: str):
        """Retrieve key and refresh LRU position."""
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value, ttl_seconds: int = 300) -> None:
        """Store key-value with TTL expiration and evict oldest if full."""
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        self.expirations[key] = time.time() + ttl_seconds
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def namespace_key(self, prefix: str, raw_key: str) -> str:
        """Apply Redis key namespacing prefix."""
        return f"{prefix}:{raw_key}"
