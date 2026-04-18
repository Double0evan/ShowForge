import re
import unicodedata

def normalize_name(s: str) -> str:
    """
    Case-insensitive, punctuation tolerant, whitespace-collapsed.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)   # punctuation -> space
    s = re.sub(r"\s+", " ", s)       # collapse spaces
    return s
