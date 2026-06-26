# Project Report: Website Automation Agent

## 1. Abstract

This project is an autonomous website automation agent, built as a small-scale
version of browser automation tools such as Browser Use. The agent controls a
real web browser without human intervention. It opens a browser, navigates to a
target web page, identifies the form fields on that page on its own, and fills
them in by driving a real mouse and keyboard. The work is implemented in Python
using the Playwright automation library, and it is presented through a control
dashboard built with FastAPI. The agent has been verified to complete the
required task locally through a command-line interface, inside a Docker
container, and on a free public deployment hosted on Hugging Face Spaces.


## 2. Objective

The assignment asks for an intelligent automation agent capable of interacting
with web pages autonomously. The specific task is to navigate to the page at
https://ui.shadcn.com/docs/forms/react-hook-form, identify the form fields, and
automatically fill in the name and description. The agent must expose a defined
set of capabilities: take a screenshot, open a browser, navigate to a URL, click
at given screen coordinates, send keystrokes, scroll the page, and perform a
double click. The agent must also demonstrate intelligent decision making when
identifying and manipulating page elements, include error handling, provide
logging, and use configuration for any settings or keys.


## 3. Target task and an important observation

The page that the assignment points to renders a Bug Report form. Inspection of
the live page showed that the first text field is labelled Bug Title, with an
underlying name attribute of title, and the second field is a multi-line
Description textarea. There is no field literally labelled Name. The agent
therefore treats Name and Bug Title as equivalent: the first field is searched
for using several candidate labels, with Bug Title tried first and Name kept as
a synonym, so the agent works correctly whether the page uses one label or the
other. The value typed into this field is configurable; by default it is
STREET ID STUDIO. The Description textarea receives a sentence describing the
automated action.


## 4. Technology choices and justification

The implementation language is Python. It is concise, widely understood, and has
mature libraries for both browser automation and language-model access.

The browser automation library is Playwright. It was chosen over Puppeteer
because Puppeteer is JavaScript only and focused on Chrome, whereas Playwright
offers an official Python interface and supports multiple browser engines. It
was chosen over Selenium because Selenium relies on separate driver binaries and
is more prone to timing problems, while Playwright waits for elements
automatically, includes built-in screenshot support, and provides a clean mouse
interface that is essential for clicking at explicit coordinates. The
asynchronous version of the Playwright interface is used throughout so that the
same agent can be driven both from the command line and from the web dashboard
without blocking.

The web framework is FastAPI, served by the Uvicorn application server. It hosts
the control dashboard and streams the agent's actions to the browser using
Server-Sent Events. Server-Sent Events were chosen rather than WebSockets
because the data flows in one direction only, from server to browser, which
makes a long-lived streaming HTTP response the simpler and sufficient choice.

Configuration is loaded from a .env file using python-dotenv, which keeps any
keys and machine-specific settings out of the source code, as the assignment
requires.

The optional language-model features use the OpenAI software development kit
pointed at any OpenAI-compatible provider. The default target is Groq, which
offers a free tier, but the same code works with OpenRouter, Google Gemini's
OpenAI-compatible endpoint, or OpenAI itself simply by changing the base URL,
model name, and key. This dependency is imported only when needed, so the
project runs even if the package is absent or no key is configured.

For deployment, Docker is used to package the project so that it runs
identically anywhere, and Hugging Face Spaces hosts the container for free.


## 5. System architecture

The design separates capability from orchestration. The low-level tools are
small and deliberately unintelligent; they only perform actions. The decision
making lives in dedicated components, and a thin orchestrator sequences
everything into the required workflow. This mirrors the structure of larger
agent frameworks while remaining easy to read.

The configuration module builds a single settings object once, from the
environment. Every other module reads from that one object, so there is exactly
one place that defines how the agent is configured.

The logging module provides a single logger used everywhere. It writes
human-readable lines to the console and to a timestamped log file, and it also
publishes the same events, in a structured form, to any number of live
subscribers. The dashboard subscribes to this stream, which is how the terminal
and the web interface see exactly the same events without any extra wiring.

