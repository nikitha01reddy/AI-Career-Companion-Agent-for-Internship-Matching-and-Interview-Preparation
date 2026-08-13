"""Agent for extracting structured resume content."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.exceptions import DocumentParsingError
from app.llm.client import StructuredExtractionClient
from app.schemas.user_detail import ExperienceItem, ResumeData
from app.utils.resume_sections import (
    extract_headline,
    extract_linkedin,
    extract_phone_number,
    split_resume_sections,
)

RESUME_EXTRACTION_INSTRUCTIONS = (
    "Extract education, skills, projects, work experience, a short professional "
    "headline (role/title line under the name, e.g. 'Software Engineer | Python'), "
    "the profile summary or career objective paragraph, and certifications from "
    "this resume. Every employer in the experience section must appear as one "
    "entry with its own company, role, dates, and bullet list."
)

CONTACT_ALREADY_KNOWN_INSTRUCTION = (
    " The phone number and LinkedIn URL are already known; return empty strings for both."
)

CONTACT_WANTED_INSTRUCTION = (
    " Also return the phone number and LinkedIn URL, using empty strings if the "
    "resume does not contain them."
)

EXPERIENCE_EXTRACTION_INSTRUCTIONS = (
    "The document below is the EXPERIENCE section of a resume. Return one entry "
    "per employer, each with the company, the job title, the start and end dates "
    "as written, and every bullet point under that employer in responsibilities. "
    "A job title and its employer are usually on adjacent lines. Do not create a "
    "separate entry for each bullet point."
)


class ExperienceSection(BaseModel):
    """Employment history extracted from the experience section alone."""

    experience: list[ExperienceItem] = Field(
        default_factory=list,
        description="One entry per employer listed in the experience section.",
    )


class ResumeAgent:
    """Convert resume text into a validated structured profile."""

    def __init__(self, extraction_client: StructuredExtractionClient) -> None:
        self._extraction_client = extraction_client

    async def parse(self, text: str) -> ResumeData:
        """Extract structured resume fields."""
        sections = split_resume_sections(text)
        phone_number = extract_phone_number(sections.header)
        linkedin = extract_linkedin(sections.header)

        contact_instruction = (
            CONTACT_ALREADY_KNOWN_INSTRUCTION
            if phone_number and linkedin
            else CONTACT_WANTED_INSTRUCTION
        )
        data = await self._extraction_client.extract(
            text,
            ResumeData,
            RESUME_EXTRACTION_INSTRUCTIONS + contact_instruction,
        )

        data.phone_number = phone_number or data.phone_number
        data.linkedin = linkedin or data.linkedin
        data.experience = _usable_experience(data.experience)
        if not data.experience and sections.has("experience"):
            data.experience = await self._extract_experience(sections.get("experience"))
        if not data.headline.strip():
            data.headline = extract_headline(sections.header)
        return data

    async def _extract_experience(self, section_text: str) -> list[ExperienceItem]:
        """Re-read the experience section on its own when the first pass missed it."""
        try:
            section = await self._extraction_client.extract(
                section_text,
                ExperienceSection,
                EXPERIENCE_EXTRACTION_INSTRUCTIONS,
            )
        except DocumentParsingError:
            # A failed retry must not discard an otherwise valid resume parse.
            return []
        return _usable_experience(section.experience)


def _usable_experience(items: list[ExperienceItem]) -> list[ExperienceItem]:
    """Drop entries that identify no employer or role."""
    return [item for item in items if item.role.strip() or item.company.strip()]
