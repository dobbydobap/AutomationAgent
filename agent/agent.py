"""
agent/agent.py
───────────────
``WebFormAgent`` — the orchestrator that ties everything together.

It is deliberately thin: all the *capability* lives in the composable pieces
(``BrowserTools``, ``ElementDetector``, ``LLMPlanner``).  The agent's job is to
sequence them into the high-level workflow the assignment describes:

    open browser → navigate → understand the page → plan → for each field:
        scroll into view → click at (x, y) → clear → type → screenshot
    → verify → final screenshot

Every one of the seven required tools is exercised here:
``open_browser, navigate_to_url, take_screenshot, scroll, double_click,
click_on_screen, send_keys`` (+ the ``press`` helper for clearing fields).
"""

from __future__ import annotations

from typing import Any, Optional

from playwright.async_api import Locator

from config import settings

from .browser_tools import BrowserTools
from .element_detector import ElementDetector, ElementNotFound, FieldSpec
from .llm_planner import FieldPlan, LLMPlanner
from .logger import get_logger


class WebFormAgent:
    """Autonomous agent that fills the target form end-to-end."""

    def __init__(self) -> None:
        self.log = get_logger()
        self.tools = BrowserTools()
        self.planner = LLMPlanner()
        self.detector: Optional[ElementDetector] = None

    # ── main entry point ───────────────────────────────────────────────────────
    async def run(self, url: str | None = None) -> dict[str, Any]:
        """Execute the full automation task and return a structured result."""
        url = url or settings.target_url
        result: dict[str, Any] = {
            "success": False,
            "url": url,
            "plan_source": None,
            "fields_filled": [],
            "screenshots": [],
            "error": None,
        }

        try:
            # ── 1. Open the browser ──────────────────────────────────────────
            self.log.step("Open browser")
            page = await self.tools.open_browser()
            self.detector = ElementDetector(page)

            # ── 2. Navigate to the target ────────────────────────────────────
            self.log.step(f"Navigate to target")
            await self.tools.navigate_to_url(url)
            shot = await self.tools.take_screenshot("page_loaded")
            result["screenshots"].append(shot.name)

            # ── 3. Understand the page + decide on a plan ────────────────────
            self.log.step("Understand page & build plan")
            # Narrow detection to the relevant <form> so labels from other demos
            # on the same page can't produce false matches.
            self.detector.root = await self._find_form_scope()
            page_context = await self._scrape_form_context()
            plan = await self.planner.build_plan(page_context)
            result["plan_source"] = plan.source
            self.log.info(f"Plan source: {plan.source} "
                          f"({len(plan.fields)} field(s))")

            # ── 4. Scroll the form into view (intelligent wheel scrolling) ───
            self.log.step("Reveal the form")
            await self._reveal_form(plan.fields[-1].spec)  # anchor on last field
            shot = await self.tools.take_screenshot("form_in_view")
            result["screenshots"].append(shot.name)

            # ── 5. Fill each field ───────────────────────────────────────────
            for index, fp in enumerate(plan.fields):
                await self._fill_field(fp, demonstrate_double_click=(index == 0))
                result["fields_filled"].append(fp.spec.name)
                shot = await self.tools.take_screenshot(f"filled_{fp.spec.name}")
                result["screenshots"].append(shot.name)

            # ── 6. Verify what we typed actually landed ──────────────────────
            self.log.step("Verify values")
            await self._verify(plan.fields)

            shot = await self.tools.take_screenshot("final_state")
            result["screenshots"].append(shot.name)
            result["success"] = True
            self.log.success(
                f"Task complete — filled {len(result['fields_filled'])} field(s): "
                f"{', '.join(result['fields_filled'])}."
            )

            # Pause so a human watching the (non-headless) browser sees the result.
            if not settings.headless:
                await page.wait_for_timeout(2500)

        except ElementNotFound as exc:
            result["error"] = str(exc)
            self.log.error(f"Detection failed: {exc}")
            await self._safe_error_shot(result)
        except Exception as exc:  # noqa: BLE001 - report any failure cleanly
            result["error"] = str(exc)
            self.log.error(f"Agent run failed: {exc}")
            await self._safe_error_shot(result)
        finally:
            await self.tools.close()

        return result

    # ── field-filling workflow ──────────────────────────────────────────────────
    async def _fill_field(self, fp: FieldPlan, demonstrate_double_click: bool) -> None:
        """Detect one field, focus it by clicking at (x, y), clear it, and type."""
        assert self.detector is not None
        self.log.step(f"Fill field: {fp.spec.name}")

        locator = await self.detector.locate(fp.spec)
        x, y = await self.detector.center_of(locator)
        self.log.info(f"Field {fp.spec.name!r} centre at ({x:.0f}, {y:.0f}).")

        if demonstrate_double_click:
            # Double-click first: selects any pre-existing word in the field so a
            # subsequent type would overwrite it. Demonstrates the double_click
            # tool on a real, explainable gesture.
            await self.tools.double_click(x, y)
        else:
            await self.tools.click_on_screen(x, y)

        # Always click to guarantee focus, then clear thoroughly before typing.
        await self.tools.click_on_screen(x, y)
        await self.tools.press("Control+A")
        await self.tools.press("Delete")

        # Type the value with the keyboard (send_keys tool).
        await self.tools.send_keys(fp.value)
        self.log.info(f"Typed into {fp.spec.name!r}: {fp.value!r}")

    async def _verify(self, fields: list[FieldPlan]) -> None:
        """Read each field's value back and confirm it matches what we typed."""
        assert self.detector is not None
        for fp in fields:
            locator = await self.detector.locate(fp.spec)
            actual = await self._read_value(locator)
            if actual.strip() == fp.value.strip():
                self.log.info(f"  ✓ {fp.spec.name}: value confirmed.")
            else:
                self.log.warn(
                    f"  ! {fp.spec.name}: expected {fp.value!r} but read {actual!r}."
                )

    # ── intelligent scrolling ────────────────────────────────────────────────────
    async def _reveal_form(self, anchor: FieldSpec) -> None:
        """Wheel-scroll until the form's anchor field sits inside the viewport."""
        assert self.detector is not None and self.tools.page is not None
        viewport = self.tools.page.viewport_size or {"height": 900}

        for attempt in range(8):
            locator = await self._safe_locate(anchor)
            if locator is not None:
                box = await locator.bounding_box()
                if box and 0 <= box["y"] <= viewport["height"] - box["height"]:
                    self.log.info("Form is in view.")
                    return
            self.log.info(f"Form not fully visible — scrolling (attempt {attempt + 1}).")
            await self.tools.scroll(dy=450)

        self.log.warn("Gave up scrolling; relying on scroll-into-view fallback.")

    # ── helpers ──────────────────────────────────────────────────────────────────
    async def _safe_locate(self, spec: FieldSpec) -> Optional[Locator]:
        """Locate without raising — used during the scroll-to-reveal loop."""
        assert self.detector is not None
        try:
            return await self.detector.locate(spec)
        except ElementNotFound:
            return None

    async def _read_value(self, locator: Locator) -> str:
        """Return a field's current value (works for input and textarea)."""
        try:
            return await locator.input_value()
        except Exception:  # noqa: BLE001
            return await locator.inner_text()

    async def _find_form_scope(self):
        """Return the target <form> (first one containing a textarea), else page.

        The shadcn docs page hosts several form examples. Our task targets the
        bug-report form, which is the first form that contains a <textarea>.
        Scoping detection to it prevents matching identically-named fields in
        the other demos further down the page.
        """
        page = self.tools.page
        assert page is not None
        forms = page.locator("form")
        try:
            count = await forms.count()
        except Exception:  # noqa: BLE001
            count = 0

        for i in range(count):
            form = forms.nth(i)
            if await form.locator("textarea").count() > 0:
                self.log.info("Scoped detection to the form containing a textarea.")
                return form

        self.log.warn("No <form> with a textarea found; scoping to whole page.")
        return page

    async def _scrape_form_context(self) -> str:
        """Collect labels/placeholders so the optional LLM planner can reason."""
        assert self.tools.page is not None
        js = """() => {
            const out = [];
            document.querySelectorAll('label').forEach(l => {
                const t = (l.innerText || '').trim();
                if (t) out.push('label: ' + t);
            });
            document.querySelectorAll('input').forEach(i => {
                out.push('input[placeholder="' + (i.placeholder || '') +
                         '" name="' + (i.name || '') + '"]');
            });
            document.querySelectorAll('textarea').forEach(t => {
                out.push('textarea[placeholder="' + (t.placeholder || '') +
                         '" name="' + (t.name || '') + '"]');
            });
            return out.join('\\n');
        }"""
        try:
            return await self.tools.page.evaluate(js)
        except Exception:  # noqa: BLE001
            return ""

    async def _safe_error_shot(self, result: dict[str, Any]) -> None:
        """Best-effort screenshot when something goes wrong (aids debugging)."""
        try:
            if self.tools.page is not None:
                shot = await self.tools.take_screenshot("error_state")
                result["screenshots"].append(shot.name)
        except Exception:  # noqa: BLE001
            pass
