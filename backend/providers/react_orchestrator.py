import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from protocol import ProtocolViolation, parse_tool_arguments, validate_tool_call_shape
from tools import registry


TOOL_EXECUTION_TIMEOUT_SECONDS = 45.0


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _execute_tool_safely(tool_name: str, tool_args: Dict[str, Any]) -> str:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(registry.execute, tool_name, tool_args),
            timeout=TOOL_EXECUTION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return f"Error executing tool '{tool_name}': timed out after {TOOL_EXECUTION_TIMEOUT_SECONDS:.0f}s"


async def stream_with_react(
    model: str,
    messages: List[Dict[str, Any]],
    provider: str,
    enable_tools: bool = True,
    max_iterations: Optional[int] = None,
    force_tool_use: bool = False,
    force_tool_retries: int = 2,
) -> AsyncGenerator[str, None]:
    if provider == "deepseek":
        from providers.deepseek import stream_deepseek_response, stream_deepseek_with_tools

        plain_stream = stream_deepseek_response
        tool_stream = stream_deepseek_with_tools
    elif provider == "kimi":
        from providers.kimi import stream_kimi_response, stream_kimi_with_tools

        plain_stream = stream_kimi_response
        tool_stream = stream_kimi_with_tools
    else:
        from providers.ollama import stream_ollama_response, stream_ollama_with_tools

        plain_stream = stream_ollama_response
        tool_stream = stream_ollama_with_tools

    if not enable_tools:
        async for event in plain_stream(model, messages):
            yield event
        return

    iteration = 0
    turn_messages: List[Dict[str, Any]] = []
    working_messages = messages.copy()
    force_tool_satisfied = not force_tool_use
    force_tool_retry_count = 0

    while True:
        if max_iterations is not None and iteration >= max_iterations:
            yield _sse({"type": "error", "message": "Max iterations reached."})
            return
        iteration += 1

        full_thinking = ""
        full_content = ""
        reasoning_content = ""
        tool_calls: List[Dict[str, Any]] = []
        done_received = False
        should_buffer = force_tool_use and not force_tool_satisfied
        buffered: List[Dict[str, Any]] = []

        async for response in tool_stream(model, working_messages, registry.get_openai_format()):
            event_type = response.get("type")
            if should_buffer:
                buffered.append(response)
            if event_type == "start":
                if not should_buffer:
                    yield _sse(response)
            elif event_type == "thinking_token":
                full_thinking += response.get("content", "")
                if not should_buffer:
                    yield _sse(response)
            elif event_type == "response_token":
                full_content += response.get("content", "")
                if not should_buffer:
                    yield _sse(response)
            elif event_type == "done":
                done_received = True
                full_thinking = response.get("thinking", full_thinking)
                full_content = response.get("content", response.get("answer", full_content))
                reasoning_content = response.get("reasoning_content", "")
                tool_calls = response.get("tool_calls", []) or []
            elif event_type == "error":
                yield _sse(response)
                return

        if not done_received:
            yield _sse({"type": "error", "message": "Provider stream ended without a done event."})
            return

        if not tool_calls:
            if force_tool_use and not force_tool_satisfied:
                if force_tool_retry_count < force_tool_retries:
                    force_tool_retry_count += 1
                    working_messages.append({"role": "assistant", "content": full_content, "reasoning_content": reasoning_content})
                    working_messages.append({"role": "user", "content": "For this turn, you must call at least one tool before the final answer."})
                    continue
                yield _sse({"type": "error", "message": "Forced tool-use mode: model did not emit tool_calls."})
                return
            message: Dict[str, Any] = {"role": "assistant", "content": full_content, "thinking": full_thinking}
            if reasoning_content:
                message["reasoning_content"] = reasoning_content
            turn_messages.append(message)
            break

        if should_buffer:
            for item in buffered:
                if item.get("type") in {"start", "thinking_token", "response_token"}:
                    yield _sse(item)
        force_tool_satisfied = True

        assistant_message = {"role": "assistant", "content": full_content or None, "thinking": full_thinking, "tool_calls": tool_calls}
        provider_message = {"role": "assistant", "content": full_content or "", "tool_calls": tool_calls}
        if reasoning_content:
            assistant_message["reasoning_content"] = reasoning_content
            provider_message["reasoning_content"] = reasoning_content
        elif provider == "kimi":
            provider_message["reasoning_content"] = ""
        working_messages.append(provider_message)
        turn_messages.append(assistant_message)

        try:
            for tool_call in tool_calls:
                validate_tool_call_shape(tool_call)
                func = tool_call.get("function", {})
                tool_name = func.get("name", "")
                tool_args = parse_tool_arguments(func.get("arguments", "{}"))
                yield _sse({"type": "tool_use", "name": tool_name, "arguments": tool_args})
                result = await _execute_tool_safely(tool_name, tool_args)
                result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                yield _sse({"type": "tool_result", "name": tool_name, "result": result_text})
                tool_message = {"role": "tool", "tool_call_id": tool_call.get("id", ""), "name": tool_name, "content": result_text}
                working_messages.append(tool_message)
                turn_messages.append(tool_message)
        except ProtocolViolation as exc:
            yield _sse({"type": "error", "message": f"Protocol violation: {exc}"})
            return
        except Exception as exc:
            yield _sse({"type": "error", "message": f"Tool execution failed: {exc}"})
            return

    final_answer = next((m.get("content") or "" for m in reversed(turn_messages) if m.get("role") == "assistant" and not m.get("tool_calls") and m.get("content")), "")
    if not final_answer:
        final_answer = "Task completed."
    thinking = "\n\n".join(m.get("thinking", "") for m in turn_messages if m.get("role") == "assistant" and m.get("thinking"))
    yield _sse({"type": "done", "thinking": thinking, "answer": final_answer, "time": str(iteration * 2)})
    yield _sse({"type": "react_complete", "messages": turn_messages, "iterations": iteration})
