"""Split raw resume text into labelled sections.

Resume PDFs flatten into a single text blob, which makes one-shot LLM extraction
unreliable for nested sections such as employment history. Splitting on headings
first lets callers hand the model a much smaller, unambiguous task.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Canonical section name -> heading spellings seen on real resumes.
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "experience": (
        "experience",
        "work experience",
        "working experience",
        "professional experience",
        "relevant experience",
        "employment",
        "employment history",
        "work history",
        "internship",
        "internships",
        "internship experience",
    ),
    "education": (
        "education",
        "educational qualifications",
        "academic background",
        "academics",
        "academic qualifications",
    ),
    "skills": (
        "skills",
        "technical skills",
        "core skills",
        "key skills",
        "skills abilities",
    ),
    "projects": (
        "projects",
        "personal projects",
        "academic projects",
        "key projects",
        "selected projects",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses certifications",
        "courses certifications",
        "achievements certifications",
    ),
    "summary": (
        "summary",
        "profile",
        "about me",
        "objective",
        "career objective",
        "career summary",
        "professional summary",
    ),
}

MAX_HEADING_CHARACTERS = 60
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_CONTACT_MARKERS = re.compile(r"[@|]|https?://|www\.|linkedin|github|\+?\d[\d\s()-]{6,}")
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,17}\d")
_LINKEDIN_PATTERN = re.compile(
    r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|pub)/[A-Za-z0-9_-]+/?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResumeSections:
    """Resume text grouped by canonical section name."""

    header: str = ""
    sections: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        """Return one section's text, or an empty string when absent."""
        return self.sections.get(name, "")

    def has(self, name: str) -> bool:
        """Report whether a non-empty section was detected."""
        return bool(self.get(name).strip())


def split_resume_sections(text: str) -> ResumeSections:
    """Group resume lines under the canonical section headings they follow."""
    header_lines: list[str] = []
    grouped: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        heading = _match_heading(line)
        if heading is not None:
            current = heading
            grouped.setdefault(current, [])
            continue
        if current is None:
            header_lines.append(line)
        else:
            grouped[current].append(line)

    return ResumeSections(
        header="\n".join(header_lines).strip(),
        sections={name: "\n".join(lines).strip() for name, lines in grouped.items()},
    )


def extract_headline(header: str) -> str:
    """Return the title line printed under the candidate's name."""
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    # Line 0 is the candidate's name; the headline is the next non-contact line.
    for line in lines[1:]:
        if len(line) <= MAX_HEADING_CHARACTERS and not _CONTACT_MARKERS.search(line.casefold()):
            return line
    return ""


def extract_phone_number(text: str) -> str:
    """Return the first phone number in the text, or an empty string."""
    for match in _PHONE_PATTERN.finditer(text):
        candidate = match.group().strip()
        # Reject date ranges and other digit runs that are too short to be a number.
        if 10 <= sum(character.isdigit() for character in candidate) <= 15:
            return candidate
    return ""


def extract_linkedin(text: str) -> str:
    """Return the first LinkedIn profile URL in the text, or an empty string."""
    match = _LINKEDIN_PATTERN.search(text)
    if match is None:
        return ""
    url = match.group().strip().rstrip("/")
    return url if url.lower().startswith("http") else f"https://{url}"


def _normalize(value: str) -> str:
    return _NON_ALPHANUMERIC.sub(" ", value.casefold()).strip()


_NORMALIZED_ALIASES: dict[str, str] = {
    _normalize(alias): canonical
    for canonical, aliases in SECTION_ALIASES.items()
    for alias in aliases
}


def _match_heading(line: str) -> str | None:
    """Return the canonical section name when a line is a bare heading."""
    stripped = line.strip().rstrip(":")
    if not stripped or len(stripped) > MAX_HEADING_CHARACTERS:
        return None
    return _NORMALIZED_ALIASES.get(_normalize(stripped))
