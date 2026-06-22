"""
STREET ID // AUTOMATION AGENT
=============================
A mini "Browser-Use" style web-automation agent built on Playwright.

Public surface
--------------
- ``BrowserTools``    : the 7 low-level, composable browser tools.
- ``ElementDetector`` : accessibility-first element finding -> (x, y) coords.
- ``WebFormAgent``    : the orchestrator that composes tools to do the task.
- ``get_logger``      : shared structured logger / live event bus.
"""

from .agent import WebFormAgent
from .browser_tools import BrowserTools
from .element_detector import ElementDetector
from .logger import get_logger

__all__ = ["WebFormAgent", "BrowserTools", "ElementDetector", "get_logger"]
