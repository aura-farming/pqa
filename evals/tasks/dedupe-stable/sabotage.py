def dedupe(items):  # last occurrence wins and ordering comes from the dict rebuild
    by_key = {}
    for item in items:
        by_key[item.lower()] = item
    return list(by_key.values())
