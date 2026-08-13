"""LaTeX escaping and URL sanitization for resume templates."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(value: str) -> str:
    """Escape characters that are special in LaTeX text mode."""
    return "".join(_LATEX_SPECIALS.get(char, char) for char in value)


def sanitize_url(value: str) -> str:
    """Allow only http(s)/mailto URLs; otherwise return an empty string."""
    cleaned = value.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() in {"http", "https", "mailto"} and (parsed.netloc or parsed.path):
        return cleaned
    if cleaned.startswith("www.") and " " not in cleaned:
        return f"https://{cleaned}"
    return ""


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_email(value: str) -> bool:
    """Return True when ``value`` looks like a simple email address."""
    return bool(_EMAIL_RE.match(value.strip()))
