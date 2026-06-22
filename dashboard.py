"""
dashboard.py
─────────────
Convenience launcher for the themed control dashboard.

    python dashboard.py

Equivalent to ``uvicorn web.server:app --host <HOST> --port <PORT>`` but reads
the host/port from your .env so there's one obvious way to start it.
"""

from __future__ import annotations

import uvicorn

from config import settings


def main() -> None:
    print("=" * 60)
    print("  STREET ID // AUTOMATION AGENT — control dashboard")
    print(f"  Open:  http://{settings.dashboard_host}:{settings.dashboard_port}")
    print("=" * 60)
    uvicorn.run(
        "web.server:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
