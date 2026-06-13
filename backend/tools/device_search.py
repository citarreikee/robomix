from services import entroflow_runtime
from tools.base import Tool
from tools.registry import register_tool


@register_tool
class DeviceSearch(Tool):
    @property
    def name(self) -> str:
        return "device_search"

    @property
    def description(self) -> str:
        return (
            "Search registered EntroFlow runtime devices and return exact device_id plus supported_actions. "
            "Call this before device_status or device_control. Set query to 'all' for the full catalog."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Registered EntroFlow name/location/remark/device_id, or 'all'."},
                "top_k": {"type": "integer", "description": "How many matches to return. Default 5."},
            },
            "required": ["query"],
        }

    def execute(self, query: str = "", top_k: int = 5) -> str:
        return entroflow_runtime.search_device_capabilities(query=query, top_k=top_k)
