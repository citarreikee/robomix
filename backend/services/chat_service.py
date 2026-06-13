from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from config import settings
from services import entroflow_runtime


@dataclass
class ChatTurnContext:
    provider: str
    session_id: str
    messages: List[Dict[str, Any]]
    token_budget: int
    estimated_tokens: int


def get_provider_for_model(model_name: str) -> str:
    if model_name.startswith("deepseek"):
        return "deepseek"
    if model_name.startswith("kimi") or model_name.startswith("moonshot"):
        return "kimi"
    return "ollama"


def _estimate_text_tokens(value: Any) -> int:
    text = "" if value is None else str(value)
    return max(1, (len(text) + 3) // 4) if text else 0


def _estimate_message_tokens(message: Dict[str, Any]) -> int:
    cost = 4 + _estimate_text_tokens(message.get("role")) + _estimate_text_tokens(message.get("content"))
    if message.get("tool_calls"):
        cost += _estimate_text_tokens(json.dumps(message.get("tool_calls"), ensure_ascii=False))
    return cost


def _token_budget(provider: str) -> int:
    window = settings.OLLAMA_CONTEXT_WINDOW
    if provider == "deepseek":
        window = settings.DEEPSEEK_CONTEXT_WINDOW
    elif provider == "kimi":
        window = settings.KIMI_CONTEXT_WINDOW
    if settings.CONTEXT_TOKEN_BUDGET > 0:
        return min(window, settings.CONTEXT_TOKEN_BUDGET)
    return max(1024, int(window * settings.CONTEXT_BUDGET_RATIO))


def _pinned_messages() -> List[Dict[str, Any]]:
    messages = []
    if settings.SYSTEM_PROMPT:
        messages.append({"role": "system", "content": settings.SYSTEM_PROMPT})
    device_prompt = entroflow_runtime.build_registered_devices_system_prompt()
    if device_prompt:
        messages.append({"role": "system", "content": device_prompt})
    if settings.DEVELOPER_PROMPT:
        messages.append({"role": "developer", "content": settings.DEVELOPER_PROMPT})
    return messages


def _build_context(history: List[Any], provider: str) -> tuple[List[Dict[str, Any]], int, int]:
    pinned = _pinned_messages()
    context = [message.to_provider_message() if hasattr(message, "to_provider_message") else dict(message) for message in history]
    budget = _token_budget(provider)
    max_turns = max(1, settings.CONTEXT_MAX_USER_TURNS)
    if sum(_estimate_message_tokens(m) for m in pinned + context) > budget:
        user_indexes = [i for i, m in enumerate(context) if m.get("role") == "user"]
        if len(user_indexes) > max_turns:
            context = context[user_indexes[-max_turns] :]
    while sum(_estimate_message_tokens(m) for m in pinned + context) > budget and context:
        context = context[1:]
    estimated = sum(_estimate_message_tokens(m) for m in pinned + context)
    return pinned + context, budget, estimated


def prepare_chat_turn(session_manager: Any, *, model: str, user_message: str, request_session_id: Optional[str]) -> ChatTurnContext:
    provider = get_provider_for_model(model)
    session = session_manager.get_session(request_session_id) if request_session_id else None
    if not session:
        session = session_manager.create_session(model=model, metadata={"provider": provider})
    session.model = model
    session.metadata["provider"] = provider
    session_manager.add_message(session.session_id, role="user", content=user_message)
    history = session_manager.get_history(session.session_id) or []
    messages, budget, estimated = _build_context(history, provider)
    return ChatTurnContext(provider=provider, session_id=session.session_id, messages=messages, token_budget=budget, estimated_tokens=estimated)


def _parse_sse_data_event(event: str) -> Optional[Dict[str, Any]]:
    if not event.startswith("data: "):
        return None
    try:
        payload = json.loads(event[6:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


async def stream_chat_with_session(
    session_manager: Any,
    react_stream: Callable[..., AsyncIterator[str]],
    *,
    model: str,
    context: ChatTurnContext,
    force_tool_use: bool,
    enable_tools: bool,
) -> AsyncIterator[str]:
    seq = 0
    done_data: Optional[Dict[str, str]] = None
    saved_from_react = False

    def to_sse(payload: Dict[str, Any]) -> str:
        nonlocal seq
        seq += 1
        return f"data: {json.dumps({**payload, 'seq': seq}, ensure_ascii=False)}\n\n"

    async for event in react_stream(
        model=model,
        messages=context.messages,
        provider=context.provider,
        enable_tools=enable_tools,
        force_tool_use=force_tool_use,
    ):
        data = _parse_sse_data_event(event)
        if not data:
            yield event
            continue
        yield to_sse(data)
        if data.get("type") == "done":
            done_data = {"answer": data.get("answer") or data.get("content") or "", "thinking": data.get("thinking", "")}
        elif data.get("type") == "react_complete":
            for msg in data.get("messages", []):
                session_manager.add_message(
                    session_id=context.session_id,
                    role=msg.get("role", "assistant"),
                    content=msg.get("content"),
                    thinking=msg.get("thinking"),
                    tool_calls=msg.get("tool_calls"),
                    tool_call_id=msg.get("tool_call_id"),
                    name=msg.get("name"),
                    reasoning_content=msg.get("reasoning_content"),
                    metadata={"provider": context.provider, "iterations": data.get("iterations", 0)},
                )
            saved_from_react = bool(data.get("messages"))
            done_data = None

    if done_data and not saved_from_react:
        session_manager.add_message(context.session_id, role="assistant", content=done_data["answer"], thinking=done_data["thinking"], metadata={"provider": context.provider})
    yield to_sse({"type": "session_id", "session_id": context.session_id, "token_budget": context.token_budget, "estimated_tokens": context.estimated_tokens})