The browser tools module wraps Playwright and exposes the seven required tools.
The element detector turns a human description of a field, such as the
Description field, into a concrete on-screen coordinate. The planner decides
which fields to fill and with what values. The orchestrator, called the web form
agent, ties these together. The web layer is presentation only and contains no
automation logic.

The overall flow of a run is as follows. The agent opens the browser and creates
an element detector for the page. It navigates to the target and takes a
screenshot of the loaded page. It then scopes its detection to the relevant
form, gathers the form's labels, and builds a plan. It scrolls the form into
view, and for each field it detects the element, computes the centre coordinate,
clicks there, clears any existing content, types the value, and takes a
screenshot. After all fields are filled it reads each field back to verify the
value, takes a final screenshot, and closes the browser. The browser is always
closed, even if an error occurs.


## 6. The seven required tools

All seven tools are implemented in the browser tools module and each one logs
its action.

The open browser tool starts Playwright, launches a Chromium browser using the
configured headless and slow-motion settings, creates an isolated browser
context with a fixed window size of 1280 by 900 pixels, and opens a page.

The navigate to URL tool sends the page to the requested address and then lets
it settle on a best-effort basis, so a busy site that never reaches a fully idle
network does not cause a failure. It retries once on a transient connection drop,
and it accepts a bare site name as well as a full URL, so typing "youtube"
becomes "https://youtube.com" automatically.

The take screenshot tool captures the current view to a numbered PNG file in the
screenshots folder and announces it to the dashboard.

The click on screen tool moves the mouse to a pixel coordinate and clicks there.
It is a real mouse event at an absolute position rather than a call on a located
element. In a visible (non-headless) run it first flashes a brief red ring at the
target coordinate, so a person watching can see exactly where each click lands.

The send keys tool types text, character by character with a small delay, into
whatever element currently holds focus.

The scroll tool performs a wheel scroll by a given vertical and horizontal
amount and then pauses briefly to let the layout settle.

The double click tool performs a mouse double click at a coordinate, which is
used to select an existing word inside a field.

A small key-press helper is also provided, used to send Control-A and Delete
when clearing a field before typing.


## 7. Intelligent element detection

The browser tools only understand pixel coordinates. The element detector is
responsible for turning a field description into those coordinates in a way that
is robust, even though the target page is a client-side application whose markup
the project does not control.

For each field the detector tries a prioritised list of strategies and uses the
first one that resolves to a visible element. It first tries to find the field
by its accessible label, then by its role and accessible name, then by its
placeholder text, and finally falls back to the first visible textarea or text
input of the appropriate kind. Accessibility-based location is preferred because
labels, roles, and placeholders are semantic and survive changes to styling and
class names far better than brittle selectors such as long XPath expressions.
Each field also carries several candidate labels, which adds redundancy.

Once a suitable element is found, the detector scrolls it into view and computes
the centre of its bounding box. That centre point is the coordinate handed to
the click tool, which bridges semantic detection and physical clicking.

A problem found and fixed during development is worth recording, because it
demonstrates real decision making. The target page hosts several form examples.
In an early version, the search for the Name field, using a loose match on the
word Name, matched a Username field belonging to a different example further down
the same page. As a result the value was typed into the wrong field, while the
verification step still reported success because it re-found the same wrong
field. The fix was to scope all detection to the correct form. Before detecting
any field, the agent finds the first form on the page that contains a textarea,
which is the bug-report form, and restricts every search to that form. Labels
belonging to other examples can no longer cause a false match. The candidate
labels were also reordered so that the page's actual label, Bug Title, is tried
first.


## 7.1 Working on any website: navigate-and-search and free-form tasks

The form task is a fixed workflow. To make the agent generally useful it also
supports two further modes that work on arbitrary sites, both reusing the same
tools and detector.

