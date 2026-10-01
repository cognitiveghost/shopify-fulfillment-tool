// The results document (Bundle 12): KPI strip, filter bar and a windowed
// order table over the bridge's `orders` and `summary`. The page owns sort,
// search, filter chips and the selection gesture (ADR 0005). A click moves the
// cursor; checkboxes, Ctrl and Shift build the checked set Python hears (phase 2
// spec section 5.5). Python hears only the
// selection and two commands. Numbers and copy:
// docs/superpowers/specs/2026-09-11-phase9-bundle12-results-doc-design.md
"use strict";

const HEADER_PX = 36;
const ROW_EXTRA_PX = 4; // a results row is the density's row plus this
const OVERSCAN = 4;
const TABLE_MIN_PX = 728;
const PANE_PX = 340;
const DASH = "—";
const FULFILLABLE = "Fulfillable";
const BLOCKED = "Blocked";
const NO_COURIER = "No courier";
const NUMBER = new Intl.NumberFormat("en-US");

// Lucide chevron-down, chevron-up and check. Paths, not a transform: the
// web tier may not rotate anything (ADR 0001).
const CHEVRON_DOWN = "m6 9 6 6 6-6";
const CHEVRON_UP = "m18 15-6-6-6 6";
const CHECK = "M20 6 9 17l-5-5";
// Lucide x, columns-3 and download, each as one path.
const X_MARK = "M18 6 6 18M6 6l12 12";
const COLUMNS = "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM9 3v18M15 3v18";
const DOWNLOAD = "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3";
// Lucide info, as one path: a circle and its two strokes.
const INFO = "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0zM12 16v-4M12 8h.01";

// Widths are the canvas's (W3); a column grows to its widest real value but
// never reflows after that. Only Customer stretches (9.15). The registry
// (columns.js) replaces the fixed list.
const SELECT_COLUMN = { key: "select", title: "", width: 36 };
const SLOT_NARROW_PX = TABLE_MIN_PX + PANE_PX; // below this the pane folds to its rail

const els = {};
const state = {
  bridge: null,
  records: [], // {o, index, key, hay} in frame order
  view: [], // records that pass the filters, in display order
  query: "",
  chips: [], // {kind, value, label}
  sort: null, // {key, dir: 1 | -1}
  selected: new Set(), // order numbers
  anchorKey: null, // the fixed end of a Shift range
  cursorKey: null, // the row the arrow keys move from
  rowH: 32,
  visible: 0,
  columnSettings: { order: null, visible: null, auto_hide_empty: false, extras: [] },
  emptyKeys: new Set(),
  tableCols: [SELECT_COLUMN],
  filler: false,
  narrow: false,
  paneHidden: false,
  paneForced: false,
  columnsOpen: false,
};

// --- formatting -------------------------------------------------------------

