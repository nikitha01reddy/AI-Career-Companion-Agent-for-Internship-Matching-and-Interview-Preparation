"""Conversation workflow: context -> history -> agent -> persist -> respond."""

from __future__ import annotations

from uuid import UUID

from app.agents.career_agent import CareerAgent
from app.core.exceptions import ResourceAccessDeniedError, ResourceNotFoundError
from app.database.repositories.conversation_repository import ConversationRepository
from app.schemas.conversation import ChatResponse
from app.services.career_context_service import CareerContextService

HISTORY_WINDOW = 5


class ConversationService:
    """Endpoint orchestrator for the conversational career agent."""

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        context_service: CareerContextService,
        agent: CareerAgent,
    ) -> None:
        self._conversations = conversations
        self._context_service = context_service
        self._agent = agent

    async def chat(
        self,
        *,
        user_id: UUID,
        message: str,
        conversation_id: UUID | None = None,
    ) -> ChatResponse:
        """Run one chat turn and persist both messages."""
        conversation = await self._resolve_conversation(user_id, conversation_id)
        context = await self._context_service.build(user_id)
        history = await self._conversations.list_recent(
            conversation.id, limit=HISTORY_WINDOW
        )
        history_dicts = [
            {"role": msg.role, "content": msg.content} for msg in history
        ]

        reply, intent, tool_used = await self._agent.run(
            message=message,
            context=context,
            history=history_dicts,
            user_id=user_id,
        )

        await self._conversations.add_message(conversation.id, "user", message)
        await self._conversations.add_message(conversation.id, "assistant", reply)

        return ChatResponse(
            conversation_id=conversation.id,
            reply=reply,
            intent=intent,
            tool_used=tool_used,
        )

    async def _resolve_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID | None,
    ) -> object:
        if conversation_id is None:
            return await self._conversations.create(user_id)
        conversation = await self._conversations.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFoundError("Conversation not found")
        if conversation.user_id != user_id:
            raise ResourceAccessDeniedError(
                "The selected conversation does not belong to this user"
            )
        return conversation
