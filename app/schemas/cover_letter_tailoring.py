"""Schemas for cover-letter tailoring (LLM I/O + LaTeX fill contract)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class LLMTailoredCoverLetterSections(BaseModel):
    """Fields the LLM is allowed to rewrite.

    Contact, date, and recipient header are merged from auth / source / job
    outside the model — never trusted from this payload.
    """

    salutation: str = ""
    opening_paragraph: str = ""
    body_paragraphs: list[str] = Field(default_factory=list)
    why_this_company: str = ""
    closing_paragraph: str = ""
    signature: str = ""


class TailoredCoverLetterContent(BaseModel):
    """Final merged cover letter used to fill ``cover_letter_template.tex.j2``."""

    applicant_name: str = ""
    email: str = ""
    phone_number: str = ""
    location: str = ""
    linkedin: str = ""
    linkedin_slug: str = ""
    letter_date: str = ""
    hiring_manager_name: str = ""
    company_name: str = ""
    company_street: str = ""
    company_city: str = ""
    company_state: str = ""
    company_zip: str = ""
    job_title: str = ""
    salutation: str = ""
    opening_paragraph: str = ""
    body_paragraphs: list[str] = Field(default_factory=list)
    why_this_company: str = ""
    closing_paragraph: str = ""
    closer: str = ""
    signature_name: str = ""


class TailorCoverLetterContext(BaseModel):
    """JSON payload sent to the LLM for one tailor request."""

    instructions: str
    source_salutation: str = ""
    opening_paragraph: str = ""
    body_paragraphs: list[str] = Field(default_factory=list)
    why_this_company: str = ""
    closing_paragraph: str = ""
    source_signature: str = ""
    job: dict[str, Any] | None = None


class TailorCoverLetterResponse(BaseModel):
    """JSON metadata returned alongside the generated PDF (when requested)."""

    cover_letter_id: uuid.UUID
    content: TailoredCoverLetterContent


def _clean(value: str) -> str:
    return value.strip()


def prune_llm_sections(sections: LLMTailoredCoverLetterSections) -> LLMTailoredCoverLetterSections:
    """Drop blank nested rows from LLM output."""
    body_paragraphs = [_clean(paragraph) for paragraph in sections.body_paragraphs if _clean(paragraph)]
    return LLMTailoredCoverLetterSections(
        salutation=_clean(sections.salutation),
        opening_paragraph=_clean(sections.opening_paragraph),
        body_paragraphs=body_paragraphs,
        why_this_company=_clean(sections.why_this_company),
        closing_paragraph=_clean(sections.closing_paragraph),
        signature=_clean(sections.signature),
    )


def prune_tailored_content(content: TailoredCoverLetterContent) -> TailoredCoverLetterContent:
    """Drop blank nested rows so empty LaTeX sections can be skipped safely."""
    llm = prune_llm_sections(
        LLMTailoredCoverLetterSections(
            salutation=content.salutation,
            opening_paragraph=content.opening_paragraph,
            body_paragraphs=content.body_paragraphs,
            why_this_company=content.why_this_company,
            closing_paragraph=content.closing_paragraph,
            signature=content.closer,
        )
    )
    return TailoredCoverLetterContent(
        applicant_name=_clean(content.applicant_name),
        email=_clean(content.email),
        phone_number=_clean(content.phone_number),
        location=_clean(content.location),
        linkedin=_clean(content.linkedin),
        linkedin_slug=_clean(content.linkedin_slug),
        letter_date=_clean(content.letter_date),
        hiring_manager_name=_clean(content.hiring_manager_name),
        company_name=_clean(content.company_name),
        company_street=_clean(content.company_street),
        company_city=_clean(content.company_city),
        company_state=_clean(content.company_state),
        company_zip=_clean(content.company_zip),
        job_title=_clean(content.job_title),
        salutation=llm.salutation,
        opening_paragraph=llm.opening_paragraph,
        body_paragraphs=llm.body_paragraphs,
        why_this_company=llm.why_this_company,
        closing_paragraph=llm.closing_paragraph,
        closer=llm.signature or _clean(content.closer),
        signature_name=_clean(content.signature_name),
    )
