"""
agent/llm_agent.py
───────────────────
Optional free-form task loop. Claude looks at the page's interactive elements and
picks the next action; we execute it with the same coordinate-based tools used
everywhere else. This is the "do arbitrary multi-step tasks on any site" mode.

It is off unless USE_LLM=true and an ANTHROPIC_API_KEY is set, and it never
crashes the caller: any error is caught and returned in the result.

ponytail: single tab, 8-step cap, 40-element cap, no DOM-history compaction and
no retry/backoff. Raise the caps or add memory only if a real task needs it.
"""

from __future__ import annotations

import json
from typing import Any

from config import settings

from .browser_tools import BrowserTools
from .element_detector import ElementDetector
from .logger import get_logger

# Tag every visible interactive element with data-agent-idx and return a compact
# list. We click later via that attribute, so the index always maps back.
_OBSERVE_JS = """(max) => {
  const els = [...document.querySelectorAll('a,button,input,textarea,select,[role=button]')];
  const out = [];
  let i = 0;
  for (const el of els) {
    const r = el.getBoundingClientRect();
    const visible = r.width > 0 && r.height > 0 && r.bottom > 0 &&
                    r.top < innerHeight && getComputedStyle(el).visibility !== 'hidden';
    if (!visible) { el.removeAttribute('data-agent-idx'); continue; }
    el.setAttribute('data-agent-idx', i);
    const name = (el.getAttribute('aria-label') || el.placeholder || el.value ||
                  el.innerText || el.name || '').trim().slice(0, 80);
    out.push({idx: i, tag: el.tagName.toLowerCase(),
              type: el.getAttribute('type') || '', name});
    i++;
    if (i >= max) break;
  }
  return out;
}"""

_SYSTEM = (
    "You are a web-browsing agent. You are given a GOAL, the current URL, and a "
    "numbered list of visible interactive elements. Reply with ONE JSON action and "
    "nothing else. Allowed actions: "
    '{"action":"click","index":N} | {"action":"type","index":N,"text":"..."} | '
    '{"action":"press","key":"Enter"} | {"action":"scroll","dy":600} | '
    '{"action":"navigate","url":"https://..."} | {"action":"done","reason":"..."}. '
    "Prefer typing into a search box then pressing Enter. Call done when the goal "
    "is met."
)


def _strip_json(text: str) -> str:
    """Pull the JSON object out of a reply that may have prose or ``` fences."""
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end != -1 else text


async def run_task(
    tools: BrowserTools, detector: ElementDetector, goal: str,
    max_steps: int | None = None,
) -> dict[str, Any]:
    """Observe -> ask Claude -> act, looping until done or the step cap."""
    log = get_logger()
    max_steps = max_steps or settings.max_task_steps
    result: dict[str, Any] = {
        "success": False, "task": "llm", "goal": goal,
        "screenshots": [], "summary": None, "error": None,
    }

    if not settings.llm_enabled:
        result["error"] = "LLM task mode needs USE_LLM=true and ANTHROPIC_API_KEY."
        log.error(result["error"])
        return result

    from anthropic import AsyncAnthropic  # lazy import — optional dependency

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    page = tools.page
    assert page is not None

    try:
        for step in range(1, max_steps + 1):
            log.step(f"Task step {step}/{max_steps}")
            elements = await page.evaluate(_OBSERVE_JS, 40)
            listing = "\n".join(
                f'{e["idx"]}: <{e["tag"]} type={e["type"]}> {e["name"]}'
                for e in elements
            )
            user = f"GOAL: {goal}\nURL: {page.url}\nELEMENTS:\n{listing}"

            resp = await client.messages.create(
                model=settings.llm_model, max_tokens=300,
                system=_SYSTEM, messages=[{"role": "user", "content": user}],
            )
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            ).strip()
            action = json.loads(_strip_json(text))
            log.info(f"LLM action: {action}")

            done = await _dispatch(tools, detector, action, log)
            shot = await tools.take_screenshot(f"task_step_{step}")
            result["screenshots"].append(shot.name)

            if done:
                result["success"] = True
                result["summary"] = (
                    f"task done in {step} step(s): {action.get('reason', '')}"
                )
                log.success(result["summary"])
                return result

        result["error"] = f"reached the {max_steps}-step cap without finishing."
        result["summary"] = result["error"]
        log.warn(result["error"])

    except Exception as exc:  # noqa: BLE001 - report any failure cleanly
        result["error"] = str(exc)
        log.error(f"LLM task failed: {exc}")

    return result


async def _dispatch(tools: BrowserTools, detector: ElementDetector,
                    action: dict, log) -> bool:
    """Execute one action with the existing tools. Returns True when done."""
    kind = action.get("action")
    if kind == "done":
        return True

    if kind in ("click", "type"):
        idx = int(action["index"])
        locator = tools.page.locator(f'[data-agent-idx="{idx}"]')
        x, y = await detector.center_of(locator)
        await tools.click_on_screen(x, y)
        if kind == "type":
            await tools.press("Control+A")
            await tools.press("Delete")
            await tools.send_keys(str(action.get("text", "")))
    elif kind == "press":
        await tools.press(str(action.get("key", "Enter")))
    elif kind == "scroll":
        await tools.scroll(dy=int(action.get("dy", 600)))
    elif kind == "navigate":
        await tools.navigate_to_url(str(action["url"]))
    else:
        log.warn(f"Unknown action ignored: {action}")
    return False


if __name__ == "__main__":
    # ponytail: one check for the pure logic that needs no browser or API key.
    assert json.loads(_strip_json('```json\n{"action":"done"}\n```'))["action"] == "done"
    assert json.loads(_strip_json('sure: {"action":"click","index":3}'))["index"] == 3
    print("llm_agent self-check ok")