function num(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function str(v) {
  return v === null || v === undefined ? "" : String(v);
}
function fmtInt(v) {
  const n = num(v);
  return n === null ? DASH : NUMBER.format(n);
}
function fmtMoney(v) {
  const n = num(v);
  return n === null ? DASH : n.toFixed(2);
}
function fmtCompact(v) {
  const n = num(v);
  if (n === null) return DASH;
  const abs = Math.abs(n);
  // Each threshold sits where rounding would reach the next unit: 999.6 is
  // "1.0k", not "1000".
  if (abs >= 999950) return (n / 1e6).toFixed(1) + "M";
  if (abs >= 999.5) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}
function ageMs(iso) {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : Math.max(0, Date.now() - t);
}
function fmtAge(iso) {
  const ms = ageMs(iso);
  if (ms === null) return DASH;
  const minutes = Math.floor(ms / 60000);
  if (minutes < 60) return minutes + " min";
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return hours + " h";
  return Math.floor(hours / 24) + " d";
}
function plural(n, word) {
  return NUMBER.format(n) + " " + word + (n === 1 ? "" : "s");
}
function isFulfillable(o) {
  return o.Order_Fulfillment_Status === FULFILLABLE;
}
// One source for the Status cell's words: the chip renders it and the column
// registry measures and empties on it.
function statusText(o) {
  return isFulfillable(o) ? FULFILLABLE : BLOCKED;
}
function courierOf(o) {
  return str(o.Shipping_Provider).trim() || NO_COURIER;
}
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function svg(path, cls) {
  return '<svg class="' + cls + '" viewBox="0 0 24 24" aria-hidden="true"><path d="' + path + '"/></svg>';
}

// --- columns, filters, sort -----------------------------------------------

const FLAGS = [
  { value: "repeat", label: "Repeat", test: (o) => o._repeat === true },
  { value: "unknown_sku", label: "Unknown SKU", test: (o) => o.Unknown_SKU === true },
  { value: "low_stock", label: "Low stock", test: (o) => o.Low_Stock === true },
  { value: "lines3", label: "3 or more lines", test: (o) => (num(o.Items) || 0) >= 3 },
];

function chipId(chip) {
  return chip.kind + ":" + chip.value;
}

const CHIP_KEYS = { status: "Status", flag: "Flag", courier: "Courier", tag: "Tag" };

// What the chip says after "is": the menu's label carries a "Courier: " or
// "Tag: " prefix the chip's own key already states.
function chipValue(chip) {
  return chip.kind === "courier" || chip.kind === "tag" ? chip.value : chip.label;
}

// The filters as one sentence, for the no-match state. Flags all have to
// hold; within Status, Courier and Tag the chips are alternatives.
function filterSentence() {
  const parts = [];
  for (const kind of Object.keys(CHIP_KEYS)) {
    const values = state.chips.filter((c) => c.kind === kind).map(chipValue);
    if (values.length) parts.push(CHIP_KEYS[kind] + " is " + values.join(kind === "flag" ? " and " : " or "));
  }
  const query = els.search.value.trim();
  if (query) parts.push("search is “" + query + "”");
  return parts.join(" and ") + ".";
}

function menuGroups() {
  const couriers = new Set();
  const tags = new Set();
  for (const r of state.records) {
    couriers.add(courierOf(r.o));
    for (const t of r.o.Tag_List || []) tags.add(String(t));
  }
  const byName = (a, b) => a.localeCompare(b);
  return [
    ["Status", [
      { kind: "status", value: "fulfillable", label: "Fulfillable" },
      { kind: "status", value: "blocked", label: "Blocked" },
    ]],
    ["Flags", FLAGS.map((f) => ({ kind: "flag", value: f.value, label: f.label }))],
    ["Courier", [...couriers].sort(byName).map((c) => ({ kind: "courier", value: c, label: "Courier: " + c }))],
    ["Tags", [...tags].sort(byName).map((t) => ({ kind: "tag", value: t, label: "Tag: " + t }))],
  ];
}

function toggleChip(chip) {
  const id = chipId(chip);
  if (state.chips.some((c) => chipId(c) === id)) {
    state.chips = state.chips.filter((c) => chipId(c) !== id);
    return;
  }
  // Status is one question with one answer: a second status replaces the first.
  if (chip.kind === "status") state.chips = state.chips.filter((c) => c.kind !== "status");
  state.chips.push(chip);
}

// Search AND every group; within Courier and within Tags, OR.
function matches(record) {
  const o = record.o;
  if (state.query && !record.hay.includes(state.query)) return false;
  const of = (kind) => state.chips.filter((c) => c.kind === kind);
  for (const c of of("status")) {
    if ((c.value === "fulfillable") !== isFulfillable(o)) return false;
  }
  for (const c of of("flag")) {
    if (!FLAGS.find((f) => f.value === c.value).test(o)) return false;
  }
  const couriers = of("courier");
  if (couriers.length && !couriers.some((c) => c.value === courierOf(o))) return false;
  const tags = of("tag");
  const own = (o.Tag_List || []).map(String);
  if (tags.length && !tags.some((c) => own.includes(c.value))) return false;
  return true;
}

// A lot stays findable by its batch and by both expiry forms, the raw
// stock-file string and the parsed date (#285). A Lot_Details cell read back
// from disk as text is searched whole, as the Qt filter did.
function searchText(o) {
  const parts = [o.Order_Number, o.Customer, o.Shipping_Provider].concat(o.Tag_List || []);
  for (const line of o.lines || []) {
    parts.push(line.SKU, line.Product_Name);
    const lots = line.Lot_Details;
    for (const lot of Array.isArray(lots) ? lots : [lots]) {
      if (lot && typeof lot === "object") parts.push(lot.batch, lot.expiry, lot.expiry_dt);
      else parts.push(lot);
    }
  }
  return parts.map(str).join(" ").toLowerCase();
}

// Empty values sort last in both directions; ties keep frame order.
function compare(col, dir) {
  return function (a, b) {
    const x = col.sortValue(a.o);
    const y = col.sortValue(b.o);
    const xEmpty = x === null || x === "";
    const yEmpty = y === null || y === "";
    if (xEmpty || yEmpty) return xEmpty === yEmpty ? a.index - b.index : xEmpty ? 1 : -1;
    const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
    return c === 0 ? a.index - b.index : c * dir;
  };
}

function recompute() {
  let view = state.records.filter(matches);
  if (state.sort) {
    const col = allColumns().find((c) => c.key === state.sort.key);
    view = view.slice().sort(compare(col, state.sort.dir));
  }
  state.view = view;
  // A filter that hides a selected order deselects it, so a bulk action can
  // never reach a row the operator cannot see (ADR 0005).
  const shown = new Set(view.map((r) => r.key));
  state.selected = new Set([...state.selected].filter((k) => shown.has(k)));
  if (state.anchorKey !== null && !shown.has(state.anchorKey)) state.anchorKey = null;
  if (state.cursorKey !== null && !shown.has(state.cursorKey)) state.cursorKey = null;
}

// --- rendering ----------------------------------------------------------------

function render() {
  recompute();
  renderChips();
  renderCount();
  renderExport();
  renderStates();
  renderSlot();
  renderHeader();
  renderSelectionBar();
  layout();
  renderRows();
  reportSelection();
}

function reportSelection() {
  if (!state.bridge) return;
  // The bridge drops a list equal to the last one, so this is safe on every render.
  state.bridge.setSelection(state.view.filter((r) => state.selected.has(r.key)).map((r) => r.key));
}

function kpiCell(key, label, value, sub, dot) {
  const cell = document.createElement("div");
  cell.className = "kpi" + (key === "oldest" ? " kpi-wide" : "");
  cell.dataset.kpi = key;
  const head = document.createElement("div");
  head.className = "kpi-label";
  if (dot) {
    const mark = document.createElement("span");
    mark.className = "kpi-dot " + dot;
    head.appendChild(mark);
  }
  head.appendChild(document.createTextNode(label));
  cell.appendChild(head);
  for (const [cls, text] of [["kpi-value", value], ["kpi-sub", sub]]) {
    const part = document.createElement("div");
    part.className = cls;
    part.textContent = text;
    cell.appendChild(part);
  }
  return cell;
}

// Until a price column is mapped the cell is a hint with the way to fix it.
function valueHint() {
  const cell = document.createElement("div");
  cell.className = "kpi kpi-hint";
  cell.dataset.kpi = "value";
  cell.innerHTML = svg(INFO, "glyph");
  const body = document.createElement("div");
  body.className = "kpi-hint-body";
  const text = document.createElement("span");
  text.textContent = "Order value shows once a price column is mapped.";
  const link = document.createElement("button");
  link.type = "button";
  link.id = "map-columns";
  link.className = "btn link";
  link.textContent = "Map columns";
  link.addEventListener("click", () => state.bridge && state.bridge.openColumnMapping());
  body.append(text, link);
  cell.appendChild(body);
  return cell;
}

function renderKpis() {
  const s = (state.bridge && state.bridge.summary) || {};
  const has = s.orders !== undefined;
  const oldest = has ? s.oldest : null;
  const cells = [
    kpiCell("orders", "Orders", has ? fmtInt(s.orders) : DASH,
      has ? NUMBER.format(s.lines) + " lines · " + NUMBER.format(s.skus) + " SKUs touched" : ""),
    kpiCell("fulfillable", "Fulfillable", has ? fmtInt(s.fulfillable) : DASH,
      has && s.orders ? Math.round((100 * s.fulfillable) / s.orders) + "% of orders" : "", "success"),
    kpiCell("blocked", "Blocked", has ? fmtInt(s.blocked) : DASH,
      has ? NUMBER.format(s.blocked_lines) + " lines, " + NUMBER.format(s.blocked_skus) + " SKUs" : "", "danger"),
    kpiCell("labels", "Labels", has ? fmtInt(s.fulfillable) : DASH,
      has ? (s.labels_by_courier || []).map((p) => p[0] + " " + NUMBER.format(p[1])).join(" · ") : ""),
    kpiCell("oldest", "Oldest waiting", oldest ? fmtAge(oldest.created_at) : DASH,
      oldest ? "order " + oldest.order_number : ""),
    has && s.value_total === null
      ? valueHint()
      : kpiCell("value", "Value ready", has && s.value_ready !== null ? fmtCompact(s.value_ready) : DASH,
        has ? "across " + plural(s.fulfillable, "fulfillable order") : ""),
  ];
  els.kpis.classList.toggle("has-wide", Boolean(oldest));
  els.kpis.replaceChildren(...cells);
}

function renderChips() {
  els.chips.textContent = "";
  for (const chip of state.chips) {
    const box = document.createElement("span");
    box.className = "chip-filter";
    box.dataset.chip = chipId(chip);
    const key = document.createElement("span");
    key.className = "chip-key";
    key.textContent = CHIP_KEYS[chip.kind] + " is";
    const value = document.createElement("span");
    value.className = "chip-value";
    value.textContent = chipValue(chip);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chip-remove";
    remove.title = "Remove filter";
    remove.setAttribute("aria-label", "Remove filter: " + CHIP_KEYS[chip.kind] + " is " + chipValue(chip));
    remove.innerHTML = svg(X_MARK, "glyph");
    remove.addEventListener("click", () => {
      toggleChip(chip);
      render();
    });
    // The text node is the space a reader hears; flex ignores it for layout.
    box.append(key, " ", value, remove);
    els.chips.appendChild(box);
  }
  els.clearAll.hidden = !(state.chips.length || state.query);
}

function renderCount() {
  const total = state.records.length;
  const shown = state.view.length;
  els.count.textContent = shown === total ? plural(total, "order") : NUMBER.format(shown) + " of " + plural(total, "order");
}

function renderExport() {
  const s = (state.bridge && state.bridge.summary) || {};
  const n = s.fulfillable || 0;
  els.exportBtn.replaceChildren();
  els.exportBtn.insertAdjacentHTML("beforeend", svg(DOWNLOAD, "glyph"));
  els.exportBtn.append(s.fulfillable === undefined ? "Export" : "Export " + plural(n, "order"));
  els.exportBtn.disabled = !(state.bridge && state.bridge.exportEnabled && n > 0);
}

function renderStates() {
  const none = state.records.length === 0;
  const noMatch = !none && state.view.length === 0;
  els.empty.hidden = !none;
  els.noMatch.hidden = !noMatch;
  if (noMatch) els.noMatchText.textContent = filterSentence();
  els.table.hidden = none || noMatch;
  els.search.disabled = none;
  els.addFilter.disabled = none;
}

function renderMenu() {
  els.menu.textContent = "";
  for (const [group, items] of menuGroups()) {
    if (!items.length) continue;
    const head = document.createElement("div");
    head.className = "menu-group";
    head.textContent = group;
    els.menu.appendChild(head);
    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "menu-item";
      button.setAttribute("role", "menuitemcheckbox");
      button.setAttribute("aria-checked", String(state.chips.some((c) => chipId(c) === chipId(item))));
      button.innerHTML = svg(CHECK, "check");
      button.appendChild(document.createTextNode(item.label));
      button.addEventListener("click", () => {
        toggleChip(item);
        closeMenu();
        render();
      });
      els.menu.appendChild(button);
    }
  }
}

