// The Logs page (phase 6 spec section 5). Python words every row
// (gui/log_buffer.py) and sends rows in batches as bridge.entriesAdded. This
// file keeps every row it was sent and owns the whole view state: the source,
// the level, the search text, wrap, follow and which rows are open. It
// reports what the operator asks for through the bridge's named slots, always
// by entry id.
//
// A row is built once and stays in the list; a filter change sets `hidden`
// on rows and rebuilds nothing. A log message can hold text from a CSV, so
// nothing from a row goes through innerHTML: textContent only.
//
// ponytail: no row windowing. Measured with 10,000 rows in QtWebEngine: a
// filter change 20 ms, a batch of 200 entries 26 ms. Window the rows, as
// results.js does, if the capacity ever grows tenfold.
"use strict";

const TOAST_MS = 4000;
// How far from its end the list may sit and still count as at its end.
const AT_END_PX = 4;

// Lucide glyphs, each as one path.
const GLYPH = {
  search: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3",
  searchX: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3M13.5 8.5l-5 5M8.5 8.5l5 5",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  right: "m9 18 6-6-6-6",
  down: "m6 9 6 6 6-6",
  x: "M18 6 6 18M6 6l12 12",
};

const STREAMS = [
  { key: "all", label: "All" },
  { key: "Activity", label: "Activity" },
  { key: "Execution", label: "Execution" },
];
const BANDS = [
  { key: "all", label: "All" },
  { key: "info", label: "Info" },
  { key: "warning", label: "Warning" },
  { key: "error", label: "Error" },
];
// A band's badge tone in the kit.
const TONE = { error: "danger", warning: "warning", info: "neutral" };

const els = {};
const page = { bridge: null, capacity: 5000, lastId: -1, renders: 0, toastTimer: null };
const view = { stream: "all", band: "all", typed: "", query: "", wrap: false, follow: true, unseen: 0 };
// Every row the page holds, oldest first: { data, hay, el, block }. `block`
// is the open traceback's element, or null.
const rows = [];
const byId = new Map();
const held = { Activity: 0, Execution: 0 };

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function entries(n) {
  return n === 1 ? "1 entry" : `${n} entries`;
}

// --- building a row ------------------------------------------------------------

function cell(cls, text, title) {
  const span = document.createElement("span");
  span.className = cls;
  span.textContent = text;
  if (title) span.title = title;
  return span;
}

function rowEl(data) {
  const el = document.createElement("div");
  el.className = `row grid ${data.band}`;
  el.dataset.id = String(data.id);
  const chevron = cell("cell-chev", "");
  if (data.traceback) {
    el.classList.add("has-tb");
    el.setAttribute("role", "button");
    el.setAttribute("aria-expanded", "false");
    el.tabIndex = 0;
    chevron.innerHTML = svg(GLYPH.right, "glyph");
  }
  const level = cell("cell-level", "");
  level.appendChild(cell(`badge ${TONE[data.band] || "neutral"}`, data.level));
  el.append(
    chevron,
    cell("cell-time mono", data.time, `${data.date} ${data.time}`),
    level,
    cell("cell-from", data.stream),
    cell("cell-source mono", data.short, data.source),
    cell("cell-message", data.message),
  );
  return el;
}

function blockEl(data) {
  const block = document.createElement("div");
  block.className = "tb";
  const box = document.createElement("div");
  box.className = "tb-box";
  const head = document.createElement("div");
  head.className = "tb-head";
  const copy = document.createElement("button");
  copy.className = "btn secondary compact";
  copy.type = "button";
  copy.textContent = "Copy";
  copy.dataset.copy = String(data.id);
  head.append(cell("tb-title", "Traceback"), cell("mono", data.source), cell("spacer", ""), copy);
  const text = document.createElement("pre");
  text.className = "tb-text mono";
  text.textContent = data.traceback;
  box.append(head, text);
  block.appendChild(box);
  return block;
}

// --- what the view state selects -----------------------------------------------

// Passes the source and the search: what the Level counts count.
function inScope(row) {
  return (
    (view.stream === "all" || row.data.stream === view.stream) &&
    (!view.query || row.hay.includes(view.query))
  );
}

function shown(row) {
  return inScope(row) && (view.band === "all" || row.data.band === view.band);
}

function setHidden(row, hidden) {
  row.el.hidden = hidden;
  if (row.block) row.block.hidden = hidden;
}

function counts() {
  const n = { all: 0, info: 0, warning: 0, error: 0 };
  for (const row of rows) {
    if (!inScope(row)) continue;
    n.all += 1;
    if (row.data.band in n) n[row.data.band] += 1;
  }
  return n;
}

// --- drawing everything but the rows -------------------------------------------

