"""Agent for extracting structured cover-letter content."""

from __future__ import annotations

import re

from app.llm.client import StructuredExtractionClient
from app.schemas.user_detail import CoverLetterData

COVER_LETTER_EXTRACTION_INSTRUCTIONS = (
    "Extract the applicant contact details, letter date, hiring manager, company, "
    "job title, salutation, opening, body paragraphs, motivation for this company, "
    "closing paragraph, and signature from this cover letter."
)


class CoverLetterAgent:
    """Convert cover-letter text into validated structured data."""

    def __init__(self, extraction_client: StructuredExtractionClient) -> None:
        self._extraction_client = extraction_client

    async def parse(self, text: str) -> CoverLetterData:
        """Extract structured cover-letter fields."""
        extracted = await self._extraction_client.extract(
            text,
            CoverLetterData,
            COVER_LETTER_EXTRACTION_INSTRUCTIONS,
        )
        fallback = _fallback_cover_letter_fields(text)
        return _merge_cover_letter_data(extracted, fallback)


MONTH_PATTERN = (
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}"
)
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
PHONE_PATTERN = r"(?:\+\d{1,3}[\s-]*)?(?:\(?\d{2,4}\)?[\s.-]*){2,}\d{3,4}"
SIGN_OFF_PREFIXES = (
    "sincerely",
    "best regards",
    "kind regards",
    "regards",
    "thank you",
    "yours faithfully",
    "yours truly",
)
SALUTATION_PREFIXES = ("dear ", "hello ", "hi ")


def _merge_cover_letter_data(
    extracted: CoverLetterData,
    fallback: CoverLetterData,
) -> CoverLetterData:
    opening_paragraph = _choose_opening_paragraph(
        extracted.opening_paragraph,
        extracted.body_paragraphs,
        fallback.opening_paragraph,
    )
    body_paragraphs = _choose_body_paragraphs(
        extracted.body_paragraphs,
        opening_paragraph,
        fallback.body_paragraphs,
    )
    closing_paragraph = _choose_closing_paragraph(
        extracted.closing_paragraph,
        extracted.signature,
        fallback.closing_paragraph,
    )
    return CoverLetterData(
        applicant_name=extracted.applicant_name or fallback.applicant_name,
        email=extracted.email or fallback.email,
        phone_number=extracted.phone_number or fallback.phone_number,
        address=extracted.address or fallback.address,
        date=extracted.date or fallback.date,
        hiring_manager_name=extracted.hiring_manager_name or fallback.hiring_manager_name,
        company_name=extracted.company_name or fallback.company_name,
        company_address=extracted.company_address or fallback.company_address,
        job_title=extracted.job_title or fallback.job_title,
        salutation=extracted.salutation or fallback.salutation,
        opening_paragraph=opening_paragraph,
        body_paragraphs=body_paragraphs,
        why_this_company=extracted.why_this_company or fallback.why_this_company,
        closing_paragraph=closing_paragraph,
        signature=extracted.signature or fallback.signature,
    )


def _choose_opening_paragraph(
    extracted_opening: str,
    extracted_body: list[str],
    fallback_opening: str,
) -> str:
    if not extracted_opening:
        return fallback_opening
    if not fallback_opening:
        return extracted_opening

    normalized_extracted = _normalize_for_compare(extracted_opening)
    normalized_fallback = _normalize_for_compare(fallback_opening)
    if normalized_extracted == normalized_fallback:
        return extracted_opening

    if extracted_body:
        first_body = extracted_body[0]
        if _sentences_overlap(extracted_opening, first_body):
            return fallback_opening

    if len(normalized_extracted) < len(normalized_fallback):
        return fallback_opening
    return extracted_opening


def _choose_body_paragraphs(
    extracted_body: list[str],
    opening_paragraph: str,
    fallback_body: list[str],
) -> list[str]:
    if not extracted_body:
        return fallback_body
    if not fallback_body:
        return extracted_body

    normalized_opening = _normalize_for_compare(opening_paragraph)
    normalized_first_body = _normalize_for_compare(extracted_body[0])
    if normalized_opening and normalized_first_body:
        if _sentences_overlap(opening_paragraph, extracted_body[0]):
            return fallback_body

    if len(extracted_body) < len(fallback_body):
        return fallback_body
    return extracted_body


def _choose_closing_paragraph(
    extracted_closing: str,
    extracted_signature: str,
    fallback_closing: str,
) -> str:
    if _looks_like_signoff(extracted_closing, extracted_signature):
        return fallback_closing
    return extracted_closing or fallback_closing


