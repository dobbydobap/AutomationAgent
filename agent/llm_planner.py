"""
agent/llm_planner.py
─────────────────────
The agent's "brain" — a **hybrid** planner.

What is a plan?
---------------
Before touching the browser the agent decides *which fields to fill and with
what*.  That decision is captured as a :class:`Plan` — an ordered list of
:class:`~agent.element_detector.FieldSpec` objects (what to look for) paired
with the values to type.  The rest of the agent is purely mechanical: detect →
click → type.

Two ways to produce a plan
--------------------------
* **Heuristic (default, offline, never fails):** a hand-tuned mapping of the
  target task to sensible label candidates and values from ``.env``.  This is
  what runs in the viva — deterministic and dependency-free.

* **LLM (optional, opt-in via ``USE_LLM=true`` + an API key):** we hand Claude
  the task plus the form labels we scraped from the live page and ask it to
  return the same plan as JSON.  This demonstrates genuine AI-driven decision
  making (mapping fuzzy human intent onto whatever fields the page exposes).

Crucially the LLM path **degrades gracefully**: any missing key, network error
or malformed response logs a warning and falls back to the heuristic plan, so
the agent is always able to complete the task.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from config import settings

from .element_detector import FieldSpec
from .llm_agent import _strip_json
from .logger import get_logger


@dataclass
class FieldPlan:
    """A field to find plus the value to type into it."""

    spec: FieldSpec
    value: str


@dataclass
class Plan:
    """The full ordered plan the agent will execute."""

    source: str            # "heuristic" or "llm"
    fields: list[FieldPlan]


class LLMPlanner:
    """Produces a :class:`Plan`, using Claude when enabled, else heuristics."""

    def __init__(self) -> None:
        self.log = get_logger()

    async def build_plan(self, page_context: str | None = None) -> Plan:
        """Return the plan to execute, preferring the LLM when configured."""
        if settings.llm_enabled:
            try:
                self.log.info(f"Planning with LLM ({settings.llm_model})…")
                plan = await self._llm_plan(page_context or "")
                self.log.success(f"LLM produced a {len(plan.fields)}-field plan.")
                return plan
            except Exception as exc:  # noqa: BLE001 - any failure -> fallback
                self.log.warn(f"LLM planning failed ({exc}); using heuristic plan.")
        else:
            self.log.info("LLM disabled — using deterministic heuristic plan.")

        return self._heuristic_plan()

    # ── deterministic plan ─────────────────────────────────────────────────────
    def _heuristic_plan(self) -> Plan:
        """Robust default: cover the labels the shadcn demo is likely to use."""
        return Plan(
            source="heuristic",
            fields=[
                FieldPlan(
                    spec=FieldSpec(
                        name="Name / Title",
                        # Real label on the page is "Bug Title"; "Name" is kept
                        # as a synonym so the agent works if the label changes.
                        labels=["Bug Title", "Title", "Name", "Username"],
                        multiline=False,
                    ),
                    value=settings.name_value,
                ),
                FieldPlan(
                    spec=FieldSpec(
                        name="Description",
                        labels=["Description", "Bio", "About", "Message"],
                        multiline=True,
                    ),
                    value=settings.description_value,
                ),
            ],
        )

    # ── LLM plan ───────────────────────────────────────────────────────────────
    async def _llm_plan(self, page_context: str) -> Plan:
        """Ask the LLM to map the task onto the form fields it can see."""
        # Imported lazily so the project runs even without the openai package.
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.llm_api_key, base_url=settings.llm_base_url or None
        )

        system = (
            "You are the planning module of a browser-automation agent. "
            "You are given a task and the form fields visible on a web page. "
            "Return ONLY compact JSON of the form: "
            '{"fields":[{"name":str,"labels":[str,...],"multiline":bool,'
            '"value":str}]}. '
            "`labels` are candidate visible label/placeholder texts to search "
            "for (most-likely first). `multiline` is true for textareas. "
            "Map the task's 'name' to the first text field and 'description' to "
            "the textarea. Do not wrap the JSON in markdown."
        )
        user = (
            f"TASK: Fill the form. Name value = {settings.name_value!r}. "
            f"Description value = {settings.description_value!r}.\n\n"
            f"FORM FIELDS DETECTED ON PAGE:\n{page_context or '(none provided)'}"
        )

        resp = await client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=700,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        text = (resp.choices[0].message.content or "").strip()

        data = json.loads(_strip_json(text))
        fields = [
            FieldPlan(
                spec=FieldSpec(
                    name=item.get("name", "field"),
                    labels=list(item.get("labels", [])),
                    multiline=bool(item.get("multiline", False)),
                ),
                value=str(item.get("value", "")),
            )
            for item in data["fields"]
        ]
        if not fields:
            raise ValueError("LLM returned an empty field list.")
        return Plan(source="llm", fields=fields)
