/* ════════════════════════════════════════════════════════════════════════════
   STREET ID // AUTOMATION AGENT — dashboard front-end logic
   - pulls the run config from /api/config
   - opens an EventSource to /api/stream for live agent events
   - renders log lines, screenshot tiles, and updates the status light
   - the RUN button POSTs to /api/run to start the agent
   ════════════════════════════════════════════════════════════════════════════ */

const el = (id) => document.getElementById(id);

const logBox      = el("log");
const shotsGrid   = el("shots");
const shotsHint   = el("shots-hint");
const runBtn      = el("run-btn");
const statusLight = el("status-light");
const statusText  = el("status-text");
const lightbox    = el("lightbox");
const lightboxImg = el("lightbox-img");

let running = false;

/* ── 1. Load + display config ──────────────────────────────────────────────── */
async function loadConfig() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    el("cfg-url").textContent  = cfg.target_url;
    el("cfg-name").textContent = cfg.name_value;
    el("cfg-desc").textContent = cfg.description_value;
    el("badge-mode").textContent =
      "BRAIN: " + (cfg.llm_enabled ? "CLAUDE (" + cfg.llm_model + ")" : "HEURISTIC");
    el("badge-headless").textContent =
      "BROWSER: " + (cfg.headless ? "HEADLESS" : "VISIBLE");
  } catch (e) {
    addLine({ level: "error", message: "Could not load /api/config: " + e });
  }
}

/* ── 2. Render a single log line ───────────────────────────────────────────── */
function addLine(event) {
  const line = document.createElement("div");
  line.className = "line";

  const time = new Date((event.ts ? event.ts * 1000 : Date.now()))
    .toLocaleTimeString("en-GB");

  const cls = event.type === "step" ? "step"
            : event.type === "tool" ? "tool"
            : event.type === "screenshot" ? "screenshot"
            : event.type === "result" ? "result"
            : (event.level || "info");

  const t = document.createElement("span");
  t.className = "t";
  t.textContent = time;

  const body = document.createElement("span");
  body.className = cls;
  body.textContent =
    (event.type === "step" ? "▶ " : "") + (event.message || "");

  line.appendChild(t);
  line.appendChild(body);
  logBox.appendChild(line);
  logBox.scrollTop = logBox.scrollHeight;
}

/* ── 3. Add a screenshot tile to the feed ──────────────────────────────────── */
function addShot(file, caption) {
  if (shotsHint) shotsHint.style.display = "none";

  const tile = document.createElement("div");
  tile.className = "shot";

  const img = document.createElement("img");
  // cache-bust so re-runs that reuse a filename still refresh the thumbnail
  img.src = "/screenshots/" + file + "?t=" + Date.now();
  img.alt = caption || file;

  const cap = document.createElement("div");
  cap.className = "cap";
  cap.textContent = (caption ? caption + "  ·  " : "") + file;

  tile.appendChild(img);
  tile.appendChild(cap);
  tile.addEventListener("click", () => openLightbox(img.src));
  shotsGrid.appendChild(tile);
}

/* ── 4. Status helpers ─────────────────────────────────────────────────────── */
function setStatus(state, text) {
  statusLight.className = "status-light" + (state ? " " + state : "");
  statusText.textContent = text;
}

/* ── 5. Lightbox ───────────────────────────────────────────────────────────── */
function openLightbox(src) {
  lightboxImg.src = src;
  lightbox.classList.remove("hidden");
}
lightbox.addEventListener("click", () => lightbox.classList.add("hidden"));

/* ── 6. Live event stream (SSE) ────────────────────────────────────────────── */
function connectStream() {
  const source = new EventSource("/api/stream");

  source.onmessage = (msg) => {
    let event;
    try { event = JSON.parse(msg.data); } catch { return; }

    addLine(event);

    if (event.type === "screenshot") {
      addShot(event.file, event.caption);
    }
    if (event.type === "result") {
      running = false;
      runBtn.disabled = false;
      if (event.level === "success") {
        setStatus("ok", "DONE — " + (event.result?.fields_filled?.join(", ") || "complete"));
      } else {
        setStatus("fail", "FAILED — " + (event.result?.error || "see log"));
      }
    }
  };

  source.onerror = () => {
    setStatus("", "stream disconnected — retrying…");
  };
}

/* ── 7. Run button ─────────────────────────────────────────────────────────── */
runBtn.addEventListener("click", async () => {
  if (running) return;
  running = true;
  runBtn.disabled = true;
  setStatus("running", "AGENT RUNNING…");
  // fresh feed for this run
  shotsGrid.innerHTML = "";
  if (shotsHint) shotsHint.style.display = "block";

  try {
    const res = await fetch("/api/run", { method: "POST" });
    if (res.status === 409) {
      addLine({ level: "warn", message: "A run is already in progress." });
    }
  } catch (e) {
    addLine({ level: "error", message: "Failed to start run: " + e });
    running = false;
    runBtn.disabled = false;
    setStatus("fail", "could not start");
  }
});

/* ── boot ──────────────────────────────────────────────────────────────────── */
loadConfig();
connectStream();
