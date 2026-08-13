"""Tests for cover-letter tailoring context building and LLM output reconciliation."""

from __future__ import annotations

from types import SimpleNamespace

from app.schemas.cover_letter_tailoring import LLMTailoredCoverLetterSections
from app.schemas.user_detail import CoverLetterData
from app.services.cover_letter_tailoring_service import (
    CoverLetterTailoringService,
    linkedin_slug,
    split_company_address,
    split_signature,
)


def _user() -> SimpleNamespace:
    return SimpleNamespace(name="Ada Lovelace", email="ada@example.com")


class TestAddressHelpers:
    """Free-form address parsing helpers."""

    def test_split_company_address_city_state_zip(self) -> None:
        street, city, state, zip_code = split_company_address(
            "123 Market St\nSan Francisco, CA 94105"
        )
        assert street == "123 Market St"
        assert city == "San Francisco"
        assert state == "CA"
        assert zip_code == "94105"

    def test_linkedin_slug_from_url(self) -> None:
        assert linkedin_slug("https://linkedin.com/in/ada-lovelace/") == "ada-lovelace"

    def test_split_signature(self) -> None:
        closer, name = split_signature("Best regards,\nAda Lovelace", "Ada Lovelace")
        assert closer == "Best regards"
        assert name == "Ada Lovelace"


class TestBuildContext:
    """The LLM receives seeded paragraphs it can rewrite."""

    def test_seeds_body_paragraphs_from_source(self) -> None:
        cover_letter = CoverLetterData(
            salutation="Dear Hiring Manager,",
            opening_paragraph="I am excited to apply.",
            body_paragraphs=["Built APIs.", "Shipped features."],
            why_this_company="Your mission inspires me.",
            closing_paragraph="Thank you for your time.",
            signature="Sincerely",
        )

        context = CoverLetterTailoringService._build_context(
            cover_letter,
            "Tailor for backend",
            None,
        )

        assert context.body_paragraphs == ["Built APIs.", "Shipped features."]
        assert context.source_salutation == "Dear Hiring Manager,"


class TestMergeCoverLetter:
    """Merging repairs empty paragraphs and applies job header overrides."""

    def test_restores_source_body_when_llm_empty(self) -> None:
        cover_letter = CoverLetterData(
            body_paragraphs=["Built APIs."],
            company_name="Acme",
            job_title="Intern",
        )
        llm = LLMTailoredCoverLetterSections(body_paragraphs=[])

        merged = CoverLetterTailoringService._merge_cover_letter(_user(), cover_letter, None, llm)

        assert merged.body_paragraphs == ["Built APIs."]
        assert merged.applicant_name == "Ada Lovelace"
        assert merged.email == "ada@example.com"

    def test_job_overrides_company_and_title(self) -> None:
        cover_letter = CoverLetterData(
            company_name="Old Co",
            job_title="Old Role",
            company_address="1 Main St\nAustin, TX 78701",
        )
        job = SimpleNamespace(
            company="New Co",
            title="Backend Intern",
            location="Remote",
        )
        llm = LLMTailoredCoverLetterSections(
            opening_paragraph="Tailored opening.",
            body_paragraphs=["One paragraph."],
        )

        merged = CoverLetterTailoringService._merge_cover_letter(_user(), cover_letter, job, llm)

        assert merged.company_name == "New Co"
        assert merged.job_title == "Backend Intern"
        assert merged.company_street == "Remote"
