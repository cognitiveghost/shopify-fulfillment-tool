// The Tools page (phase 5 spec section 5). Python builds everything this page
// draws (gui/tools_state.py) and sends it as bridge.state; this file renders
// that map and reports what the operator asks for through the bridge's named
// slots. No rule, count or enabled flag is computed here. The page's own state
// is which menu is open and which Label setup folds are open.
"use strict";

const TOAST_MS = 4000;
const TOAST_ACTION_MS = 8000;

// Lucide glyphs, each as one path.
const GLYPH = {
  folder: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z",
  file: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7zM14 2v4a2 2 0 0 0 2 2h4",
  alert: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01",
  refresh: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5",
  printer: "M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6M7 14h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z",
  chevron: "m6 9 6 6 6-6",
  chevronRight: "m9 18 6-6-6-6",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
};

const TOOLS = {
  reference: {
    title: "Reference labels",
    text: "Stamps each courier label PDF with its order's reference number.",
    action: "Process labels",
  },
  barcode: {
    title: "Barcode labels",
    text: "One barcode label for every Fulfillable order in a packing list. Each list gets its own folder.",
    action: "Generate barcode labels",
  },
};

const FILES = {
  pdf: { label: "Labels PDF", choose: "Choose PDF…", again: "Choose another PDF" },
  csv: { label: "Mapping CSV", choose: "Choose CSV…", again: "Choose another CSV" },
};

const MODES = [
  { value: "driver", label: "Driver" },
  { value: "raw_zpl", label: "Raw ZPL" },
];

const els = {};
const page = { bridge: null, state: null, renders: 0, toastTimer: null };
// menu: "barcode-list", "reference-printer", "barcode-printer", or null.
const view = { menu: null, fold: { reference: false, barcode: false } };

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

// --- head and banner ---------------------------------------------------------

function head(s) {
  const session = s.session.name
    ? `<span class="code">${esc(s.session.name)}</span><span class="page-meta">${esc(s.session.meta)}</span>`
    : "";
  return `<div class="page-head"><span class="page-title">Tools</span>${session}</div>`;
}

function banner() {
  return `<section class="banner neutral" data-banner="no-session">
    ${svg(GLYPH.folder, "glyph")}
    <div class="banner-body">
      <span class="banner-title">Open a session to use these tools</span>
      <span class="banner-text">Both tools read the session's files and save into its folder. Print modes can be set now; they're saved on this PC.</span>
    </div>
    <button class="btn primary" type="button" data-act="new-session" data-key="new-session">New session</button>
    <button class="btn secondary" type="button" data-act="open-recent" data-key="open-recent">Open recent</button>
  </section>`;
}

// --- rows --------------------------------------------------------------------

function cardHead(tool) {
  return `<div class="tool-head">
    <span class="tool-title">${TOOLS[tool].title}</span>
    <span class="tool-text">${TOOLS[tool].text}</span>
  </div>`;
}

function row(name, label, body) {
  return `<div class="form-row" data-row="${name}"><span class="form-label">${label}</span><div class="tool-control">${body}</div></div>`;
}

function problemBlock(kind, problem, disabled) {
  return `<div class="banner danger" role="alert">
    ${svg(GLYPH.alert, "glyph")}
    <div class="banner-body">
      <span class="problem-title">${esc(problem.title)}</span>
      <span class="banner-text">${esc(problem.text)}</span>
      <button class="btn link" type="button" data-act="choose" data-kind="${kind}" data-key="${kind}-again"${off(disabled)}>${FILES[kind].again}</button>
    </div>
  </div>`;
}

function fileRow(kind, picked, disabled) {
  const file = FILES[kind];
  if (!picked.name) {
    return row(
      kind,
      file.label,
      `<div class="tool-line"><button class="btn secondary" type="button" data-act="choose" data-kind="${kind}" data-key="${kind}-choose"${off(disabled)}>${file.choose}</button></div>`,
    );
  }
  const bad = Boolean(picked.problem && picked.problem.title);
  return row(
    kind,
    file.label,
    `<div class="tool-line${bad ? " bad" : ""}">
      ${svg(GLYPH.file, "glyph")}
      <span class="file-name" title="${esc(picked.name)}">${esc(picked.name)}</span>
      <span class="file-meta">${esc(picked.meta)}</span>
      <span class="spacer"></span>
      <button class="btn secondary compact" type="button" data-act="clear" data-kind="${kind}" data-key="${kind}-clear"${off(disabled)}>Replace</button>
    </div>${bad ? problemBlock(kind, picked.problem, disabled) : ""}`,
  );
}

