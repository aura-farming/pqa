import re
import unicodedata

def slugify(title):
    folded = unicodedata.normalize("NFKD", title)
    ascii_text = "".join(c for c in folded if not unicodedata.combining(c))
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
