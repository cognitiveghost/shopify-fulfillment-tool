// The Setup page (phase 3 spec section 5). Python builds everything this page
// draws (gui/setup_state.py) and sends it as bridge.state; this file renders
// that map and reports clicks through the bridge's named slots. No rule, count
// or enabled flag is computed here. Its own words are fixed labels, plus the
// progress line and the Run and Cancel captions, worded from the run's step.
"use strict";

const TOAST_MS = 4000;

// Lucide glyphs, each as one path.
const GLYPH = {
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  alert: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01",
  clipboard: "M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M12 11h4M12 16h4M8 11h.01M8 16h.01",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  file: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7zM14 2v4a2 2 0 0 0 2 2h4",
  folder: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z",
  x: "M18 6 6 18M6 6l12 12",
};

const FILES = {
  orders: {
    title: "Orders file",
    hint: "Shopify orders export · CSV",
    drop: "Drop the Shopify orders export here",
  },
  stock: {
    title: "Stock file",
    hint: "Warehouse stock export · CSV",
    drop: "Drop the warehouse stock export here",
  },
};

const STRATEGIES = [
  {
    value: "multi_first",
    title: "Multi-item first",
    text: "Fills orders that can go out whole before partial ones. A few old orders wait longer for stock instead.",
  },
  {
    value: "fifo",
    title: "Oldest first",
    text: "Fills strictly by order date, whatever it contains. No order waits behind a newer one; more leave part-filled.",
  },
];

const els = {};
const page = { bridge: null, state: null, renders: 0, toastTimer: null };

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function off(disabled) {
  return disabled ? " disabled" : "";
}

// --- the three panels --------------------------------------------------------

function panel(s) {
  if (s.view === "unreachable") {
    return `<div class="state">
      ${svg(GLYPH.alert, "state-glyph")}
      <p class="state-title">This PC can't reach the fulfilment server</p>
      <p class="state-text">Clients, stock files and past sessions all live on the server. Until this PC reaches it, there is nothing to set up.</p>
      <span class="state-path">${esc(s.server_path)}</span>
      <button class="btn secondary" type="button" data-act="open-connection" data-key="open-connection">Server connection…</button>
    </div>`;
  }
  if (s.view === "no_session") {
    return `<div class="state">
      ${svg(GLYPH.clipboard, "state-glyph")}
      <p class="state-title">No session open for ${esc(s.client)}</p>
      <p class="state-text">Start a session for today's orders, or reopen one from this client.</p>
      <div class="state-actions">
        <button class="btn primary" type="button" data-act="new-session" data-key="new-session">New session</button>
        <button class="btn secondary" type="button" data-act="open-recent" data-key="open-recent">Open recent</button>
      </div>
    </div>`;
  }
  return `<div class="state">
    ${svg(GLYPH.users, "state-glyph")}
    <p class="state-title">Choose a client to begin</p>
    <p class="state-text">Pick a client in the bar above. Sessions, stock and reports all belong to one client.</p>
  </div>`;
}

// --- file card ---------------------------------------------------------------

function dropzone(kind, locked) {
  return `<div class="dropzone">
    ${svg(GLYPH.upload, "dropzone-glyph")}
    <span class="dropzone-text">${FILES[kind].drop}</span>
    <div class="dropzone-buttons">
      <button class="btn secondary" type="button" data-act="choose-file" data-kind="${kind}" data-key="${kind}-file"${off(locked)}>Choose file…</button>
      <button class="btn secondary" type="button" data-act="choose-folder" data-kind="${kind}" data-key="${kind}-folder"${off(locked)}>Choose folder…</button>
    </div>
    <span class="dropzone-note">A folder merges every CSV in it into one input.</span>
  </div>`;
}

function fileBody(kind, card, locked) {
  const parts = card.parts.length
    ? `<div class="parts">${card.parts
        .map(
          (p) =>
            `<div class="part"><span class="part-name">${esc(p.name)}</span><span class="part-rows">${esc(p.rows)} rows</span></div>`,
        )
        .join("")}</div>`
    : "";
  const note = card.note ? `<span class="file-note">${esc(card.note)}</span>` : "";
  const stats = card.stats
    .map(
      (st) =>
        `<div class="stat"><span class="stat-k">${esc(st.k)}</span><span class="stat-v${st.muted ? " muted" : ""}">${esc(st.v)}</span></div>`,
    )
    .join("");
  return `<div class="file-body">
    <div class="file-row">
      ${svg(card.is_folder ? GLYPH.folder : GLYPH.file, "glyph")}
      <span class="file-name" title="${esc(card.name)}">${esc(card.name)}</span>
      <button class="btn secondary compact" type="button" data-act="clear" data-kind="${kind}" data-key="${kind}-clear"${off(locked)}>Replace</button>
    </div>
    ${parts}${note}
    <div class="stats">${stats}</div>
  </div>`;
}