function folderText(folder) {
  return `<span class="path${folder.muted ? " muted" : ""}" title="${esc(folder.title)}">${esc(folder.text)}</span>`;
}

function option(tool, name, label, checked, disabled) {
  return `<label class="option${disabled ? " disabled" : ""}"><input type="checkbox" data-opt="${name}" data-tool="${tool}" data-key="${tool}-${name}"${checked ? " checked" : ""}${off(disabled)}>${label}</label>`;
}

function menuItem(act, tool, value, label, hint, checked, key) {
  const meta = hint ? `<span class="menu-hint mono">${esc(hint)}</span>` : "";
  return `<button class="menu-item" type="button" role="menuitemradio" aria-checked="${Boolean(checked)}" data-act="${act}" data-tool="${tool}" data-value="${esc(value)}" data-key="${key}">${svg(GLYPH.check, "check")}<span class="menu-label">${esc(label)}</span>${meta}</button>`;
}

function listRow(s) {
  const card = s.barcode;
  const open = view.menu === "barcode-list";
  const disabled = card.quiet || card.locked || !card.lists.length;
  const shown = card.list.name
    ? `<span class="select-value">${esc(card.list.name)}</span><span class="select-meta">${esc(card.list.meta)}</span>`
    : `<span class="select-value placeholder">${esc(card.list.placeholder)}</span>`;
  const items = card.lists
    .map((entry, n) =>
      menuItem("list", "barcode", entry.name, entry.name, entry.meta, entry.checked, `barcode-list-item-${n}`),
    )
    .join("");
  const menu = open
    ? `<div class="menu" role="menu"><div class="menu-group">Packing lists in ${esc(s.session.name)}</div>${items}</div>`
    : "";
  return row(
    "list",
    "Packing list",
    `<div class="tool-line">
      <div class="menu-anchor list-anchor">
        <button class="select" type="button" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="barcode-list" data-key="barcode-list"${off(disabled)}>${shown}${svg(GLYPH.chevron, "glyph")}</button>
        ${menu}
      </div>
      <button class="btn secondary" type="button" data-act="refresh" data-key="barcode-refresh" title="Refresh packing lists"${off(card.quiet || card.locked)}>${svg(GLYPH.refresh, "glyph")}Refresh</button>
    </div>`,
  );
}

// --- print mode --------------------------------------------------------------

function size(value) {
  return Number(value) > 0 ? String(value) : "";
}

function fold(tool, card) {
  const setup = card.print.setup;
  if (!setup.summary) return "";
  const open = view.fold[tool];
  const locked = card.locked;
  const turned = setup.rotate ? " checked" : "";
  const inverted = setup.invert ? " checked" : "";
  const body = open
    ? `<div class="fold-body">
        <label class="fold-label" for="${tool}-target">Target</label>
        <input id="${tool}-target" class="field" type="text" value="${esc(setup.target)}" placeholder="Printer name, or \\\\server\\printer" data-print="target" data-tool="${tool}" data-key="${tool}-target"${off(locked)}>
        <span class="fold-label">Label size</span>
        <div class="size">
          <input class="field size-field" type="number" min="0" max="500" step="0.1" value="${size(setup.width)}" placeholder="PDF" title="${esc(setup.size_hint)}" aria-label="Label width in mm" data-print="width" data-tool="${tool}" data-key="${tool}-width"${off(locked)}>
          <span>×</span>
          <input class="field size-field" type="number" min="0" max="500" step="0.1" value="${size(setup.height)}" placeholder="PDF" title="${esc(setup.size_hint)}" aria-label="Label height in mm" data-print="height" data-tool="${tool}" data-key="${tool}-height"${off(locked)}>
          <span>mm</span>
        </div>
        <span></span>
        <label class="option${locked ? " disabled" : ""}"><input type="checkbox" data-print="rotate" data-tool="${tool}" data-key="${tool}-rotate"${turned}${off(locked)}>Rotate 90°</label>
        <span></span>
        <label class="option${locked ? " disabled" : ""}" title="Tick if labels print white on black."><input type="checkbox" data-print="invert" data-tool="${tool}" data-key="${tool}-invert"${inverted}${off(locked)}>Invert colours</label>
      </div>`
    : "";
  return `<button class="fold" type="button" aria-expanded="${open}" data-act="fold" data-tool="${tool}" data-key="${tool}-fold">${svg(open ? GLYPH.chevron : GLYPH.chevronRight, "glyph")}<span class="fold-title">Label setup</span><span class="fold-summary">${esc(setup.summary)}</span></button>${body}`;
}

