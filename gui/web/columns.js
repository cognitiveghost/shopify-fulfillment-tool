// The column registry (Bundle 13 spec §6.8). Keys are persisted per client,
// so never rename one. Python stores only names; titles, defaults and
// pinning live here. Loaded before results.js: nothing at top level may call
// into it, only function bodies.
"use strict";

const REGISTRY = [
  { key: "status", title: () => t("Status"), width: 108, pinned: true, shown: true,
    text: (o) => statusText(o), sortValue: (o) => (isFulfillable(o) ? 0 : 1) },
  { key: "order", title: () => t("Order"), width: 64, pinned: true, shown: true, mono: true,
    text: (o) => str(o.Order_Number) },
  { key: "customer", title: () => t("Customer"), stretch: true, shown: true, text: (o) => str(o.Customer) },
  { key: "lines", title: () => t("Lines"), width: 52, shown: true, numeric: true, mono: true,
    text: (o) => fmtInt(o.Items), sortValue: (o) => num(o.Items) },
  { key: "units", title: () => t("Units"), width: 52, shown: true, numeric: true, mono: true,
    text: (o) => fmtInt(o.Units), sortValue: (o) => num(o.Units) },
  { key: "value", title: () => t("Value"), width: 76, shown: true, numeric: true, mono: true,
    text: (o) => fmtMoney(o.Total_Price), sortValue: (o) => num(o.Total_Price) },
  { key: "courier", title: () => t("Courier"), width: 72, shown: true, text: (o) => str(o.Shipping_Provider) },
  { key: "age", title: () => t("Age"), width: 52, shown: true, numeric: true, mono: true,
    text: (o) => fmtAge(o.Created_At), sortValue: (o) => ageMs(o.Created_At) },
  { key: "type", title: () => t("Type"), width: 64, maxWidth: 120, text: (o) => str(o.Order_Type) },
  { key: "reason", title: () => t("Reason"), width: 120, maxWidth: 240, text: (o) => str(o.Blocker) },
  { key: "country", title: () => t("Country"), width: 64, maxWidth: 120, text: (o) => str(o.Destination_Country) },
  { key: "subtotal", title: () => t("Subtotal"), width: 84, numeric: true, mono: true,
    text: (o) => fmtMoney(o.Subtotal), sortValue: (o) => num(o.Subtotal) },
  { key: "method", title: () => t("Shipping method"), width: 120, maxWidth: 240, text: (o) => str(o.Shipping_Method) },
  { key: "internal_tags", title: () => t("Internal tags"), width: 120, maxWidth: 240,
    text: (o) => (o.Tag_List || []).map(String).join(", ") },
  { key: "shopify_tags", title: () => t("Shopify tags"), width: 120, maxWidth: 240, text: (o) => str(o.Tags) },
  { key: "notes", title: () => t("Notes"), width: 160, maxWidth: 240, text: (o) => str(o.Notes) },
  { key: "status_note", title: () => t("Status note"), width: 120, maxWidth: 240, text: (o) => str(o.Status_Note) },
  { key: "repeat", title: () => t("Repeat"), width: 76, shown: true, text: (o) => (o._repeat === true ? t("Repeat") : "") },
];
const PINNED_KEYS = REGISTRY.filter((c) => c.pinned).map((c) => c.key);

function allColumns() {
  const extras = (state.columnSettings.extras || []).map((field) => ({
    key: "extra:" + field, title: String(field).replace(/_/g, " "), extra: true,
    width: 120, maxWidth: 240, text: (o) => str(o[field]),
  }));
  return REGISTRY.concat(extras).map((col) => (col.sortValue ? col : Object.assign({ sortValue: col.text }, col)));
}

// A column's header as drawn. The registry's titles are the app's own, so they
// translate; an additional column is named after the file's field, so it does not.
function colTitle(col) {
  return col.extra ? col.title : col.title();
}

// Pinned first, then the saved order, then everything else in registry order.
function orderedColumns() {
  const all = allColumns();
  const byKey = new Map(all.map((c) => [c.key, c]));
  const keys = PINNED_KEYS.slice();
  for (const key of state.columnSettings.order || []) if (byKey.has(key) && !keys.includes(key)) keys.push(key);
  for (const col of all) if (!keys.includes(col.key)) keys.push(col.key);
  return keys.map((key) => byKey.get(key));
}

