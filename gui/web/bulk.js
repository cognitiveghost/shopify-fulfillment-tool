// The selection bar, its menu, the bulk popover and the toast (Bundle 14).
// Loads before results.js: nothing here may name results.js's helpers at the
// top level, only inside a function body.
// Spec: docs/superpowers/specs/2026-09-14-phase9-bundle14-selection-bulk-design.md
"use strict";

// The bar's height is CSS's to state (--selection-bar-height) and JS's to
// read, so the row budget can never disagree with what is drawn.
function selectionBarPx() {
  return parseFloat(cssVar("--selection-bar-height")) || 44;
}

function selectedOrders() {
  return state.view.filter((r) => state.selected.has(r.key)).map((r) => r.o);
}

function selectedKeys() {
  return state.view.filter((r) => state.selected.has(r.key)).map((r) => r.key);
}

function selectionSummary() {
  const orders = selectedOrders();
  let units = 0;
  let value = 0;
  let anyValue = false;
  const couriers = new Set();
  for (const o of orders) {
    units += num(o.Units) || 0;
    const v = num(o.Total_Price);
    if (v !== null) {
      value += v;
      anyValue = true;
    }
    couriers.add(courierOf(o));
  }
  return { orders: orders.length, units, value: anyValue ? value : null, couriers: couriers.size };
}

function countedWord(n, word) {
  return NUMBER.format(n) + " " + word + (n === 1 ? "" : "s");
}

function theseOrders(n) {
  return n === 1 ? "this order" : "these " + countedWord(n, "order");
}

function renderSelectionBar() {
  const n = state.selected.size;
  els.selectionBar.hidden = n === 0;
  els.exportBtn.className = "btn " + (n === 0 ? "primary" : "secondary");
  if (n === 0) {
    closeSelectionMenu();
    closeBulkPopover();
    return;
  }
  const s = selectionSummary();
  els.selectionCount.textContent =
    countedWord(s.orders, "order") + " · " + countedWord(s.units, "unit") + " selected";
  const parts = [];
  if (s.value !== null) parts.push(fmtMoney(s.value));
  parts.push(countedWord(s.couriers, "courier"));
  els.selectionSub.textContent = parts.join(" · ");
  els.selectionMark.textContent =
    n === 1 ? "Mark fulfillable" : "Mark " + NUMBER.format(n) + " fulfillable";
  els.selectionHold.textContent = n === 1 ? "Hold" : "Hold these " + NUMBER.format(n);
}

function clearSelection() {
  state.selected = new Set();
  render();
  els.table.focus();
}

function bindSelectionBar() {
  els.selectionMark.addEventListener("click", () => {
    state.bridge.setStatus(selectedKeys(), true);
  });
  els.selectionHold.addEventListener("click", () => {
    state.bridge.setStatus(selectedKeys(), false);
  });
  els.selectionExclude.addEventListener("click", () => {
    state.bridge.excludeOrders(selectedKeys());
  });
  els.selectionClear.addEventListener("click", clearSelection);
  els.selectionMore.addEventListener("click", () => {
    if (els.selectionMenu.hidden) openSelectionMenu();
    else closeSelectionMenu();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest("#selection-menu, #selection-more")) closeSelectionMenu();
    if (!e.target.closest("#bulk-popover, #selection-menu, #selection-more")) closeBulkPopover();
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && state.selected.size) {
      const t = document.activeElement;
      if (t && t.matches && t.matches("input, textarea")) return;
      e.preventDefault();
      copySelection();
    }
  });
  // Capture phase: results.js's own Escape handler would otherwise clear the
  // selection before this can close just the innermost thing. Popover, then
  // menu, then -- by falling through -- the selection (spec section 10).
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Escape") return;
      if (document.getElementById("bulk-popover")) closeBulkPopover();
      else if (!els.selectionMenu.hidden) closeSelectionMenu();
      else return;
      e.stopPropagation();
      els.selectionMore.focus();
    },
    { capture: true }
  );
}

