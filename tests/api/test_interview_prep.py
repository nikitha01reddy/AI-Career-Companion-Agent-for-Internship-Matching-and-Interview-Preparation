"""API tests for interview-prep endpoint wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_interview_prep_service
from app.api.interview_prep import router
from app.auth.dependencies import get_current_user
from app.schemas.auth import UserPublic
from app.schemas.interview_prep import (
    BehavioralQuestion,
    FocusArea,
    InterviewPrepResponse,
    PreparationStep,
    TechnicalQuestion,
)


class TestInterviewPrepAPI:
    """HTTP contract for POST /interview-prep."""

    def _client(self, service: AsyncMock) -> TestClient:
        service.prepare.return_value = InterviewPrepResponse(
            job_title="SRE Intern",
            preparation_summary="Focus on Linux, Python, and monitoring.",
            focus_areas=[
                FocusArea(topic="Linux", reason="Required for SRE role", priority="high"),
                FocusArea(topic="Python", reason="Relevant to the role", priority="high"),
            ],
            technical_questions=[
                TechnicalQuestion(
                    question="What is a process?",
                    topic="Operating Systems",
                    difficulty="medium",
                    expected_points=["separate memory", "threads share memory"],
                )
            ],
            behavioral_questions=[
                BehavioralQuestion(
                    question="Tell me about a challenge.",
                    what_interviewer_looks_for=["Problem solving", "Ownership"],
                )
            ],
            preparation_plan=[
                PreparationStep(
                    step=1,
                    title="Review Job Requirements",
                    description="Study Linux and Python fundamentals.",
                )
            ],
            interview_tips=["Use examples.", "Explain your thinking."],
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: UserPublic(
            id=uuid4(),
            name="Rahul",
            email="rahul@gmail.com",
        )
        app.dependency_overrides[get_interview_prep_service] = lambda: service
        return TestClient(app)

    def test_requires_auth(self) -> None:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.post("/interview-prep", data={"job_id": str(uuid4())})
        assert response.status_code == 401

    def test_rejects_missing_job_id_and_instructions(self) -> None:
        client = self._client(AsyncMock())
        response = client.post("/interview-prep", data={})
        assert response.status_code == 422
        assert "at least one" in response.json()["detail"].lower()

    def test_rejects_invalid_job_id(self) -> None:
        client = self._client(AsyncMock())
        response = client.post("/interview-prep", data={"job_id": "not-a-uuid"})
        assert response.status_code == 422

    def test_accepts_instructions_only(self) -> None:
        service = AsyncMock()
        client = self._client(service)
        response = client.post(
            "/interview-prep",
            data={"instructions": "Focus on system design."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["job_title"] == "SRE Intern"
        assert body["focus_areas"][0]["topic"] == "Linux"
        assert body["technical_questions"][0]["difficulty"] == "medium"
        assert body["preparation_plan"][0]["step"] == 1
        service.prepare.assert_awaited_once()
        assert service.prepare.await_args.kwargs["job_id"] is None
        assert service.prepare.await_args.kwargs["instructions"] == "Focus on system design."

    def test_accepts_job_id_and_instructions(self) -> None:
        service = AsyncMock()
        client = self._client(service)
        job_id = uuid4()
        response = client.post(
            "/interview-prep",
            data={"job_id": str(job_id), "instructions": "  focus on Python  "},
        )
        assert response.status_code == 200
        assert service.prepare.await_args.kwargs["job_id"] == job_id
        assert service.prepare.await_args.kwargs["instructions"] == "focus on Python"
