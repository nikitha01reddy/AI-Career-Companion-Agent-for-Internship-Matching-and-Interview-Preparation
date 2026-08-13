"""Tests for cover-letter tailoring agent reconciliation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.cover_letter_tailoring_agent import CoverLetterTailoringAgent
from app.schemas.cover_letter_tailoring import (
    LLMTailoredCoverLetterSections,
    TailorCoverLetterContext,
)


class TestCoverLetterTailoringAgent:
    """LLM-only sections + salutation fallback + pruning."""

    @pytest.mark.asyncio
    async def test_prunes_blank_paragraphs(self) -> None:
        client = AsyncMock()
        client.extract.return_value = LLMTailoredCoverLetterSections(
            salutation="Dear Hiring Manager,",
            opening_paragraph="Opening.",
            body_paragraphs=["First paragraph.", "", "Second paragraph."],
            why_this_company="Motivation.",
            closing_paragraph="Thanks.",
            signature="Best regards",
        )
        agent = CoverLetterTailoringAgent(client)
        context = TailorCoverLetterContext(
            instructions="Emphasize backend",
            source_salutation="Dear Team,",
            body_paragraphs=["Seed paragraph."],
        )

        result = await agent.tailor(context)

        assert result.salutation == "Dear Hiring Manager,"
        assert result.body_paragraphs == ["First paragraph.", "Second paragraph."]
        client.extract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_source_salutation_when_llm_empty(self) -> None:
        client = AsyncMock()
        client.extract.return_value = LLMTailoredCoverLetterSections(
            salutation="",
            opening_paragraph="Opening.",
        )
        agent = CoverLetterTailoringAgent(client)
        context = TailorCoverLetterContext(
            instructions="Keep greeting",
            source_salutation="Dear Recruiting Team,",
        )

        result = await agent.tailor(context)

        assert result.salutation == "Dear Recruiting Team,"
        assert result.opening_paragraph == "Opening."
