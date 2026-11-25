import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.config import BASE_DIR, settings
from backend.database import ClinicStore
from backend.pipeline import run_voice_session

FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Alderbrook Clinic Voice Desk")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ClinicStore(settings.db_path)
_subscribers: set[asyncio.Queue] = set()


async def broadcast_event(payload: dict) -> None:
    stale: list[asyncio.Queue] = []
    for queue in _subscribers:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            stale.append(queue)
    for queue in stale:
        _subscribers.discard(queue)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "keys_configured": bool(settings.elevenlabs_api_key and settings.google_api_key),
    }


@app.get("/api/dashboard")
async def get_dashboard():
    return {
        "doctors": store.list_doctors_with_slots(),
        "appointments": store.list_appointments(),
    }


@app.get("/api/events")
async def sse_events():
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.add(queue)

    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.websocket("/ws/call")
async def websocket_call(websocket: WebSocket):
    await websocket.accept()
    try:
        await run_voice_session(websocket, store, broadcast_event)
    except WebSocketDisconnect:
        logger.info("Caller WebSocket closed")
    except Exception as exc:
        logger.exception("Voice session error: {}", exc)
        try:
            await websocket.send_json({"type": "error", "message": "Voice service unavailable. Please try again."})
        except Exception:
            pass


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(str(Path(FRONTEND_DIR) / "index.html"))
