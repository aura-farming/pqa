import re

def slugify(title):  # no NFKD fold: accented characters vanish entirely
    ascii_text = title.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
