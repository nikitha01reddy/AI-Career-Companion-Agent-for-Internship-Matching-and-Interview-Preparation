"""Authenticated interview-preparation HTTP endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, status

from app.api.dependencies import get_interview_prep_service
from app.auth.dependencies import get_current_user
from app.core.exceptions import DocumentParsingError, ResourceNotFoundError
from app.schemas.interview_prep import InterviewPrepResponse
from app.services.interview_prep_service import InterviewPrepService

router = APIRouter(
    prefix="/interview-prep",
    tags=["interview preparation"],
    dependencies=[Depends(get_current_user)],
)


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


@router.post("", response_model=InterviewPrepResponse)
async def prepare_interview(
    job_id: str = Form(
        default="",
        description="Optional job ID from the jobs table to prepare against.",
    ),
    instructions: str = Form(
        default="",
        description="Optional free-form guidance sent to the LLM.",
    ),
    service: InterviewPrepService = Depends(get_interview_prep_service),
) -> InterviewPrepResponse:
    """Generate interview preparation guidance for a job and/or instructions."""
    selected_job_id = _parse_optional_uuid(job_id, "job_id")
    cleaned_instructions = instructions.strip()
    if selected_job_id is None and not cleaned_instructions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide at least one of job_id or instructions",
        )

    try:
        return await service.prepare(
            job_id=selected_job_id,
            instructions=cleaned_instructions,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentParsingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