def _fallback_cover_letter_fields(text: str) -> CoverLetterData:
    normalized_text = _normalize_text(text)
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    salutation_index = next(
        (index for index, line in enumerate(lines) if line.casefold().startswith(SALUTATION_PREFIXES)),
        -1,
    )
    closing_index, signature_name = _find_signature(lines)

    date_match = re.search(MONTH_PATTERN, normalized_text)
    date_line = date_match.group(0) if date_match else ""
    date_index = next((index for index, line in enumerate(lines) if line == date_line), -1)

    applicant_name = signature_name or _infer_name_from_header(lines[0]) if lines else ""
    email = _first_match(EMAIL_PATTERN, normalized_text)
    phone_number = _first_phone(normalized_text)
    header_block = []
    if date_index >= 0 and salutation_index >= 0 and date_index < salutation_index:
        header_block = lines[date_index + 1 : salutation_index]
    header_lines = lines[:date_index] if date_index > 0 else lines[:1]

    email = _clean_email(email, applicant_name)
    address = _extract_header_location(header_lines)

    hiring_manager_name = header_block[0] if header_block else None
    company_name = header_block[1] if len(header_block) > 1 else ""
    company_address = ", ".join(header_block[2:]) if len(header_block) > 2 else None

    salutation = lines[salutation_index] if salutation_index >= 0 else ""

    body_lines = (
        lines[salutation_index + 1 : closing_index]
        if salutation_index >= 0 and closing_index > salutation_index
        else []
    )
    opening_paragraph, body_paragraphs, why_this_company, closing_paragraph = _extract_body_sections(
        body_lines
    )

    return CoverLetterData(
        applicant_name=applicant_name or "",
        email=email,
        phone_number=phone_number,
        address=address,
        date=date_line,
        hiring_manager_name=hiring_manager_name,
        company_name=company_name,
        company_address=company_address,
        salutation=salutation,
        opening_paragraph=opening_paragraph,
        body_paragraphs=body_paragraphs,
        why_this_company=why_this_company,
        closing_paragraph=closing_paragraph,
        signature=signature_name,
    )


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"(?<=[A-Za-z])-\n(?=[a-z])", "", text)
    return text


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(0) if match else ""


def _first_phone(text: str) -> str:
    for match in re.finditer(PHONE_PATTERN, text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if len(digits) >= 10:
            return candidate
    return ""


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _sentences_overlap(left: str, right: str) -> bool:
    left_last = _last_sentence(left)
    right_first = _first_sentence(right)
    if not left_last or not right_first:
        return False
    normalized_left = _normalize_for_compare(left_last)
    normalized_right = _normalize_for_compare(right_first)
    return normalized_left == normalized_right


def _first_sentence(text: str) -> str:
    sentences = _split_sentences(text)
    return sentences[0] if sentences else ""


def _last_sentence(text: str) -> str:
    sentences = _split_sentences(text)
    return sentences[-1] if sentences else ""


def _split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
        if sentence.strip()
    ]


def _looks_like_signoff(closing: str, signature: str) -> bool:
    if not closing:
        return False
    normalized = _normalize_for_compare(closing).rstrip(",")
    if normalized in SIGN_OFF_PREFIXES:
        return True
    if signature and normalized == _normalize_for_compare(signature):
        return True
    return False


def _clean_email(email: str, applicant_name: str) -> str:
    if not email or "@" not in email:
        return email
    local_part, domain = email.split("@", 1)
    normalized_local = re.sub(r"[^a-z0-9._%+-]", "", local_part.casefold())
    name_tokens = [token.casefold() for token in re.findall(r"[A-Za-z]+", applicant_name) if len(token) >= 3]
    candidates = ["".join(name_tokens), *name_tokens]

    for candidate in candidates:
        if candidate and normalized_local.endswith(candidate):
            prefix = normalized_local[: -len(candidate)]
            if len(prefix) <= 4:
                return f"{candidate}@{domain}"
    return email


def _extract_header_location(header_lines: list[str]) -> str | None:
    for header_line in reversed(header_lines):
        if "@" in header_line:
            location_match = re.search(
                r"([A-Za-z][A-Za-z .'-]+,\s*[A-Z]{2,})\s*$",
                header_line,
            )
            if location_match:
                return _clean_location_text(location_match.group(1))

        location_match = re.search(
            r"([A-Za-z][A-Za-z .'-]+,\s*[A-Z]{2,}(?:\s+\d{4,6})?)\s*$",
            header_line,
        )
        if location_match:
            return _clean_location_text(location_match.group(1))
    return None


def _clean_location_text(location: str) -> str:
    words = []
    for word in re.sub(r"\s+", " ", location).strip().split(" "):
        if re.fullmatch(r"[a-z]+(?:[A-Z][a-z]+)+", word):
            transition_points = [index for index, char in enumerate(word) if char.isupper()]
            if transition_points:
                word = word[transition_points[-1] :]
        words.append(word)
    return " ".join(words).strip()


