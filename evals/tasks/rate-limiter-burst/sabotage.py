from collections import defaultdict

def allow(events, limit, window):  # fixed-window: resets at bucket edges
    counts = defaultdict(int)
    out = []
    for ts, key in events:
        bucket = (key, int(ts // window))
        ok = counts[bucket] < limit
        out.append(ok)
        if ok:
            counts[bucket] += 1
    return out