function selectionTags() {
  const seen = new Set();
  for (const o of selectedOrders()) for (const t of o.Tag_List || []) seen.add(String(t));
  return [...seen].sort();
}

function moreItems() {
  const n = state.selected.size;
  const orders = countedWord(n, "order");
  const tagged = selectionTags().length > 0;
  return [
    { id: "more-add-tag", label: "Add a tag to " + orders, run: () => openTagPopover("add") },
    {
      id: "more-remove-tag",
      label: "Remove a tag from " + orders,
      disabled: !tagged,
      title: tagged
        ? ""
        : n === 1
          ? "This order doesn't carry a tag"
          : "None of these " + orders + " carry a tag",
      run: () => openTagPopover("remove"),
    },
    { id: "more-copy", label: "Copy " + countedWord(n, "order number"), hint: "Ctrl+C", run: copySelection },
    {
      id: "more-export-xlsx",
      label: "Export " + theseOrders(n) + " to Excel",
      run: () => exportSelectionAs("xlsx"),
    },
    {
      id: "more-export-csv",
      label: "Export " + theseOrders(n) + " to CSV",
      run: () => exportSelectionAs("csv"),
    },
    { separator: true },
    { id: "more-remove-sku", label: "Remove a SKU from " + theseOrders(n), danger: true, run: () => openSkuPopover("line") },
    { id: "more-remove-orders", label: "Remove whole orders containing a SKU", danger: true, run: () => openSkuPopover("order") },
  ];
}

function copySelection() {
  state.bridge.copyText(selectedKeys().join("\n"));
  raiseToast(countedWord(state.selected.size, "order number") + " copied", false);
}

function exportSelectionAs(fmt) {
  state.bridge.exportSelection(selectedKeys(), fmt);
}

function renderSelectionMenu() {
  els.selectionMenu.textContent = "";
  for (const item of moreItems()) {
    if (item.separator) {
      els.selectionMenu.appendChild(el("div", "menu-separator"));
      continue;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.id = item.id;
    button.className = "menu-item" + (item.danger ? " danger" : "");
    button.setAttribute("role", "menuitem");
    button.disabled = Boolean(item.disabled);
    if (item.title) button.title = item.title;
    button.appendChild(document.createTextNode(item.label));
    if (item.hint) button.appendChild(el("span", "menu-hint", item.hint));
    button.addEventListener("click", () => {
      closeSelectionMenu();
      item.run();
    });
    els.selectionMenu.appendChild(button);
  }
}

function openSelectionMenu() {
  renderSelectionMenu();
  els.selectionMenu.hidden = false;
  els.selectionMore.setAttribute("aria-expanded", "true");
  const first = els.selectionMenu.querySelector(".menu-item:not(:disabled)");
  if (first) first.focus();
}

function closeSelectionMenu() {
  if (!els.selectionMenu) return;
  els.selectionMenu.hidden = true;
  els.selectionMore.setAttribute("aria-expanded", "false");
}

function tagRows(categories, exclude) {
  const skip = exclude || new Set();
  const rows = [];
  for (const id of Object.keys(categories || {})) {
    const category = categories[id] || {};
    const tags = (category.tags || []).map(String).filter((t) => !skip.has(t));
    if (tags.length) rows.push({ id: id, label: str(category.label) || id, tags: tags });
  }
  return rows;
}

// `badge` is {total, counts} or null for the pane, which wants no counts. A
// row with no label is drawn without a group header -- remove-a-tag lists
// tags you can already see, so a category does not help you find one.
function renderTagList(host, rows, badge, onPick) {
  for (const row of rows) {
    if (row.label) host.appendChild(el("div", "menu-group", row.label));
    for (const tag of row.tags) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "menu-item bulk-row";
      button.dataset.tag = tag;
      button.appendChild(document.createTextNode(tag));
      const on = badge ? badge.counts.get(tag) || 0 : 0;
      if (on) {
        button.appendChild(
          el("span", "bulk-count", "on " + NUMBER.format(on) + " of " + NUMBER.format(badge.total))
        );
      }
      button.addEventListener("click", () => onPick(tag, button));
      host.appendChild(button);
    }
  }
}