function openMenu() {
  renderMenu();
  els.menu.hidden = false;
  els.addFilter.setAttribute("aria-expanded", "true");
  const first = els.menu.querySelector(".menu-item");
  if (first) first.focus();
}

function closeMenu() {
  els.menu.hidden = true;
  els.addFilter.setAttribute("aria-expanded", "false");
}

function renderHeader() {
  els.header.textContent = "";
  const picked = state.view.filter((r) => state.selected.has(r.key)).length;
  const all = picked > 0 && picked === state.view.length;
  for (const col of state.tableCols) {
    const cell = document.createElement("div");
    cell.className = "cell head " + col.key + (col.numeric ? " num" : "");
    cell.setAttribute("role", "columnheader");
    if (col.key === "select") {
      const box = document.createElement("input");
      box.type = "checkbox";
      box.tabIndex = -1;
      // With anything checked the box clears; with nothing, it checks all shown.
      box.title = picked > 0 ? "Clear selection" : "Select every order shown";
      box.setAttribute("aria-label", box.title);
      box.checked = all;
      box.indeterminate = picked > 0 && !all;
      box.addEventListener("click", () => selectAll(picked === 0));
      cell.appendChild(box);
    } else {
      const sorted = Boolean(state.sort && state.sort.key === col.key);
      cell.dataset.sort = col.key;
      cell.classList.toggle("sorted", sorted);
      cell.setAttribute("aria-sort", sorted ? (state.sort.dir === 1 ? "ascending" : "descending") : "none");
      const s = (state.bridge && state.bridge.summary) || {};
      if (col.key === "value" && s.orders !== undefined && s.value_total === null) cell.classList.add("unmapped");
      const label = document.createElement("span");
      label.textContent = col.title;
      cell.appendChild(label);
      cell.insertAdjacentHTML("beforeend", svg(sorted && state.sort.dir === 1 ? CHEVRON_UP : CHEVRON_DOWN, "caret"));
      cell.addEventListener("click", () => cycleSort(col.key));
    }
    els.header.appendChild(cell);
  }
  if (state.filler) els.header.insertAdjacentHTML("beforeend", '<div class="cell filler" role="presentation">');
}