function problemBlock(kind, problem) {
  const link = problem.fix_label
    ? `<button class="btn link" type="button" data-act="fix" data-kind="${kind}" data-key="${kind}-fix">${esc(problem.fix_label)}</button>`
    : "";
  return `<div class="banner danger" role="alert">
    ${svg(GLYPH.alert, "glyph")}
    <div class="banner-body">
      <span class="problem-title">${esc(problem.title)}</span>
      <span class="banner-text">${esc(problem.text)}</span>
      ${link}
    </div>
  </div>`;
}

function fileCard(kind, card, locked) {
  const body =
    card.state === "missing"
      ? dropzone(kind, locked)
      : fileBody(kind, card, locked) +
        (card.state === "problem" ? problemBlock(kind, card.problem) : "");
  // No data-file-kind while a run holds the inputs: a drop then finds no card.
  const target = locked ? "" : ` data-file-kind="${kind}"`;
  return `<section class="card file-card" data-card="${kind}" data-state="${card.state}"${target} aria-label="${FILES[kind].title}">
    <div class="file-head">
      <div class="file-titles">
        <span class="file-title">${FILES[kind].title}</span>
        <span class="file-hint">${FILES[kind].hint}</span>
      </div>
      <span class="badge ${esc(card.badge_tone)}">${esc(card.badge)}</span>
    </div>
    ${body}
  </section>`;
}

// --- options -----------------------------------------------------------------

function optionsCard(s) {
  const locked = s.run.locked;
  const on = s.memory.on;
  const previous = on && s.memory.previous
    ? `<span class="memory-previous">${esc(s.memory.previous)}</span>`
    : "";
  const radios = STRATEGIES.map((o) => {
    const checked = s.strategy === o.value;
    return `<button class="radio-card" type="button" role="radio" aria-checked="${checked}" tabindex="${checked ? 0 : -1}" data-act="strategy" data-value="${o.value}" data-key="strategy-${o.value}"${off(locked)}>
      <span class="radio-mark"></span>
      <span class="radio-card-body">
        <span class="radio-card-title">${o.title}</span>
        <span class="radio-card-text">${o.text}</span>
      </span>
    </button>`;
  }).join("");
  return `<section class="card options">
    <div class="form-row">
      <span class="form-label" id="memory-label">Inventory memory</span>
      <div class="memory">
        <div class="memory-toggle">
          <button class="switch" type="button" role="switch" aria-checked="${on}" aria-labelledby="memory-label" data-act="memory" data-key="memory"${off(locked)}><span class="switch-knob"></span></button>
          <span class="memory-state">${on ? "On" : "Off"}</span>
        </div>
        <span class="memory-text">${esc(s.memory.text)}</span>
        ${previous}
      </div>
    </div>
    <div class="form-row">
      <span class="form-label" id="strategy-label">Allocation strategy</span>
      <div class="strategies" role="radiogroup" aria-labelledby="strategy-label">${radios}</div>
    </div>
  </section>`;
}

// --- run summary -------------------------------------------------------------

function summaryCard(s) {
  const run = s.run;
  const rows = s.summary.rows
    .map(
      (r) =>
        `<div class="summary-row"><span class="summary-k">${esc(r.k)}</span><span class="summary-v${r.muted ? " muted" : ""}">${esc(r.v)}</span></div>`,
    )
    .join("");
  let progress = "";
  if (run.running) {
    const bars = Array.from(
      { length: run.steps },
      (_, n) => `<span class="progress-bar${n <= run.step ? " done" : ""}"></span>`,
    ).join("");
    progress = `<div class="progress">
      <span class="progress-label">Working · step ${run.step + 1} of ${run.steps}</span>
      <span class="progress-step">${esc(run.step_name)}</span>
      <div class="progress-bars">${bars}</div>
    </div>`;
  }
  const lastStep = run.step >= run.steps - 1;
  const cancel = run.running
    ? `<button class="btn secondary" type="button" data-act="cancel" data-key="cancel" title="${lastStep ? "Saving can't be cancelled" : ""}"${off(!run.can_cancel)}>${run.cancelling ? "Cancelling…" : "Cancel"}</button>`
    : "";
  const reason = s.summary.reason
    ? `<span class="summary-reason${s.summary.reason_tone === "danger" ? " danger" : ""}">${esc(s.summary.reason)}</span>`
    : "";
  return `<aside class="card summary" aria-label="Run summary">
    <div class="summary-head">
      <span class="summary-label">Run summary</span>
      <span class="summary-headline${s.summary.ready ? " ready" : ""}">${esc(s.summary.headline)}</span>
    </div>
    <div class="summary-rows">${rows}</div>
    ${progress}
    <div class="summary-actions">
      <button class="btn primary" type="button" data-act="run" data-key="run"${off(!run.enabled)}>${run.running ? "Running…" : "Run analysis"}</button>
      ${cancel}
    </div>
    ${reason}
  </aside>`;
}

