// The Browse page (phase 4 spec section 5). Python words every fact about a
// session (gui/browse_state.py) and sends the rows as bridge.state. This file
// owns the view state only: the tab, the search text, the checked rows,
// whether archived rows are shown and which popover is open. It filters,
// counts and groups rows it already holds, and reports what the operator asks
// for through the bridge's named slots, always by session name.
//
// ponytail: the list is redrawn whole on every change, with no row windowing.
// A client has tens of sessions and archived ones are hidden by default.
// Window the rows, as results.js does, if a client ever shows thousands.
"use strict";

const TOAST_MS = 4000;
const SKELETON_ROWS = 10;

// Lucide glyphs, each as one path.
const GLYPH = {
  folder: "m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2",
  alert: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01",
  plus: "M5 12h14M12 5v14",
  search: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3",
  searchX: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3M13.5 8.5l-5 5M8.5 8.5l5 5",
  refresh: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5",
  loader: "M21 12a9 9 0 1 1-6.22-8.56",
  chevron: "m6 9 6 6 6-6",
  x: "M18 6 6 18M6 6l12 12",
};

const TABS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "completed", label: "Completed" },
  { key: "abandoned", label: "Abandoned" },
  { key: "archived", label: "Archived" },
];

// The four statuses a person can set, and what each one resolves to.
const STATUS_ITEMS = [
  { status: "active", label: "Active", tone: "info", dot: "half", note: "Shows as Not started, In progress, Paused or Stale from activity" },
  { status: "completed", label: "Completed", tone: "success", dot: "solid", note: "Shows as Incomplete if packing is not finished" },
  { status: "abandoned", label: "Abandoned", tone: "neutral", dot: "solid", note: "Kept on the server. Repeat-order checks ignore it" },
  { status: "archived", label: "Archived", tone: "neutral", dot: "solid", note: "Hidden from All until you choose Show" },
];

// The Needs attention note, in the order it reads.
const REASONS = [
  ["paused", "paused"],
  ["stale", "stale"],
  ["incomplete", "incomplete"],
  ["blocked", "with blocked orders"],
];

const els = {};
const page = { bridge: null, state: { view: "", client: "", rows: [] }, client: "", renders: 0, toastTimer: null };
const view = { tab: "all", query: "", checked: new Set(), showArchived: false, open: null };

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

function sessions(n) {
  return n === 1 ? "1 session" : `${n} sessions`;
}

function badge(tone, dot, label) {
  return `<span class="badge ${esc(tone)}"><span class="badge-dot ${esc(dot)}"></span>${esc(label)}</span>`;
}

// --- what the view state selects ---------------------------------------------

function allRows() {
  return (page.state && page.state.rows) || [];
}

function inTab(row, key) {
  if (key === "all") return row.tab !== "archived" || view.showArchived;
  return row.tab === key;
}

// All never counts archived rows, shown or not: the footer counts those.
function tabCount(key) {
  return allRows().filter((row) => (key === "all" ? row.tab !== "archived" : row.tab === key)).length;
}

function visibleRows() {
  const q = view.query;
  return allRows().filter(
    (row) =>
      inTab(row, view.tab) &&
      (!q || row.name.toLowerCase().includes(q) || row.comment.toLowerCase().includes(q)),
  );
}

// A row hidden by the tab or the search is never acted on.
function checkedNames(visible) {
  return visible.filter((row) => view.checked.has(row.name)).map((row) => row.name);
}

function tabLabel() {
  return TABS.find((tab) => tab.key === view.tab).label;
}

// --- the three panels --------------------------------------------------------

function panel(s) {
  if (s.view === "failed") {
    return `<div class="state">
      ${svg(GLYPH.alert, "state-glyph")}
      <p class="state-title">Sessions didn't load</p>
      <p class="state-text">Details are in Logs.</p>
      <button class="btn secondary" type="button" data-act="refresh" data-key="try-again">Try again</button>
    </div>`;
  }
  if (s.view === "empty") {
    return `<div class="state">
      ${svg(GLYPH.folder, "state-glyph")}
      <p class="state-title">No sessions yet</p>
      <p class="state-text">CLIENT_${esc(s.client)} has no sessions on the file server.</p>
      <button class="btn primary" type="button" data-act="new-session" data-key="new-session">${svg(GLYPH.plus, "glyph")}New session</button>
    </div>`;
  }
  return `<div class="state">
    ${svg(GLYPH.folder, "state-glyph")}
    <p class="state-title">Choose a client</p>
    <p class="state-text">Pick a client in the bar above to see its sessions.</p>
  </div>`;
}