function measureColumns() {
  measureColumns.ctx = measureColumns.ctx || document.createElement("canvas").getContext("2d");
  const ctx = measureColumns.ctx;
  const cols = [SELECT_COLUMN].concat(visibleColumns());
  const body = getComputedStyle(document.body);
  const sans = body.fontSize + " " + body.fontFamily;
  const mono = body.fontSize + " " + cssVar("--font-family-mono");
  const caption = cssVar("--type-caption-size") + " " + body.fontFamily;
  const widths = cols.map((col) => {
    if (col.key === "select" || col.stretch) return col.width || 0;
    ctx.font = "700 " + caption;
    let widest = ctx.measureText(col.title).width + 14; // + the sort caret
    if (col.key === "status") {
      widest = Math.max(widest, ctx.measureText(FULFILLABLE).width + 18); // badge padding + edge
    } else {
      ctx.font = (col.key === "order" ? "700 " : "") + (col.mono ? mono : sans);
      for (const r of state.records) widest = Math.max(widest, ctx.measureText(col.text(r.o) || DASH).width);
    }
    const width = Math.max(col.width, Math.ceil(widest + 16));
    return col.maxWidth ? Math.min(col.maxWidth, width) : width;
  });
  const fixed = widths.reduce((a, b) => a + b, 0);
  const stretch = cols.some((c) => c.stretch);
  const customerMin = stretch ? Math.max(140, TABLE_MIN_PX - fixed) : 0;
  const template = cols.map((col, i) => (col.stretch ? "minmax(" + customerMin + "px, 1fr)" : widths[i] + "px"));
  // Customer hidden: an empty track takes the growth, so no column stretches.
  if (!stretch) template.push("minmax(0, 1fr)");
  state.tableCols = cols;
  state.filler = !stretch;
  els.table.style.setProperty("--cols", template.join(" "));
  els.table.style.setProperty("--table-min", fixed + customerMin + "px");
  // The selection bar covers the header from the first named column on, so the
  // select-all box in the header stays reachable while a selection is up.
  els.selectionBar.style.left = widths[0] + "px";
}

