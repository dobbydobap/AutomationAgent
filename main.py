"""
main.py
────────
Command-line entry point for the STREET ID automation agent.

Usage
-----
    python main.py                              fill the shadcn demo form (default)
    python main.py --headless                   force a headless run
    python main.py --url <URL>                  override the target for one run

    python main.py --search "iphone 15 pro"     go to a site and search for it
    python main.py --search "Alan Turing" --url en.wikipedia.org

    python main.py --task "search wikipedia for Alan Turing and open the first
        result"                                 optional LLM free-form task (needs USE_LLM)

The agent itself is async; this module just parses flags, runs the event loop,
and prints a tidy summary at the end (exit code 0 = success).

Note on import order
--------------------
``config.settings`` is built once at import time from the environment, so the
``--headless`` flag has to be turned into an env var *before* anything imports
``config``.  That's why the heavy imports live inside the functions below.
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
        "--url", default=None,
        help="Target/start URL (default: from .env).",
    )
    parser.add_argument(
        "--search", default=None, metavar="QUERY",
        help="Go to a site (use --url, else SEARCH_URL) and search for QUERY.",
    )
    parser.add_argument(
        "--task", default=None, metavar="GOAL",
        help="Free-form goal for the optional LLM agent (needs USE_LLM=true).",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run Chromium headless (overrides HEADLESS from .env).",
    )
    return parser.parse_args()


def _print_summary(result: dict) -> int:
    print("\n" + "=" * 64)
    print("  STREET ID // AGENT RUN SUMMARY")
    print("=" * 64)
    for key in ("url", "task", "query", "goal", "plan_source", "summary"):
        if result.get(key):
            print(f"  {key:<12}: {result[key]}")
    print(f"  screenshots : {len(result.get('screenshots', []))}")
    print(f"  status      : {'SUCCESS' if result.get('success') else 'FAILED'}")
    if result.get("error"):
        print(f"  error       : {result['error']}")
    print("=" * 64 + "\n")
    return 0 if result.get("success") else 1


async def _run_form(url: str) -> int:
    from agent import WebFormAgent
    return _print_summary(await WebFormAgent().run(url=url))


async def _run_search(url: str, query: str) -> int:
    from agent import WebFormAgent
    return _print_summary(await WebFormAgent().search(url=url, query=query))


async def _run_task(url: str | None, goal: str) -> int:
    from agent import WebFormAgent
    return _print_summary(await WebFormAgent().do_task(goal=goal, url=url))


def main() -> None:
    args = _parse_args()
    if args.headless:
        os.environ["HEADLESS"] = "true"  # set before config is imported

    from config import settings

    if args.search is not None:
        url = args.url or settings.search_url
        exit_code = asyncio.run(_run_search(url, args.search))
    elif args.task is not None:
        exit_code = asyncio.run(_run_task(args.url, args.task))
    else:
        url = args.url or settings.target_url
        exit_code = asyncio.run(_run_form(url))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