// The operator's choice, before auto-hide.
function userVisible(col) {
  if (col.pinned) return true;
  const visible = state.columnSettings.visible;
  return visible ? visible.includes(col.key) : Boolean(col.shown);
}

function autoHidden(col) {
  return !col.pinned && Boolean(state.columnSettings.auto_hide_empty) && state.emptyKeys.has(col.key);
}

function visibleColumns() {
  return orderedColumns().filter((col) => userVisible(col) && !autoHidden(col));
}

// Apply a layout change here at once, then tell Python to store it.
function storeColumns(changes, send) {
  state.columnSettings = Object.assign({}, state.columnSettings, changes);
  refreshColumns();
  if (state.bridge) send(state.bridge);
}

// --- the column manager (spec §6.9) -----------------------------------------
// A popover under the Columns button (phase 2 spec section 5.8). It lists every
// column in the table's own order, the one a drop rearranges.

// Six dots, drawn as zero-length round-capped subpaths.
const GRIP = "M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01";
let columnQuery = "";
let columnDragKey = null;

function openColumnsPanel() {
  columnQuery = "";
  state.columnsOpen = true;
  renderSlot();
  const search = document.getElementById("columns-search");
  search.value = "";
  search.focus();
}

// An outside click closes without taking focus from what was clicked.
function closeColumnsPanel(restoreFocus = true) {
  state.columnsOpen = false;
  columnDragKey = null;
  renderSlot();
  if (restoreFocus) els.columnsButton.focus();
}

// The chrome is built once so typing in the search box keeps the caret.
function renderColumnsPanel() {
  if (!els.columnsPanel.firstChild) buildColumnsChrome();
  const shown = visibleColumns().length;
  const total = allColumns().length;
  document.getElementById("columns-count").textContent = t("{shown} shown · {hidden} hidden", {
    shown: NUMBER.format(shown),
    hidden: NUMBER.format(total - shown),
  });
  document.getElementById("hide-empty").checked = Boolean(state.columnSettings.auto_hide_empty);
  renderColumnRows();
}

function buildColumnsChrome() {
  const panel = els.columnsPanel;
  const head = el("div", "columns-head");
  head.append(el("div", "columns-title", t("Columns")), el("div", "columns-count-line"));
  head.lastChild.id = "columns-count";

  const search = el("input", "field columns-search");
  search.id = "columns-search";
  search.type = "search";
  search.placeholder = t("Find a column");
  search.setAttribute("aria-label", t("Find a column"));
  search.addEventListener("input", () => {
    columnQuery = search.value;
    renderColumnRows();
  });

  const scroller = el("div", "columns-scroller");
  scroller.id = "columns-scroller";

  const foot = el("div", "columns-foot");
  const hideLabel = el("label", "columns-hide-empty");
  const hideBox = el("input");
  hideBox.id = "hide-empty";
  hideBox.type = "checkbox";
  hideBox.addEventListener("change", () =>
    storeColumns({ auto_hide_empty: hideBox.checked }, (b) => b.setAutoHideEmpty(hideBox.checked)),
  );
  hideLabel.append(hideBox, el("span", "", t("Hide empty columns")));
  const reset = paneButton("ghost compact", t("Reset"));
  reset.id = "columns-reset";
  reset.title = t("Reset to defaults");
  reset.addEventListener("click", () => storeColumns({ order: null, visible: null }, (b) => b.resetColumns()));
  foot.append(hideLabel, el("span", "spacer"), reset);

  panel.append(head, search, scroller, foot);
}

function renderColumnRows() {
  const scroller = document.getElementById("columns-scroller");
  const active = document.activeElement;
  const keep = active && active.closest ? active.closest(".col-row") : null;
  const keepKey = keep ? keep.dataset.key : null;
  const keepCheck = Boolean(keep && active.classList.contains("col-check"));

  const query = columnQuery.trim().toLowerCase();
  scroller.textContent = "";
  for (const col of orderedColumns()) {
    if (colTitle(col).toLowerCase().includes(query)) scroller.append(columnRow(col));
  }
  if (!keepKey) return;
  const row = scroller.querySelector('.col-row[data-key="' + CSS.escape(keepKey) + '"]');
  if (row) (keepCheck ? row.querySelector(".col-check") : row).focus();
}

