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
}

// Tasks 5 and 6 replace these with the real menu and popover.
function closeSelectionMenu() {}
function closeBulkPopover() {}