def _find_signature(lines: list[str]) -> tuple[int, str]:
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index].strip()
        if not line:
            continue
        if line.casefold().startswith(SIGN_OFF_PREFIXES):
            name = lines[index + 1].strip() if index + 1 < len(lines) else ""
            return index, name
    if lines:
        return len(lines) - 1, lines[-1].strip()
    return -1, ""


def _infer_name_from_header(first_line: str) -> str:
    cleaned = re.sub(r"[^A-Za-z]", " ", first_line).strip()
    if not cleaned:
        return ""
    if " " in cleaned:
        return re.sub(r"\s+", " ", cleaned).title()
    return ""


def _extract_body_sections(body_lines: list[str]) -> tuple[str, list[str], str, str]:
    if not body_lines:
        return "", [], "", ""

    paragraphs = _split_paragraphs(body_lines)
    if not paragraphs:
        return "", [], "", ""

    closing_index = next(
        (index for index, paragraph in enumerate(paragraphs) if _is_closing_paragraph(paragraph)),
        -1,
    )

    if closing_index >= 0:
        closing = paragraphs[closing_index]
        content_paragraphs = paragraphs[:closing_index]
    else:
        closing = ""
        content_paragraphs = paragraphs

    if not content_paragraphs:
        return "", [], "", closing

    opening = content_paragraphs[0]
    middle = content_paragraphs[1:]

    why_this_company = next(
        (
            paragraph
            for paragraph in content_paragraphs
            if "company" in paragraph.casefold()
            or "organization" in paragraph.casefold()
            or "team" in paragraph.casefold()
            or "because" in paragraph.casefold()
            or "drawn to" in paragraph.casefold()
            or "excited about" in paragraph.casefold()
        ),
        "",
    )

    return opening, middle, why_this_company, closing


def _split_paragraphs(lines: list[str]) -> list[str]:
    from_lines = _split_paragraphs_from_lines(lines)
    if from_lines:
        return from_lines

    raw_text = "\n".join(lines).strip()
    explicit = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", raw_text) if paragraph.strip()]
    if len(explicit) > 1:
        return [re.sub(r"\s+", " ", paragraph) for paragraph in explicit]

    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", raw_text))
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if len(sentences) <= 2:
        return [" ".join(sentences)] if sentences else []

    closing_start = next(
        (index for index, sentence in enumerate(sentences) if _is_closing_paragraph(sentence)),
        -1,
    )
    if closing_start >= 0:
        leading = sentences[:closing_start]
        closing = " ".join(sentences[closing_start:])
        if not leading:
            return [closing]
        if len(leading) <= 3:
            return [" ".join(leading), closing]
        if len(leading) <= 6:
            return [" ".join(leading[:2]), " ".join(leading[2:]), closing]
        return [" ".join(leading[:3]), " ".join(leading[3:]), closing]

    if len(sentences) <= 4:
        return [" ".join(sentences[:2]), " ".join(sentences[2:])]
    if len(sentences) <= 6:
        return [" ".join(sentences[:3]), " ".join(sentences[3:])]
    if len(sentences) <= 9:
        return [" ".join(sentences[:3]), " ".join(sentences[3:6]), " ".join(sentences[6:])]
    return [
        " ".join(sentences[:3]),
        " ".join(sentences[3:-2]),
        " ".join(sentences[-2:]),
    ]


def _split_paragraphs_from_lines(lines: list[str]) -> list[str]:
    if len(lines) < 2:
        return []

    paragraphs: list[str] = []
    current: list[str] = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        current.append(stripped)
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if _should_break_paragraph(current, next_line, len(paragraphs)):
            paragraphs.append(_join_paragraph_lines(current))
            current = []

    if current:
        paragraphs.append(_join_paragraph_lines(current))

    return paragraphs if len(paragraphs) > 1 else []


def _should_break_paragraph(
    current: list[str],
    next_line: str,
    paragraph_count: int,
) -> bool:
    if not current:
        return False

    current_line = current[-1].strip()
    if not current_line.endswith((".", "!", "?")):
        return False
    if not next_line:
        return True

    char_count = len(_join_paragraph_lines(current))
    line_count = len(current)

    if paragraph_count == 0 and char_count <= 140:
        return True
    if line_count >= 6:
        return True
    return False


def _join_paragraph_lines(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _is_closing_paragraph(text: str) -> bool:
    lowered = text.casefold()
    return any(
        phrase in lowered
        for phrase in (
            "thank you for your time",
            "thank you for considering",
            "thank you for your consideration",
            "i would welcome the opportunity",
            "i look forward to",
            "please feel free to contact me",
        )
    )