function tagCounts(tags) {
  const counts = new Map();
  for (const o of selectedOrders()) {
    for (const t of o.Tag_List || []) {
      const key = String(t);
      if (tags.has(key)) counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  return counts;
}

let bulkPicked = null;

function closeBulkPopover() {
  const open = document.getElementById("bulk-popover");
  if (open) open.remove();
  bulkPicked = null;
}

function openBulkPopover(opts) {
  closeBulkPopover();
  const box = el("div", "bulk-popover");
  box.id = "bulk-popover";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", opts.title);

  const title = el("div", "bulk-title", opts.title);
  title.id = "bulk-title";
  box.appendChild(title);

  const list = el("div", "bulk-list");
  list.id = "bulk-list";
  box.appendChild(list);

  const verb = document.createElement("button");
  verb.type = "button";
  verb.id = "bulk-verb";
  verb.className = "btn " + (opts.danger ? "danger" : "primary");
  verb.disabled = true;
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn ghost";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", closeBulkPopover);
  const footer = el("div", "bulk-footer");
  footer.append(cancel, verb);
  box.appendChild(footer);

  opts.fill(list, (value, row) => {
    bulkPicked = value;
    for (const other of list.querySelectorAll(".bulk-row")) other.classList.remove("picked");
    row.classList.add("picked");
    const label = opts.verb(value);
    verb.textContent = label.text;
    verb.disabled = label.disabled;
  });

  list.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const rows = [...list.querySelectorAll(".bulk-row")].filter((r) => !r.hidden);
    const here = rows.indexOf(document.activeElement);
    const next = here + (e.key === "ArrowDown" ? 1 : -1);
    if (next < 0 || next >= rows.length) return;
    e.preventDefault();
    rows[next].focus();
  });

  verb.addEventListener("click", () => {
    const value = bulkPicked;
    closeBulkPopover();
    opts.onCommit(value);
  });

  els.selectionBar.appendChild(box);
  const first = list.querySelector(".bulk-row");
  if (first) first.focus();
  return box;
}

function openTagPopover(mode) {
  const n = state.selected.size;
  const orders = countedWord(n, "order");
  const categories = (state.bridge && state.bridge.tagCategories) || {};
  const present = new Set(selectionTags());
  const add = mode === "add";
  // Section 5.2: the remove list is ungrouped, so its one row carries no label.
  const rows = add ? tagRows(categories, null) : [{ id: "on", label: "", tags: [...present] }];
  const known = new Set();
  for (const row of rows) for (const t of row.tags) known.add(t);
  const badge = { total: n, counts: tagCounts(known) };

  openBulkPopover({
    title: (add ? "Add a tag to " : "Remove a tag from ") + orders,
    danger: false,
    fill: (host, onPick) => {
      renderTagList(host, rows, badge, onPick);
      if (!add) return;
      host.appendChild(el("div", "menu-group", "NEW"));
      const input = el("input", "new-tag");
      input.id = "bulk-new-tag";
      input.placeholder = "New tag";
      input.setAttribute("aria-label", "New tag");
      input.addEventListener("keydown", (e) => {
        const tag = input.value.trim();
        if (e.key !== "Enter" || !tag) return;
        const keys = selectedKeys();
        closeBulkPopover();
        state.bridge.addTag(keys, tag);
      });
      host.appendChild(input);
    },
    verb: (tag) => {
      const on = badge.counts.get(tag) || 0;
      if (add) {
        return on === n
          ? { text: "Already on all " + NUMBER.format(n), disabled: true }
          : { text: "Add to " + countedWord(n - on, "order"), disabled: false };
      }
      return { text: "Remove from " + countedWord(on, "order"), disabled: on === 0 };
    },
    onCommit: (tag) => {
      const keys = selectedKeys();
      if (add) state.bridge.addTag(keys, tag);
      else state.bridge.removeTag(keys, tag);
    },
  });
}

