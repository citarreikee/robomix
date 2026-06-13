from typing import Any, Dict, List

from .base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found. Available tools: {list(self._tools.keys())}")
        return self._tools[name]

    def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        try:
            return self.get(name).execute(**arguments)
        except KeyError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Error executing tool '{name}': {exc}"

    def get_openai_format(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_format() for tool in self._tools.values()]

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())


registry = ToolRegistry()


def register_tool(tool_class):
    registry.register(tool_class())
    return tool_class
