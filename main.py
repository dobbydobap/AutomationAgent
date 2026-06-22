"""
main.py
────────
Command-line entry point for the STREET ID automation agent.

Usage
-----
    python main.py                 # run the task using settings from .env
    python main.py --url <URL>     # override the target URL for this run
    python main.py --headless      # force a headless run (no visible window)

The agent itself is async; this module just parses a couple of flags, runs the
event loop, and prints a tidy summary at the end (exit code 0 = success).

Note on import order
--------------------
``config.settings`` is built once at import time from the environment, so the
``--headless`` flag has to be turned into an env var *before* anything imports
``config``.  That's why the heavy imports live inside ``main()`` rather than at
module top-level.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="STREET ID // Website Automation Agent",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Target URL to automate (default: from .env / TARGET_URL).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium headless (overrides HEADLESS from .env).",
    )
    return parser.parse_args()


async def _run(url: str) -> int:
    # Imported here so any env overrides set in main() are already in place.
    from agent import WebFormAgent
    from config import settings

    agent = WebFormAgent()
    result = await agent.run(url=url)

    # ── human-readable summary ────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  STREET ID // AGENT RUN SUMMARY")
    print("=" * 64)
    print(f"  Target URL    : {result['url']}")
    print(f"  Plan source   : {result['plan_source']}")
    print(f"  Fields filled : {', '.join(result['fields_filled']) or '-'}")
    print(f"  Screenshots   : {len(result['screenshots'])} "
          f"(in ./{settings.screenshot_dir.name}/)")
    print(f"  Status        : {'SUCCESS' if result['success'] else 'FAILED'}")
    if result["error"]:
        print(f"  Error         : {result['error']}")
    print("=" * 64 + "\n")

    return 0 if result["success"] else 1


def main() -> None:
    args = _parse_args()
    if args.headless:
        # Set the env var the (yet-to-be-imported) config will read.
        os.environ["HEADLESS"] = "true"

    # Resolve the URL after env is settled so the default reflects .env.
    from config import settings

    url = args.url or settings.target_url
    exit_code = asyncio.run(_run(url))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