function printRow(tool, card) {
  const print = card.print;
  const locked = card.locked;
  const menuName = `${tool}-printer`;
  const open = view.menu === menuName;
  const segments = MODES.map((mode) => {
    const on = print.mode === mode.value;
    return `<button class="segment" type="button" role="radio" aria-checked="${on}" tabindex="${on ? 0 : -1}" data-act="mode" data-tool="${tool}" data-value="${mode.value}" data-key="${tool}-mode-${mode.value}"${off(locked)}>${mode.label}</button>`;
  }).join("");
  const items = print.printers
    .map((entry, n) =>
      menuItem("printer", tool, entry.value, entry.label, "", entry.checked, `${menuName}-item-${n}`),
    )
    .join("");
  const menu = open ? `<div class="menu" role="menu">${items}</div>` : "";
  return row(
    "print",
    "Print mode",
    `<div class="mode-line">
      <div class="segmented" role="radiogroup" aria-label="Print mode">${segments}</div>
      <div class="menu-anchor printer-anchor">
        <button class="select" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="Printer" data-act="menu" data-menu="${menuName}" data-key="${menuName}"${off(locked)}>${svg(GLYPH.printer, "glyph")}<span class="select-value${print.printer.placeholder ? " placeholder" : ""}">${esc(print.printer.label)}</span>${svg(GLYPH.chevron, "glyph")}</button>
        ${menu}
      </div>
    </div>
    <span class="mode-help${print.help_tone === "danger" ? " danger" : ""}">${esc(print.help)}</span>
    ${fold(tool, card)}`,
  );
}

// --- footer ------------------------------------------------------------------

function printButton(tool, what, button) {
  return `<button class="btn secondary" type="button" data-act="print" data-tool="${tool}" data-what="${what}" data-key="${tool}-print-${what}" title="${esc(button.title)}"${off(!button.enabled)}>${esc(button.label)}</button>`;
}

function foot(tool, card) {
  const run = card.run;
  if (run.label) {
    const count = run.count ? ` — <span class="mono run-count">${esc(run.count)}</span>` : "";
    const bar = run.bar
      ? `<div class="run-track"><div class="run-fill" style="width: ${Number(run.percent)}%"></div></div>`
      : "";
    const cancel = run.cancel && run.cancel.label
      ? `<button class="btn secondary" type="button" data-act="cancel" data-key="${tool}-cancel" title="${esc(run.cancel.title)}"${off(!run.cancel.enabled)}>${esc(run.cancel.label)}</button>`
      : "";
    return `<div class="tool-foot" data-running="true">
      <div class="run"><span class="run-label">${esc(run.label)}${count}</span>${bar}</div>
      ${cancel}
    </div>`;
  }
  const qr = card.qr_button && card.qr_button.label ? printButton(tool, "qr", card.qr_button) : "";
  return `<div class="tool-foot">
    <span class="tool-reason${card.tone ? ` ${esc(card.tone)}` : ""}">${esc(card.reason)}</span>
    ${qr}
    ${printButton(tool, "labels", card.print_button)}
    <button class="btn primary" type="button" data-act="run" data-tool="${tool}" data-key="${tool}-run"${off(!card.can_run)}>${TOOLS[tool].action}</button>
  </div>`;
}

// --- the two cards -----------------------------------------------------------

