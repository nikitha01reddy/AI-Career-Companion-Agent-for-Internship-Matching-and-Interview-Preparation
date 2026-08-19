"""Tests for skill-gap agent pruning and readiness normalization."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.skill_gap_agent import SkillGapAgent
from app.schemas.skill_gap import (
    MatchedSkill,
    ReadinessScore,
    SkillGapContext,
    SkillGapItem,
    SkillGapLLMResult,
)


class TestReadinessScore:
    """Cloud-model drift normalization for readiness fields."""

    def test_accepts_fractional_percentage(self) -> None:
        score = ReadinessScore.model_validate({"matched": 2, "total": 7, "percentage": 28.57})
        assert score.percentage == 29

    def test_accepts_matched_count_aliases(self) -> None:
        score = ReadinessScore.model_validate(
            {"matched_count": 2, "total_count": 7, "percentage": 28.6}
        )
        assert score.matched == 2
        assert score.total == 7
        assert score.percentage == 29


class TestSkillGapAgent:
    """LLM skill-gap analysis + pruning."""

    @pytest.mark.asyncio
    async def test_prunes_blank_rows_and_recomputes_readiness(self) -> None:
        client = AsyncMock()
        client.extract.return_value = SkillGapLLMResult(
            readiness=ReadinessScore(matched=9, total=9, percentage=100),
            matched_skills=[
                MatchedSkill(skill="Python", status="matched"),
                MatchedSkill(skill="  ", status="matched"),
            ],
            skill_gaps=[
                SkillGapItem(
                    skill="Linux",
                    importance="high",
                    reason="Essential for SRE and production system work.",
                ),
                SkillGapItem(skill="", importance="low", reason="ignored"),
                SkillGapItem(skill="Go", importance="medium", reason=""),
            ],
            summary="Strengthen Linux and related ops skills.",
        )
        agent = SkillGapAgent(client)
        context = SkillGapContext(
            skills=["Python"],
            job={"title": "SRE Intern", "required_skills": ["Python", "Linux", "Go"]},
        )

        result = await agent.analyze(context)

        assert result.matched_skills == [MatchedSkill(skill="Python", status="matched")]
        assert len(result.skill_gaps) == 1
        assert result.skill_gaps[0].skill == "Linux"
        assert result.readiness.matched == 1
        assert result.readiness.total == 2
        assert result.readiness.percentage == 50
        assert result.summary == "Strengthen Linux and related ops skills."
        client.extract.assert_awaited_once()
