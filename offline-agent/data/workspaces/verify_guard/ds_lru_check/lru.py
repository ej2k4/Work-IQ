from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return -1
        # Fix: mark as recently used by moving to the end
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache[key] = value
            self.cache.move_to_end(key)
            return
        if len(self.cache) >= self.capacity:
            # Fix: pop the least recently used (last=False)
            self.cache.popitem(last=False)
        self.cache[key] = value