// Whole rows only: the table is as tall as the rows that fit, and whatever is
// left over stays page surface below it (9.15).
// ponytail: a horizontal scrollbar (page < 812px) eats into the last row; that
// state is unreachable at 1366, so it is not compensated for.
function layout() {
  const narrow = els.tableArea.clientWidth < SLOT_NARROW_PX;
  if (narrow !== state.narrow) {
    state.narrow = narrow;
    if (!narrow) state.paneForced = false;
    renderSlot();
  }
  state.rowH = (parseFloat(cssVar("--row-height")) || 28) + ROW_EXTRA_PX;
  els.table.style.setProperty("--results-row-height", state.rowH + "px");
  // The selection bar covers the header rather than adding to it, so the row
  // budget is the same whether or not anything is selected.
  const rows = Math.max(0, Math.floor((els.tableArea.clientHeight - HEADER_PX) / state.rowH));
  state.visible = rows;
  els.scroller.style.height = HEADER_PX + rows * state.rowH + "px";
  els.rows.style.height = state.view.length * state.rowH + "px";
  els.table.dataset.visibleRows = String(Math.min(rows, state.view.length));
}

function refreshColumns() {
  const empty = (col) => state.records.every((r) => {
    const t = col.text(r.o);
    return t === "" || t === DASH;
  });
  state.emptyKeys = new Set(allColumns().filter(empty).map((c) => c.key));
  if (state.sort && !visibleColumns().some((c) => c.key === state.sort.key)) state.sort = null;
  measureColumns();
  render();
}

