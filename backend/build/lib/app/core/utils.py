"""Small shared helpers."""
from __future__ import annotations

import html as _html
import re
import unicodedata


def slugify(value: str) -> str:
    """URL-safe slug: lowercase, hyphenated, ASCII."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value or "item"


def html_to_text(value: str) -> str:
    """Convert ADO's HTML comment/description bodies to safe plain text.

    ADO comments are stored as HTML authored by arbitrary users; we render them
    as text in the portal to avoid injecting untrusted markup. Block-level tags
    and <br> become newlines; remaining tags are stripped and entities decoded.
    """
    if not value:
        return ""
    value = re.sub(r"(?i)<\s*br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</\s*(p|div|li|tr|h[1-6])\s*>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = _html.unescape(value)
    # Collapse runs of blank lines and trailing whitespace.
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def text_to_html(value: str) -> str:
    """Escape user-entered plain text and preserve line breaks as <br> for ADO."""
    return _html.escape(value).replace("\n", "<br>")
