"""LangGraph conversational career agent.

Three nodes:
  - intent_router: structured-extraction call classifies intent + args.
  - dispatch: pure-Python routing to a CareerTools method (or none).
  - compose: plain ChatOllama call produces the natural-language reply.

Edges: START -> intent_router -> dispatch -> compose -> END.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from app.agents.career_tools import CareerTools, ToolResult
from app.llm.client import StructuredExtractionClient
from app.schemas.conversation import CareerContext, IntentDecision

ROUTER_INSTRUCTIONS = (
    "You classify a user's chat message into one career-assistant intent. "
    "The DOCUMENT JSON has `message` (the user's latest message), `history` "
    "(recent prior turns, oldest first), and `context` (the candidate's "
    "profile + resume). "
    "Choose exactly one `intent`: "
    "`greet` — the user is saying hi / starting the conversation; "
    "`find_jobs` — the user wants internship listings or job search; "
    "`match` — the user wants to know how well they fit a job or which job is best; "
    "`skill_gap` — the user asks what skills they are missing for a job; "
    "`interview_prep` — the user asks how to prepare for an interview; "
    "`general` — anything else the agent can answer directly "
    "(advice, questions about the platform). "
    "If the user references a specific job by id or description from prior tool output, "
    "set `job_id` to that job's id when known; otherwise leave `job_id` null. "
    "For `find_jobs`, put the search keywords in `query` and any city/region in `location`. "
    "For `interview_prep`, put any extra guidance in `instructions` (empty if none). "
    "Field-name rules (use these EXACT JSON keys — do not rename them): "
    "the response must have: intent, job_id, query, location, instructions. "
    "Example: {\"intent\":\"find_jobs\",\"job_id\":null,\"query\":\"Python internships\","
    "\"location\":\"Hyderabad\",\"instructions\":\"\"}."
)

COMPOSE_SYSTEM = (
    "You are a concise, friendly career assistant for internship candidates. "
    "You are talking to {name}. "
    "Use the candidate context and any tool results provided to answer. "
    "If this is the first turn (no history) and the user is greeting you, "
    "greet them by name and ask how you can help with internships, career "
    "guidance, or interview preparation. "
    "Never invent job matches, scores, skill gaps, or interview details — "
    "only use data from the tool results. If a tool reported an error or "
    "missing resume, tell the user what they need to do. "
    "Always respond in natural conversational English. "
    "Never output JSON, raw data, or structured output. "
    "When listing jobs, present them as a short readable list with title, "
    "company, location, and a one-line summary. "
    "Keep replies under 150 words unless the user explicitly asks for "
    "detail. Use bullet points, not tables. Be concise and natural."
)


class AgentState(TypedDict, total=False):
    """Mutable state passed between graph nodes."""

    user_id: Any
    message: str
    context: CareerContext
    history: list[dict[str, str]]
    intent: str
    router_args: dict[str, Any]
    tool_result: ToolResult | None
    reply: str


class CareerAgent:
    """Conversational career agent backed by a LangGraph state machine."""

    def __init__(
        self,
        *,
        chat_model: ChatOllama,
        extraction_client: StructuredExtractionClient,
        tools: CareerTools,
    ) -> None:
        self._chat_model = chat_model
        self._extraction_client = extraction_client
        self._tools = tools
        self._graph = self._build_graph()

    async def run(
        self,
        message: str,
        context: CareerContext,
        history: list[dict[str, str]],
        user_id: Any,
    ) -> tuple[str, str, str | None]:
        """Run one turn; return (reply, intent, tool_used)."""
        state: AgentState = {
            "user_id": user_id,
            "message": message,
            "context": context,
            "history": history,
        }
        final = await self._graph.ainvoke(state)
        return (
            final.get("reply", ""),
            final.get("intent", "general"),
            final.get("tool_result").tool if final.get("tool_result") else None,
        )

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("intent_router", self._intent_router)
        graph.add_node("dispatch", self._dispatch)
        graph.add_node("compose", self._compose)
        graph.add_edge(START, "intent_router")
        graph.add_edge("intent_router", "dispatch")
        graph.add_edge("dispatch", "compose")
        graph.add_edge("compose", END)
        return graph.compile()

    async def _intent_router(self, state: AgentState) -> AgentState:
        document = json.dumps(
            {
                "message": state["message"],
                "history": state.get("history", []),
                "context": state["context"].model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        try:
            decision = await self._extraction_client.extract(
                document,
                IntentDecision,
                ROUTER_INSTRUCTIONS,
            )
            return {"intent": decision.intent, **_decision_args(decision)}
        except Exception:
            return {"intent": "general"}

    async def _dispatch(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "general")
        message = state["message"]
        user_id = state.get("user_id")
        if intent == "find_jobs":
            args = state.get("router_args", {})
            result = await self._tools.job_search(
                query=args.get("query") or message,
                location=args.get("location"),
            )
            return {"tool_result": result}
        if intent == "match":
            result = await self._tools.match_jobs(user_id=user_id)
            return {"tool_result": result}
        if intent == "skill_gap":
            args = state.get("router_args", {})
            job_id = args.get("job_id")
            if job_id is None:
                return {"tool_result": None}
            result = await self._tools.skill_gap(user_id=user_id, job_id=job_id)
            return {"tool_result": result}
        if intent == "interview_prep":
            args = state.get("router_args", {})
            result = await self._tools.interview_prep(
                job_id=args.get("job_id"),
                instructions=args.get("instructions") or "",
            )
            return {"tool_result": result}
        return {"tool_result": None}

    async def _compose(self, state: AgentState) -> AgentState:
        context = state["context"]
        tool_result = state.get("tool_result")
        messages: list[Any] = [
            SystemMessage(content=COMPOSE_SYSTEM.format(name=context.name)),
            SystemMessage(content=_context_block(context, tool_result)),
        ]
        for turn in state.get("history", []):
            role = turn.get("role")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=state["message"]))
        response = await self._chat_model.ainvoke(messages)
        reply = response.content if isinstance(response.content, str) else str(response.content)
        return {"reply": reply.strip()}


def _decision_args(decision: IntentDecision) -> dict[str, Any]:
    return {
        "router_args": {
            "job_id": decision.job_id,
            "query": decision.query,
            "location": decision.location,
            "instructions": decision.instructions,
        }
    }


def _context_block(context: CareerContext, tool_result: ToolResult | None) -> str:
    parts = [f"CANDIDATE_CONTEXT:\n{context.model_dump_json(indent=2)}"]
    if tool_result is not None:
        label = tool_result.tool
        payload = (
            {"error": tool_result.error} if tool_result.error else tool_result.data
        )
        parts.append(
            f"TOOL_RESULT ({label}):\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )
    return "\n\n".join(parts)
