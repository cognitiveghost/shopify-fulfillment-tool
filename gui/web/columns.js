// The column registry (Bundle 13 spec §6.8). Keys are persisted per client,
// so never rename one. Python stores only names; titles, groups, defaults and
// pinning live here. Loaded before results.js: nothing at top level may call
// into it, only function bodies.
"use strict";

const COLUMN_GROUPS = ["Order", "Customer", "Money", "Shipping", "Tags & notes", "Other"];

const REGISTRY = [
  { key: "status", title: "Status", group: "Order", width: 132, pinned: true, shown: true,
    text: (o) => statusText(o), sortValue: (o) => (isFulfillable(o) ? 0 : 1) },
  { key: "order", title: "Order", group: "Order", width: 84, pinned: true, shown: true, mono: true,
    text: (o) => str(o.Order_Number) },
  { key: "customer", title: "Customer", group: "Customer", stretch: true, shown: true, text: (o) => str(o.Customer) },
  { key: "lines", title: "Lines", group: "Order", width: 56, shown: true, numeric: true,
    text: (o) => fmtInt(o.Items), sortValue: (o) => num(o.Items) },
  { key: "units", title: "Units", group: "Order", width: 56, shown: true, numeric: true,
    text: (o) => fmtInt(o.Units), sortValue: (o) => num(o.Units) },
  { key: "value", title: "Value", group: "Money", width: 84, shown: true, numeric: true,
    text: (o) => fmtMoney(o.Total_Price), sortValue: (o) => num(o.Total_Price) },
  { key: "courier", title: "Courier", group: "Shipping", width: 76, shown: true, text: (o) => str(o.Shipping_Provider) },
  { key: "age", title: "Age", group: "Order", width: 56, shown: true, numeric: true,
    text: (o) => fmtAge(o.Created_At), sortValue: (o) => ageMs(o.Created_At) },
  { key: "type", title: "Type", group: "Order", width: 64, maxWidth: 120, text: (o) => str(o.Order_Type) },
  { key: "reason", title: "Reason", group: "Order", width: 120, maxWidth: 240, text: (o) => str(o.Blocker) },
  { key: "country", title: "Country", group: "Customer", width: 64, maxWidth: 120, text: (o) => str(o.Destination_Country) },
  { key: "subtotal", title: "Subtotal", group: "Money", width: 84, numeric: true,
    text: (o) => fmtMoney(o.Subtotal), sortValue: (o) => num(o.Subtotal) },
  { key: "method", title: "Shipping method", group: "Shipping", width: 120, maxWidth: 240, text: (o) => str(o.Shipping_Method) },
  { key: "internal_tags", title: "Internal tags", group: "Tags & notes", width: 120, maxWidth: 240,
    text: (o) => (o.Tag_List || []).map(String).join(", ") },
  { key: "shopify_tags", title: "Shopify tags", group: "Tags & notes", width: 120, maxWidth: 240, text: (o) => str(o.Tags) },
  { key: "notes", title: "Notes", group: "Tags & notes", width: 160, maxWidth: 240, text: (o) => str(o.Notes) },
  { key: "status_note", title: "Status note", group: "Tags & notes", width: 120, maxWidth: 240, text: (o) => str(o.Status_Note) },
  { key: "repeat", title: "Repeat", group: "Tags & notes", width: 64, text: (o) => (o._repeat === true ? "Repeat" : "") },
];
const PINNED_KEYS = REGISTRY.filter((c) => c.pinned).map((c) => c.key);

function allColumns() {
  const extras = (state.columnSettings.extras || []).map((field) => ({
    key: "extra:" + field, title: String(field).replace(/_/g, " "), group: "Other",
    width: 120, maxWidth: 240, text: (o) => str(o[field]),
  }));
  return REGISTRY.concat(extras).map((col) => (col.sortValue ? col : Object.assign({ sortValue: col.text }, col)));
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
// The slot's third mode. It shows every column grouped for finding, while the
// table beside it keeps the one order a drop rearranges.

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

function closeColumnsPanel() {
  state.columnsOpen = false;
  columnDragKey = null;
  renderSlot();
  els.columnsButton.focus();
}

// The chrome is built once so typing in the search box keeps the caret.
function renderColumnsPanel() {
  if (!els.columnsPanel.firstChild) buildColumnsChrome();
  const shown = visibleColumns().length;
  const total = allColumns().length;
  document.getElementById("columns-count").textContent =
    NUMBER.format(shown) + " shown · " + NUMBER.format(total - shown) + " hidden";
  document.getElementById("hide-empty").checked = Boolean(state.columnSettings.auto_hide_empty);
  renderColumnRows();
}

function buildColumnsChrome() {
  const panel = els.columnsPanel;
  const head = el("div", "columns-head");
  const titles = el("div", "columns-titles");
  titles.append(el("div", "columns-title", "Columns"), el("div", "columns-count-line"));
  titles.lastChild.id = "columns-count";
  const close = paneButton("ghost icon columns-close", "×", "Close column manager");
  close.id = "columns-close";
  close.addEventListener("click", closeColumnsPanel);
  head.append(titles, el("span", "spacer"), close);

  const search = el("input", "columns-search");
  search.id = "columns-search";
  search.type = "search";
  search.placeholder = "Find a column";
  search.setAttribute("aria-label", "Find a column");
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
  hideLabel.append(hideBox, el("span", "", "Hide empty columns"));
  const reset = paneButton("ghost", "Reset to defaults");
  reset.id = "columns-reset";
  reset.addEventListener("click", () => storeColumns({ order: null, visible: null }, (b) => b.resetColumns()));
  const done = paneButton("secondary", "Done");
  done.id = "columns-done";
  done.addEventListener("click", closeColumnsPanel);
  foot.append(hideLabel, el("span", "spacer"), reset, done);

  panel.append(head, search, scroller, foot);
}

function renderColumnRows() {
  const scroller = document.getElementById("columns-scroller");
  const active = document.activeElement;
  const keep = active && active.closest ? active.closest(".col-row") : null;
  const keepKey = keep ? keep.dataset.key : null;
  const keepCheck = Boolean(keep && active.classList.contains("col-check"));

  const query = columnQuery.trim().toLowerCase();
  const visible = new Set(visibleColumns().map((c) => c.key));
  const ordered = orderedColumns();
  scroller.textContent = "";
  for (const group of COLUMN_GROUPS) {
    const cols = ordered.filter((c) => c.group === group);
    const hits = cols.filter((c) => c.title.toLowerCase().includes(query));
    if (!hits.length) continue;
    const head = el("div", "col-group", group.toUpperCase() + " ");
    head.dataset.group = group;
    head.append(el("span", "col-group-count",
      NUMBER.format(cols.filter((c) => visible.has(c.key)).length) + " of " + NUMBER.format(cols.length)));
    scroller.append(head);
    for (const col of hits) scroller.append(columnRow(col));
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
  box.setAttribute("aria-label", col.title);
  box.addEventListener("change", () => setColumnShown(col.key, box.checked));
  row.append(box);

  const title = el("span", "col-title" + (hidden ? " muted" : ""), col.title);
  title.title = col.title;
  row.append(title, el("span", "col-note", col.pinned ? "pinned" : hidden ? "empty" : ""));

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
}
