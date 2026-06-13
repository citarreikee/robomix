from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ProtocolViolation(Exception):
    pass


@dataclass
class StreamState:
    start_time: float = field(default_factory=time.time)
    started: bool = False
    terminated: bool = False
    saw_done_sentinel: bool = False
    saw_finish_reason: bool = False
    thinking: str = ""
    content: str = ""
    reasoning_content: str = ""

    def make_start_event(self) -> Optional[Dict[str, Any]]:
        if self.started:
            return None
        self.started = True
        return {"type": "start", "time": str(round(time.time() - self.start_time, 1))}

    def append_thinking(self, token: str) -> None:
        if token:
            self.thinking += token
            self.reasoning_content += token

    def append_content(self, token: str) -> None:
        if token:
            self.content += token

    def mark_finish_reason(self, finish_reason: Any) -> None:
        if finish_reason is not None:
            self.saw_finish_reason = True

    def mark_done_sentinel(self) -> None:
        self.saw_done_sentinel = True

    def _mark_terminal(self) -> None:
        if self.terminated:
            raise ProtocolViolation("duplicate terminal event")
        self.terminated = True

    def done_event(
        self,
        *,
        answer_key: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        include_reasoning_content: bool = False,
    ) -> Dict[str, Any]:
        self._mark_terminal()
        payload: Dict[str, Any] = {
            "type": "done",
            "thinking": self.thinking.strip(),
            answer_key: self.content.strip(),
            "time": str(round(time.time() - self.start_time, 1)),
        }
        payload["answer" if answer_key == "content" else "content"] = self.content.strip()
        if include_reasoning_content:
            payload["reasoning_content"] = self.reasoning_content.strip()
        if tool_calls is not None:
            payload["tool_calls"] = tool_calls
        return payload

    def error_event(self, message: str) -> Dict[str, Any]:
        self._mark_terminal()
        return {"type": "error", "message": message}


def parse_json_payload(raw: str, *, context: str) -> Dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolViolation(f"{context}: invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise ProtocolViolation(f"{context}: payload must be a JSON object")
    return payload


def format_http_error(prefix: str, status_code: int, body: str) -> str:
    detail = body.strip()
    if len(detail) > 300:
        detail = detail[:300] + "..."
    return f"{prefix} (HTTP {status_code}): {detail}" if detail else f"{prefix} (HTTP {status_code})"


def format_exception_message(exc: Exception) -> str:
    return str(exc).strip() or type(exc).__name__


def validate_tool_call_shape(tool_call: Dict[str, Any]) -> None:
    if not isinstance(tool_call, dict):
        raise ProtocolViolation("tool_call must be an object")
    if not str(tool_call.get("id") or "").strip():
        raise ProtocolViolation("tool_call.id is required")
    function_data = tool_call.get("function")
    if not isinstance(function_data, dict):
        raise ProtocolViolation("tool_call.function must be an object")
    if not str(function_data.get("name") or "").strip():
        raise ProtocolViolation("tool_call.function.name is required")
    if "arguments" not in function_data:
        raise ProtocolViolation("tool_call.function.arguments is required")


def parse_tool_arguments(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ProtocolViolation("tool_call.function.arguments must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ProtocolViolation("tool_call.function.arguments JSON must decode to object")
        return parsed
    raise ProtocolViolation("tool_call.function.arguments must be string or object")
