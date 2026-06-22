"""
agent/logger.py
───────────────
Comprehensive logging for the agent (assignment requirement) *plus* a tiny
live event bus so the themed web dashboard can stream the agent's actions in
real time.

Why both in one place?
----------------------
Every meaningful thing the agent does should be observable in exactly one way,
whether you are watching the terminal, reading the log file afterwards, or
looking at the live dashboard.  So a single ``AgentLogger``:

  1. writes human-readable lines to the **console** and a **timestamped file**
     (standard ``logging`` module), and
  2. publishes the same events as **structured dicts** to any number of
     ``asyncio.Queue`` subscribers (the dashboard's Server-Sent-Events stream).

Modules never instantiate this directly — they call ``get_logger()`` which
returns a process-wide singleton.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import settings


class AgentLogger:
    """Structured logger that also fans events out to live subscribers."""

    def __init__(self) -> None:
        settings.ensure_dirs()

        # ── stdlib logger: console + rotating-by-run file ────────────────────
        self._log = logging.getLogger("street_id_agent")
        self._log.setLevel(logging.INFO)
        self._log.propagate = False

        if not self._log.handlers:  # avoid duplicate handlers on re-import
            fmt = logging.Formatter(
                "%(asctime)s │ %(levelname)-7s │ %(message)s",
                datefmt="%H:%M:%S",
            )

            console = logging.StreamHandler()
            console.setFormatter(fmt)
            self._log.addHandler(console)

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logfile = settings.log_dir / f"agent_{stamp}.log"
            file_handler = logging.FileHandler(logfile, encoding="utf-8")
            file_handler.setFormatter(fmt)
            self._log.addHandler(file_handler)
            self.logfile = logfile

        # ── live event subscribers (dashboard SSE) ───────────────────────────
        self._subscribers: list[asyncio.Queue] = []

    # ── subscription API used by the dashboard ───────────────────────────────
    def subscribe(self) -> asyncio.Queue:
        """Register a new live listener and return its event queue."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def _publish(self, event: dict[str, Any]) -> None:
        """Push a structured event to every live subscriber (non-blocking)."""
        event.setdefault("ts", time.time())
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - queues are unbounded
                pass

    # ── public logging helpers (used throughout the agent) ────────────────────
    def info(self, message: str, **data: Any) -> None:
        self._log.info(message)
        self._publish({"type": "log", "level": "info", "message": message, **data})

    def warn(self, message: str, **data: Any) -> None:
        self._log.warning(message)
        self._publish({"type": "log", "level": "warn", "message": message, **data})

    def error(self, message: str, **data: Any) -> None:
        self._log.error(message)
        self._publish({"type": "log", "level": "error", "message": message, **data})

    def step(self, name: str) -> None:
        """Mark the start of a high-level agent step (shown as a heading)."""
        self._log.info("▶ STEP: %s", name)
        self._publish({"type": "step", "level": "info", "message": name})

    def tool(self, name: str, detail: str = "", **data: Any) -> None:
        """Log a single tool invocation (open_browser, click_on_screen, ...)."""
        text = f"⚙ tool:{name} {detail}".rstrip()
        self._log.info(text)
        self._publish(
            {"type": "tool", "level": "info", "tool": name,
             "message": text, "detail": detail, **data}
        )

    def screenshot(self, path: Path, caption: str = "") -> None:
        """Announce a freshly captured screenshot to the dashboard."""
        rel = path.name
        self._log.info("📸 screenshot saved: %s  %s", rel, caption)
        self._publish(
            {"type": "screenshot", "level": "info", "file": rel,
             "caption": caption, "message": f"screenshot: {rel}"}
        )

    def success(self, message: str, **data: Any) -> None:
        self._log.info("✅ %s", message)
        self._publish({"type": "done", "level": "success", "message": message, **data})


_singleton: AgentLogger | None = None


def get_logger() -> AgentLogger:
    """Return the process-wide AgentLogger, creating it on first use."""
    global _singleton
    if _singleton is None:
        _singleton = AgentLogger()
    return _singleton
