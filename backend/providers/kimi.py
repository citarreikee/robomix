import json
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from config import settings
from protocol import StreamState, format_exception_message, format_http_error, parse_json_payload, validate_tool_call_shape


KIMI_URL = f"{settings.KIMI_API_BASE}/chat/completions"


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {settings.KIMI_API_KEY}", "Content-Type": "application/json"}


def _normalize_tool_calls(tool_calls: Any) -> list:
    normalized = []
    if not isinstance(tool_calls, list):
        return normalized
    for index, raw in enumerate(tool_calls):
        if not isinstance(raw, dict):
            continue
        func = raw.get("function") if isinstance(raw.get("function"), dict) else {}
        name = str(func.get("name") or "").strip()
        if not name:
            continue
        args = func.get("arguments", "")
        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)
        normalized.append({"id": str(raw.get("id") or f"call_{index}"), "type": raw.get("type") or "function", "function": {"name": name, "arguments": str(args or "")}})
    return normalized


def _format_messages(messages: list) -> list:
    formatted = []
    pending = []
    for msg in messages:
        role = "system" if msg.get("role") == "developer" else msg.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        item = {"role": role, "content": msg.get("content") or ""}
        if role == "assistant":
            tool_calls = _normalize_tool_calls(msg.get("tool_calls"))
            if tool_calls:
                item["tool_calls"] = tool_calls
                item["reasoning_content"] = msg.get("reasoning_content") or msg.get("thinking") or ""
                pending.extend({"id": call["id"], "name": call["function"]["name"]} for call in tool_calls)
            elif "reasoning_content" in msg:
                item["reasoning_content"] = msg.get("reasoning_content") or ""
        elif role == "tool":
            tool_call_id = str(msg.get("tool_call_id") or "").strip()
            name = str(msg.get("name") or "").strip()
            if not tool_call_id and pending:
                matched = next((item for item in pending if item["name"] == name), pending[0])
                tool_call_id = matched["id"]
            if tool_call_id:
                item["tool_call_id"] = tool_call_id
            if name:
                item["name"] = name
        formatted.append(item)
    return formatted


def _pick_choice(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    choices = payload.get("choices", [])
    if not choices:
        return None
    return next((choice for choice in choices if choice.get("index", 0) == 0), choices[0])


async def stream_kimi_response(model: str, messages: list) -> AsyncGenerator[str, None]:
    async for event in stream_kimi_with_tools(model, messages, []):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_kimi_with_tools(model: str, messages: list, tools: list) -> AsyncGenerator[Dict[str, Any], None]:
    state = StreamState()
    if not settings.KIMI_API_KEY:
        yield state.error_event("KIMI_API_KEY is not configured. Set it in backend/.env or choose another model provider.")
        return
    try:
        payload: Dict[str, Any] = {"model": model, "messages": _format_messages(messages), "stream": True}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", KIMI_URL, json=payload, headers=_headers()) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="ignore")
                    yield state.error_event(format_http_error("Kimi request failed", response.status_code, body))
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
                    choice = _pick_choice(parse_json_payload(line[6:], context="Kimi stream"))
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
                        func = chunk.get("function") or {}
                        if "id" in chunk:
                            tool_calls[idx]["id"] = chunk["id"]
                        if "type" in chunk:
                            tool_calls[idx]["type"] = chunk["type"]
                        if "name" in func:
                            tool_calls[idx]["function"]["name"] = func["name"]
                        if "arguments" in func and func["arguments"] is not None:
                            tool_calls[idx]["function"]["arguments"] += str(func["arguments"])
                if not state.saw_done_sentinel and not state.saw_finish_reason:
                    yield state.error_event("Kimi stream ended unexpectedly.")
                    return
                calls = [tool_calls[i] for i in sorted(tool_calls)]
                for call in calls:
                    validate_tool_call_shape(call)
                yield state.done_event(answer_key="content", tool_calls=calls, include_reasoning_content=True)
    except Exception as exc:
        yield state.error_event(format_exception_message(exc)) if not state.terminated else {"type": "error", "message": format_exception_message(exc)}


async def get_kimi_models() -> list[Dict[str, Any]]:
    models = [m.strip() for m in settings.KIMI_MODELS.split(",") if m.strip()] or ["kimi-k2.5"]
    return [{"name": model, "id": model, "provider": "kimi", "size": "API", "modified": ""} for model in models]
