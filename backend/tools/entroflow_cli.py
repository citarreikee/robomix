import json
from typing import Any, Dict, Optional

from services import entroflow_runtime
from tools.base import Tool
from tools.registry import register_tool


@register_tool
class EntroFlowCli(Tool):
    @property
    def name(self) -> str:
        return "entroflow_cli"

    @property
    def description(self) -> str:
        return (
            "Run a restricted EntroFlow setup command. Allowed commands: doctor, list_platforms, "
            "connect, connect_poll, list_devices, setup, update. Runtime control must use device_search/device_status/device_control. "
            "Use connect for platform login such as Mi Home QR login; do not use setup until after list_devices returns "
            "a concrete device did/model and the user confirms the exact device registration. "
            "For QR login prefer command='connect', platform='mihome', presentation='url' or 'file'. "
            "Setup requires confirmed=true after user confirmation."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": ["doctor", "list_platforms", "connect", "connect_poll", "list_devices", "setup", "update"]},
                "platform": {"type": "string"},
                "query": {"type": "string"},
                "supported_only": {"type": "boolean"},
                "did": {"type": "string", "description": "Bare platform-local id from list_devices for setup."},
                "model": {"type": "string"},
                "version": {"type": "string"},
                "name": {"type": "string"},
                "location": {"type": "string"},
                "remark": {"type": "string"},
                "confirmed": {"type": "boolean"},
                "presentation": {"type": "string", "enum": ["auto", "url", "file", "none"]},
                "url": {"type": "string"},
                "token": {"type": "string"},
                "inputs": {
                    "type": "object",
                    "description": "Connector inputs. For connect_poll, pass {'session_id': '...'} from connect output.",
                },
                "connect_timeout": {"type": "integer"},
            },
            "required": ["command"],
        }

    def execute(
        self,
        command: str = "",
        platform: str = "",
        query: str = "",
        supported_only: bool = False,
        did: str = "",
        model: str = "",
        version: str = "",
        name: str = "",
        location: str = "",
        remark: str = "",
        confirmed: bool = False,
        presentation: str = "",
        url: str = "",
        token: str = "",
        inputs: Optional[Dict[str, Any]] = None,
        connect_timeout: Optional[int] = None,
    ) -> str:
        result = entroflow_runtime.run_cli_command(
            command,
            platform=platform,
            query=query,
            supported_only=supported_only,
            did=did,
            model=model,
            version=version,
            name=name,
            location=location,
            remark=remark,
            confirmed=confirmed,
            presentation=presentation,
            url=url,
            token=token,
            inputs=inputs or {},
            connect_timeout=connect_timeout,
        )
        if token and isinstance(result, dict):
            dumped = json.dumps(result, ensure_ascii=False).replace(token, "***")
            return dumped
        return json.dumps(result, ensure_ascii=False)
