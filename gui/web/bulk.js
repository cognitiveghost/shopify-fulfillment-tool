// The selection bar, its menu, the bulk popover and the toast (Bundle 14).
// Loads before results.js: nothing here may name results.js's helpers at the
// top level, only inside a function body.
// Spec: docs/superpowers/specs/2026-09-14-phase9-bundle14-selection-bulk-design.md
"use strict";

const SELECTION_BAR_PX = 44;

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
  els.selectionMark.textContent = n === 1 ? "Mark fulfillable" : "Mark " + n + " fulfillable";
  els.selectionHold.textContent = n === 1 ? "Hold" : "Hold these " + n;
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
  // selection before this can close just the popover.
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Escape" || !document.getElementById("bulk-popover")) return;
      e.stopPropagation();
      closeBulkPopover();
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
      title: tagged ? "" : "None of these " + orders + " carry a tag",
      run: () => openTagPopover("remove"),
    },
    { id: "more-copy", label: "Copy " + countedWord(n, "order number"), hint: "Ctrl+C", run: copySelection },
    { id: "more-export-xlsx", label: "Export just these " + n + " to Excel", run: () => exportSelectionAs("xlsx") },
    { id: "more-export-csv", label: "Export just these " + n + " to CSV", run: () => exportSelectionAs("csv") },
    { separator: true },
    { id: "more-remove-sku", label: "Remove a SKU from these " + orders, danger: true, run: () => openSkuPopover("line") },
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

function renderTagList(host, rows, counts, onPick) {
  for (const row of rows) {
    host.appendChild(el("div", "menu-group", row.label));
    for (const tag of row.tags) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "menu-item bulk-row";
      button.dataset.tag = tag;
      button.appendChild(document.createTextNode(tag));
      const on = counts ? counts.get(tag) || 0 : 0;
      if (on) button.appendChild(el("span", "bulk-count", "on " + on + " of " + counts.get("__total__")));
      button.addEventListener("click", () => onPick(tag, button));
      host.appendChild(button);
    }
  }
}

function tagCounts(tags) {
  const counts = new Map();
  const orders = selectedOrders();
  counts.set("__total__", orders.length);
  for (const o of orders) {
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
  const rows = add ? tagRows(categories, null) : [{ id: "on", label: "On these orders", tags: [...present] }];
  const known = new Set();
  for (const row of rows) for (const t of row.tags) known.add(t);
  const counts = tagCounts(known);

  openBulkPopover({
    title: (add ? "Add a tag to " : "Remove a tag from ") + orders,
    danger: false,
    fill: (host, onPick) => {
      renderTagList(host, rows, counts, onPick);
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
      const on = counts.get(tag) || 0;
      if (add) {
        return on === n
          ? { text: "Already on all " + n, disabled: true }
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

// Task 7/8 replace these with the real popover and toast.
function openSkuPopover() {}
function raiseToast() {}