function atEnd() {
  const list = els.list;
  return list.scrollHeight - list.scrollTop - list.clientHeight <= AT_END_PX;
}

function drawSegments(group, chosen, n) {
  for (const button of group.children) {
    const on = button.dataset.key === chosen;
    button.setAttribute("aria-checked", String(on));
    button.tabIndex = on ? 0 : -1;
    const count = button.querySelector(".segment-count");
    if (!count) continue;
    count.textContent = String(n[button.dataset.key]);
    count.classList.toggle("alert", button.dataset.key === "error" && n.error > 0);
  }
}

function drawEmpty(visible) {
  const empty = visible === 0;
  els.list.hidden = empty;
  els.empty.hidden = !empty;
  if (!empty) return;
  const scope = [
    view.band === "all" ? "" : BANDS.find((band) => band.key === view.band).label,
    view.stream === "all" ? "" : view.stream,
  ].filter(Boolean).join(" ");
  let title = "No entries match";
  let text = "";
  if (view.query) {
    text = `Nothing${scope ? ` in ${scope}` : ""} contains “${view.typed}” in its message or source.`;
  } else if (scope) {
    text = `No ${scope} entries yet.`;
  } else {
    title = "No entries yet";
  }
  els.emptyTitle.textContent = title;
  els.emptyText.textContent = text;
  els.emptyText.hidden = !text;
  els.clearSearch.hidden = !view.query;
  els.showAll.hidden = !scope;
}

function draw() {
  const n = counts();
  const visible = n[view.band];
  drawSegments(els.streams, view.stream, n);
  drawSegments(els.bands, view.band, n);
  els.count.textContent =
    visible === rows.length ? entries(rows.length) : `${visible} of ${entries(rows.length)}`;
  els.save.disabled = visible === 0;
  els.card.classList.toggle("one-stream", view.stream !== "all");
  els.list.classList.toggle("wrap", view.wrap);
  drawEmpty(visible);
  els.wrap.checked = view.wrap;
  els.follow.checked = view.follow;
  els.paused.hidden = view.follow || visible === 0;
  els.pausedText.textContent = view.unseen
    ? `${view.unseen} new ${view.unseen === 1 ? "entry" : "entries"} below`
    : "Paused while scrolled up";
  if (view.follow) els.list.scrollTop = els.list.scrollHeight;
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// --- rows arriving -------------------------------------------------------------

// Each stream keeps its newest `capacity` rows, as Python's buffer does.
function evict() {
  for (const stream of Object.keys(held)) {
    let at = 0;
    while (held[stream] > page.capacity) {
      while (rows[at].data.stream !== stream) at += 1;
      const row = rows.splice(at, 1)[0];
      row.el.remove();
      if (row.block) row.block.remove();
      byId.delete(row.data.id);
      held[stream] -= 1;
    }
  }
}

function onEntries(batch) {
  const fragment = document.createDocumentFragment();
  let unseen = 0;
  for (const data of batch) {
    if (data.id <= page.lastId) continue; // start() was answered twice
    page.lastId = data.id;
    const row = {
      data,
      hay: `${data.message} ${data.source}`.toLowerCase(),
      el: rowEl(data),
      block: null,
    };
    if (shown(row)) unseen += 1;
    else row.el.hidden = true;
    rows.push(row);
    byId.set(data.id, row);
    held[data.stream] = (held[data.stream] || 0) + 1;
    fragment.appendChild(row.el);
  }
  els.list.appendChild(fragment);
  evict();
  if (!view.follow) view.unseen += unseen;
  draw();
}

// --- input ---------------------------------------------------------------------

function setFollow(on) {
  view.follow = on;
  view.unseen = 0;
  draw();
}

// Source, Level or the search changed: every row is asked again.
function refilter() {
  for (const row of rows) setHidden(row, !shown(row));
  setFollow(true);
}

function choose(kind, key) {
  view[kind] = key;
  refilter();
}

function setSearch(text) {
  els.search.value = text;
  view.typed = text.trim();
  view.query = view.typed.toLowerCase();
  refilter();
}

function onSegmentClick(event, kind) {
  const button = event.target.closest("[data-key]");
  if (button) choose(kind, button.dataset.key);
}

function onSegmentKey(event, kind, options, group) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const index = options.findIndex((option) => option.key === view[kind]);
  const step = event.key === "ArrowLeft" ? -1 : 1;
  const next = options[(index + step + options.length) % options.length];
  event.preventDefault();
  choose(kind, next.key);
  group.querySelector(`[data-key="${next.key}"]`).focus();
}

function toggle(row) {
  const open = row.block === null;
  if (open) {
    row.block = blockEl(row.data);
    row.el.after(row.block);
  } else {
    row.block.remove();
    row.block = null;
  }
  row.el.classList.toggle("open", open);
  row.el.setAttribute("aria-expanded", String(open));
  row.el.firstChild.innerHTML = svg(open ? GLYPH.down : GLYPH.right, "glyph");
  view.follow = false;
  draw();
}

