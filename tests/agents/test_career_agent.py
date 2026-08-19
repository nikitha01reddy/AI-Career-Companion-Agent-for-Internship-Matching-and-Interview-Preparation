"""Tests for the career agent intent-routing and dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.agents.career_agent import CareerAgent
from app.agents.career_tools import ToolResult
from app.schemas.conversation import CareerContext, IntentDecision, ResumeContext


def _context(name="John"):
    return CareerContext(
        name=name,
        skills=["Python"],
        location_preference="Hyderabad",
        resume=ResumeContext(headline="Python Developer", skills=["Python"]),
    )


def _make_agent(client_extract, chat_reply, tools):
    client = AsyncMock()
    client.extract = client_extract
    chat_model = AsyncMock()
    chat_model.ainvoke = AsyncMock(
        return_value=SimpleNamespace_content(chat_reply)
    )
    return CareerAgent(chat_model=chat_model, extraction_client=client, tools=tools)


def SimpleNamespace_content(text):
    from types import SimpleNamespace

    return SimpleNamespace(content=text)


class TestCareerAgent:
    """Intent routing dispatches to the right tool; compose produces reply."""

    @pytest.mark.asyncio
    async def test_find_jobs_calls_job_search(self) -> None:
        tools = AsyncMock()
        tools.job_search.return_value = ToolResult(
            tool="job_search", data=[{"title": "SRE Intern"}]
        )
        client_extract = AsyncMock(
            return_value=IntentDecision(
                intent="find_jobs",
                query="Python internships",
                location="Hyderabad",
            )
        )
        agent = _make_agent(client_extract, "Found 1 internship.", tools)

        reply, intent, tool_used = await agent.run(
            message="Find Python internships in Hyderabad",
            context=_context(),
            history=[],
            user_id=uuid4(),
        )

        assert intent == "find_jobs"
        assert tool_used == "job_search"
        assert reply == "Found 1 internship."
        tools.job_search.assert_awaited_once()
        tools.match_jobs.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_match_calls_match_jobs(self) -> None:
        tools = AsyncMock()
        tools.match_jobs.return_value = ToolResult(
            tool="match_jobs", data=[{"score": 0.9}]
        )
        client_extract = AsyncMock(
            return_value=IntentDecision(intent="match")
        )
        agent = _make_agent(client_extract, "Your best match is SRE Intern.", tools)
        uid = uuid4()

        reply, intent, tool_used = await agent.run(
            message="Which job is best for me?",
            context=_context(),
            history=[],
            user_id=uid,
        )

        assert intent == "match"
        assert tool_used == "match_jobs"
        tools.match_jobs.assert_awaited_once_with(user_id=uid)

    @pytest.mark.asyncio
    async def test_skill_gap_calls_skill_gap_tool(self) -> None:
        job_id = uuid4()
        tools = AsyncMock()
        tools.skill_gap.return_value = ToolResult(
            tool="skill_gap", data={"summary": "Missing Linux."}
        )
        client_extract = AsyncMock(
            return_value=IntentDecision(intent="skill_gap", job_id=job_id)
        )
        agent = _make_agent(client_extract, "Your main gap is Linux.", tools)
        uid = uuid4()

        reply, intent, tool_used = await agent.run(
            message="What skills am I missing?",
            context=_context(),
            history=[],
            user_id=uid,
        )

        assert intent == "skill_gap"
        assert tool_used == "skill_gap"
        tools.skill_gap.assert_awaited_once_with(user_id=uid, job_id=job_id)

    @pytest.mark.asyncio
    async def test_interview_prep_calls_interview_tool(self) -> None:
        job_id = uuid4()
        tools = AsyncMock()
        tools.interview_prep.return_value = ToolResult(
            tool="interview_prep", data={"preparation_summary": "Focus on Linux."}
        )
        client_extract = AsyncMock(
            return_value=IntentDecision(
                intent="interview_prep", job_id=job_id, instructions="focus on Python"
            )
        )
        agent = _make_agent(client_extract, "Focus on Linux fundamentals.", tools)

        reply, intent, tool_used = await agent.run(
            message="How do I prepare?",
            context=_context(),
            history=[],
            user_id=uuid4(),
        )

        assert intent == "interview_prep"
        assert tool_used == "interview_prep"
        tools.interview_prep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_greet_skips_tools(self) -> None:
        tools = AsyncMock()
        client_extract = AsyncMock(return_value=IntentDecision(intent="greet"))
        agent = _make_agent(
            client_extract, "Hi John! How can I assist you today?", tools
        )

        reply, intent, tool_used = await agent.run(
            message="Hi",
            context=_context(name="John"),
            history=[],
            user_id=uuid4(),
        )

        assert intent == "greet"
        assert tool_used is None
        tools.job_search.assert_not_awaited()
        tools.match_jobs.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_router_fallback_on_extraction_error(self) -> None:
        tools = AsyncMock()
        client_extract = AsyncMock(side_effect=Exception("LLM down"))
        agent = _make_agent(client_extract, "I can help with that.", tools)

        reply, intent, tool_used = await agent.run(
            message="something random",
            context=_context(),
            history=[],
            user_id=uuid4(),
        )

        assert intent == "general"
        assert tool_used is None
        assert "I can help" in reply

    @pytest.mark.asyncio
    async def test_skill_gap_without_job_id_skips_tool(self) -> None:
        tools = AsyncMock()
        client_extract = AsyncMock(
            return_value=IntentDecision(intent="skill_gap", job_id=None)
        )
        agent = _make_agent(client_extract, "Which job are you asking about?", tools)

        reply, intent, tool_used = await agent.run(
            message="What skills am I missing?",
            context=_context(),
            history=[],
            user_id=uuid4(),
        )

        assert intent == "skill_gap"
        assert tool_used is None
        tools.skill_gap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_id_uuid_passthrough(self) -> None:
        uid: UUID = uuid4()
        tools = AsyncMock()
        tools.match_jobs.return_value = ToolResult(tool="match_jobs", data=[])
        client_extract = AsyncMock(return_value=IntentDecision(intent="match"))
        agent = _make_agent(client_extract, "Here are your matches.", tools)

        await agent.run(
            message="match me",
            context=_context(),
            history=[],
            user_id=uid,
        )

        assert tools.match_jobs.await_args.kwargs["user_id"] == uid
