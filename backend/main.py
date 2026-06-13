from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from chat_history import session_manager
from config import settings
from providers import react_orchestrator
from services import entroflow_runtime
from services.chat_service import prepare_chat_turn, stream_chat_with_session
from tools import registry


class ChatRequest(BaseModel):
    message: str
    model: str = settings.DEFAULT_MODEL
    sessionId: Optional[str] = None
    enableTools: bool = True
    forceToolUse: bool = False


class SessionCreateRequest(BaseModel):
    model: str = settings.DEFAULT_MODEL
    metadata: Optional[Dict[str, Any]] = None


app = FastAPI(title="Robomix API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Dict[str, Any]:
    return {"name": "robomix", "status": "running", "docs": "/docs"}


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "tools": registry.list_tools(), "entroflow_devices": len(entroflow_runtime.list_devices())}


@app.get("/api/tools")
async def tools() -> Dict[str, Any]:
    return {"tools": registry.get_openai_format()}


@app.get("/api/devices")
async def devices() -> Dict[str, Any]:
    return {"devices": entroflow_runtime.list_device_cards()}


@app.get("/api/entroflow/qr/{session_id}")
async def entroflow_qr(session_id: str) -> FileResponse:
    try:
        path = entroflow_runtime.get_login_qr_path(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FileResponse(path, media_type="image/png", filename=path.name)


@app.get("/api/models")
async def models() -> Dict[str, Any]:
    items = []
    errors: Dict[str, str] = {}
    if settings.DEEPSEEK_API_KEY:
        try:
            from providers.deepseek import get_deepseek_models

            items.extend(await get_deepseek_models())
        except Exception as exc:
            errors["deepseek"] = str(exc)
    else:
        errors["deepseek"] = "DEEPSEEK_API_KEY is not configured."
    if settings.KIMI_API_KEY:
        try:
            from providers.kimi import get_kimi_models

            items.extend(await get_kimi_models())
        except Exception as exc:
            errors["kimi"] = str(exc)
    else:
        errors["kimi"] = "KIMI_API_KEY is not configured."
    try:
        from providers.ollama import get_ollama_models

        items.extend(await get_ollama_models())
    except Exception as exc:
        errors["ollama"] = str(exc)
    return {"models": items, "default_model": settings.DEFAULT_MODEL, "errors": errors}


@app.post("/api/sessions")
async def create_session(request: SessionCreateRequest) -> Dict[str, Any]:
    session = session_manager.create_session(model=request.model, metadata=request.metadata or {})
    return {"session_id": session.session_id, "model": session.model, "created_at": session.created_at}


@app.get("/api/sessions")
async def list_sessions() -> Dict[str, Any]:
    return {"sessions": session_manager.list_sessions()}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@app.post("/api/chat")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    try:
        context = prepare_chat_turn(
            session_manager,
            model=request.model,
            user_message=request.message,
            request_session_id=request.sessionId,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to prepare chat: {exc}")
    return StreamingResponse(
        stream_chat_with_session(
            session_manager,
            react_orchestrator.stream_with_react,
            model=request.model,
            context=context,
            force_tool_use=request.forceToolUse,
            enable_tools=request.enableTools,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
