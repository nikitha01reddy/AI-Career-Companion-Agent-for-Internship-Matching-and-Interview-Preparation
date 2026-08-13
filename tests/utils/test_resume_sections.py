"""Tests for resume section splitting."""

from __future__ import annotations

from app.utils.resume_sections import (
    extract_headline,
    extract_linkedin,
    extract_phone_number,
    split_resume_sections,
)

RESUME_TEXT = """A Chetan Varma
Associate Data Scientist
chetanvarmaatla@gmail.com | +91 9441321253 | Hyderabad, India
https://www.linkedin.com/in/chetan-varma-a-980631335/
Career Objective
Python Developer with experience in AI-powered application development.
Education
B.Tech in CSE (AI & ML) Raghu Engineering College 2021 - 2025
Experience
Associate Data Scientist
Seanergy.ai
Feb 2026 - Present
- Developed backend services for AI-powered voice agents.
Projects
Knowledge Engine [GitHub]
- Built a RAG-based support system.
"""


class TestSplitResumeSections:
    """Headings group the surrounding lines."""

    def test_detects_sections_and_header(self) -> None:
        sections = split_resume_sections(RESUME_TEXT)

        assert sections.header.startswith("A Chetan Varma")
        assert sections.has("experience")
        assert "Seanergy.ai" in sections.get("experience")
        assert "Knowledge Engine" not in sections.get("experience")
        assert sections.has("summary")
        assert sections.has("projects")

    def test_reports_missing_sections(self) -> None:
        sections = split_resume_sections("Jane Doe\nSoftware Engineer\n")

        assert sections.has("experience") is False
        assert sections.get("experience") == ""

    def test_matches_heading_spelling_variants(self) -> None:
        text = "WORK EXPERIENCE:\nIntern at Acme\nTECHNICAL SKILLS\nPython"
        sections = split_resume_sections(text)

        assert sections.get("experience") == "Intern at Acme"
        assert sections.get("skills") == "Python"

    def test_ignores_long_lines_that_merely_mention_a_heading(self) -> None:
        text = "Experience building distributed systems across several teams and domains\nBody"
        sections = split_resume_sections(text)

        assert sections.has("experience") is False


class TestExtractHeadline:
    """The title line sits under the name, above the contact details."""

    def test_returns_title_line_under_the_name(self) -> None:
        header = split_resume_sections(RESUME_TEXT).header

        assert extract_headline(header) == "Associate Data Scientist"

    def test_skips_contact_lines(self) -> None:
        header = "Jane Doe\njane@example.com | +91 9441321253\nBackend Engineer"

        assert extract_headline(header) == "Backend Engineer"

    def test_returns_empty_when_only_a_name_is_present(self) -> None:
        assert extract_headline("Jane Doe") == ""


class TestExtractPhoneNumber:
    """Phone numbers are read without the LLM."""

    def test_reads_an_international_number(self) -> None:
        header = split_resume_sections(RESUME_TEXT).header

        assert extract_phone_number(header) == "+91 9441321253"

    def test_ignores_year_ranges(self) -> None:
        assert extract_phone_number("B.Tech 2021 - 2025, CGPA: 8.83") == ""

    def test_returns_empty_when_absent(self) -> None:
        assert extract_phone_number("Jane Doe\njane@example.com") == ""


class TestExtractLinkedin:
    """LinkedIn profile URLs are read without the LLM."""

    def test_reads_a_full_profile_url(self) -> None:
        header = split_resume_sections(RESUME_TEXT).header

        assert extract_linkedin(header) == "https://www.linkedin.com/in/chetan-varma-a-980631335"

    def test_adds_a_scheme_to_a_bare_url(self) -> None:
        assert extract_linkedin("linkedin.com/in/jane-doe") == "https://linkedin.com/in/jane-doe"

    def test_returns_empty_when_absent(self) -> None:
        assert extract_linkedin("github.com/jane-doe") == ""