// --- toolbar -----------------------------------------------------------------

function renderTabs(loading) {
  els.tabs.innerHTML = TABS.map((tab) => {
    const on = tab.key === view.tab;
    const count = loading ? "–" : tabCount(tab.key);
    return `<button class="tab" type="button" role="tab" aria-selected="${on}" tabindex="${on ? 0 : -1}" data-tab="${tab.key}" data-key="tab-${tab.key}">${tab.label}<span class="segment-count">${count}</span></button>`;
  }).join("");
}

function countLabel(loading, visible) {
  if (loading) return "Reading…";
  const inThisTab = allRows().filter((row) => inTab(row, view.tab)).length;
  return view.query ? `${visible.length} of ${sessions(inThisTab)}` : sessions(inThisTab);
}

// --- header row and selection bar --------------------------------------------

function renderBar(loading, visible) {
  const n = checkedNames(visible).length;
  els.head.hidden = n > 0;
  els.selbar.hidden = n === 0;
  if (n === 0) {
    closePopover();
    els.headCheck.checked = false;
    els.headCheck.disabled = loading || visible.length === 0;
    return;
  }
  els.selCheck.checked = n === visible.length;
  els.selCheck.indeterminate = n < visible.length;
  els.selCount.textContent = `${n} selected`;
  els.selOpen.hidden = n !== 1;
  els.selExport.hidden = n < 2;
}

// --- the list ----------------------------------------------------------------

function num(value, alert) {
  if (!value) return `<span class="cell-num none">—</span>`;
  return `<span class="cell-num${alert ? " alert" : ""}">${esc(value)}</span>`;
}

function rowHtml(row) {
  const on = view.checked.has(row.name);
  const name = esc(row.name);
  const pack = row.pack
    ? `<span class="pack-text">${esc(row.pack)}</span><span class="pack-track"><span class="pack-fill ${esc(row.pack_tone)}" style="width:${Number(row.pack_pct) || 0}%"></span></span>`
    : `<span class="pack-text none">—</span>`;
  const comment = row.comment
    ? `<span class="cell-comment" title="${esc(row.comment)}">${esc(row.comment)}</span>`
    : `<span class="cell-comment none">—</span>`;
  return `<div class="row grid${on ? " checked" : ""}" data-row="${name}">
    <span class="cell-check"><input type="checkbox" data-key="row-${name}" aria-label="Select ${name}"${on ? " checked" : ""}></span>
    <span class="cell-name">${name}</span>
    <span class="cell-age${row.age_warn ? " warn" : ""}" title="${esc(row.age_title)}">${esc(row.age)}</span>
    <span>${badge(row.tone, row.dot, row.label)}</span>
    ${num(row.orders)}${num(row.items)}${num(row.blocked, row.blocked_alert)}
    <span class="cell-pack" title="${esc(row.pack_title)}">${pack}</span>
    ${comment}
  </div>`;
}

function groupHtml(label, rows, note, attention) {
  return `<div class="group-head" data-group="${attention ? "attention" : "rest"}">
    ${attention ? `<span class="group-dot"></span>` : ""}
    <span class="group-label">${label}</span>
    <span class="group-count">${rows.length}</span>
    <span class="group-note">${note}</span>
  </div>${rows.map(rowHtml).join("")}`;
}

function attentionNote(rows) {
  return REASONS.map(([why, words]) => {
    const n = rows.filter((row) => row.why === why).length;
    return n ? `${n} ${words}` : "";
  })
    .filter(Boolean)
    .join(" · ");
}

