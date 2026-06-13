from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from services import entroflow_runtime


@dataclass
class DeviceActionExecution:
    action: str
    ok: bool
    message: str
    args: Dict[str, Any] = field(default_factory=dict)

    def to_line(self) -> str:
        if not self.action:
            return self.message
        if self.ok or self.message.startswith("Error:"):
            return f"{self.action}: {self.message}"
        return f"{self.action}: Error: {self.message}"


@dataclass
class DeviceControlExecution:
    device_id: str
    results: List[DeviceActionExecution]


def execute_device_actions(device_id: str, actions: Any) -> DeviceControlExecution:
    payload = entroflow_runtime.execute_device_actions(device_id, actions)
    return DeviceControlExecution(
        device_id=payload.get("device_id") or device_id,
        results=[
            DeviceActionExecution(action=item.action, ok=item.ok, message=item.message, args=item.args)
            for item in payload.get("results", [])
        ],
    )


def format_device_control_text(execution: DeviceControlExecution) -> str:
    return "\n".join(item.to_line() for item in execution.results)