The first is a deterministic navigate-and-search mode. Given any URL and a query,
the agent navigates to the site, finds its search box, types the query, and
presses Enter. Because search boxes vary across sites, detection first tries the
common patterns: the search role, search input types, the usual field names such
as q, search, or field-keywords, and aria-labels that contain the word search,
before falling back to the general label and placeholder strategies. This single
set of rules locates the search box on a wide range of sites, including
DuckDuckGo, Bing, Wikipedia, and YouTube, without any per-site code, and it needs
no language model. It is worth noting that some large commerce and search sites,
notably Amazon and Google, actively present CAPTCHAs or bot checks to automated
or headless browsers, especially from a data-centre address, so demonstrations
favour sites that permit automation.

The second is an optional free-form task mode, enabled only when the language
model is configured. The agent runs a short observe, decide, act loop. At each
step it tags the visible interactive elements on the page and sends a compact,
numbered list of them, together with the goal and the current address, to the
model, which replies with a single structured action: click an element, type into one,
press a key, scroll, navigate, or declare the goal done. The agent carries out
that action with the same coordinate-based tools and repeats until the goal is
met or a small step limit is reached. This mode demonstrates genuine multi-step,
model-driven control of the browser, while the deterministic search remains the
reliable default for live demonstration.


## 8. The hybrid planner

Before touching the browser, the agent decides which fields to fill and with
what values. This decision is captured as a plan. There are two ways to produce
a plan.

The default is a deterministic heuristic plan. It maps the task to sensible
candidate labels and to the values held in configuration. It makes no network
calls, is completely repeatable, and cannot fail during a live demonstration.

The optional method uses an OpenAI-compatible model (Groq by default, which is
free). The agent scrapes the visible labels and placeholders from the live form
and asks the model to return a plan, as structured data, that maps the task onto
the fields it can see. This demonstrates genuine model-driven decision making.

The two methods are combined so that the language-model path degrades
gracefully. If the model option is turned off, or the key is missing, or the
network call fails, or the response cannot be parsed, the agent logs a warning
and uses the heuristic plan instead. The task therefore always completes.


## 9. Logging, observability, and the dashboard

Every meaningful action passes through one logger. It records steps, individual
tool calls, screenshots, warnings, errors, and the final result. These go to the
console and to a timestamped file in the logs folder, and the same events are
published to live subscribers.

The dashboard is a single themed web page. It shows the current configuration,
the agent's brain mode, and the browser mode; a button to start a run; a live log
that mirrors the agent's actions line by line; and a feed that fills with
screenshots as they are captured. When the run button is pressed, the server
starts the agent in the background and the page receives events over a
Server-Sent Events stream. The visual theme follows a streetwear studio style
with a dark background and red accents, but it is purely presentation over the
same agent that the command line uses.


## 10. Browser lifecycle

The browser is ephemeral rather than persistent. Each run launches a fresh
browser and a fresh, isolated context, and tears them down at the end. No browser
profile directory is used, so no cookies, cache, stored logins, or history carry
over between runs. The browser does persist across all the tool calls within a
single run, but nothing survives from one run to the next. This was a deliberate
choice: it makes each run clean and repeatable, removes the need to manage a
profile directory, and matches the deployment environment, whose file system is
itself temporary. A persistent profile, using Playwright's persistent context
feature, would have been the alternative and would only be preferable if the task
required staying logged in across runs.


## 11. Error handling

Error handling is layered. Each tool wraps its Playwright calls and raises a
clear browser error that names the action and the relevant coordinate or URL. The
detector raises a not-found error only after every strategy has failed, and the
scroll-to-reveal loop uses a non-raising variant so that scrolling can continue
while the form is still off screen. The orchestrator catches detection failures
and general failures separately, captures an error-state screenshot to aid
debugging, and returns a structured result that reports success or failure rather
than crashing. The planner falls back to the heuristic plan on any model error. A
single timeout value governs navigation and element waits, and the browser is
always closed in a final cleanup step.


## 12. Configuration management