function columnRow(col) {
  const reorderable = !col.pinned && columnQuery.trim() === "";
  const hidden = autoHidden(col);
  const row = el("div", "col-row");
  row.dataset.key = col.key;
  row.tabIndex = 0;

  const grip = el("span", "col-grip");
  if (reorderable) grip.innerHTML = svg(GRIP, "grip");
  row.append(grip);

  const box = el("input", "col-check");
  box.type = "checkbox";
  box.checked = userVisible(col);
  box.disabled = Boolean(col.pinned);
  box.setAttribute("aria-label", colTitle(col));
  box.addEventListener("change", () => setColumnShown(col.key, box.checked));
  row.append(box);

  const title = el("span", "col-title" + (hidden ? " muted" : ""), colTitle(col));
  title.title = colTitle(col);
  row.append(title, el("span", "col-note", col.pinned ? t("pinned") : hidden ? t("empty") : ""));

  // Pinned rows accept a drop too -- moveColumn's floor is what keeps a drop
  // above the pinned pair legal, landing the moved column right after them.
  if (columnQuery.trim() === "") bindColumnDrag(row, col.key, reorderable);
  row.addEventListener("keydown", (e) => onColumnRowKey(e, col));
  return row;
}

// The operator's choice, before auto-hide. Pinned keys are never in the list:
// `userVisible` returns true for them whatever it holds.
function setColumnShown(key, on) {
  const keys = orderedColumns()
    .filter((c) => !c.pinned && (c.key === key ? on : userVisible(c)))
    .map((c) => c.key);
  storeColumns({ visible: keys }, (b) => b.setVisibleColumns(keys));
}

// The table's one sequence, pinned pair first.
function moveColumn(key, target, after) {
  const keys = orderedColumns().map((c) => c.key).filter((k) => k !== key);
  const floor = keys.indexOf(PINNED_KEYS[PINNED_KEYS.length - 1]) + 1;
  const at = Math.max(floor, keys.indexOf(target) + (after ? 1 : 0));
  keys.splice(at, 0, key);
  storeColumns({ order: keys }, (b) => b.setColumnOrder(keys));
}

// Alt+arrow uses the rows on screen, so it reads as moving up or down the list.
function moveByList(key, delta) {
  const keys = [...document.querySelectorAll(".col-row")].map((r) => r.dataset.key);
  const target = keys[keys.indexOf(key) + delta];
  if (target !== undefined) moveColumn(key, target, delta > 0);
}

function onColumnRowKey(e, col) {
  if (e.key === " " && !e.target.classList.contains("col-check")) {
    e.preventDefault();
    if (!col.pinned) setColumnShown(col.key, !userVisible(col));
    return;
  }
  if (!e.altKey || col.pinned || columnQuery.trim() !== "") return;
  if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    moveByList(col.key, e.key === "ArrowDown" ? 1 : -1);
  }
}

function clearDropMarks() {
  for (const row of document.querySelectorAll(".col-row[data-drop]")) delete row.dataset.drop;
}

function bindColumnDrag(row, key, draggable) {
  if (draggable) {
    row.draggable = true;
    row.addEventListener("dragstart", (e) => {
      columnDragKey = key;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", key);
    });
    row.addEventListener("dragend", () => {
      columnDragKey = null;
      clearDropMarks();
    });
  }
  row.addEventListener("dragover", (e) => {
    if (columnDragKey === null || columnDragKey === key) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const box = row.getBoundingClientRect();
    row.dataset.drop = e.clientY - box.top > box.height / 2 ? "after" : "before";
  });
  row.addEventListener("dragleave", () => delete row.dataset.drop);
  row.addEventListener("drop", (e) => {
    e.preventDefault();
    const after = row.dataset.drop === "after";
    const moved = columnDragKey;
    columnDragKey = null;
    clearDropMarks();
    if (moved !== null && moved !== key) moveColumn(moved, key, after);
  });
}

function bindColumns() {
  els.columnsButton.addEventListener("click", () =>
    state.columnsOpen ? closeColumnsPanel() : openColumnsPanel(),
  );
  els.columnsPanel.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    closeColumnsPanel();
  });
  document.addEventListener("mousedown", (e) => {
    if (state.columnsOpen && !e.target.closest("#columns-anchor")) closeColumnsPanel(false);
  });
}
