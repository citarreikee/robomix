import json
from typing import Any, AsyncGenerator, Dict

import httpx

from config import settings
from protocol import StreamState, format_exception_message, format_http_error


def _format_messages(messages: list) -> list:
    formatted = []
    for msg in messages:
        role = "system" if msg.get("role") == "developer" else msg.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        item = {"role": role, "content": msg.get("content") if msg.get("content") is not None else ""}
        for key in ("tool_calls", "tool_call_id", "name", "reasoning_content"):
            if key in msg:
                item[key] = msg[key]
        formatted.append(item)
    return formatted


async def stream_ollama_response(model: str, messages: list) -> AsyncGenerator[str, None]:
    async for event in stream_ollama_with_tools(model, messages, []):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_ollama_with_tools(model: str, messages: list, tools: list) -> AsyncGenerator[Dict[str, Any], None]:
    state = StreamState()
    try:
        payload: Dict[str, Any] = {"model": model, "messages": _format_messages(messages), "stream": True}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{settings.OLLAMA_API_BASE}/api/chat", json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="ignore")
                    yield state.error_event(format_http_error("Ollama request failed", response.status_code, body))
                    return
                saw_done = False
                tool_calls = []
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    start = state.make_start_event()
                    if start:
                        yield start
                    message = data.get("message", {}) or {}
                    thinking = message.get("thinking", "")
                    if thinking:
                        state.append_thinking(thinking)
                        yield {"type": "thinking_token", "content": thinking}
                    content = message.get("content", "")
                    if content:
                        state.append_content(content)
                        yield {"type": "response_token", "content": content}
                    if "tool_calls" in message:
                        tool_calls = message["tool_calls"]
                    if data.get("done", False):
                        state.mark_finish_reason("stop")
                        saw_done = True
                        break
                if not saw_done:
                    yield state.error_event("Ollama stream ended unexpectedly.")
                    return
                yield state.done_event(answer_key="content", tool_calls=tool_calls)
    except Exception as exc:
        yield state.error_event(format_exception_message(exc)) if not state.terminated else {"type": "error", "message": format_exception_message(exc)}


async def get_ollama_models() -> list[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.OLLAMA_API_BASE}/api/tags")
        response.raise_for_status()
        return [
            {"name": item["name"], "id": item["name"], "provider": "ollama", "size": str(item.get("size", "")), "modified": item.get("modified_at", "")}
            for item in response.json().get("models", [])
        ]