// --- render ------------------------------------------------------------------

function setupView(s) {
  const locked = s.run.locked;
  return `<div class="page-head">
      <span class="page-title">${esc(s.session.title)}</span>
      <span class="code">${esc(s.session.name)}</span>
      <span class="page-meta">${esc(s.session.meta)}</span>
    </div>
    <div class="setup-grid">
      <div class="setup-main">
        <div class="file-cards">
          ${fileCard("orders", s.files.orders, locked)}
          ${fileCard("stock", s.files.stock, locked)}
        </div>
        ${optionsCard(s)}
      </div>
      ${summaryCard(s)}
    </div>`;
}

function render() {
  const s = page.state;
  if (!s || !s.view) return;
  // The whole page is redrawn, so the control that had focus is found again
  // by its key: a click on the switch must not drop focus to the body.
  const active = document.activeElement;
  const key = active && active.dataset ? active.dataset.key : null;
  els.setup.dataset.view = s.view;
  els.setup.innerHTML = s.view === "setup" ? setupView(s) : panel(s);
  if (key) {
    const again = els.setup.querySelector(`[data-key="${key}"]`);
    if (again && !again.disabled) again.focus();
  }
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// --- input -------------------------------------------------------------------

function onClick(event) {
  const el = event.target.closest("[data-act]");
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const kind = el.dataset.kind;
  switch (el.dataset.act) {
    case "choose-file": bridge.chooseFile(kind); break;
    case "choose-folder": bridge.chooseFolder(kind); break;
    case "clear": bridge.clearFile(kind); break;
    case "fix": bridge.fixProblem(kind); break;
    case "memory": bridge.setMemory(el.getAttribute("aria-checked") !== "true"); break;
    case "strategy": bridge.setStrategy(el.dataset.value); break;
    case "run": bridge.runAnalysis(); break;
    case "cancel": bridge.cancelRun(); break;
    case "new-session": bridge.newSession(); break;
    case "open-recent": bridge.openRecent(); break;
    case "open-connection": bridge.openConnection(); break;
  }
}

// Arrow keys move between the radio cards; Space and Enter are the button's own.
function onKey(event) {
  const el = event.target.closest('[role="radio"]');
  if (!el) return;
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
  const radios = Array.from(els.setup.querySelectorAll('[role="radio"]:not(:disabled)'));
  if (radios.length < 2) return;
  const step = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
  const next = radios[(radios.indexOf(el) + step + radios.length) % radios.length];
  event.preventDefault();
  next.focus();
}

// The drop itself is the view's (gui/setup_bridge.py, SetupView); the page only
// shows which card would take it.
function markDropTarget(event) {
  const target = event.target.closest ? event.target.closest("[data-file-kind]") : null;
  els.setup.querySelectorAll(".file-card.over").forEach((card) => {
    if (card !== target) card.classList.remove("over");
  });
  if (target) target.classList.add("over");
}

function clearDropTarget() {
  els.setup.querySelectorAll(".file-card.over").forEach((card) => card.classList.remove("over"));
}

// --- toast (ADR 0007: a web page draws its own) --------------------------------

function raiseToast(text) {
  els.toastText.textContent = text;
  els.toast.hidden = false;
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(dismissToast, TOAST_MS);
}

function dismissToast() {
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = null;
  els.toast.hidden = true;
}

// --- boot --------------------------------------------------------------------

function bind() {
  els.setup = document.getElementById("setup");
  els.themeVars = document.getElementById("theme-vars");
  els.toast = document.getElementById("toast");
  els.toastText = document.getElementById("toast-text");
  els.toastDismiss = document.getElementById("toast-dismiss");
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");
  els.toastDismiss.addEventListener("click", dismissToast);
  els.setup.addEventListener("click", onClick);
  els.setup.addEventListener("keydown", onKey);
  document.addEventListener("dragenter", (event) => { event.preventDefault(); markDropTarget(event); });
  document.addEventListener("dragover", (event) => { event.preventDefault(); markDropTarget(event); });
  document.addEventListener("dragleave", (event) => {
    // Leaving the document, not moving between two of its elements.
    if (!event.relatedTarget) clearDropTarget();
  });
  document.addEventListener("drop", (event) => { event.preventDefault(); clearDropTarget(); });
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.setup;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => {
    els.themeVars.textContent = bridge.themeCss;
    // Two frames: the first callback runs before this frame is painted.
    requestAnimationFrame(() => requestAnimationFrame(() => bridge.themeApplied()));
  });
  bridge.stateChanged.connect(() => { page.state = bridge.state; render(); });
  bridge.toastRaised.connect((text) => raiseToast(text));
  page.state = bridge.state;
  render();
  window.setupBridge = bridge;
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
