from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    role: str
    content: Optional[str] = None
    thinking: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    reasoning_content: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_provider_message(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": self.role, "content": self.content}
        for key in ("tool_calls", "tool_call_id", "name", "reasoning_content", "thinking"):
            value = getattr(self, key)
            if value is not None and value != "":
                payload[key] = value
        return payload


@dataclass
class Session:
    session_id: str
    model: str
    messages: List[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model": self.model,
            "messages": [message.to_dict() for message in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}

    def create_session(self, model: str, metadata: Optional[Dict[str, Any]] = None) -> Session:
        session = Session(session_id=str(uuid.uuid4()), model=model, metadata=metadata or {})
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def add_message(self, session_id: str, role: str, content: Optional[str], **kwargs: Any) -> Optional[Message]:
        session = self.get_session(session_id)
        if not session:
            return None
        message = Message(role=role, content=content, **kwargs)
        session.add_message(message)
        return message

    def get_history(self, session_id: str, limit: Optional[int] = None) -> Optional[List[Message]]:
        session = self.get_session(session_id)
        if not session:
            return None
        return session.messages if limit is None else session.messages[-limit:]

    def delete_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [
            {
                "session_id": session.session_id,
                "model": session.model,
                "message_count": len(session.messages),
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }
            for session in self._sessions.values()
        ]


session_manager = SessionManager()
