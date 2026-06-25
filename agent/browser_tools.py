"""
agent/browser_tools.py
───────────────────────
The seven low-level "tools" the assignment asks for, wrapped around Playwright.

    1. open_browser       – launch a Chromium instance + page
    2. navigate_to_url    – point the browser at a URL
    3. take_screenshot    – capture the current viewport
    4. click_on_screen    – mouse-click at absolute (x, y) pixel coordinates
    5. send_keys          – type text via the keyboard
    6. scroll             – wheel-scroll the page
    7. double_click       – mouse double-click at (x, y)

Design decisions
----------------
* **Coordinate-based input.**  ``click_on_screen`` and ``double_click`` drive
  the real *mouse* at pixel coordinates (``page.mouse``) rather than calling
  ``locator.click()``.  This mirrors how human-like / vision tools such as
  Browser-Use operate and is exactly what the assignment specifies.  The
  intelligent part — turning a "Description field" into an (x, y) point — lives
  in ``ElementDetector``; these tools stay dumb, small and reusable.
* **Async Playwright.**  The whole stack is async so the same agent can be
  awaited both from the CLI (``asyncio.run``) and from the FastAPI dashboard
  without blocking the event loop.
* **Every call is logged** through the shared :class:`AgentLogger`, so each
  tool invocation shows up in the console, the log file and the live dashboard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from config import settings

from .logger import get_logger


class BrowserError(RuntimeError):
    """Raised when a browser tool cannot complete its action."""


class BrowserTools:
    """A thin, well-logged, composable wrapper over Playwright's Chromium."""

    def __init__(self) -> None:
        self.log = get_logger()
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._shot_index = 0

    # ── TOOL 1: open_browser ─────────────────────────────────────────────────
    async def open_browser(self) -> Page:
        """Initialise Playwright and launch a Chromium browser + blank page."""
        self.log.tool(
            "open_browser",
            f"headless={settings.headless} slow_mo={settings.slow_mo}ms",
        )
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=settings.headless,
                slow_mo=settings.slow_mo,
            )
            # A realistic viewport + user-agent makes the target page render
            # exactly as a human would see it (important for coordinate clicks).
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 900},
                device_scale_factor=1,
            )
            self._context.set_default_timeout(settings.timeout_ms)
            self.page = await self._context.new_page()
            self.log.info("Browser ready (Chromium 1280×900).")
            return self.page
        except Exception as exc:  # noqa: BLE001 - surface a clean error
            raise BrowserError(f"Failed to open browser: {exc}") from exc

    # ── TOOL 2: navigate_to_url ──────────────────────────────────────────────
    async def navigate_to_url(self, url: str, attempts: int = 2) -> None:
        """Navigate the page to ``url``, tolerating busy sites and transient drops."""
        self._require_page()
        self.log.tool("navigate_to_url", url)

        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                await self.page.goto(url, wait_until="domcontentloaded")
                # Best-effort settle: let the page (e.g. shadcn's React form)
                # hydrate, but don't fail when a busy site like YouTube never
                # reaches networkidle.  # ponytail: best-effort settle; busy sites never idle
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:  # noqa: BLE001
                    await self.page.wait_for_timeout(800)
                self.log.info(f"Loaded: {await self.page.title()!r}")
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.log.warn(f"Navigation attempt {attempt}/{attempts} failed: {exc}")
                if attempt < attempts:  # ponytail: one retry, not a backoff framework
                    await self.page.wait_for_timeout(1000)

        err = str(last_exc)
        msg = f"Navigation to {url} failed: {last_exc}"
        if "ERR_NAME_NOT_RESOLVED" in err:
            msg += " (could not resolve the domain — check the URL, e.g. 'youtube.com' not 'youtube')"
        elif "ERR_CONNECTION" in err:
            msg += (" (the site may be blocking automated/datacenter browsers — "
                    "try a visible local run or a different site)")
        raise BrowserError(msg) from last_exc

    # ── TOOL 3: take_screenshot ──────────────────────────────────────────────
    async def take_screenshot(self, label: str = "") -> Path:
        """Capture the current viewport to ``screenshots/`` and return its path."""
        self._require_page()
        self._shot_index += 1
        safe = "".join(c if c.isalnum() else "_" for c in label).strip("_")
        name = f"{self._shot_index:02d}_{safe or 'shot'}.png"
        path = settings.screenshot_dir / name
        try:
            await self.page.screenshot(path=str(path))
            self.log.screenshot(path, caption=label)
            return path
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"Screenshot failed: {exc}") from exc

    # ── TOOL 4: click_on_screen(x, y) ────────────────────────────────────────
    async def click_on_screen(self, x: float, y: float) -> None:
        """Perform a real mouse click at absolute viewport pixel (x, y)."""
        self._require_page()
        self.log.tool("click_on_screen", f"({x:.0f}, {y:.0f})")
        try:
            await self.page.mouse.move(x, y)
            await self._show_click(x, y)
            await self.page.mouse.click(x, y)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"Click at ({x},{y}) failed: {exc}") from exc

    # ── TOOL 5: send_keys ────────────────────────────────────────────────────
    async def send_keys(self, text: str, delay: int = 25) -> None:
        """Type ``text`` into whatever element currently has focus."""
        self._require_page()
        preview = text if len(text) <= 40 else text[:37] + "..."
        self.log.tool("send_keys", f"{preview!r}")
        try:
            await self.page.keyboard.type(text, delay=delay)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"send_keys failed: {exc}") from exc

    async def press(self, key: str) -> None:
        """Press a single named key (e.g. 'Control+A', 'Backspace'). Helper."""
        self._require_page()
        self.log.tool("press", key)
        await self.page.keyboard.press(key)

    # ── TOOL 6: scroll ───────────────────────────────────────────────────────
    async def scroll(self, dy: int = 600, dx: int = 0) -> None:
        """Wheel-scroll the page by (dx, dy) pixels (positive dy = down)."""
        self._require_page()
        self.log.tool("scroll", f"dx={dx} dy={dy}")
        try:
            await self.page.mouse.wheel(dx, dy)
            await self.page.wait_for_timeout(250)  # let layout settle
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"scroll failed: {exc}") from exc

    # ── TOOL 7: double_click(x, y) ───────────────────────────────────────────
    async def double_click(self, x: float, y: float) -> None:
        """Double-click at (x, y) — e.g. to select a word inside a field."""
        self._require_page()
        self.log.tool("double_click", f"({x:.0f}, {y:.0f})")
        try:
            await self.page.mouse.move(x, y)
            await self._show_click(x, y)
            await self.page.mouse.dblclick(x, y)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"double_click at ({x},{y}) failed: {exc}") from exc

    # ── lifecycle ─────────────────────────────────────────────────────────────
    async def close(self) -> None:
        """Tear down the page, context, browser and Playwright cleanly."""
        self.log.tool("close_browser")
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception as exc:  # noqa: BLE001
            self.log.warn(f"Cleanup warning: {exc}")

    # ── visual aid ────────────────────────────────────────────────────────────
    async def _show_click(self, x: float, y: float) -> None:
        """Flash a red ring at (x, y) so a human can see where the agent clicks.

        Purely cosmetic; only visible in a non-headless window, and never fatal.
        """
        try:
            await self.page.evaluate(
                """([x, y]) => {
                  const d = document.createElement('div');
                  d.style.cssText = `position:fixed;left:${x-13}px;top:${y-13}px;`
                    + `width:26px;height:26px;border:3px solid #ff3b1d;border-radius:50%;`
                    + `z-index:2147483647;pointer-events:none;`
                    + `transition:opacity .6s ease, transform .6s ease;`;
                  document.body.appendChild(d);
                  requestAnimationFrame(() => {
                    d.style.opacity = '0';
                    d.style.transform = 'scale(2.2)';
                  });
                  setTimeout(() => d.remove(), 650);
                }""",
                [x, y],
            )
            await self.page.wait_for_timeout(450)  # let the ring be seen before clicking
        except Exception:  # noqa: BLE001 - cosmetic only
            pass

    # ── internal guards ───────────────────────────────────────────────────────
    def _require_page(self) -> None:
        if self.page is None:
            raise BrowserError("Browser is not open — call open_browser() first.")
