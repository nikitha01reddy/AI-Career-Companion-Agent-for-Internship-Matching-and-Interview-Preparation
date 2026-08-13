"""API tests for resume tailoring endpoint wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_resume_tailoring_service
from app.api.resume_tailoring import router
from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.schemas.auth import UserPublic
from app.schemas.resume_tailoring import TailoredResumeContent
from app.services.resume_tailoring_service import TailoredResumeArtifacts


class TestResumeTailoringAPI:
    """HTTP contract for POST /resume-tailoring."""

    def _client(self, service: AsyncMock, tmp_path: Path) -> TestClient:
        pdf_path = tmp_path / "resume.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        service.tailor.return_value = TailoredResumeArtifacts(
            resume_id=uuid4(),
            content=TailoredResumeContent(name="Rahul", email="rahul@gmail.com"),
            tex_path=tmp_path / "resume.tex",
            pdf_path=pdf_path,
        )
        settings = Settings(
            jwt_secret_key="test-secret-key-at-least-32-bytes!!",
            latex_compiler_path="pdflatex",
            tailored_resume_dir=tmp_path,
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_current_user] = lambda: UserPublic(
            id=uuid4(),
            name="Rahul",
            email="rahul@gmail.com",
        )
        app.dependency_overrides[get_resume_tailoring_service] = lambda: service
        return TestClient(app)

    def test_requires_auth(self) -> None:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.post(
            "/resume-tailoring",
            data={"instructions": "Focus on backend", "user_detail_id": str(uuid4())},
        )
        assert response.status_code == 401

    def test_rejects_blank_instructions(self, tmp_path: Path) -> None:
        client = self._client(AsyncMock(), tmp_path)
        response = client.post(
            "/resume-tailoring",
            data={"instructions": "   ", "user_detail_id": str(uuid4())},
        )
        assert response.status_code == 422

    def test_rejects_both_file_and_detail_id(self, tmp_path: Path) -> None:
        client = self._client(AsyncMock(), tmp_path)
        response = client.post(
            "/resume-tailoring",
            data={
                "instructions": "Focus on backend",
                "user_detail_id": str(uuid4()),
            },
            files={"file": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 422

    def test_returns_pdf(self, tmp_path: Path) -> None:
        service = AsyncMock()
        client = self._client(service, tmp_path)
        detail_id = uuid4()
        response = client.post(
            "/resume-tailoring",
            data={
                "instructions": "Emphasize FastAPI and RAG",
                "user_detail_id": str(detail_id),
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert "X-Resume-Id" in response.headers
        service.tailor.assert_awaited_once()
