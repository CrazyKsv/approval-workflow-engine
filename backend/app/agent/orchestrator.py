"""Agent orchestration: multi-turn chat with tool calling against Kimi (Moonshot).

Uses the OpenAI SDK pointed at the Moonshot base URL. Every model step and tool
invocation is persisted to agent_messages (args, result, latency, error) so a full
trace is available via the API; transient model failures are retried with backoff.
"""
import json
import logging
import time

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from sqlalchemy.orm import Session
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.agent.prompts import build_system_prompt
from app.agent.tools import TOOL_SCHEMAS, run_tool
from app.config import get_settings
from app.exceptions import NotFoundError, PermissionDeniedError
from app.models import AgentConversation, AgentMessage, User, utcnow
from app.schemas import AgentChatResponse, AgentToolEvent

logger = logging.getLogger("agent.orchestrator")

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Module-level factory so tests can monkeypatch it with a scripted fake."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(api_key=settings.kimi_api_key, base_url=settings.kimi_base_url)
    return _client


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _complete(client: OpenAI, messages: list[dict]):
    settings = get_settings()
    # kimi-k2.6 only accepts the default temperature, so none is set here.
    return client.chat.completions.create(
        model=settings.kimi_model,
        messages=messages,
        tools=TOOL_SCHEMAS,
    )


def _load_conversation(db: Session, user: User, conversation_id: int | None, first_message: str) -> AgentConversation:
    if conversation_id is not None:
        conversation = db.get(AgentConversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        if conversation.user_id != user.id:
            raise PermissionDeniedError("This conversation belongs to another user")
        return conversation
    conversation = AgentConversation(user_id=user.id, title=first_message[:80])
    db.add(conversation)
    db.flush()
    return conversation


def _history_to_messages(conversation: AgentConversation, limit: int) -> list[dict]:
    messages: list[dict] = []
    for row in conversation.messages[-limit:]:
        if row.role == "user":
            messages.append({"role": "user", "content": row.content or ""})
        elif row.role == "assistant":
            msg: dict = {"role": "assistant", "content": row.content or ""}
            if row.tool_calls:
                msg["tool_calls"] = row.tool_calls
            messages.append(msg)
        elif row.role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": row.tool_call_id,
                    "content": json.dumps(row.tool_result) if row.tool_result is not None else (row.error or "{}"),
                }
            )
    return messages


def chat(db: Session, user: User, message: str, conversation_id: int | None = None) -> AgentChatResponse:
    settings = get_settings()
    conversation = _load_conversation(db, user, conversation_id, message)
    db.add(AgentMessage(conversation_id=conversation.id, role="user", content=message))
    db.commit()

    messages = [{"role": "system", "content": build_system_prompt(user)}]
    messages += _history_to_messages(conversation, settings.agent_history_limit)

    client = get_client()
    tool_events: list[AgentToolEvent] = []

    for _ in range(settings.agent_max_iterations):
        try:
            response = _complete(client, messages)
        except Exception as exc:
            logger.exception("Model call failed after retries")
            error_text = f"model_error: {type(exc).__name__}"
            reply = "The AI service is currently unavailable. Your data is unchanged — please try again shortly."
            db.add(
                AgentMessage(conversation_id=conversation.id, role="assistant", content=reply, error=error_text)
            )
            db.commit()
            return AgentChatResponse(conversation_id=conversation.id, reply=reply, tool_events=tool_events)

        choice = response.choices[0].message
        tool_calls = choice.tool_calls or []

        if not tool_calls:
            reply = choice.content or ""
            db.add(AgentMessage(conversation_id=conversation.id, role="assistant", content=reply))
            conversation.updated_at = utcnow()
            db.commit()
            return AgentChatResponse(conversation_id=conversation.id, reply=reply, tool_events=tool_events)

        serialized_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in tool_calls
        ]
        db.add(
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=choice.content,
                tool_calls=serialized_calls,
            )
        )
        db.commit()
        messages.append({"role": "assistant", "content": choice.content or "", "tool_calls": serialized_calls})

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            started = time.monotonic()
            if args is None:
                result = {"error": "invalid_arguments", "message": "Tool arguments were not valid JSON"}
            else:
                result = run_tool(db, user, name, args)
            latency_ms = int((time.monotonic() - started) * 1000)
            error = result.get("error") if isinstance(result, dict) else None
            logger.info("tool=%s user=%s latency_ms=%d error=%s", name, user.email, latency_ms, error)
            db.add(
                AgentMessage(
                    conversation_id=conversation.id,
                    role="tool",
                    tool_call_id=tc.id,
                    tool_name=name,
                    tool_args=args,
                    tool_result=result,
                    latency_ms=latency_ms,
                    error=error,
                )
            )
            db.commit()
            tool_events.append(
                AgentToolEvent(tool_name=name, arguments=args or {}, result=result, latency_ms=latency_ms, error=error)
            )
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

    reply = (
        "I hit the maximum number of orchestration steps for one message. "
        "The actions completed so far are recorded; please continue with a follow-up message."
    )
    db.add(AgentMessage(conversation_id=conversation.id, role="assistant", content=reply, error="max_iterations"))
    db.commit()
    return AgentChatResponse(conversation_id=conversation.id, reply=reply, tool_events=tool_events)
