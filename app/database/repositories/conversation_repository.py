"""Persistence operations for conversations and chat messages."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ChatMessage, Conversation


class ConversationRepository:
    """Data-access layer for chat conversations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: UUID) -> Conversation:
        """Create a new conversation for a user."""
        conversation = Conversation(user_id=user_id)
        self._session.add(conversation)
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        """Fetch a conversation by id."""
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(
        self,
        conversation_id: UUID,
        limit: int = 5,
    ) -> list[ChatMessage]:
        """Return the most recent messages for a conversation, oldest first."""
        result = await self._session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def add_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
    ) -> ChatMessage:
        """Append a message to a conversation."""
        message = ChatMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message
