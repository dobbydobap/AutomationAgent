# STREET ID Website Automation Agent

An autonomous web automation agent built with Python and Playwright. It opens a
real Chromium browser, navigates to a target page, detects the form fields on
its own, and fills them in by driving a real mouse and keyboard. A control
dashboard (FastAPI) lets you run the agent with one click and watch every action
and screenshot live.

This is Assignment 04 (Website Automation Agent). The agent navigates to
https://ui.shadcn.com/docs/forms/react-hook-form, detects the form's two fields
(the Bug Title field, which stands in for "Name", and the Description textarea),
and fills them in automatically while capturing screenshots.

## Live demo

The agent is deployed for free on Hugging Face Spaces:

https://varshitha2007899-automationagent.hf.space

Open the link and click "RUN AGENT". The browser runs headless on the server, so
you follow along through the live log and the screenshot feed. The first run may
take 20 to 30 seconds while the server starts Chromium.

## Cost and API keys

The project runs at no cost and needs no API key. The default planner is a
deterministic heuristic that makes no network calls beyond the target site. The
optional Claude planner is the only feature that would use a key, and it is off
by default.

## Features

- All seven required tools as small, composable methods: open_browser,
  navigate_to_url, take_screenshot, click_on_screen, send_keys, scroll, and
  double_click.
- Coordinate-based interaction. Clicks are real mouse events at pixel positions,
  the way a human or vision-based agent works, rather than calling a locator's
  click method directly.
- Intelligent element detection. Fields are found by their accessibility
  information (label, then role, then placeholder, then a tag fallback), which
  is resilient to changes in CSS and markup.
- Hybrid planner. A deterministic heuristic plan by default, with an optional
  Claude planner that can be turned on through configuration.
- Comprehensive logging to the console, to a timestamped log file, and to a live
  web dashboard that streams every action and screenshot.
- Two ways to run: a command-line interface and a themed web dashboard.

## Project structure

- config.py - single source of truth for settings, read from a .env file.
- main.py - command-line entry point.
- dashboard.py - launches the web dashboard.
- agent/
  - logger.py - console and file logging, plus a live event bus for the dashboard.
  - browser_tools.py - the seven low-level browser tools over Playwright.
  - element_detector.py - accessibility-first detection that returns (x, y) coordinates.
  - llm_planner.py - the hybrid planner (heuristic by default, optional Claude).
  - agent.py - the orchestrator that composes the tools into the workflow.
- web/
  - server.py - the FastAPI dashboard, including the live event stream.
  - static/ - the dashboard front end (index.html, styles.css, app.js).
- Dockerfile, .dockerignore - container definition for deployment.
- requirements.txt, .env.example - dependencies and configuration template.
- PROJECT_REPORT.md - the full project report (design, workflow, results).

## Requirements

- Python 3.10 or newer (developed on 3.14).
- Works on Windows, macOS, and Linux.

## Setup

1. Create and activate a virtual environment.

   On Windows (PowerShell):

       python -m venv .venv
       .venv\Scripts\Activate.ps1

   On macOS or Linux:

       python -m venv .venv
       source .venv/bin/activate

2. Install the dependencies.

       pip install -r requirements.txt

3. Install the Playwright browser (one time).

       python -m playwright install chromium

4. Create your configuration file from the template.

   On Windows: copy .env.example .env
   On macOS or Linux: cp .env.example .env

   The defaults work out of the box. Edit .env only if you want to change the
   target page, the text typed in, headless mode, or to enable the LLM.

## Running

Command-line interface:

    python main.py                 runs with the settings from .env
    python main.py --headless      runs without a visible window
    python main.py --url <URL>     overrides the target page for one run

You will see live logs in the terminal, a summary at the end, and PNG
screenshots in the screenshots folder.

Web dashboard:

    python dashboard.py

Then open http://127.0.0.1:8000 and click "RUN AGENT". The agent launches, its
actions stream into the live log, and screenshots appear in the feed.

## Running with Docker

The repository includes a Dockerfile based on the official Playwright image,
which already contains Chromium and all the operating-system libraries it needs.
It runs headless and serves the dashboard on port 7860.

    docker build -t streetid-agent .
    docker run -p 7860:7860 streetid-agent

Then open http://localhost:7860 and click "RUN AGENT".

## Deploying free on Hugging Face Spaces

The same container deploys to a free Hugging Face Space (Docker SDK, no credit
card, no API key).

1. Create a free account at https://huggingface.co.
2. Create a new Space, choose the Docker SDK with a blank template, and make it
   public.
3. Push this repository to the Space's git remote. Hugging Face builds the
   Dockerfile automatically and serves it on port 7860.

       git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
       git push space main

   When git asks for a password, paste a Hugging Face write token (from
   Settings, Access Tokens), not an AI API key.
4. Wait for the build to finish, then open the Space URL and click "RUN AGENT".

The Docker SDK is selected when you create the Space, and Hugging Face serves
Docker Spaces on port 7860 by default, which is the port this app listens on.

## Configuration

All settings are read from the .env file:

- TARGET_URL - the page the agent automates. Default: the shadcn form page.
- NAME_VALUE - the text typed into the first text field. Default: STREET ID STUDIO.
- DESCRIPTION_VALUE - the text typed into the Description textarea.
- HEADLESS - true hides the browser window; false shows it. Default: false.
- SLOW_MO - milliseconds of delay per action so a demo is watchable. Default: 350.
- TIMEOUT_MS - navigation and element timeout in milliseconds. Default: 30000.
- USE_LLM - true uses the Claude planner; false uses the heuristic planner. Default: false.
- ANTHROPIC_API_KEY - required only when USE_LLM is true.
- LLM_MODEL - the Claude model for the planner. Default: claude-sonnet-4-6.
- DASHBOARD_HOST and DASHBOARD_PORT - the dashboard address. Default: 127.0.0.1 and 8000.

To enable the Claude planner, set USE_LLM to true and provide an
ANTHROPIC_API_KEY. If the key is missing or the call fails, the agent
automatically falls back to the heuristic plan, so the task always completes.

## How it works

The agent opens a browser, navigates to the page, takes a screenshot, scopes its
detection to the target form, builds a plan, scrolls the form into view, and for
each field detects the element, converts it to a screen coordinate, clicks
there, clears it, types the value, and screenshots the result. It then reads
each field back to verify the values, takes a final screenshot, and closes the
browser. The full reasoning is in PROJECT_REPORT.md.

## Troubleshooting

- "Executable doesn't exist" from Playwright: run python -m playwright install chromium.
- A field is not found: the live page changed its labels. Add a candidate label
  to the field in agent/llm_planner.py.
- The dashboard shows no screenshots: confirm the run started (the status light
  turns amber) and that the screenshots folder is writable.
- LLM errors: leave USE_LLM as false. The heuristic planner needs no network.
