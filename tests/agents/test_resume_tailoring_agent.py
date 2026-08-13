"""Tests for resume-tailoring agent reconciliation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.resume_tailoring_agent import ResumeTailoringAgent
from app.schemas.resume_tailoring import (
    LLMTailoredSections,
    SkillGroup,
    TailoredExperienceItem,
    TailoredProjectItem,
    TailorResumeContext,
)


class TestResumeTailoringAgent:
    """LLM-only sections + headline fallback + pruning."""

    @pytest.mark.asyncio
    async def test_prunes_blank_rows_and_keeps_llm_headline(self) -> None:
        client = AsyncMock()
        client.extract.return_value = LLMTailoredSections(
            headline="Backend Engineer",
            summary="Focused backend engineer.",
            skill_groups=[
                SkillGroup(category="Languages", skills=["Python", ""]),
                SkillGroup(category="", skills=["ignored"]),
            ],
            experience=[
                TailoredExperienceItem(role="Intern", company="Acme", bullets=["Built APIs", ""]),
                TailoredExperienceItem(role="", company="", bullets=[]),
            ],
            projects=[
                TailoredProjectItem(name="Matcher", bullets=["RAG search"]),
                TailoredProjectItem(name="", bullets=[]),
            ],
        )
        agent = ResumeTailoringAgent(client)
        context = TailorResumeContext(
            instructions="Emphasize FastAPI",
            source_headline="Software Engineer",
            skills=["Python"],
            experience=[{"role": "Intern", "company": "Acme"}],
        )

        result = await agent.tailor(context)

        assert result.headline == "Backend Engineer"
        assert result.skill_groups == [SkillGroup(category="Languages", skills=["Python"])]
        assert len(result.experience) == 1
        assert result.experience[0].bullets == ["Built APIs"]
        assert len(result.projects) == 1
        client.extract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_source_headline_when_llm_empty(self) -> None:
        client = AsyncMock()
        client.extract.return_value = LLMTailoredSections(
            headline="",
            summary="Short summary.",
        )
        agent = ResumeTailoringAgent(client)
        context = TailorResumeContext(
            instructions="Keep title",
            source_headline="Python Developer",
        )

        result = await agent.tailor(context)

        assert result.headline == "Python Developer"
        assert result.summary == "Short summary."
