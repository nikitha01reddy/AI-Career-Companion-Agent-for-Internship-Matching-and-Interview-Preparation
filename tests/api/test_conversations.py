"""API tests for the conversational career agent endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.conversations import router
from app.api.dependencies import get_conversation_service
from app.auth.dependencies import get_current_user
from app.schemas.auth import UserPublic
from app.schemas.conversation import ChatResponse


class TestConversationsAPI:
    """HTTP contract for POST /chat."""

    def _client(self, service: AsyncMock) -> TestClient:
        service.chat.return_value = ChatResponse(
            conversation_id=uuid4(),
            reply="Hi John! How can I assist you today?",
            intent="greet",
            tool_used=None,
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: UserPublic(
            id=uuid4(),
            name="John",
            email="john@gmail.com",
        )
        app.dependency_overrides[get_conversation_service] = lambda: service
        return TestClient(app)

    def test_requires_auth(self) -> None:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.post("/chat", json={"message": "Hi"})
        assert response.status_code == 401

    def test_rejects_blank_message(self) -> None:
        client = self._client(AsyncMock())
        response = client.post("/chat", json={"message": "  "})
        assert response.status_code == 422

    def test_returns_chat_payload(self) -> None:
        service = AsyncMock()
        client = self._client(service)
        response = client.post(
            "/chat",
            json={"message": "Hi"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "conversation_id" in body
        assert "Hi John" in body["reply"]
        assert body["intent"] == "greet"
        service.chat.assert_awaited_once()

    def test_passes_conversation_id(self) -> None:
        service = AsyncMock()
        client = self._client(service)
        conv_id = uuid4()
        response = client.post(
            "/chat",
            json={"message": "Find jobs", "conversation_id": str(conv_id)},
        )
        assert response.status_code == 200
        service.chat.assert_awaited_once()
        assert service.chat.await_args.kwargs["conversation_id"] == conv_id
