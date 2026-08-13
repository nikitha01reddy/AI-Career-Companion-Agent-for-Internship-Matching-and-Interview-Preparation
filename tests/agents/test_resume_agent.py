"""Tests for resume parsing recovery behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.resume_agent import (
    CONTACT_ALREADY_KNOWN_INSTRUCTION,
    CONTACT_WANTED_INSTRUCTION,
    ExperienceSection,
    ResumeAgent,
)
from app.core.exceptions import DocumentParsingError
from app.schemas.user_detail import ExperienceItem, ResumeData

RESUME_TEXT = """A Chetan Varma
Associate Data Scientist
chetanvarmaatla@gmail.com | +91 9441321253
https://www.linkedin.com/in/chetan-varma-a-980631335/
Experience
Associate Data Scientist
Seanergy.ai
Feb 2026 - Present
- Developed backend services for AI-powered voice agents.
"""


class TestResumeAgent:
    """The agent repairs the sections the model most often drops."""

    @pytest.mark.asyncio
    async def test_rereads_experience_section_when_first_pass_returns_none(self) -> None:
        client = AsyncMock()
        client.extract.side_effect = [
            ResumeData(headline="Associate Data Scientist", experience=[]),
            ExperienceSection(
                experience=[
                    ExperienceItem(
                        company="Seanergy.ai",
                        role="Associate Data Scientist",
                        start_date="Feb 2026",
                        end_date="Present",
                        responsibilities=["Developed backend services."],
                    )
                ]
            ),
        ]

        result = await ResumeAgent(client).parse(RESUME_TEXT)

        assert client.extract.await_count == 2
        assert [item.company for item in result.experience] == ["Seanergy.ai"]

    @pytest.mark.asyncio
    async def test_does_not_reread_when_experience_was_extracted(self) -> None:
        client = AsyncMock()
        client.extract.return_value = ResumeData(
            headline="Associate Data Scientist",
            experience=[ExperienceItem(company="Seanergy.ai", role="Associate Data Scientist")],
        )

        result = await ResumeAgent(client).parse(RESUME_TEXT)

        assert client.extract.await_count == 1
        assert len(result.experience) == 1

    @pytest.mark.asyncio
    async def test_drops_entries_without_a_role_or_company(self) -> None:
        client = AsyncMock()
        client.extract.return_value = ResumeData(
            headline="Associate Data Scientist",
            experience=[
                ExperienceItem(company="Seanergy.ai", role="Associate Data Scientist"),
                ExperienceItem(responsibilities=["Stray bullet promoted to an entry"]),
            ],
        )

        result = await ResumeAgent(client).parse(RESUME_TEXT)

        assert len(result.experience) == 1
        assert result.experience[0].company == "Seanergy.ai"

    @pytest.mark.asyncio
    async def test_falls_back_to_header_for_a_missing_headline(self) -> None:
        client = AsyncMock()
        client.extract.return_value = ResumeData(
            headline="",
            experience=[ExperienceItem(company="Seanergy.ai", role="Associate Data Scientist")],
        )

        result = await ResumeAgent(client).parse(RESUME_TEXT)

        assert result.headline == "Associate Data Scientist"

    @pytest.mark.asyncio
    async def test_prefers_regex_contacts_and_stops_asking_the_model(self) -> None:
        client = AsyncMock()
        client.extract.return_value = ResumeData(
            headline="Associate Data Scientist",
            experience=[ExperienceItem(company="Seanergy.ai", role="Associate Data Scientist")],
            phone_number="",
            linkedin="",
        )

        result = await ResumeAgent(client).parse(RESUME_TEXT)

        assert result.phone_number == "+91 9441321253"
        assert result.linkedin == "https://www.linkedin.com/in/chetan-varma-a-980631335"
        assert CONTACT_ALREADY_KNOWN_INSTRUCTION in client.extract.await_args.args[2]

    @pytest.mark.asyncio
    async def test_asks_the_model_for_contacts_regex_cannot_find(self) -> None:
        client = AsyncMock()
        client.extract.return_value = ResumeData(
            headline="Associate Data Scientist",
            experience=[ExperienceItem(company="Seanergy.ai", role="Associate Data Scientist")],
            phone_number="+1 (555) 010-2030",
            linkedin="https://linkedin.com/in/jane-doe",
        )
        text = "Jane Doe\nBackend Engineer\nExperience\nEngineer at Acme\n"

        result = await ResumeAgent(client).parse(text)

        assert result.phone_number == "+1 (555) 010-2030"
        assert result.linkedin == "https://linkedin.com/in/jane-doe"
        assert CONTACT_WANTED_INSTRUCTION in client.extract.await_args.args[2]

    @pytest.mark.asyncio
    async def test_keeps_the_parse_when_the_focused_retry_fails(self) -> None:
        client = AsyncMock()
        client.extract.side_effect = [
            ResumeData(headline="Associate Data Scientist", skills=["Python"]),
            DocumentParsingError("Ollama is unavailable"),
        ]

        result = await ResumeAgent(client).parse(RESUME_TEXT)

        assert result.experience == []
        assert result.skills == ["Python"]