function slotMode() {
  if (!state.records.length) return "none";
  return state.paneHidden || (state.narrow && !state.paneForced) ? "rail" : "pane";
}

function renderSlot() {
  const mode = slotMode();
  els.tableArea.dataset.slot = mode;
  els.pane.hidden = mode !== "pane";
  els.paneStrip.hidden = mode !== "rail";
  // The column manager is a popover of its own; it only needs a session.
  if (mode === "none") state.columnsOpen = false;
  els.columnsPanel.hidden = !state.columnsOpen;
  els.columnsButton.disabled = mode === "none";
  els.columnsButton.setAttribute("aria-expanded", String(state.columnsOpen));
  const count = document.createElement("span");
  count.className = "columns-count mono";
  count.textContent = visibleColumns().length + "/" + allColumns().length;
  els.columnsButton.replaceChildren();
  els.columnsButton.insertAdjacentHTML("beforeend", svg(COLUMNS, "glyph"));
  els.columnsButton.append("Columns ", count);
  if (mode === "pane") renderPane();
  if (state.columnsOpen) renderColumnsPanel();
}

// The bridge hands `columns` over as a QVariantMap, which reaches JS with its keys
// sorted; the local literal keeps insertion order. Compare the values positionally
// so the page's own write does not read back as a change and re-render twice.
function columnsKey(c) {
  return JSON.stringify([c.order || null, c.visible || null, Boolean(c.auto_hide_empty), c.extras || []]);
}

function onColumns() {
  const next = state.bridge.columns || {};
  if (columnsKey(next) === columnsKey(state.columnSettings)) return;
  state.columnSettings = Object.assign({ order: null, visible: null, auto_hide_empty: false, extras: [] }, next);
  refreshColumns();
}

function renderRows() {
  const start = Math.floor(els.scroller.scrollTop / state.rowH);
  const first = Math.max(0, start - OVERSCAN);
  const last = Math.min(state.view.length, start + state.visible + OVERSCAN);
  const frag = document.createDocumentFragment();
  for (let i = first; i < last; i++) frag.appendChild(rowElement(state.view[i], i));
  els.rows.replaceChildren(frag);
}

function rowElement(record, index) {
  const row = document.createElement("div");
  const selected = state.selected.has(record.key);
  const cursor = state.cursorKey === record.key;
  row.className = "row" + (selected ? " selected" : "") + (cursor ? " cursor" : "");
  row.setAttribute("role", "row");
  row.setAttribute("aria-selected", String(selected));
  if (cursor) row.setAttribute("aria-current", "true");
  row.dataset.order = record.key;
  row.dataset.index = String(index);
  row.style.top = index * state.rowH + "px";
  for (const col of state.tableCols) row.appendChild(cellElement(col, record, selected));
  if (state.filler) row.insertAdjacentHTML("beforeend", '<div class="cell filler" role="presentation">');
  return row;
}

