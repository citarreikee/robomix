from typing import Any

from services.device_control_executor import execute_device_actions, format_device_control_text
from tools.base import Tool
from tools.registry import register_tool


@register_tool
class DeviceControl(Tool):
    @property
    def name(self) -> str:
        return "device_control"

    @property
    def description(self) -> str:
        return (
            "Control a registered EntroFlow runtime device by exact device_id. "
            "Always call device_search first and use only supported_actions. "
            "Actions format: [{action: \"...\", args: {...}}]; all parameters must be nested under args."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "Exact registered EntroFlow device_id."},
                "actions": {"type": "array", "description": "List of action objects. Put parameters under args.", "items": {"type": "object"}},
            },
            "required": ["device_id", "actions"],
        }

    def execute(self, device_id: str = "", actions: Any = None) -> str:
        try:
            execution = execute_device_actions(device_id, actions)
        except ValueError as exc:
            return f"Error: {exc}"
        return format_device_control_text(execution)
