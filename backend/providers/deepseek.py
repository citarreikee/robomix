import json
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from config import settings
from protocol import StreamState, format_exception_message, format_http_error, parse_json_payload


DEEPSEEK_URL = f"{settings.DEEPSEEK_API_BASE}/chat/completions"


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}


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


def _pick_choice(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    choices = payload.get("choices", [])
    if not choices:
        return None
    return next((choice for choice in choices if choice.get("index", 0) == 0), choices[0])


async def stream_deepseek_response(model: str, messages: list) -> AsyncGenerator[str, None]:
    async for event in stream_deepseek_with_tools(model, messages, []):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_deepseek_with_tools(model: str, messages: list, tools: list) -> AsyncGenerator[Dict[str, Any], None]:
    state = StreamState()
    if not settings.DEEPSEEK_API_KEY:
        yield state.error_event("DEEPSEEK_API_KEY is not configured. Set it in backend/.env or choose another model provider.")
        return
    try:
        payload: Dict[str, Any] = {"model": model, "messages": _format_messages(messages), "stream": True}
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            async with client.stream("POST", DEEPSEEK_URL, json=payload, headers=_headers()) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="ignore")
                    yield state.error_event(format_http_error("DeepSeek request failed", response.status_code, body))
                    return

                tool_calls: Dict[int, Dict[str, Any]] = {}
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    if line == "data: [DONE]":
                        state.mark_done_sentinel()
                        break
                    if not line.startswith("data: "):
                        continue

                    start = state.make_start_event()
                    if start:
                        yield start

                    choice = _pick_choice(parse_json_payload(line[6:], context="DeepSeek stream"))
                    if not choice:
                        continue
                    delta = choice.get("delta", {}) or {}
                    state.mark_finish_reason(choice.get("finish_reason"))

                    thinking = delta.get("reasoning_content", "")
                    if thinking:
                        state.append_thinking(thinking)
                        yield {"type": "thinking_token", "content": thinking}

                    content = delta.get("content", "")
                    if content:
                        state.append_content(content)
                        yield {"type": "response_token", "content": content}

                    for chunk in delta.get("tool_calls", []) or []:
                        idx = chunk.get("index", 0)
                        if idx not in tool_calls:
                            tool_calls[idx] = {"id": chunk.get("id", ""), "type": chunk.get("type", "function"), "function": {"name": "", "arguments": ""}}
                        if "id" in chunk:
                            tool_calls[idx]["id"] = chunk["id"]
                        if "type" in chunk:
                            tool_calls[idx]["type"] = chunk["type"]
                        func = chunk.get("function") or {}
                        if "name" in func:
                            tool_calls[idx]["function"]["name"] = func["name"]
                        if "arguments" in func and func["arguments"] is not None:
                            tool_calls[idx]["function"]["arguments"] += str(func["arguments"])

                if not state.saw_done_sentinel and not state.saw_finish_reason:
                    yield state.error_event("DeepSeek stream ended unexpectedly.")
                    return

                yield state.done_event(
                    answer_key="content",
                    tool_calls=[tool_calls[i] for i in sorted(tool_calls)],
                    include_reasoning_content=True,
                )
    except Exception as exc:
        yield state.error_event(format_exception_message(exc)) if not state.terminated else {"type": "error", "message": format_exception_message(exc)}


async def get_deepseek_models() -> list[Dict[str, Any]]:
    return [
        {"name": "deepseek-v4-flash", "id": "deepseek-v4-flash", "provider": "deepseek", "size": "API", "modified": ""},
        {"name": "deepseek-v4-pro", "id": "deepseek-v4-pro", "provider": "deepseek", "size": "API", "modified": ""},
    ]
