"""API tests for skill-gap endpoint wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_skill_gap_service
from app.api.skill_gaps import router
from app.auth.dependencies import get_current_user
from app.schemas.auth import UserPublic
from app.schemas.skill_gap import (
    MatchedSkill,
    ReadinessScore,
    SkillGapItem,
    SkillGapResponse,
)


class TestSkillGapsAPI:
    """HTTP contract for POST /skill-gaps."""

    def _client(self, service: AsyncMock) -> TestClient:
        service.analyze.return_value = SkillGapResponse(
            job_title="SRE Intern",
            readiness=ReadinessScore(matched=1, total=5, percentage=20),
            matched_skills=[MatchedSkill(skill="Python", status="matched")],
            skill_gaps=[
                SkillGapItem(
                    skill="Linux",
                    importance="high",
                    reason="Essential for SRE and production system work.",
                )
            ],
            summary=(
                "You have a foundation in Python. Strengthen Linux, Prometheus, "
                "Grafana, and Go to improve your readiness for this role."
            ),
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: UserPublic(
            id=uuid4(),
            name="Rahul",
            email="rahul@gmail.com",
        )
        app.dependency_overrides[get_skill_gap_service] = lambda: service
        return TestClient(app)

    def test_requires_auth(self) -> None:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.post(
            "/skill-gaps",
            data={"job_id": str(uuid4()), "user_detail_id": str(uuid4())},
        )
        assert response.status_code == 401

    def test_rejects_both_file_and_detail_id(self) -> None:
        client = self._client(AsyncMock())
        response = client.post(
            "/skill-gaps",
            data={
                "job_id": str(uuid4()),
                "user_detail_id": str(uuid4()),
            },
            files={"file": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 422

    def test_rejects_missing_job_id(self) -> None:
        client = self._client(AsyncMock())
        response = client.post(
            "/skill-gaps",
            data={"user_detail_id": str(uuid4())},
        )
        assert response.status_code == 422

    def test_rejects_invalid_job_id(self) -> None:
        client = self._client(AsyncMock())
        response = client.post(
            "/skill-gaps",
            data={"job_id": "not-a-uuid", "user_detail_id": str(uuid4())},
        )
        assert response.status_code == 422

    def test_returns_skill_gap_payload(self) -> None:
        service = AsyncMock()
        client = self._client(service)
        detail_id = uuid4()
        job_id = uuid4()
        response = client.post(
            "/skill-gaps",
            data={
                "job_id": str(job_id),
                "user_detail_id": str(detail_id),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["job_title"] == "SRE Intern"
        assert body["readiness"]["percentage"] == 20
        assert body["matched_skills"][0]["skill"] == "Python"
        assert body["skill_gaps"][0]["importance"] == "high"
        service.analyze.assert_awaited_once()