function statusBadge(o) {
  const badge = document.createElement("span");
  badge.className = "badge " + (isFulfillable(o) ? "success" : "danger");
  badge.textContent = statusText(o);
  return badge;
}

function cellElement(col, record, selected) {
  const cell = document.createElement("div");
  cell.className = "cell " + col.key + (col.numeric ? " num" : "") + (col.mono ? " mono" : "");
  cell.setAttribute("role", "gridcell");
  if (col.key === "select") {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.tabIndex = -1;
    box.checked = selected;
    box.setAttribute("aria-label", "Select order " + record.key);
    cell.appendChild(box);
  } else if (col.key === "status") {
    cell.appendChild(statusBadge(record.o));
  } else if (col.key === "repeat" && record.o._repeat === true) {
    const badge = document.createElement("span");
    badge.className = "badge info";
    badge.textContent = "Repeat";
    cell.appendChild(badge);
  } else {
    const text = col.text(record.o);
    const missing = text === "" || text === DASH;
    cell.textContent = missing ? DASH : text;
    cell.classList.toggle("missing", missing);
  }
  return cell;
}

// --- interaction ----------------------------------------------------------------

function cycleSort(key) {
  if (!state.sort || state.sort.key !== key) state.sort = { key: key, dir: 1 };
  else if (state.sort.dir === 1) state.sort = { key: key, dir: -1 };
  else state.sort = null;
  render();
}

function selectAll(on) {
  state.selected = on ? new Set(state.view.map((r) => r.key)) : new Set();
  render();
}

function selectRange(fromKey, toKey, additive) {
  const keys = state.view.map((r) => r.key);
  const a = keys.indexOf(fromKey);
  const b = keys.indexOf(toKey);
  if (a < 0 || b < 0) return;
  if (!additive) state.selected = new Set();
  for (let i = Math.min(a, b); i <= Math.max(a, b); i++) state.selected.add(keys[i]);
}

// The cursor is the one order the pane shows. Asking for an order brings a
// pane the operator hid back; a pane folded because the page is narrow stays.
function moveCursor(key) {
  state.cursorKey = key;
  state.anchorKey = key;
  state.paneHidden = false;
}

function onRowClick(event) {
  const row = event.target.closest(".row");
  if (!row || !row.dataset.order) return;
  const key = row.dataset.order;
  const ctrl = event.ctrlKey || event.metaKey;
  if (event.shiftKey && state.anchorKey !== null) {
    selectRange(state.anchorKey, key, ctrl);
    state.cursorKey = key; // the range's moving end, so Shift+arrow carries on from it
  } else if (ctrl || event.target.matches("input[type=checkbox]")) {
    if (state.selected.has(key)) state.selected.delete(key);
    else state.selected.add(key);
    state.anchorKey = key;
  } else {
    moveCursor(key);
  }
  els.table.focus({ preventScroll: true });
  render();
}

function scrollIntoView(index) {
  const top = index * state.rowH;
  const s = els.scroller;
  if (top < s.scrollTop) s.scrollTop = top;
  else if (top + state.rowH > s.scrollTop + state.visible * state.rowH) {
    s.scrollTop = top + state.rowH - state.visible * state.rowH;
  }
}

function onTableKey(event) {
  const ctrl = event.ctrlKey || event.metaKey;
  if (ctrl && event.key.toLowerCase() === "a") {
    event.preventDefault();
    selectAll(true);
    return;
  }
  if (event.key === "Escape") {
    // Innermost first: the checked orders, then the cursor.
    if (state.selected.size) {
      state.selected = new Set();
    } else {
      state.cursorKey = null;
      state.anchorKey = null;
    }
    render();
    return;
  }
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  if (!state.view.length) return;
  const keys = state.view.map((r) => r.key);
  const from = state.cursorKey !== null ? state.cursorKey : state.anchorKey;
  const at = from === null ? -1 : keys.indexOf(from);
  const next = Math.min(keys.length - 1, Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)));
  if (event.shiftKey) {
    // The anchor stays and the range re-spans to the cursor, so reversing shrinks.
    const anchor = state.anchorKey !== null ? state.anchorKey : keys[Math.max(0, at)];
    selectRange(anchor, keys[next], false);
    state.anchorKey = anchor;
    state.cursorKey = keys[next];
    state.paneHidden = false;
  } else {
    moveCursor(keys[next]);
  }
  scrollIntoView(next);
  render();
}

