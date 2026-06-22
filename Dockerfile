# ─────────────────────────────────────────────────────────────────────────────
#  STREET ID // AUTOMATION AGENT — container image
#
#  Base: the official Playwright Python image, which already ships Chromium +
#  all the OS libraries Playwright needs AND the matching `playwright` Python
#  package (v1.60.0). Because the pinned browser and library versions line up,
#  there is nothing to `playwright install` here — it "just works".
#
#  Designed for Hugging Face Spaces (Docker SDK): runs headless on port 7860 as
#  user UID 1000 (the UID Spaces expects), and needs NO API keys to run.
# ─────────────────────────────────────────────────────────────────────────────
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

# Headless on the server; bind to all interfaces on the HF Spaces port.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HEADLESS=true \
    DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_PORT=7860

WORKDIR /app

# Install the web/agent dependencies. `playwright` is already present in the
# base image at the matching version, so pip leaves it untouched.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code.
COPY . .

# Run as UID 1000 (Hugging Face Spaces requirement) and make the app directory
# writable so the agent can create screenshots/ and logs/ at runtime.
RUN chown -R 1000:1000 /app
USER 1000

EXPOSE 7860

# Start the themed dashboard. Clicking "RUN AGENT" launches headless Chromium,
# fills the form, and streams logs + screenshots back to the browser.
CMD ["uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "7860"]
