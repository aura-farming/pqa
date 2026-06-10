from collections import defaultdict, deque

def allow(events, limit, window):
    seen = defaultdict(deque)
    out = []
    for ts, key in events:
        q = seen[key]
        while q and q[0] <= ts - window:
            q.popleft()
        ok = len(q) < limit
        out.append(ok)
        if ok:
            q.append(ts)
    return out