function skeleton() {
  const bar = (width) => `<span><span class="sk" style="width:${width}px"></span></span>`;
  let rows = "";
  for (let i = 0; i < SKELETON_ROWS; i += 1) {
    const mid = 64 + (i % 3) * 8;
    rows += `<div class="sk-row grid"><span></span>${bar(96)}${bar(28)}${bar(mid)}${bar(28)}${bar(28)}${bar(28)}${bar(mid)}${bar(60 + ((i * 37) % 120))}</div>`;
  }
  return `<div class="loading-line">${svg(GLYPH.loader, "glyph")}<span>Reading sessions from the server…</span></div>${rows}`;
}

// A panel names its cause and offers the act that resolves it.
function noRows() {
  if (view.query) {
    return `<div class="state">
      ${svg(GLYPH.searchX, "state-glyph")}
      <p class="state-title">No sessions match</p>
      <p class="state-text">Nothing in ${tabLabel()} has “${esc(els.search.value.trim())}” in its name or comment.</p>
      <button class="btn secondary" type="button" data-act="clear-search" data-key="clear-search">Clear search</button>
    </div>`;
  }
  if (view.tab === "all") {
    return `<div class="state">
      ${svg(GLYPH.folder, "state-glyph")}
      <p class="state-title">Nothing in All</p>
      <p class="state-text">Every session of this client is archived.</p>
      <button class="btn secondary" type="button" data-act="toggle-archived" data-key="show-archived">Show archived</button>
    </div>`;
  }
  return `<div class="state">
    ${svg(GLYPH.folder, "state-glyph")}
    <p class="state-title">Nothing in ${tabLabel()}</p>
    <p class="state-text">No session of this client is ${tabLabel().toLowerCase()}.</p>
  </div>`;
}

function renderList(loading, visible) {
  if (loading) {
    els.list.innerHTML = skeleton();
    return;
  }
  if (!visible.length) {
    els.list.innerHTML = noRows();
    return;
  }
  const attention = visible.filter((row) => row.why);
  const rest = visible.filter((row) => !row.why);
  let html = "";
  if (attention.length) html += groupHtml("Needs attention", attention, attentionNote(attention), true);
  if (rest.length) html += groupHtml(attention.length ? "Everything else" : tabLabel(), rest, "", false);
  els.list.innerHTML = html;
}

function renderFooter(loading) {
  const archived = allRows().filter((row) => row.tab === "archived").length;
  const line =
    view.tab === "all" && archived > 0 && !loading
      ? `<span id="archived-count">${archived} archived${view.showArchived ? " shown" : ""}</span><span>·</span><button class="btn link" type="button" data-act="toggle-archived" data-key="toggle-archived">${view.showArchived ? "Hide" : "Show"}</button>`
      : "";
  els.footer.innerHTML = `${line}<span class="spacer"></span><span>Double-click a session to open it</span>`;
}

// --- render ------------------------------------------------------------------

