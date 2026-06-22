---
title: STREET ID Automation Agent
emoji: 🤖
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

<!--
The YAML block above is configuration for Hugging Face Spaces (it tells the
Space to build from the Dockerfile and serve on port 7860). It is harmless on
GitHub, where it renders as a small metadata table. Everything below is the
normal project README.
-->

# STREET ID // Website Automation Agent

> A mini "Browser-Use" — an autonomous web-automation agent that navigates to a
> page, *intelligently* finds form fields, and fills them in by driving a real
> mouse and keyboard. Built with **Python + Playwright**, with a themed
> **STREET ID STUDIO** control dashboard (FastAPI) on top.

**Assignment 04 — Website Automation Agent.** The agent navigates to
`https://ui.shadcn.com/docs/forms/react-hook-form`, detects the form's
fields (the "Bug Title"/Name field and the "Description" textarea), and fills
them in autonomously — capturing screenshots along the way.

## 🤗 Live demo

**Try it now (no setup):** **https://varshitha2007899-automationagent.hf.space**

[![Open in HF Spaces](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-md.svg)](https://huggingface.co/spaces/varshitha2007899/automationAgent)

Open the link and click **▶ RUN AGENT** — the agent runs **headless on the
server**, so you watch it work through the live log and the screenshot feed
(first run may take ~20–30s while the server cold-starts Chromium).

> 💸 **Cost & API keys:** This project runs **100% free** and needs **no API
> key**. The default "brain" is a deterministic heuristic planner — no LLM, no
> network calls beyond the target site. (The optional Claude planner is the
> *only* thing that would use a key, and it stays off by default.)

---

## ✦ Features

- **All 7 required tools**, implemented as small composable methods:
  `open_browser`, `navigate_to_url`, `take_screenshot`, `click_on_screen(x, y)`,
  `send_keys`, `scroll`, `double_click`.
- **Coordinate-based interaction** — clicks are real mouse events at pixel
  `(x, y)`, exactly like a vision/human-style agent (not `locator.click()`).
- **Intelligent element detection** — accessibility-first (label → role → 
  placeholder → tag fallback), resilient to CSS/markup changes.
- **Hybrid "brain"** — deterministic heuristic planner by default (offline,
  never fails live); optional **Claude** planner when you set an API key.
- **Comprehensive logging** — console + timestamped log file + a **live web
  dashboard** that streams every action and screenshot in real time.
- **Two ways to run** — a clean CLI (`main.py`) or the themed dashboard
  (`dashboard.py`).

---

## ✦ Project structure

```
assignement4GenAI/
├── agent/
│   ├── __init__.py          # package exports
│   ├── logger.py            # console + file logging AND a live event bus (SSE)
│   ├── browser_tools.py     # the 7 low-level tools (Playwright wrapper)
│   ├── element_detector.py  # accessibility-first detection → (x, y) coords
│   ├── llm_planner.py        # hybrid brain: heuristic + optional Claude planner
│   └── agent.py             # orchestrator: composes the tools into the workflow
├── web/
│   ├── server.py            # FastAPI dashboard (SSE stream, run endpoint)
│   └── static/
│       ├── index.html       # themed control panel
│       ├── styles.css       # STREET ID STUDIO theme
│       └── app.js           # SSE client + screenshot feed
├── config.py                # single source of truth for settings (.env)
├── main.py                  # CLI entry point
├── dashboard.py             # launches the FastAPI dashboard
├── requirements.txt
├── .env.example             # copy to .env
├── ARCHITECTURE.md          # design decisions & workflow
└── README.md
```

---

## ✦ Setup

### 1. Prerequisites
- **Python 3.10+** (developed on 3.14)
- Windows / macOS / Linux

### 2. Create a virtual environment & install dependencies

```bash
# from the project root
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Install the Playwright browser (one-time)

```bash
python -m playwright install chromium
```

### 4. Create your config

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if you want to change the
target, the values typed, headless mode, or enable the LLM.

---

## ✦ Run it

### Option A — CLI

```bash
python main.py                 # uses .env settings (visible browser by default)
python main.py --headless      # no visible window
python main.py --url <URL>     # override the target for one run
```

You'll see live logs in the terminal, a summary table at the end, and PNGs in
`screenshots/`.

### Option B — Themed dashboard (recommended for the demo)

```bash
python dashboard.py
```

Then open **http://127.0.0.1:8000**. Click **▶ RUN AGENT** — the agent launches,
its actions stream into the live log, and screenshots appear in the feed as it
captures them.

---

## ✦ Run with Docker

The repo ships a `Dockerfile` based on the official Playwright image (Chromium +
all OS dependencies preinstalled), so it runs anywhere with **no local Python
setup**. It runs **headless** and serves the dashboard on port `7860`.

```bash
docker build -t streetid-agent .
docker run -p 7860:7860 streetid-agent
# open http://localhost:7860  →  click ▶ RUN AGENT
```

On the server, "RUN AGENT" drives a headless Chromium; you watch progress
through the live log and screenshot feed (no visible browser window needed).

---

## ✦ Deploy free on Hugging Face Spaces

The same container deploys to a **free** Hugging Face Space (Docker SDK — ~16 GB
RAM, public URL, **no credit card, no API key**).

1. Create a free account at <https://huggingface.co>.
2. **New → Space** → choose **Docker** (blank template), make it **Public**.
3. Push this repo to the Space's git remote (it builds the `Dockerfile`
   automatically and serves on port `7860`):

   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```

   When git asks for a password, paste a free **Hugging Face write token**
   (Settings → Access Tokens) — *not* an AI API key.
4. Wait for the build, then open `https://<your-username>-<space-name>.hf.space`
   and click **▶ RUN AGENT**.

> The Space’s configuration (Docker SDK + port 7860) is read from the YAML
> header at the top of this README.

---

## ✦ Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `TARGET_URL` | shadcn react-hook-form | Page the agent automates |
| `NAME_VALUE` | `STREET ID STUDIO` | Text typed into the Name/Title field |
| `DESCRIPTION_VALUE` | *(sentence)* | Text typed into the Description textarea |
| `HEADLESS` | `false` | `true` hides the browser window |
| `SLOW_MO` | `350` | ms delay per action so the demo is watchable |
| `TIMEOUT_MS` | `30000` | navigation/element timeout |
| `USE_LLM` | `false` | `true` → use the Claude planner |
| `ANTHROPIC_API_KEY` | *(empty)* | required only when `USE_LLM=true` |
| `LLM_MODEL` | `claude-sonnet-4-6` | model for the planner |
| `DASHBOARD_HOST` / `DASHBOARD_PORT` | `127.0.0.1` / `8000` | dashboard address |

### Optional: enable the Claude brain
Set `USE_LLM=true` and `ANTHROPIC_API_KEY=sk-ant-...` in `.env`. The agent will
ask Claude to map the task onto the page's detected fields. If the key is
missing or the call fails, it **automatically falls back** to the heuristic
plan — so the task always completes.

---

## ✦ How it works (60-second version)

```
open_browser → navigate_to_url → screenshot
            → scrape labels → plan (heuristic | Claude)
            → scroll form into view
            → for each field: detect → center (x,y) → click_on_screen
                              → clear → send_keys → screenshot
            → verify typed values → final screenshot → close
```

The agent never hard-codes pixel positions: it *detects* each field
semantically, then converts the element's bounding box into the `(x, y)` it
clicks. See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full reasoning.

---

## ✦ Troubleshooting

- **`Executable doesn't exist … run playwright install`** → run
  `python -m playwright install chromium`.
- **Field not found** → the live page changed labels; add a candidate to the
  field's `labels` list in `agent/llm_planner.py` (heuristic plan).
- **Dashboard shows no screenshots** → ensure the run actually started (status
  light turns amber) and that `screenshots/` is writable.
- **LLM errors** → leave `USE_LLM=false`; the heuristic brain needs no network.

---

*Don't copy — automate.* — STREET ID // AUTOMATION AGENT