There are no secrets hard-coded anywhere. All settings, including the target
page, the values typed in, headless mode, the slow-motion delay, the timeout, the
optional model settings, and the dashboard address, are read from environment
variables, with a template file provided for convenience. The Docker image
sets the headless and network settings it needs through environment variables,
and the container ignore file ensures the configuration file and the private
preparation notes never enter the image.


## 13. Deployment

The project is containerised with a Dockerfile based on the official Playwright
Python image, which already includes Chromium, the required system libraries, and
a matching Playwright version, so no separate browser installation step is
needed. The container runs the dashboard headless on port 7860, as the user
account that the hosting platform expects, and is configured so that the agent
can write its screenshots and logs at run time.

The image was built and run locally to confirm the agent completes the task
inside a container before deployment. The same container is deployed to a free
Hugging Face Space using the Docker option. The platform builds the image and
serves it at a public address. On the server the browser runs headless, so a
viewer follows the run through the live log and the screenshot feed. The
deployment costs nothing and requires no API key; the only credential involved is
a free write token used to upload the code.


## 14. Testing and results

The agent was verified in three environments, and in each case it filled both
fields and confirmed the typed values by reading them back.

In a local headless command-line run, the agent navigated to the page, scoped
detection to the bug-report form, used the heuristic plan, scrolled the form into
view, detected the Bug Title field by its label and the Description field by its
label, typed the configured values, and verified both. It produced five
screenshots, ending with the completed form.

In a local Docker container, the same sequence ran headless and produced the same
five screenshots, confirming that the packaged image behaves identically.

On the live Hugging Face deployment, a run triggered from the dashboard produced
the same result, with the live log and screenshot feed updating in real time and
the status ending in a completed state.

A useful detail observed in the logs is that the two fields resolve to different
on-screen coordinates, for example around 640 by 348 for the title field and 640
by 474 for the description field, which confirms that the agent locates and
clicks two distinct elements rather than repeatedly acting on one.


## 15. Mapping to the evaluation criteria

For functionality, the agent completes the target task end to end and verifies
its own work, in three separate environments.

For code quality, the project is organised into focused modules with a clear
separation between the tools, the detection logic, the planner, and the
orchestrator, and every module is documented.

For agent intelligence, the agent detects fields semantically, scopes detection
to the correct form to avoid false matches, converts elements to coordinates, and
can optionally plan with a language model.

For error handling, failures are handled at every layer, an error screenshot is
captured, the browser is always cleaned up, and the language-model path falls
back safely.

For documentation, this report, the README, and inline comments together explain
how to set up, run, and reason about the project.


## 16. Limitations and future work

The coordinate-based click assumes the element does not move between the moment
it is located and the moment it is clicked; this is mitigated by computing the
coordinate immediately before clicking and by scrolling the element into view
first. The agent currently fills the form but does not submit it, to avoid side
effects; submitting would be a small addition that locates the submit button and
clicks its centre.

The deterministic search does not yet verify that the typed query actually
landed, so on an anti-bot page that hides the real search box it can report
success without having searched; the form task, by contrast, verifies by reading
the field values back, and adding the same post-type check to search would close
this gap. Finally, large sites such as Amazon, Google, and YouTube refuse the
cloud Space's data-centre address and serve a bot page with no search box, so
those sites are demonstrated in a local run while the deployed Space uses
automation-friendly sites such as DuckDuckGo and Wikipedia.

Future work could include driving multiple pages or forms from a configurable
list, running several browser contexts at once for throughput, and expanding the
language-model planner to handle more varied page layouts.


## 17. Conclusion

The project delivers a working, autonomous website automation agent that meets
the assignment requirements. It exposes the seven required tools, detects form
fields intelligently and robustly, fills them by driving a real mouse and
keyboard at computed coordinates, verifies its own results, and reports its
progress through thorough logging and a live dashboard. It is configurable,
handles errors gracefully, and is deployed as a free public demonstration. The
design keeps simple, reusable tools separate from the logic that orchestrates
them, which makes the system easy to understand, explain, and extend.
