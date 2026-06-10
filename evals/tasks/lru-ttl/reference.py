class LRUTTL:
    def __init__(self, capacity, ttl):
        self.capacity, self.ttl = capacity, ttl
        self._data = {}  # key -> [value, expires_at, last_used]

    def _expired(self, key, now):
        return self._data[key][1] <= now

    def put(self, key, value, now):
        if key not in self._data and len(self._data) >= self.capacity:
            corpses = [k for k in self._data if self._expired(k, now)]
            victim = corpses[0] if corpses else min(self._data, key=lambda k: self._data[k][2])
            del self._data[victim]
        self._data[key] = [value, now + self.ttl, now]

    def get(self, key, now):
        entry = self._data.get(key)
        if entry is None or entry[1] <= now:
            return None
        entry[2] = now
        return entry[0]
