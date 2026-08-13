"""Tests for resume-tailoring context building and LLM output reconciliation."""

from __future__ import annotations

from types import SimpleNamespace

from app.schemas.resume_tailoring import (
    LLMTailoredSections,
    SkillGroup,
    TailoredProjectItem,
)
from app.schemas.user_detail import ExperienceItem, ProjectItem, ResumeData
from app.services.resume_tailoring_service import ResumeTailoringService, split_skill_values


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        name="Ada Lovelace",
        email="ada@example.com",
        profile=SimpleNamespace(location_preference="Hyderabad", skills=[]),
    )


class TestSplitSkillValues:
    """Comma-joined resume skill lines become atomic skills."""

    def test_splits_on_top_level_commas_only(self) -> None:
        values = ["Python, SQL, C", "Vector Databases (FAISS, Qdrant), LangChain"]

        assert split_skill_values(values) == [
            "Python",
            "SQL",
            "C",
            "Vector Databases (FAISS, Qdrant)",
            "LangChain",
        ]

    def test_drops_blanks_and_case_insensitive_duplicates(self) -> None:
        assert split_skill_values(["Python, , python", "PYTHON"]) == ["Python"]


class TestBuildContext:
    """The LLM receives bullets it can rewrite, not free-text descriptions."""

    def test_seeds_project_bullets_from_description(self) -> None:
        resume = ResumeData(
            projects=[
                ProjectItem(
                    name="Knowledge Engine",
                    description="Built a RAG support system. Added Slack alerts.",
                    technologies=["Python"],
                    url="GitHub",
                )
            ],
            skills=["Python, SQL"],
        )

        context = ResumeTailoringService._build_context(_user(), resume, "Tailor for SDE", None)

        assert context.projects[0]["bullets"] == [
            "Built a RAG support system.",
            "Added Slack alerts.",
        ]
        assert context.skills == ["Python", "SQL"]

    def test_seeds_experience_bullets_from_responsibilities(self) -> None:
        resume = ResumeData(
            experience=[
                ExperienceItem(company="Acme", role="Intern", responsibilities=["Shipped APIs"])
            ]
        )

        context = ResumeTailoringService._build_context(_user(), resume, "Tailor", None)

        assert context.experience[0]["bullets"] == ["Shipped APIs"]


class TestMergeResume:
    """Merging repairs empty bullets and rejects skills the candidate never claimed."""

    def test_restores_project_bullets_when_llm_returns_none(self) -> None:
        resume = ResumeData(
            projects=[
                ProjectItem(name="Knowledge Engine", description="Built a RAG support system.")
            ]
        )
        llm = LLMTailoredSections(
            summary="Summary.",
            projects=[TailoredProjectItem(name="Knowledge Engine", bullets=[])],
        )

        merged = ResumeTailoringService._merge_resume(_user(), resume, llm)

        assert merged.projects[0].bullets == ["Built a RAG support system."]

    def test_drops_skills_absent_from_the_source_resume(self) -> None:
        resume = ResumeData(skills=["Python, Google Colab, Recurrent Neural Networks (RNNs)"])
        llm = LLMTailoredSections(
            summary="Summary.",
            skill_groups=[
                SkillGroup(category="Languages", skills=["Python", "Go"]),
                SkillGroup(category="Ops", skills=["Linux"]),
                SkillGroup(category="ML", skills=["RNNs"]),
            ],
        )

        merged = ResumeTailoringService._merge_resume(_user(), resume, llm)

        assert merged.skill_groups == [
            SkillGroup(category="Languages", skills=["Python"]),
            SkillGroup(category="ML", skills=["RNNs"]),
        ]
