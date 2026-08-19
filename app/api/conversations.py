"""Authenticated conversational career agent HTTP endpoint."""

from __future__ import annotations

import uuid

import pydantic
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_conversation_service
from app.auth.dependencies import get_current_user
from app.core.exceptions import (
    DocumentParsingError,
    ResourceAccessDeniedError,
    ResourceNotFoundError,
)
from app.schemas.auth import UserPublic
from app.schemas.conversation import ChatResponse
from app.services.conversation_service import ConversationService

router = APIRouter(
    prefix="/chat",
    tags=["conversations"],
    dependencies=[Depends(get_current_user)],
)


class _MessageBody(pydantic.BaseModel):
    """JSON body for POST /chat."""

    message: str
    conversation_id: uuid.UUID | None = None

    @pydantic.field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value.strip()


@router.post("", response_model=ChatResponse)
async def chat(
    body: _MessageBody,
    current_user: UserPublic = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ChatResponse:
    """Run one turn of the conversational career agent."""
    try:
        return await service.chat(
            user_id=current_user.id,
            message=body.message,
            conversation_id=body.conversation_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResourceAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DocumentParsingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
