from services import entroflow_runtime
from tools.base import Tool
from tools.registry import register_tool


@register_tool
class DeviceStatus(Tool):
    @property
    def name(self) -> str:
        return "device_status"

    @property
    def description(self) -> str:
        return (
            "Query a registered EntroFlow runtime device status by exact device_id. "
            "If device_id is unknown, call device_search first."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "Exact registered EntroFlow device_id, for example mihome:708678806."}
            },
            "required": ["device_id"],
        }

    def execute(self, device_id: str = "") -> str:
        if not device_id:
            return "Error: device_id is required."
        return entroflow_runtime.get_device_status_text(device_id)
