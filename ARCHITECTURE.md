# Architecture — STREET ID // Website Automation Agent

This document explains **how the agent is designed and why**. It maps directly
onto the assignment's evaluation criteria (functionality, code quality, agent
intelligence, error handling, documentation).

---

## 1. High-level design

The project is built around a strict separation between **capabilities** (small,
dumb, reusable tools) and **orchestration** (the smart sequencing of those
tools). This is the same philosophy as tools like Browser-Use / the OpenAI
Agents SDK: an agent is a *loop over composable tools*, not one giant function.

```
┌──────────────────────────────────────────────────────────────────┐
│                          ENTRY POINTS                              │
│   main.py (CLI)                       dashboard.py → web/server.py │
│        │                                        │ (FastAPI + SSE)  │
└────────┼────────────────────────────────────────┼─────────────────┘
         │                                         │
         ▼                                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                       WebFormAgent (agent.py)                        │
│   Orchestrates the workflow; composes the pieces below.              │
└───────┬───────────────────┬───────────────────────┬─────────────────┘
        │                   │                       │
        ▼                   ▼                       ▼
 LLMPlanner          ElementDetector           BrowserTools
 (llm_planner.py)    (element_detector.py)     (browser_tools.py)
 heuristic |         label→role→placeholder     the 7 tools over
 Claude plan         →tag  ⇒  (x, y) coords      Playwright Chromium
        │                   │                       │
        └─────────── all log through ───────────────┘
                             ▼
                    AgentLogger (logger.py)
              console + file  +  live SSE event bus
                             │
                             ▼
                  web dashboard live log & feed
```

---

## 2. Module responsibilities

| Module | Responsibility | Why it's separate |
|---|---|---|
| `config.py` | Read every setting once from `.env`. | One source of truth; keeps secrets/paths out of code (assignment: "use env vars/config files"). |
| `agent/logger.py` | Structured logging to console + file **and** a live event bus. | Observability requirement; lets the dashboard mirror the terminal with zero extra wiring. |
| `agent/browser_tools.py` | The 7 low-level tools over Playwright. | Tools stay small/dumb so they're trivially reusable and testable. |
| `agent/element_detector.py` | Turn "the Description field" into a visible element and an `(x, y)`. | This is the *intelligence*; isolating it makes the detection strategy explicit and swappable. |
| `agent/llm_planner.py` | Decide **what** to fill (heuristic or Claude). | Separates *planning* (what) from *acting* (how); enables the hybrid brain. |
| `agent/agent.py` | Sequence everything into the task workflow. | Thin orchestrator — easy to read top-to-bottom. |
| `web/` | Themed dashboard + SSE streaming. | Pure presentation layer; contains no automation logic. |

---

## 3. Key design decisions

### 3.1 Playwright over Puppeteer/Selenium
- First-class **Python async** API, auto-waiting (less flaky than Selenium),
  reliable `page.mouse` coordinate control, and built-in screenshots.
- The whole stack is **async** so the *same* agent can be `await`-ed from the
  CLI (`asyncio.run`) and from FastAPI without blocking the event loop.

### 3.2 Coordinate-based clicking (`click_on_screen(x, y)`)
The assignment explicitly asks for `click_on_screen(x, y)` and `double_click`.
So the tools drive `page.mouse` at **absolute pixel coordinates** rather than
calling `locator.click()`. This mirrors how vision-based agents operate. The
"how do we know the coordinates?" problem is solved by the `ElementDetector`,
which computes the **centre of the element's bounding box** — bridging semantic
detection and physical clicking.

### 3.3 Accessibility-first element detection
Detection tries a prioritised ladder and uses the first **visible** match:

1. `get_by_label` — matches `<label for>`, `aria-label`, `aria-labelledby`
2. `get_by_role("textbox", name=…)` — semantic role + accessible name
3. `get_by_placeholder` — shadcn inputs have descriptive placeholders
4. Tag fallback — first visible `<textarea>` / `<input>`

Semantic locators survive class-name churn and re-styling far better than
brittle XPath like `//div[3]/form/input[2]`. Each field also carries **multiple
label candidates** (`["Name", "Bug Title", "Title", "Username"]`) so the agent
works whether the page says "Name" or "Bug Title".

### 3.4 Hybrid brain (heuristic + optional LLM)
- **Heuristic plan** (default): deterministic, offline, instant — it never
  fails during a live demo. Already demonstrates real detection logic.
- **Claude plan** (opt-in): we scrape the page's labels/placeholders and ask
  Claude to map the fuzzy task onto concrete fields, returning JSON. This is
  genuine AI-driven decision-making.
- **Graceful degradation:** any LLM problem (missing key, network, bad JSON)
  logs a warning and falls back to the heuristic plan. The task always finishes.

### 3.5 Logging + live dashboard via one event bus
Every tool call, step, and screenshot goes through `AgentLogger`, which both
writes to console/file and `put_nowait`s a structured event onto each
subscriber queue. The FastAPI dashboard subscribes and relays events over
**Server-Sent Events**, so the browser sees exactly what the terminal sees.

---

## 4. The agent workflow (what `run()` does)

1. **open_browser** — launch Chromium (visible by default, `slow_mo` for demos).
2. **navigate_to_url** — go to the target, wait for DOM + network idle (React
   needs to hydrate the shadcn form).
3. **take_screenshot** — record the loaded page.
4. **Understand + plan** — scrape labels, build a `Plan` (heuristic or Claude).
5. **scroll** — wheel-scroll until the form's anchor field is in the viewport.
6. **For each field**: detect → compute `(x, y)` → `double_click`/`click_on_screen`
   to focus → `Ctrl+A` + `Delete` to clear → `send_keys` to type →
   `take_screenshot`.
7. **Verify** — read each field's value back and confirm it matches.
8. **Final screenshot**, then **close** the browser cleanly.

All seven required tools are exercised in this single run.

---

## 5. Error handling

- **Tool layer** — each tool wraps Playwright calls and raises a clean
  `BrowserError` with context (which action, which coords/URL).
- **Detection layer** — `ElementNotFound` is raised only after *every* strategy
  fails; the scroll-to-reveal loop uses a non-raising `_safe_locate`.
- **Agent layer** — `run()` catches `ElementNotFound` and generic exceptions
  separately, captures an `error_state` screenshot, and returns a structured
  result (`success=False`, `error=…`) instead of crashing.
- **Planner layer** — LLM failures degrade to the heuristic plan.
- **Browser lifecycle** — `close()` runs in a `finally` block so the browser is
  always torn down, even on failure.
- **Timeouts** — a single `TIMEOUT_MS` governs navigation and element waits.

---

## 6. Extensibility

- **New field?** Add a `FieldPlan` to the heuristic plan (or let the LLM infer
  it). No tool changes needed.
- **New action (e.g. submit)?** Add one method to `BrowserTools` and call it
  from `agent.py`.
- **Different site?** Change `TARGET_URL`; the accessibility-first detector is
  site-agnostic.
- **Swap the brain?** `LLMPlanner.build_plan()` is the single seam between
  "what to do" and "how to do it".
