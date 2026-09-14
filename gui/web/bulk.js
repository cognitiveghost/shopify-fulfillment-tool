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
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && state.selected.size) {
      const t = document.activeElement;
      if (t && t.matches && t.matches("input, textarea")) return;
      e.preventDefault();
      copySelection();
    }
  });
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

// Task 6/7/8 replace these with the real popovers and toast.
function closeBulkPopover() {}
function openTagPopover() {}
function openSkuPopover() {}
function raiseToast() {}
