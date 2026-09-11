// The results document (Bundle 12): KPI strip, filter bar and a windowed
// order table over the bridge's `orders` and `summary`. The page owns sort,
// search, filter chips and the selection gesture (ADR 0005). Python hears
// only the selection and two commands. Numbers and copy:
// docs/superpowers/specs/2026-09-11-phase9-bundle12-results-doc-design.md
"use strict";

const HEADER_PX = 28;
const OVERSCAN = 4;
const TABLE_MIN_PX = 780;
const DASH = "—";
const FULFILLABLE = "Fulfillable";
const NO_COURIER = "No courier";
const NUMBER = new Intl.NumberFormat("en-US");

// Lucide chevron-down, chevron-up and check. Paths, not a transform: the
// web tier may not rotate anything (ADR 0001).
const CHEVRON_DOWN = "m6 9 6 6 6-6";
const CHEVRON_UP = "m18 15-6-6-6 6";
const CHECK = "M20 6 9 17l-5-5";

const els = {};
const state = {
  bridge: null,
  records: [], // {o, index, key, hay} in frame order
  view: [], // records that pass the filters, in display order
  query: "",
  chips: [], // {kind, value, label}
  sort: null, // {key, dir: 1 | -1}
  selected: new Set(), // order numbers
  anchorKey: null, // the row a Shift-click or an arrow key starts from
  rowH: 28,
  visible: 0,
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
  if (abs >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (n / 1e3).toFixed(1) + "k";
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

// Widths are the canvas's (W3); a column grows to its widest real value but
// never reflows after that. Only Customer stretches (9.15).
const COLUMNS = [
  { key: "select", title: "", width: 32 },
  { key: "status", title: "Status", width: 132, sortValue: (o) => (isFulfillable(o) ? 0 : 1) },
  { key: "order", title: "Order", width: 84, mono: true, text: (o) => str(o.Order_Number), sortValue: (o) => str(o.Order_Number) },
  { key: "customer", title: "Customer", stretch: true, text: (o) => str(o.Customer), sortValue: (o) => str(o.Customer) },
  { key: "lines", title: "Lines", width: 56, numeric: true, text: (o) => fmtInt(o.Items), sortValue: (o) => num(o.Items) },
  { key: "units", title: "Units", width: 56, numeric: true, text: (o) => fmtInt(o.Units), sortValue: (o) => num(o.Units) },
  { key: "value", title: "Value", width: 84, numeric: true, text: (o) => fmtMoney(o.Total_Price), sortValue: (o) => num(o.Total_Price) },
  { key: "courier", title: "Courier", width: 76, text: (o) => str(o.Shipping_Provider), sortValue: (o) => str(o.Shipping_Provider) },
  { key: "age", title: "Age", width: 56, numeric: true, text: (o) => fmtAge(o.Created_At), sortValue: (o) => ageMs(o.Created_At) },
];

const FLAGS = [
  { value: "repeat", label: "Repeat", test: (o) => o._repeat === true },
  { value: "unknown_sku", label: "Unknown SKU", test: (o) => o.Unknown_SKU === true },
  { value: "low_stock", label: "Low stock", test: (o) => o.Low_Stock === true },
  { value: "lines3", label: "3 or more lines", test: (o) => (num(o.Items) || 0) >= 3 },
];

function chipId(chip) {
  return chip.kind + ":" + chip.value;
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

function searchText(o) {
  const parts = [o.Order_Number, o.Customer, o.Shipping_Provider].concat(o.Tag_List || []);
  for (const line of o.lines || []) parts.push(line.SKU, line.Product_Name);
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
    const col = COLUMNS.find((c) => c.key === state.sort.key);
    view = view.slice().sort(compare(col, state.sort.dir));
  }
  state.view = view;
  // A filter that hides a selected order deselects it, so a bulk action can
  // never reach a row the operator cannot see (ADR 0005).
  const shown = new Set(view.map((r) => r.key));
  state.selected = new Set([...state.selected].filter((k) => shown.has(k)));
  if (state.anchorKey !== null && !shown.has(state.anchorKey)) state.anchorKey = null;
}

// --- rendering ----------------------------------------------------------------

function render() {
  recompute();
  renderChips();
  renderCount();
  renderExport();
  renderStates();
  renderHeader();
  layout();
  renderRows();
  reportSelection();
}

function reportSelection() {
  if (!state.bridge) return;
  // The bridge drops a list equal to the last one, so this is safe on every render.
  state.bridge.setSelection(state.view.filter((r) => state.selected.has(r.key)).map((r) => r.key));
}

function renderKpis() {
  const s = (state.bridge && state.bridge.summary) || {};
  const has = s.orders !== undefined;
  const oldest = has ? s.oldest : null;
  let valueSub = "";
  if (has) {
    valueSub = s.value_total === null ? "No price column mapped" : "of " + fmtCompact(s.value_total) + " analysed";
  }
  const cards = [
    ["orders", "Orders", has ? fmtInt(s.orders) : DASH,
      has ? NUMBER.format(s.lines) + " lines · " + NUMBER.format(s.skus) + " SKUs touched" : ""],
    ["fulfillable", "Fulfillable", has ? fmtInt(s.fulfillable) : DASH,
      has && s.orders ? Math.round((100 * s.fulfillable) / s.orders) + "% of orders" : ""],
    ["blocked", "Blocked", has ? fmtInt(s.blocked) : DASH,
      has ? NUMBER.format(s.blocked_lines) + " lines, " + NUMBER.format(s.blocked_skus) + " SKUs" : ""],
    ["labels", "Labels", has ? fmtInt(s.fulfillable) : DASH,
      has ? (s.labels_by_courier || []).map((p) => p[0] + " " + NUMBER.format(p[1])).join(" · ") : ""],
    ["value", "Value ready", has && s.value_ready !== null ? fmtCompact(s.value_ready) : DASH, valueSub],
    ["oldest", "Oldest waiting", oldest ? fmtAge(oldest.created_at) : DASH,
      oldest ? "order " + oldest.order_number : ""],
  ];
  els.kpis.classList.toggle("has-wide", Boolean(oldest));
  els.kpis.textContent = "";
  for (const [key, label, value, sub] of cards) {
    const card = document.createElement("div");
    card.className = "kpi" + (key === "oldest" ? " kpi-wide" : "");
    card.dataset.kpi = key;
    for (const [cls, text] of [["kpi-label", label], ["kpi-value", value], ["kpi-sub", sub]]) {
      const part = document.createElement("div");
      part.className = cls;
      part.textContent = text;
      card.appendChild(part);
    }
    els.kpis.appendChild(card);
  }
}

function renderChips() {
  els.chips.textContent = "";
  for (const chip of state.chips) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip-filter";
    button.dataset.chip = chipId(chip);
    button.title = "Remove this filter";
    button.textContent = chip.label + "  ×";
    button.addEventListener("click", () => {
      toggleChip(chip);
      render();
    });
    els.chips.appendChild(button);
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
  els.exportBtn.textContent = s.fulfillable === undefined ? "Export" : "Export " + plural(n, "order");
  els.exportBtn.disabled = !(state.bridge && state.bridge.exportEnabled && n > 0);
}

function renderStates() {
  const none = state.records.length === 0;
  const noMatch = !none && state.view.length === 0;
  els.empty.hidden = !none;
  els.noMatch.hidden = !noMatch;
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
  for (const col of COLUMNS) {
    const cell = document.createElement("div");
    cell.className = "cell head " + col.key + (col.numeric ? " num" : "");
    cell.setAttribute("role", "columnheader");
    if (col.key === "select") {
      const box = document.createElement("input");
      box.type = "checkbox";
      box.tabIndex = -1;
      box.setAttribute("aria-label", "Select every order shown");
      box.checked = all;
      box.indeterminate = picked > 0 && !all;
      box.addEventListener("click", () => selectAll(!all));
      cell.appendChild(box);
    } else {
      const sorted = Boolean(state.sort && state.sort.key === col.key);
      cell.dataset.sort = col.key;
      cell.classList.toggle("sorted", sorted);
      cell.setAttribute("aria-sort", sorted ? (state.sort.dir === 1 ? "ascending" : "descending") : "none");
      const label = document.createElement("span");
      label.textContent = col.title;
      cell.appendChild(label);
      cell.insertAdjacentHTML("beforeend", svg(sorted && state.sort.dir === 1 ? CHEVRON_UP : CHEVRON_DOWN, "caret"));
      cell.addEventListener("click", () => cycleSort(col.key));
    }
    els.header.appendChild(cell);
  }
}

function measureColumns() {
  measureColumns.ctx = measureColumns.ctx || document.createElement("canvas").getContext("2d");
  const ctx = measureColumns.ctx;
  const body = getComputedStyle(document.body);
  const sans = body.fontSize + " " + body.fontFamily;
  const mono = body.fontSize + " " + cssVar("--font-family-mono");
  const caption = cssVar("--type-caption-size") + " " + body.fontFamily;
  const widths = COLUMNS.map((col) => {
    if (col.key === "select" || col.stretch) return col.width || 0;
    ctx.font = "700 " + caption;
    let widest = ctx.measureText(col.title).width + 14; // + the sort caret
    if (col.key === "status") {
      ctx.font = caption;
      widest = Math.max(widest, ctx.measureText(FULFILLABLE).width + 30); // chip padding + border
    } else {
      ctx.font = col.mono ? mono : sans;
      for (const r of state.records) widest = Math.max(widest, ctx.measureText(col.text(r.o) || DASH).width);
    }
    return Math.max(col.width, Math.ceil(widest + 16));
  });
  const fixed = widths.reduce((a, b) => a + b, 0);
  const customerMin = Math.max(120, TABLE_MIN_PX - fixed);
  const template = COLUMNS.map((col, i) => (col.stretch ? "minmax(" + customerMin + "px, 1fr)" : widths[i] + "px"));
  els.table.style.setProperty("--cols", template.join(" "));
}

// Whole rows only: the table is as tall as the rows that fit, and whatever is
// left over stays page surface below it (9.15).
// ponytail: a horizontal scrollbar (page < 812px) eats into the last row; that
// state is unreachable at 1366, so it is not compensated for.
function layout() {
  state.rowH = parseFloat(cssVar("--row-height")) || 28;
  const rows = Math.max(0, Math.floor((els.tableArea.clientHeight - HEADER_PX) / state.rowH));
  state.visible = rows;
  els.scroller.style.height = HEADER_PX + rows * state.rowH + "px";
  els.rows.style.height = state.view.length * state.rowH + "px";
  els.table.dataset.visibleRows = String(Math.min(rows, state.view.length));
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
  row.className = "row" + (selected ? " selected" : "");
  row.setAttribute("role", "row");
  row.setAttribute("aria-selected", String(selected));
  row.dataset.order = record.key;
  row.dataset.index = String(index);
  row.style.top = index * state.rowH + "px";
  for (const col of COLUMNS) row.appendChild(cellElement(col, record, selected));
  return row;
}

function cellElement(col, record, selected) {
  const cell = document.createElement("div");
  cell.className = "cell " + col.key + (col.numeric ? " num" : "");
  cell.setAttribute("role", "gridcell");
  if (col.key === "select") {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.tabIndex = -1;
    box.checked = selected;
    box.setAttribute("aria-label", "Select order " + record.key);
    cell.appendChild(box);
  } else if (col.key === "status") {
    const ok = isFulfillable(record.o);
    const chip = document.createElement("span");
    chip.className = "chip " + (ok ? "success" : "danger");
    chip.textContent = ok ? "Fulfillable" : "Blocked";
    cell.appendChild(chip);
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

function onRowClick(event) {
  const row = event.target.closest(".row");
  if (!row || !row.dataset.order) return;
  const key = row.dataset.order;
  const ctrl = event.ctrlKey || event.metaKey;
  if (event.shiftKey && state.anchorKey !== null) {
    selectRange(state.anchorKey, key, ctrl);
  } else if (ctrl || event.target.matches("input[type=checkbox]")) {
    if (state.selected.has(key)) state.selected.delete(key);
    else state.selected.add(key);
    state.anchorKey = key;
  } else {
    state.selected = new Set([key]);
    state.anchorKey = key;
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
    state.selected = new Set();
    state.anchorKey = null;
    render();
    return;
  }
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  if (!state.view.length) return;
  const keys = state.view.map((r) => r.key);
  const at = state.anchorKey === null ? -1 : keys.indexOf(state.anchorKey);
  const next = Math.min(keys.length - 1, Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)));
  if (event.shiftKey) state.selected.add(keys[next]);
  else state.selected = new Set([keys[next]]);
  state.anchorKey = keys[next];
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
  measureColumns();
  renderKpis();
  render();
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
    empty: "results-empty", noMatch: "results-no-match", noMatchClear: "no-match-clear",
    themeVars: "theme-vars",
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
    if (!els.menu.hidden && !e.target.closest(".menu-anchor")) closeMenu();
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
}

bind();
renderKpis();
render();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.results;
  state.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(onTheme);
  bridge.ordersChanged.connect(onOrders);
  bridge.summaryChanged.connect(() => {
    renderKpis();
    renderExport();
  });
  bridge.exportEnabledChanged.connect(renderExport);
  bridge.focusSearchRequested.connect(() => els.search.focus());
  onOrders();
  window.resultsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