function referenceCard(s) {
  const card = s.reference;
  const disabled = card.quiet || card.locked;
  return `<section class="card tool-card" data-tool="reference" aria-label="${TOOLS.reference.title}">
    ${cardHead("reference")}
    ${fileRow("pdf", card.pdf, disabled)}
    ${fileRow("csv", card.csv, disabled)}
    ${row(
      "folder",
      "Output folder",
      `<div class="tool-line">
        ${folderText(card.folder)}
        <span class="spacer"></span>
        <button class="btn secondary" type="button" data-act="folder" data-key="reference-folder"${off(disabled)}>Change…</button>
      </div>
      ${option("reference", "open_pdf", "Open the PDF when it's ready", card.open_pdf, disabled)}`,
    )}
    ${printRow("reference", card)}
    ${foot("reference", card)}
  </section>`;
}

function barcodeCard(s) {
  const card = s.barcode;
  const disabled = card.quiet || card.locked;
  return `<section class="card tool-card" data-tool="barcode" aria-label="${TOOLS.barcode.title}">
    ${cardHead("barcode")}
    ${listRow(s)}
    ${row(
      "folder",
      "Output folder",
      `<div class="tool-line">${folderText(card.folder)}</div>
      <div class="options">
        ${option("barcode", "qr", "Add QR labels (order number)", card.qr, disabled)}
        ${option("barcode", "open_pdf", "Open the PDF when it's ready", card.open_pdf, disabled)}
      </div>`,
    )}
    ${printRow("barcode", card)}
    ${foot("barcode", card)}
  </section>`;
}

// --- render ------------------------------------------------------------------

// A menu whose select a new state disabled must not stay open over it.
function menuStillOpens(s) {
  if (view.menu === "barcode-list") {
    return !s.barcode.quiet && !s.barcode.locked && s.barcode.lists.length > 0;
  }
  if (view.menu === "reference-printer") return !s.reference.locked;
  if (view.menu === "barcode-printer") return !s.barcode.locked;
  return false;
}

