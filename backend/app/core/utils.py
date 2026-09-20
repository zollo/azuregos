"""Small shared helpers."""
from __future__ import annotations

import re
import unicodedata


def slugify(value: str) -> str:
    """URL-safe slug: lowercase, hyphenated, ASCII."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value or "item"