function clearFilters() {
  state.query = "";
  els.search.value = "";
  state.chips = [];
  render();
}

// --- bridge ---------------------------------------------------------------------

function onOrders() {
  const orders = state.bridge.orders || [];
  state.records = orders.map((o, index) => ({ o: o, index: index, key: str(o.Order_Number), hay: searchText(o) }));
  renderKpis();
  refreshColumns();
}

function onTheme() {
  els.themeVars.textContent = state.bridge.themeCss;
  // Density moves the type scale and the row height: re-measure, re-lay.
  measureColumns();
  render();
}

function bind() {
  const ids = {
    kpis: "kpis", search: "search", chips: "chips", addFilter: "add-filter", menu: "filter-menu",
    clearAll: "clear-all", count: "count", screenMenu: "screen-menu", exportBtn: "export",
    tableArea: "table-area", table: "table", scroller: "scroller", header: "header", rows: "rows",
    empty: "results-empty", noMatch: "results-no-match", noMatchClear: "no-match-clear", noMatchText: "no-match-text",
    themeVars: "theme-vars",
    columnsButton: "columns-button", pane: "pane", paneStrip: "pane-strip",
    paneShow: "pane-show", columnsPanel: "columns-panel",
    selectionBar: "selection-bar", selectionCount: "selection-count",
    selectionMark: "selection-mark",
    selectionHold: "selection-hold", selectionMore: "selection-more",
    selectionMenu: "selection-menu",
    toast: "toast", toastText: "toast-text", toastBadge: "toast-badge",
    toastUndo: "toast-undo",
  };
  for (const name of Object.keys(ids)) els[name] = document.getElementById(ids[name]);

  els.search.addEventListener("input", () => {
    state.query = els.search.value.trim().toLowerCase();
    render();
  });
  els.addFilter.addEventListener("click", () => (els.menu.hidden ? openMenu() : closeMenu()));
  els.menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeMenu();
      els.addFilter.focus();
    }
  });
  document.addEventListener("mousedown", (e) => {
    // This menu's own anchor, not any .menu-anchor: the selection bar's More
    // is one too, and clicking it used to leave this menu open behind it.
    if (!els.menu.hidden && !e.target.closest("#filter-anchor")) closeMenu();
  });
  els.clearAll.addEventListener("click", clearFilters);
  els.noMatchClear.addEventListener("click", clearFilters);
  els.screenMenu.addEventListener("click", () => state.bridge && state.bridge.openScreenMenu());
  els.exportBtn.addEventListener("click", () => state.bridge && state.bridge.openExport());
  els.rows.addEventListener("click", onRowClick);
  els.table.addEventListener("keydown", onTableKey);
  els.scroller.addEventListener("scroll", renderRows);
  new ResizeObserver(() => {
    layout();
    renderRows();
  }).observe(els.tableArea);
  bindPane();
  bindColumns();
  bindSelectionBar();
  bindToast();
}

bind();
renderKpis();
render();
// Columns are measured on a canvas, which needs the real face: measure again
// once Inter has loaded, or widths from the fallback font would stick.
document.fonts.ready.then(() => {
  measureColumns();
  render();
});

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.results;
  state.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(onTheme);
  bridge.ordersChanged.connect(onOrders);
  bridge.summaryChanged.connect(() => {
    renderKpis();
    renderExport();
    renderHeader();
  });
  bridge.exportEnabledChanged.connect(renderExport);
  bridge.focusSearchRequested.connect(() => els.search.focus());
  bridge.columnsChanged.connect(onColumns);
  bridge.toastRaised.connect((text, undoable) => raiseToast(text, undoable));
  bridge.undoAvailableChanged.connect(updateToastUndo);
  state.columnSettings = Object.assign(state.columnSettings, bridge.columns || {});
  onOrders();
  window.resultsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
