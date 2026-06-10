class LRUTTL:
    def __init__(self, capacity, ttl):
        self.capacity, self.ttl = capacity, ttl
        self._data = {}

    def put(self, key, value, now):  # always evicts LRU, even when a corpse exists
        if key not in self._data and len(self._data) >= self.capacity:
            victim = min(self._data, key=lambda k: self._data[k][2])
            del self._data[victim]
        self._data[key] = [value, now + self.ttl, now]

    def get(self, key, now):
        entry = self._data.get(key)
        if entry is None or entry[1] <= now:
            return None
        entry[2] = now
        return entry[0]
