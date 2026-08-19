"""Tests for the career-context service (profile + latest resume merge)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.career_context_service import CareerContextService


def _user_with_profile(name="John", skills=None, location="Hyderabad"):
    profile = SimpleNamespace(
        skills=skills or ["Python", "FastAPI"],
        location_preference=location,
    )
    return SimpleNamespace(name=name, email="john@example.com", profile=profile)


def _detail(skills=None):
    return SimpleNamespace(
        headline="Python Developer",
        skills=skills or ["Python", "Docker", "SQL"],
        experience=[{"company": "Acme", "role": "Intern"}],
        projects=[{"name": "API"}],
        education=[{"institution": "Univ"}],
        profile_summary="Backend dev.",
    )


class TestCareerContextService:
    """Merges profile skills + latest resume skills into CareerContext."""

    @pytest.mark.asyncio
    async def test_builds_context_and_dedups_skills(self) -> None:
        users = AsyncMock()
        users.get_by_id.return_value = _user_with_profile(
            skills=["python", "FastAPI", "SQL"]
        )
        details = AsyncMock()
        details.list_by_user.return_value = [_detail(skills=["Python", "Docker"])]

        service = CareerContextService(users, details)
        ctx = await service.build(uuid4())

        assert ctx.name == "John"
        assert ctx.location_preference == "Hyderabad"
        # casefold-dedup: profile "python" is first-seen, casing preserved from first hit
        assert "python" in [s.casefold() for s in ctx.skills]
        assert "FastAPI".casefold() in [s.casefold() for s in ctx.skills]
        assert "Docker".casefold() in [s.casefold() for s in ctx.skills]
        assert "SQL".casefold() in [s.casefold() for s in ctx.skills]
        assert len(ctx.skills) == len(set(s.casefold() for s in ctx.skills))
        assert ctx.resume is not None
        assert ctx.resume.headline == "Python Developer"

    @pytest.mark.asyncio
    async def test_handles_no_resume(self) -> None:
        users = AsyncMock()
        users.get_by_id.return_value = _user_with_profile(skills=["Python"])
        details = AsyncMock()
        details.list_by_user.return_value = []

        service = CareerContextService(users, details)
        ctx = await service.build(uuid4())

        assert ctx.resume is None
        assert ctx.skills == ["Python"]

    @pytest.mark.asyncio
    async def test_handles_missing_user(self) -> None:
        users = AsyncMock()
        users.get_by_id.return_value = None
        details = AsyncMock()

        service = CareerContextService(users, details)
        ctx = await service.build(uuid4())

        assert ctx.name == ""
        assert ctx.resume is None
