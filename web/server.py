import asyncio
import json
import logging
import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import AGENT_MAX_STEPS, LOG_TAG, WEB_HOST, WEB_PORT, llm_endpoint_label
from agent.llm_errors import friendly_llm_error
from agent.loop import run_agent_state
from agent.state import AgentState, empty_state

logger = logging.getLogger(LOG_TAG)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="myAgent Research UI", version="0.1.0")

_sessions: Dict[str, AgentState] = {}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: Optional[str] = None
    reset: bool = False


class SessionResponse(BaseModel):
    session_id: str


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(levelname)s [{LOG_TAG}] %(message)s",
    )


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def api_config() -> Dict[str, Any]:
    return {"llm": llm_endpoint_label(), "max_steps": AGENT_MAX_STEPS}


@app.post("/api/session", response_model=SessionResponse)
def create_session() -> SessionResponse:
    sid = uuid.uuid4().hex
    _sessions[sid] = empty_state()
    return SessionResponse(session_id=sid)


def _get_session(session_id: str, *, reset: bool) -> AgentState:
    if reset or session_id not in _sessions:
        state = empty_state()
        _sessions[session_id] = state
        return state
    state = _sessions[session_id]
    state.refresh_system_prompt()
    return state


def _run_agent_thread(
    state: AgentState,
    message: str,
    event_q: "queue.Queue[Optional[Dict[str, Any]]]",
) -> None:
    try:
        state.append_user(message)

        def on_event(kind: str, data: Dict[str, Any]) -> None:
            event_q.put({"event": kind, **data})

        answer = run_agent_state(state, log_steps=True, on_event=on_event)
        event_q.put({"event": "finished", "answer": answer})
    except Exception as exc:
        logger.exception("web agent run failed")
        event_q.put({"event": "error", "message": friendly_llm_error(exc)})
    finally:
        event_q.put(None)


async def _sse_stream(session_id: str, message: str, reset: bool):
    if not session_id:
        raise HTTPException(400, "session_id required")

    state = _get_session(session_id, reset=reset)
    event_q: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()

    thread = threading.Thread(
        target=_run_agent_thread,
        args=(state, message, event_q),
        daemon=True,
    )
    thread.start()

    yield f"data: {json.dumps({'event': 'started', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    while True:
        item = await asyncio.to_thread(event_q.get)
        if item is None:
            break
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        if item.get("event") in ("finished", "error"):
            break

    thread.join(timeout=1.0)


@app.post("/api/chat")
async def chat_stream(body: ChatRequest):
    sid = body.session_id or uuid.uuid4().hex
    if body.session_id is None:
        _sessions[sid] = empty_state()

    return StreamingResponse(
        _sse_stream(sid, body.message.strip(), body.reset),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": sid,
        },
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    import uvicorn

    _setup_logging()
    logger.info("research UI http://%s:%s  llm: %s", WEB_HOST, WEB_PORT, llm_endpoint_label())
    uvicorn.run(
        "web.server:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
