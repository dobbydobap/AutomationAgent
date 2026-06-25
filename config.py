"""
config.py
─────────
Single source of truth for every tunable setting in the project.

Design decision
---------------
All configuration is read from environment variables (loaded from a local
``.env`` file via python-dotenv).  This keeps secrets and machine-specific
paths out of the source code and satisfies the assignment's requirement to
"use environment variables or configuration files for API keys and settings".

Nothing else in the codebase reads ``os.environ`` directly — every module
imports the singleton ``settings`` object defined here, so there is exactly
one place to look when you want to know how the agent is configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env (if present) into the process environment. Calling this at import
# time means simply importing `config` is enough to make settings available.
load_dotenv()

# Project root = the folder this file lives in. Output dirs are resolved
# relative to it so the agent works regardless of the current working dir.
ROOT_DIR = Path(__file__).resolve().parent


def _env_bool(key: str, default: bool) -> bool:
    """Parse a boolean-ish environment variable ('true', '1', 'yes' -> True)."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    """Parse an integer environment variable, falling back on bad input."""
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable bundle of every runtime setting, built once from the env."""

    # Target task
    target_url: str = field(
        default_factory=lambda: os.getenv(
            "TARGET_URL", "https://ui.shadcn.com/docs/forms/react-hook-form"
        )
    )
    name_value: str = field(
        default_factory=lambda: os.getenv("NAME_VALUE", "STREET ID STUDIO")
    )
    description_value: str = field(
        default_factory=lambda: os.getenv(
            "DESCRIPTION_VALUE",
            "Autonomous form fill performed by the STREET ID automation agent.",
        )
    )

    # Browser behaviour
    headless: bool = field(default_factory=lambda: _env_bool("HEADLESS", False))
    slow_mo: int = field(default_factory=lambda: _env_int("SLOW_MO", 350))
    timeout_ms: int = field(default_factory=lambda: _env_int("TIMEOUT_MS", 30000))

    # Generic "navigate + search" task (dashboard/CLI defaults)
    search_url: str = field(
        default_factory=lambda: os.getenv("SEARCH_URL", "https://duckduckgo.com")
    )
    search_query: str = field(
        default_factory=lambda: os.getenv("SEARCH_QUERY", "iphone 15 pro")
    )

    # Agent brain
    use_llm: bool = field(default_factory=lambda: _env_bool("USE_LLM", False))
    max_task_steps: int = field(default_factory=lambda: _env_int("MAX_TASK_STEPS", 8))
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    )

    # Output locations (resolved to absolute paths under the project root)
    screenshot_dir: Path = field(
        default_factory=lambda: ROOT_DIR / os.getenv("SCREENSHOT_DIR", "screenshots")
    )
    log_dir: Path = field(
        default_factory=lambda: ROOT_DIR / os.getenv("LOG_DIR", "logs")
    )

    # Dashboard
    dashboard_host: str = field(
        default_factory=lambda: os.getenv("DASHBOARD_HOST", "127.0.0.1")
    )
    dashboard_port: int = field(
        default_factory=lambda: _env_int("DASHBOARD_PORT", 8000)
    )

    def ensure_dirs(self) -> None:
        """Create the screenshot/log output folders if they don't exist yet."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def llm_enabled(self) -> bool:
        """LLM mode is only truly active when toggled ON *and* a key exists."""
        return self.use_llm and bool(self.anthropic_api_key.strip())


# The one and only Settings instance the rest of the app imports.
settings = Settings()
