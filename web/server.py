"""
web/server.py
──────────────
The STREET ID // AUTOMATION AGENT control dashboard (FastAPI).

This is the themed UI layer.  It does not contain any automation logic of its
own — it simply:

  * serves the themed single-page front-end (``static/index.html``),
  * exposes ``POST /api/run`` to kick off an agent run in the background,
  * streams the agent's live actions to the browser via **Server-Sent Events**
    (``GET /api/stream``) by subscribing to the shared :class:`AgentLogger`,
  * serves captured screenshots so they appear live in the screenshot feed.

Because every part of the agent logs through the same logger singleton, the
dashboard sees exactly the same events as the terminal — no extra plumbing.

Run it with:   python dashboard.py      (or: uvicorn web.server:app)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent import WebFormAgent
from agent.logger import get_logger
from config import settings

# Make sure output folders exist before we try to mount/serve them.
settings.ensure_dirs()

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="STREET ID // Automation Agent")

# Serve the front-end assets and the live screenshot feed as static files.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount(
    "/screenshots",
    StaticFiles(directory=str(settings.screenshot_dir)),
    name="screenshots",
)

# Only one agent run at a time — track the in-flight task here.
_current_run: asyncio.Task | None = None


@app.get("/")
async def index() -> FileResponse:
    """Serve the themed dashboard page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def config_snapshot() -> JSONResponse:
    """Expose the (non-secret) runtime config so the UI can display it."""
    return JSONResponse(
        {
            "target_url": settings.target_url,
            "headless": settings.headless,
            "llm_enabled": settings.llm_enabled,
            "llm_model": settings.llm_model if settings.llm_enabled else None,
            "name_value": settings.name_value,
            "description_value": settings.description_value,
            "search_url": settings.search_url,
            "search_query": settings.search_query,
        }
    )


@app.post("/api/run")
async def run_agent(payload: dict | None = Body(default=None)) -> JSONResponse:
    """Start a run in the background. Body: {mode, url, query, goal} (all optional).

    mode is one of: "form" (default, fill the shadcn form), "search" (go to a site
    and search), "task" (optional Claude free-form loop).
    """
    global _current_run
    if _current_run is not None and not _current_run.done():
        return JSONResponse({"status": "already_running"}, status_code=409)

    body = payload or {}
    mode = (body.get("mode") or "form").lower()
    log = get_logger()

    async def _job() -> None:
        log.info(f"──────── NEW {mode.upper()} RUN TRIGGERED FROM DASHBOARD ────────")
        agent = WebFormAgent()
        if mode == "search":
            result = await agent.search(
                url=body.get("url") or settings.search_url,
                query=body.get("query") or settings.search_query,
            )
        elif mode == "task":
            result = await agent.do_task(
                goal=body.get("goal") or "", url=body.get("url") or None,
            )
        else:
            result = await agent.run()
        # Final structured event so the UI can flip its status badge.
        log._publish({  # noqa: SLF001 - intentional internal publish
            "type": "result",
            "level": "success" if result["success"] else "error",
            "message": "RUN COMPLETE" if result["success"] else "RUN FAILED",
            "result": result,
        })

    _current_run = asyncio.create_task(_job())
    return JSONResponse({"status": "started"})


@app.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent-Events stream of live agent log/tool/screenshot events."""
    log = get_logger()
    queue = log.subscribe()

    async def event_generator():
        try:
            yield _sse({"type": "log", "level": "info",
                        "message": "live stream connected — standing by."})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    # Comment line keeps the connection alive through proxies.
                    yield ": keep-alive\n\n"
        finally:
            log.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        event_generator(), media_type="text/event-stream", headers=headers
    )


def _sse(event: dict) -> str:
    """Format a dict as a single Server-Sent-Events 'data:' frame."""
    return f"data: {json.dumps(event)}\n\n"