function onListClick(event) {
  const copy = event.target.closest("[data-copy]");
  if (copy) {
    if (page.bridge) page.bridge.copyTraceback(Number(copy.dataset.copy));
    return;
  }
  const el = event.target.closest(".row.has-tb");
  // A click that ends a drag over the text is a selection, not a toggle.
  if (!el || String(window.getSelection())) return;
  toggle(byId.get(Number(el.dataset.id)));
}

function onListKey(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  if (!event.target.classList.contains("has-tb")) return;
  event.preventDefault();
  toggle(byId.get(Number(event.target.dataset.id)));
}

function onScroll() {
  const end = atEnd();
  if (end === view.follow) return;
  view.follow = end;
  if (end) view.unseen = 0;
  draw();
}

function save() {
  if (!page.bridge) return;
  const ids = rows.filter((row) => !row.el.hidden).map((row) => row.data.id);
  if (ids.length) page.bridge.saveShown(ids);
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

// --- boot ----------------------------------------------------------------------

function segments(options, counted) {
  return options.map((option) => {
    const dot = counted && option.key in TONE && option.key !== "info"
      ? `<span class="seg-dot ${option.key}"></span>`
      : "";
    const count = counted ? `<span class="segment-count">0</span>` : "";
    return `<button class="segment" type="button" role="radio" aria-checked="false" tabindex="-1" data-key="${option.key}">${dot}${option.label}${count}</button>`;
  }).join("");
}

function bind() {
  const ids = {
    card: "card", streams: "streams", bands: "bands", searchBox: "search-box", search: "search",
    count: "count", save: "save", list: "list", empty: "empty", emptyTitle: "empty-title",
    emptyText: "empty-text", clearSearch: "clear-search", showAll: "show-all", wrap: "wrap",
    follow: "follow", paused: "paused", pausedText: "paused-text", jump: "jump",
    themeVars: "theme-vars", toast: "toast", toastText: "toast-text", toastDismiss: "toast-dismiss",
  };
  for (const name of Object.keys(ids)) els[name] = document.getElementById(ids[name]);

  // The fixed parts of the page: the two controls and the glyphs.
  els.streams.innerHTML = segments(STREAMS, false);
  els.bands.innerHTML = segments(BANDS, true);
  els.searchBox.insertAdjacentHTML("afterbegin", svg(GLYPH.search, "glyph"));
  els.save.innerHTML = `${svg(GLYPH.download, "glyph")}Save as text`;
  els.empty.insertAdjacentHTML("afterbegin", svg(GLYPH.searchX, "state-glyph"));
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");

  els.streams.addEventListener("click", (event) => onSegmentClick(event, "stream"));
  els.bands.addEventListener("click", (event) => onSegmentClick(event, "band"));
  els.streams.addEventListener("keydown", (event) => onSegmentKey(event, "stream", STREAMS, els.streams));
  els.bands.addEventListener("keydown", (event) => onSegmentKey(event, "band", BANDS, els.bands));
  els.search.addEventListener("input", () => setSearch(els.search.value));
  els.save.addEventListener("click", save);
  els.list.addEventListener("click", onListClick);
  els.list.addEventListener("keydown", onListKey);
  els.list.addEventListener("scroll", onScroll);
  els.clearSearch.addEventListener("click", () => setSearch(""));
  els.showAll.addEventListener("click", () => {
    view.stream = "all";
    view.band = "all";
    refilter();
  });
  els.wrap.addEventListener("change", () => {
    view.wrap = els.wrap.checked;
    if (page.bridge) page.bridge.setWrap(view.wrap);
    draw();
  });
  els.follow.addEventListener("change", () => setFollow(els.follow.checked));
  els.jump.addEventListener("click", () => setFollow(true));
  els.toastDismiss.addEventListener("click", dismissToast);
  // A window made smaller leaves the list short of its end, with no scroll event.
  window.addEventListener("resize", () => {
    if (view.follow) els.list.scrollTop = els.list.scrollHeight;
  });
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return;
    event.preventDefault();
    save();
  });
}

bind();
draw();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.logs;
  page.bridge = bridge;
  page.capacity = bridge.capacity;
  view.wrap = bridge.wrap;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => {
    els.themeVars.textContent = bridge.themeCss;
    // Two frames: the first callback runs before this frame is painted.
    requestAnimationFrame(() => requestAnimationFrame(() => bridge.themeApplied()));
  });
  bridge.toastRaised.connect((text) => raiseToast(text));
  bridge.entriesAdded.connect(onEntries);
  draw();
  bridge.start();
  window.logsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
