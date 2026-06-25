"""
agent/llm_agent.py
───────────────────
Optional free-form task loop. Claude looks at the page's interactive elements and
picks the next action; we execute it with the same coordinate-based tools used
everywhere else. This is the "do arbitrary multi-step tasks on any site" mode.

It is off unless USE_LLM=true and an LLM_API_KEY is set, and it never
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
  const sel = 'a,button,input,textarea,select,[role=button],[role=link],[role=option]';
  const els = [...document.querySelectorAll(sel)];
  const out = [];
  let i = 0;
  for (const el of els) {
    const r = el.getBoundingClientRect();
    const visible = r.width > 0 && r.height > 0 && r.bottom > 0 &&
                    r.top < innerHeight && getComputedStyle(el).visibility !== 'hidden';
    if (!visible) { el.removeAttribute('data-agent-idx'); continue; }
    el.setAttribute('data-agent-idx', i);
    const name = (el.getAttribute('aria-label') || el.placeholder || el.value ||
                  el.innerText || el.name || '').trim().replace(/\\s+/g, ' ').slice(0, 90);
    const item = {idx: i, tag: el.tagName.toLowerCase(),
                  type: el.getAttribute('type') || '', name};
    const href = el.getAttribute('href');
    if (href) item.href = href.slice(0, 80);
    out.push(item);
    i++;
    if (i >= max) break;
  }
  return out;
}"""

_SYSTEM = (
    "You are an autonomous web-browsing agent controlling a REAL Chromium browser "
    "to accomplish the user's GOAL. You work in a loop: each turn you are given the "
    "current URL and a numbered list of the visible, interactive elements on the "
    "page; you reply with EXACTLY ONE action as compact JSON (no prose, no "
    "markdown, no code fences); the action is executed and you see the updated "
    "page next turn.\n\n"
    "Actions:\n"
    '- {"action":"navigate","url":"https://..."}  open a site. Do this FIRST if the '
    "current URL is about:blank or the wrong site for the goal.\n"
    '- {"action":"type","index":N,"text":"..."}  click element N and type text '
    "(use for a search box).\n"
    '- {"action":"press","key":"Enter"}  submit the text you just typed.\n'
    '- {"action":"click","index":N}  click element N (a link, button, or result).\n'
    '- {"action":"scroll","dy":600}  scroll down to reveal more elements if what '
    "you need is not in the list.\n"
    '- {"action":"done","reason":"..."}  the goal is achieved.\n\n'
    "Rules:\n"
    "- Output ONLY the single JSON object, nothing else.\n"
    "- To search a site: find the search box, type the query, then press Enter on "
    "the next turn, then read the results.\n"
    "- Ordinals like 'the second video', '2nd result', 'next link' mean: count the "
    "relevant items in the list IN ORDER and click the one at that position. Video "
    "and result titles are usually links (tag 'a') whose name is the title.\n"
    "- If the element you need is not listed, scroll down and look again.\n"
    "- Take the fewest steps possible and call done as soon as the goal is "
    "satisfied (e.g. the requested video/page is open)."
)


def _strip_json(text: str) -> str:
    """Pull the JSON object out of a reply that may have prose or ``` fences."""
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end != -1 else text


def _format_element(e: dict) -> str:
    """One line per element for the model: index, tag, type, name, and href."""
    typ = f" type={e['type']}" if e.get("type") else ""
    href = f" (href {e['href']})" if e.get("href") else ""
    return f'{e["idx"]}: <{e["tag"]}{typ}> {e["name"]}{href}'


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
        result["error"] = "LLM task mode needs USE_LLM=true and an LLM_API_KEY."
        log.error(result["error"])
        return result

    from openai import AsyncOpenAI  # lazy import — optional dependency

    client = AsyncOpenAI(
        api_key=settings.llm_api_key, base_url=settings.llm_base_url or None
    )
    page = tools.page
    assert page is not None

    try:
        for step in range(1, max_steps + 1):
            log.step(f"Task step {step}/{max_steps}")
            elements = await page.evaluate(_OBSERVE_JS, 50)
            listing = "\n".join(_format_element(e) for e in elements)
            user = f"GOAL: {goal}\nURL: {page.url}\nELEMENTS:\n{listing}"

            resp = await client.chat.completions.create(
                model=settings.llm_model, max_tokens=300,
                messages=[{"role": "system", "content": _SYSTEM},
                          {"role": "user", "content": user}],
            )
            text = (resp.choices[0].message.content or "").strip()
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
