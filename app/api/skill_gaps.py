"""Authenticated skill-gap analysis HTTP endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import get_skill_gap_service
from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    DocumentParsingError,
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidDocumentError,
    InvalidDocumentSelectionError,
    ResourceAccessDeniedError,
    ResourceNotFoundError,
    UnsupportedDocumentTypeError,
)
from app.schemas.auth import UserPublic
from app.schemas.skill_gap import SkillGapResponse
from app.services.skill_gap_service import SkillGapService

router = APIRouter(prefix="/skill-gaps", tags=["skill gaps"])


async def _read_upload(file: UploadFile, settings: Settings) -> bytes:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        return await file.read(max_bytes + 1)
    finally:
        await file.close()


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} must be a valid UUID",
        ) from exc


def _parse_optional_uuid(value: str, field_name: str) -> uuid.UUID | None:
    if not value.strip():
        return None
    return _parse_uuid(value, field_name)


def _raise_document_http_error(exc: Exception) -> None:
    if isinstance(exc, DocumentTooLargeError):
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc))
    if isinstance(exc, UnsupportedDocumentTypeError):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        )
    if isinstance(exc, (EmptyDocumentError, InvalidDocumentError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    if isinstance(exc, DocumentParsingError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    raise exc


@router.post("", response_model=SkillGapResponse)
async def analyze_skill_gaps(
    job_id: str = Form(..., description="Job ID from the jobs table to compare against."),
    file: UploadFile | None = File(
        default=None,
        description="Optional PDF/DOCX resume. Parsed, then skills are compared.",
    ),
    user_detail_id: str = Form(
        default="",
        description="Optional existing parsed resume ID. Do not send with file.",
    ),
    current_user: UserPublic = Depends(get_current_user),
    service: SkillGapService = Depends(get_skill_gap_service),
    settings: Settings = Depends(get_settings),
) -> SkillGapResponse:
    """Compare candidate skills to a job and return readiness + skill gaps."""
    selected_job_id = _parse_uuid(job_id, "job_id")
    selected_detail_id = _parse_optional_uuid(user_detail_id, "user_detail_id")
    has_upload = file is not None and bool((file.filename or "").strip())
    if has_upload == (selected_detail_id is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide exactly one of user_detail_id or file",
        )

    resume_bytes: bytes | None = None
    resume_name: str | None = None
    if has_upload and file is not None:
        resume_bytes = await _read_upload(file, settings)
        resume_name = file.filename or "resume.pdf"

    try:
        return await service.analyze(
            user_id=current_user.id,
            job_id=selected_job_id,
            resume_file_name=resume_name,
            resume_content=resume_bytes,
            user_detail_id=selected_detail_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResourceAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidDocumentSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (
        DocumentParsingError,
        DocumentTooLargeError,
        EmptyDocumentError,
        InvalidDocumentError,
        UnsupportedDocumentTypeError,
    ) as exc:
        _raise_document_http_error(exc)
        raise AssertionError("unreachable") from exc
