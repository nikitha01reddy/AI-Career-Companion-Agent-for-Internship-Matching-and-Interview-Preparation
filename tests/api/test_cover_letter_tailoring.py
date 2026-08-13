"""API tests for cover-letter tailoring endpoint wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.cover_letter_tailoring import router
from app.api.dependencies import get_cover_letter_tailoring_service
from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.schemas.auth import UserPublic
from app.schemas.cover_letter_tailoring import TailoredCoverLetterContent
from app.services.cover_letter_tailoring_service import TailoredCoverLetterArtifacts


class TestCoverLetterTailoringAPI:
    """HTTP contract for POST /cover-letter-tailoring."""

    def _client(self, service: AsyncMock, tmp_path: Path) -> TestClient:
        pdf_path = tmp_path / "cover_letter.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        service.tailor.return_value = TailoredCoverLetterArtifacts(
            cover_letter_id=uuid4(),
            content=TailoredCoverLetterContent(
                applicant_name="Rahul",
                email="rahul@gmail.com",
            ),
            tex_path=tmp_path / "cover_letter.tex",
            pdf_path=pdf_path,
        )
        settings = Settings(
            jwt_secret_key="test-secret-key-at-least-32-bytes!!",
            latex_compiler_path="pdflatex",
            tailored_cover_letter_dir=tmp_path,
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_current_user] = lambda: UserPublic(
            id=uuid4(),
            name="Rahul",
            email="rahul@gmail.com",
        )
        app.dependency_overrides[get_cover_letter_tailoring_service] = lambda: service
        return TestClient(app)

    def test_requires_auth(self) -> None:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.post(
            "/cover-letter-tailoring",
            data={"instructions": "Focus on backend", "user_detail_id": str(uuid4())},
        )
        assert response.status_code == 401

    def test_rejects_blank_instructions(self, tmp_path: Path) -> None:
        client = self._client(AsyncMock(), tmp_path)
        response = client.post(
            "/cover-letter-tailoring",
            data={"instructions": "   ", "user_detail_id": str(uuid4())},
        )
        assert response.status_code == 422

    def test_rejects_both_file_and_detail_id(self, tmp_path: Path) -> None:
        client = self._client(AsyncMock(), tmp_path)
        response = client.post(
            "/cover-letter-tailoring",
            data={
                "instructions": "Focus on backend",
                "user_detail_id": str(uuid4()),
            },
            files={"file": ("cover_letter.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 422

    def test_returns_pdf(self, tmp_path: Path) -> None:
        service = AsyncMock()
        client = self._client(service, tmp_path)
        detail_id = uuid4()
        response = client.post(
            "/cover-letter-tailoring",
            data={
                "instructions": "Emphasize FastAPI and RAG",
                "user_detail_id": str(detail_id),
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert "X-Cover-Letter-Id" in response.headers
        service.tailor.assert_awaited_once()
