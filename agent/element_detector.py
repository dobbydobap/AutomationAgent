"""
agent/element_detector.py
──────────────────────────
The "intelligence" behind the agent's element handling.

The browser tools only know how to click at raw (x, y) pixels.  Something has
to turn the human intent *"the Description field"* into those pixels — robustly,
even though the shadcn demo is a React app whose markup we don't control.  That
is this module's job.

Detection strategy (accessibility-first, with graceful fallbacks)
-----------------------------------------------------------------
For each field we try a prioritised list of locators and use the **first one
that actually resolves to a visible element**:

    1. by ARIA/label   – ``get_by_label`` (matches <label for=…> + aria-label)
    2. by role + name   – ``get_by_role("textbox", name=…)``
    3. by placeholder   – ``get_by_placeholder`` (shadcn fields have these)
    4. by raw tag       – first visible ``<textarea>`` / ``<input>`` on the page

Why prioritise accessibility?  Labels/roles/placeholders are *semantic* — they
survive CSS refactors and class-name churn far better than brittle XPath or
`.css-1x2y3z` selectors, which is precisely the kind of resilient detection the
assignment is asking for.

Once a locator is found we scroll it into view and compute the **centre of its
bounding box**.  Those coordinates are what we hand to ``click_on_screen``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from playwright.async_api import Locator, Page

from .logger import get_logger

# A "scope" is either the whole Page or a single container (e.g. a <form>).
# Both expose get_by_label / get_by_role / get_by_placeholder / locator, so the
# detector works identically against either.
Scope = Page | Locator


class ElementNotFound(RuntimeError):
    """Raised when no detection strategy can locate a required field."""


@dataclass
class FieldSpec:
    """Describes a field the agent wants to find, independent of the markup."""

    name: str                       # human label, used only for logging
    labels: list[str] = field(default_factory=list)  # candidate label/placeholder texts
    multiline: bool = False         # True -> prefer <textarea>
    search: bool = False            # True -> also try search-box-specific strategies


class ElementDetector:
    """Resolves a :class:`FieldSpec` to a Playwright locator and to (x, y)."""

    def __init__(self, page: Page, scope: Scope | None = None) -> None:
        self.page = page
        # ``root`` is what we actually search inside. Defaults to the whole
        # page but the agent narrows it to the target <form> so that labels
        # belonging to *other* demos on the same page can't cause false matches
        # (e.g. "Name" loosely matching a "Username" field elsewhere).
        self.root: Scope = scope if scope is not None else page
        self.log = get_logger()

    # ── public API ────────────────────────────────────────────────────────────
    async def locate(self, spec: FieldSpec) -> Locator:
        """Return a visible locator for ``spec`` using the strategy ladder."""
        self.log.info(f"Detecting field {spec.name!r} (candidates={spec.labels})")

        strategies = self._build_strategies(spec)
        for description, locator in strategies:
            resolved = await self._first_visible(locator)
            if resolved is not None:
                self.log.info(f"  ✓ matched via {description}")
                return resolved
            self.log.info(f"  · no match via {description}")

        raise ElementNotFound(
            f"Could not locate field {spec.name!r} with any strategy."
        )

    async def center_of(self, locator: Locator) -> tuple[float, float]:
        """Scroll ``locator`` into view and return the centre (x, y) in pixels."""
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        if box is None:
            raise ElementNotFound("Element has no bounding box (not rendered).")
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        return x, y

    # ── strategy construction ──────────────────────────────────────────────────
    def _build_strategies(self, spec: FieldSpec) -> list[tuple[str, Locator]]:
        """Build the ordered (description, locator) list for a field spec."""
        role = "textbox"  # ARIA role for both <input type=text> and <textarea>
        strategies: list[tuple[str, Locator]] = []

        # Search boxes vary a lot across sites, so try the common patterns first.
        if spec.search:
            strategies.append(("role=searchbox", self.root.get_by_role("searchbox")))
            strategies.append((
                "search input/textarea",
                self.root.locator(
                    "input[type='search'], input[name='q'], input[name='search'], "
                    "input[name='field-keywords'], textarea[name='q'], "
                    "input[aria-label*='search' i], textarea[aria-label*='search' i]"
                ),
            ))

        for label in spec.labels:
            strategies.append(
                (f"label≈{label!r}", self.root.get_by_label(label, exact=False))
            )
            strategies.append(
                (f"role=textbox name≈{label!r}",
                 self.root.get_by_role(role, name=label, exact=False))
            )
            strategies.append(
                (f"placeholder≈{label!r}",
                 self.root.get_by_placeholder(label, exact=False))
            )

        # Last-resort fallback: the right *kind* of control inside the scope.
        if spec.multiline:
            strategies.append(("first <textarea>", self.root.locator("textarea")))
        else:
            strategies.append(
                ("first text <input>",
                 self.root.locator("input[type='text'], input:not([type])"))
            )

        return strategies

    # ── helpers ────────────────────────────────────────────────────────────────
    async def _first_visible(self, locator: Locator) -> Optional[Locator]:
        """Return the first visible element of ``locator``, or None."""
        try:
            count = await locator.count()
        except Exception:  # noqa: BLE001 - malformed selector etc.
            return None

        for i in range(count):
            candidate = locator.nth(i)
            try:
                if await candidate.is_visible():
                    return candidate
            except Exception:  # noqa: BLE001
                continue
        return None
