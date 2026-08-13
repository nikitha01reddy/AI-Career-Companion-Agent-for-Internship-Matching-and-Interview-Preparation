"""Authenticated cover-letter-tailoring HTTP endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.dependencies import get_cover_letter_tailoring_service
from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    DocumentParsingError,
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidDocumentError,
    InvalidDocumentSelectionError,
    LatexCompileError,
    LatexCompilerMissingError,
    LatexRenderError,
    ResourceAccessDeniedError,
    ResourceNotFoundError,
    UnsupportedDocumentTypeError,
)
from app.schemas.auth import UserPublic
from app.services.cover_letter_tailoring_service import CoverLetterTailoringService

router = APIRouter(prefix="/cover-letter-tailoring", tags=["cover letter tailoring"])


async def _read_upload(file: UploadFile, settings: Settings) -> bytes:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        return await file.read(max_bytes + 1)
    finally:
        await file.close()


def _parse_optional_uuid(value: str, field_name: str) -> uuid.UUID | None:
    if not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} must be a valid UUID",
        ) from exc


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


@router.post("")
async def tailor_cover_letter(
    instructions: str = Form(..., description="How to tailor the cover letter."),
    file: UploadFile | None = File(
        default=None,
        description="Optional PDF/DOCX cover letter. Parsed, saved, then tailored.",
    ),
    user_detail_id: str = Form(
        default="",
        description="Optional existing parsed cover letter ID. Do not send with file.",
    ),
    job_id: str = Form(
        default="",
        description="Optional job ID from the jobs table to tailor toward.",
    ),
    current_user: UserPublic = Depends(get_current_user),
    service: CoverLetterTailoringService = Depends(get_cover_letter_tailoring_service),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Tailor a cover letter and return the compiled PDF."""
    if not instructions.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="instructions must not be blank",
        )

    selected_detail_id = _parse_optional_uuid(user_detail_id, "user_detail_id")
    selected_job_id = _parse_optional_uuid(job_id, "job_id")
    has_upload = file is not None and bool((file.filename or "").strip())
    if has_upload == (selected_detail_id is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide exactly one of user_detail_id or file",
        )

    cover_letter_bytes: bytes | None = None
    cover_letter_name: str | None = None
    if has_upload and file is not None:
        cover_letter_bytes = await _read_upload(file, settings)
        cover_letter_name = file.filename or "cover_letter.pdf"

    try:
        artifacts = await service.tailor(
            user_id=current_user.id,
            instructions=instructions,
            cover_letter_file_name=cover_letter_name,
            cover_letter_content=cover_letter_bytes,
            user_detail_id=selected_detail_id,
            job_id=selected_job_id,
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
    except LatexCompilerMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (LatexRenderError, LatexCompileError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return FileResponse(
        path=artifacts.pdf_path,
        media_type="application/pdf",
        filename=f"tailored-cover-letter-{artifacts.cover_letter_id}.pdf",
        headers={"X-Cover-Letter-Id": str(artifacts.cover_letter_id)},
    )