function render() {
  const s = page.state || {};
  const active = document.activeElement;
  const key = active && active.dataset ? active.dataset.key : "";
  const isCard = s.view === "list" || s.view === "loading";

  els.browse.dataset.view = s.view || "";
  els.panel.hidden = isCard || !s.view;
  els.card.hidden = !isCard;
  if (isCard) {
    const loading = s.view === "loading";
    const visible = loading ? [] : visibleRows();
    renderTabs(loading);
    els.count.textContent = countLabel(loading, visible);
    els.refresh.disabled = loading;
    renderBar(loading, visible);
    renderList(loading, visible);
    renderFooter(loading);
  } else {
    closePopover();
    els.panel.innerHTML = s.view ? panel(s) : "";
  }

  // Redrawing replaces the element that had focus; hand focus to its twin.
  if (key && !document.contains(active)) {
    const again = document.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (again && !again.disabled) again.focus();
  }
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// A new state from Python. Session names repeat between clients (they are
// dates), so another client's rows never inherit this one's view state.
function onState() {
  const s = page.state || {};
  if ((s.client || "") !== page.client) {
    page.client = s.client || "";
    view.tab = "all";
    view.query = "";
    view.showArchived = false;
    els.search.value = "";
    uncheckAll();
  } else if (s.view === "loading") {
    uncheckAll();
  }
  render();
}

function uncheckAll() {
  view.checked.clear();
  closePopover();
}

// --- menu and popover --------------------------------------------------------

function syncPopover() {
  els.statusMenu.hidden = view.open !== "status";
  els.commentPop.hidden = view.open !== "comment";
  els.statusButton.setAttribute("aria-expanded", String(view.open === "status"));
  els.commentButton.setAttribute("aria-expanded", String(view.open === "comment"));
}

function closePopover() {
  if (view.open === null) return;
  view.open = null;
  syncPopover();
}

function namesList(names) {
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 2).join(", ")} and ${names.length - 2} more`;
}

function openPopover(which) {
  const names = checkedNames(visibleRows());
  if (!names.length) return;
  const what = names.length === 1 ? names[0] : `${names.length} sessions`;
  view.open = which;
  if (which === "status") {
    els.statusTitle.textContent = `Set status for ${what}`;
  } else {
    const row = allRows().find((r) => r.name === names[0]);
    els.commentTitle.textContent = `Comment on ${what}`;
    els.commentText.value = names.length === 1 && row ? row.comment : "";
    els.commentNote.textContent =
      names.length === 1 ? "Shown in the Comment column." : `Replaces the comment on ${namesList(names)}.`;
  }
  syncPopover();
  if (which === "status") els.statusMenu.querySelector(".status-item").focus();
  else els.commentText.focus();
}

function togglePopover(which) {
  if (view.open === which) closePopover();
  else openPopover(which);
}

function saveComment() {
  const names = checkedNames(visibleRows());
  const text = els.commentText.value.trim();
  closePopover();
  if (names.length && page.bridge) page.bridge.setComment(names, text);
}

// --- input -------------------------------------------------------------------

function chooseTab(key) {
  view.tab = key;
  uncheckAll();
  render();
}

function onTabsKey(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const index = TABS.findIndex((tab) => tab.key === view.tab);
  const next = TABS[(index + (event.key === "ArrowLeft" ? -1 : 1) + TABS.length) % TABS.length];
  event.preventDefault();
  chooseTab(next.key);
  els.tabs.querySelector(`[data-tab="${next.key}"]`).focus();
}

function onAct(event) {
  const el = event.target.closest("[data-act]");
  if (!el || el.disabled) return;
  switch (el.dataset.act) {
    case "refresh":
      if (page.bridge) page.bridge.refresh();
      break;
    case "new-session":
      if (page.bridge) page.bridge.newSession();
      break;
    case "clear-search":
      els.search.value = "";
      view.query = "";
      render();
      els.search.focus();
      break;
    case "toggle-archived":
      view.showArchived = !view.showArchived;
      uncheckAll();
      render();
      break;
  }
}

function onListClick(event) {
  const row = event.target.closest(".row");
  if (!row) return;
  const name = row.dataset.row;
  if (view.checked.has(name)) view.checked.delete(name);
  else view.checked.add(name);
  render();
}

function onListDoubleClick(event) {
  const row = event.target.closest(".row");
  if (row && page.bridge) page.bridge.openSession(row.dataset.row);
}

// Up and Down walk the rows' checkboxes; Enter opens. Space is the checkbox's own.
function onListKey(event) {
  const row = event.target.closest(".row");
  if (!row) return;
  if (event.key === "Enter") {
    event.preventDefault();
    if (page.bridge) page.bridge.openSession(row.dataset.row);
    return;
  }
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
  const boxes = Array.from(els.list.querySelectorAll(".row input"));
  const next = boxes[boxes.indexOf(event.target) + (event.key === "ArrowUp" ? -1 : 1)];
  event.preventDefault();
  if (next) next.focus();
}

function onHeadCheck() {
  const visible = visibleRows();
  const every = visible.length > 0 && visible.every((row) => view.checked.has(row.name));
  if (every) view.checked.clear();
  else visible.forEach((row) => view.checked.add(row.name));
  render();
}

function onStatusChoice(event) {
  const item = event.target.closest("[data-status]");
  if (!item) return;
  const names = checkedNames(visibleRows());
  closePopover();
  if (names.length && page.bridge) page.bridge.setStatus(names, item.dataset.status);
}

// --- toast (ADR 0007: a web page draws its own) --------------------------------

function raiseToast(text, undoable) {
  els.toastText.textContent = text;
  els.toastUndo.hidden = !undoable;
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
  const ids = {
    browse: "browse", panel: "panel", card: "card", tabs: "tabs", searchBox: "search-box",
    search: "search", count: "count", refresh: "refresh", head: "head", headCheck: "head-check",
    selbar: "selbar", selCheck: "sel-check", selCount: "sel-count", selOpen: "sel-open",
    selExport: "sel-export", statusButton: "status-button", statusMenu: "status-menu",
    commentButton: "comment-button", commentPop: "comment-pop", commentTitle: "comment-title",
    commentText: "comment-text", commentNote: "comment-note", commentCancel: "comment-cancel",
    commentSave: "comment-save", list: "list", footer: "footer", themeVars: "theme-vars",
    toast: "toast", toastText: "toast-text", toastUndo: "toast-undo", toastDismiss: "toast-dismiss",
  };
  for (const name of Object.keys(ids)) els[name] = document.getElementById(ids[name]);

  // The fixed parts of the page: glyphs, and the Status menu's four choices.
  els.searchBox.insertAdjacentHTML("afterbegin", svg(GLYPH.search, "glyph"));
  els.refresh.innerHTML = `${svg(GLYPH.refresh, "glyph")}Refresh`;
  els.statusButton.innerHTML = `Status${svg(GLYPH.chevron, "glyph")}`;
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");
  els.statusMenu.innerHTML =
    `<div id="status-title" class="menu-group"></div>` +
    STATUS_ITEMS.map(
      (item) =>
        `<button class="status-item" type="button" role="menuitem" data-status="${item.status}">${badge(item.tone, item.dot, item.label)}<span class="status-note">${item.note}</span></button>`,
    ).join("");
  els.statusTitle = document.getElementById("status-title");

  els.tabs.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) chooseTab(tab.dataset.tab);
  });
  els.tabs.addEventListener("keydown", onTabsKey);
  els.search.addEventListener("input", () => {
    view.query = els.search.value.trim().toLowerCase();
    uncheckAll();
    render();
  });
  els.refresh.addEventListener("click", () => page.bridge && page.bridge.refresh());
  els.browse.addEventListener("click", onAct);
  els.headCheck.addEventListener("click", onHeadCheck);
  els.selCheck.addEventListener("click", () => {
    uncheckAll();
    render();
  });
  els.selOpen.addEventListener("click", () => {
    const names = checkedNames(visibleRows());
    if (names.length === 1 && page.bridge) page.bridge.openSession(names[0]);
  });
  els.selExport.addEventListener("click", () => {
    const names = checkedNames(visibleRows());
    if (names.length >= 2 && page.bridge) page.bridge.exportCombined(names);
  });
  els.statusButton.addEventListener("click", () => togglePopover("status"));
  els.commentButton.addEventListener("click", () => togglePopover("comment"));
  els.statusMenu.addEventListener("click", onStatusChoice);
  els.commentCancel.addEventListener("click", closePopover);
  els.commentSave.addEventListener("click", saveComment);
  els.commentText.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.ctrlKey) {
      event.preventDefault();
      saveComment();
    }
  });
  els.list.addEventListener("click", onListClick);
  els.list.addEventListener("dblclick", onListDoubleClick);
  els.list.addEventListener("keydown", onListKey);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || view.open === null) return;
    const button = view.open === "status" ? els.statusButton : els.commentButton;
    closePopover();
    button.focus();
  });
  document.addEventListener("mousedown", (event) => {
    if (view.open !== null && !event.target.closest(".menu-anchor")) closePopover();
  });
  els.toastUndo.addEventListener("click", () => {
    dismissToast();
    if (page.bridge) page.bridge.undo();
  });
  els.toastDismiss.addEventListener("click", dismissToast);
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.browse;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
  bridge.stateChanged.connect(() => { page.state = bridge.state; onState(); });
  bridge.toastRaised.connect((text, undoable) => raiseToast(text, undoable));
  page.state = bridge.state;
  onState();
  window.browseBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