// Section 5.3: "the search row shows above 10 rows" -- at exactly ten, no row.
const BULK_SEARCH_ABOVE = 10;

function skuCounts() {
  const counts = new Map();
  for (const o of selectedOrders()) {
    const own = new Set();
    for (const line of o.lines || []) {
      const sku = str(line.SKU).trim();
      if (sku) own.add(sku);
    }
    for (const sku of own) counts.set(sku, (counts.get(sku) || 0) + 1);
  }
  return counts;
}

function openSkuPopover(mode) {
  const n = state.selected.size;
  const badge = { total: n, counts: skuCounts() };
  const skus = [...badge.counts.keys()].sort(
    (a, b) => badge.counts.get(b) - badge.counts.get(a) || a.localeCompare(b)
  );
  const line = mode === "line";

  openBulkPopover({
    title: line
      ? "Remove a SKU from " + theseOrders(n)
      : "Remove whole orders containing a SKU",
    danger: true,
    fill: (host, onPick) => {
      if (skus.length > BULK_SEARCH_ABOVE) {
        const search = el("input", "bulk-search");
        search.id = "bulk-search";
        search.type = "search";
        search.placeholder = "Find a SKU";
        search.setAttribute("aria-label", "Find a SKU");
        search.addEventListener("input", () => {
          const q = search.value.trim().toLowerCase();
          for (const row of host.querySelectorAll(".bulk-row")) {
            row.hidden = q !== "" && !row.dataset.tag.toLowerCase().includes(q);
          }
        });
        host.appendChild(search);
      }
      renderTagList(host, [{ id: "skus", label: "SKUs on these orders", tags: skus }], badge, onPick);
    },
    verb: (sku) => {
      const on = badge.counts.get(sku) || 0;
      return {
        text: (line ? "Remove from " : "Remove ") + countedWord(on, "order"),
        disabled: on === 0,
      };
    },
    onCommit: (sku) => {
      const keys = selectedKeys();
      if (line) state.bridge.removeSkuFromOrders(keys, sku);
      else state.bridge.removeOrdersWithSku(keys, sku);
    },
  });
}

// Mirrors gui/components/toast.py. Two implementations, one appearance --
// change one and change the other (ADR 0007).
const TOAST_MS = 4000;
const TOAST_BADGE_AT = 3;
let toastTimer = null;
let toastRun = 0;
let toastUndoable = false;

function raiseToast(text, undoable) {
  toastRun += 1;
  els.toastText.textContent = text;
  els.toastBadge.hidden = toastRun < TOAST_BADGE_AT;
  els.toastBadge.textContent = String(toastRun);
  toastUndoable = Boolean(undoable);
  updateToastUndo();
  els.toast.hidden = false;
  if (toastTimer !== null) clearTimeout(toastTimer);
  toastTimer = setTimeout(dismissToast, TOAST_MS);
}

// QWebChannel can deliver toastRaised before a same-tick undoAvailable
// property push lands, so results.js also calls this from
// undoAvailableChanged rather than trusting a single read at raise time.
function updateToastUndo() {
  els.toastUndo.hidden = !(toastUndoable && state.bridge && state.bridge.undoAvailable);
}

function dismissToast() {
  if (toastTimer !== null) clearTimeout(toastTimer);
  toastTimer = null;
  toastRun = 0;
  toastUndoable = false;
  els.toast.hidden = true;
}

function bindToast() {
  els.toastUndo.addEventListener("click", () => {
    dismissToast();
    if (state.bridge) state.bridge.undo();
  });
}