function render() {
  const s = page.state;
  if (!s || !s.reference) return;
  if (view.menu !== null && !menuStillOpens(s)) view.menu = null;
  // The whole page is redrawn, so the control that had focus is found again
  // by its key, and a field being typed in keeps what was typed: a state can
  // arrive mid-edit, from the other card's run.
  const active = document.activeElement;
  const key = active && active.dataset ? active.dataset.key : null;
  const typing = key && (active.type === "text" || active.type === "number");
  const typed = typing ? active.value : null;
  const caret = typing && active.type === "text" ? [active.selectionStart, active.selectionEnd] : null;
  els.tools.innerHTML =
    head(s) +
    (s.banner ? banner() : "") +
    `<div class="tool-cards">${referenceCard(s)}${barcodeCard(s)}</div>`;
  if (key) {
    const again = els.tools.querySelector(`[data-key="${key}"]`);
    if (again && !again.disabled) {
      if (typed !== null) again.value = typed;
      again.focus();
      if (caret) again.setSelectionRange(caret[0], caret[1]);
    }
  }
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

function focusKey(key) {
  const el = els.tools.querySelector(`[data-key="${key}"]`);
  if (el && !el.disabled) el.focus();
}

// --- input -------------------------------------------------------------------

function onClick(event) {
  const el = event.target.closest("[data-act]");
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const data = el.dataset;
  switch (data.act) {
    case "choose": bridge.chooseFile(data.kind); break;
    case "clear": bridge.clearFile(data.kind); break;
    case "folder": bridge.changeFolder(); break;
    case "mode": bridge.setPrint(data.tool, "mode", data.value); break;
    case "menu":
      view.menu = view.menu === data.menu ? null : data.menu;
      render();
      focusKey(data.menu);
      break;
    case "printer": {
      const menu = view.menu;
      view.menu = null;
      bridge.setPrint(data.tool, "printer", data.value);
      render();
      focusKey(menu);
      break;
    }
    case "list":
      view.menu = null;
      bridge.chooseList(data.value);
      render();
      focusKey("barcode-list");
      break;
    case "refresh": bridge.refreshLists(); break;
    case "fold":
      view.fold[data.tool] = !view.fold[data.tool];
      render();
      focusKey(`${data.tool}-fold`);
      break;
    case "run": bridge.run(data.tool); break;
    case "cancel": bridge.cancel(); break;
    case "print": bridge.printLabels(data.tool, data.what); break;
    case "new-session": bridge.newSession(); break;
    case "open-recent": bridge.openRecent(); break;
  }
}

// A checkbox reports at once; a text or number field on change (blur or
// Enter), never per keystroke.
function onChange(event) {
  const el = event.target;
  const bridge = page.bridge;
  if (!bridge || !el.dataset) return;
  const data = el.dataset;
  if (data.opt) {
    bridge.setOption(data.tool, data.opt, el.checked);
    return;
  }
  if (!data.print) return;
  if (el.type === "checkbox") {
    bridge.setPrint(data.tool, data.print, el.checked);
  } else if (el.type === "number") {
    const value = Number(el.value);
    bridge.setPrint(data.tool, data.print, Number.isFinite(value) ? value : 0);
  } else {
    bridge.setPrint(data.tool, data.print, el.value);
  }
}

function closeMenu() {
  const menu = view.menu;
  if (menu === null) return;
  view.menu = null;
  render();
  focusKey(menu);
}

function onKey(event) {
  if (event.key === "Escape" && view.menu !== null) {
    event.preventDefault();
    closeMenu();
    return;
  }
  const vertical = event.key === "ArrowUp" || event.key === "ArrowDown";
  if (vertical && view.menu !== null) {
    // Up and Down walk the open menu, from its select or from an item.
    const items = Array.from(els.tools.querySelectorAll(".menu .menu-item"));
    if (!items.length) return;
    const at = items.indexOf(document.activeElement);
    const step = event.key === "ArrowUp" ? -1 : 1;
    const next = at < 0 ? (step > 0 ? 0 : items.length - 1) : (at + step + items.length) % items.length;
    event.preventDefault();
    items[next].focus();
    return;
  }
  // Left and Right move between the two mode segments; Space and Enter are
  // the button's own.
  const segment = event.target.closest ? event.target.closest(".segment") : null;
  if (!segment || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
  const group = Array.from(segment.parentElement.querySelectorAll(".segment:not(:disabled)"));
  if (group.length < 2) return;
  const step = event.key === "ArrowLeft" ? -1 : 1;
  event.preventDefault();
  group[(group.indexOf(segment) + step + group.length) % group.length].focus();
}

// --- toast (ADR 0007: a web page draws its own) --------------------------------

function raiseToast(text, action) {
  els.toastText.textContent = text;
  els.toastAction.hidden = !action;
  els.toast.hidden = false;
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(dismissToast, action ? TOAST_ACTION_MS : TOAST_MS);
}

function dismissToast() {
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = null;
  els.toast.hidden = true;
}

// --- boot --------------------------------------------------------------------

function bind() {
  els.tools = document.getElementById("tools");
  els.themeVars = document.getElementById("theme-vars");
  els.toast = document.getElementById("toast");
  els.toastText = document.getElementById("toast-text");
  els.toastAction = document.getElementById("toast-action");
  els.toastDismiss = document.getElementById("toast-dismiss");
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");
  els.toastDismiss.addEventListener("click", dismissToast);
  els.toastAction.addEventListener("click", () => {
    if (page.bridge) page.bridge.openFolder();
    dismissToast();
  });
  els.tools.addEventListener("click", onClick);
  els.tools.addEventListener("change", onChange);
  document.addEventListener("keydown", onKey);
  // After the page's own handler: a click anywhere but a menu's anchor closes
  // the open menu.
  document.addEventListener("click", (event) => {
    if (view.menu === null || event.target.closest(".menu-anchor")) return;
    view.menu = null;
    render();
  });
  // A file dropped on the page must not navigate the view. It loads nothing.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => event.preventDefault());
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.tools;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
  bridge.stateChanged.connect(() => { page.state = bridge.state; render(); });
  bridge.toastRaised.connect((text, action) => raiseToast(text, action));
  page.state = bridge.state;
  render();
  window.toolsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
