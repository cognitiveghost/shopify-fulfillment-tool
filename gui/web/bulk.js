// The selection bar, its menu, the bulk popover and the toast (Bundle 14).
// The three verbs that remove orders or lines say what will change and confirm
// in the popover; no dialog follows (phase 2 spec section 5.7).
// Loads before results.js: nothing here may name results.js's helpers at the
// top level, only inside a function body.
// Spec: docs/superpowers/specs/2026-09-14-phase9-bundle14-selection-bulk-design.md
"use strict";

function selectedOrders() {
  return state.view.filter((r) => state.selected.has(r.key)).map((r) => r.o);
}

function selectedKeys() {
  return state.view.filter((r) => state.selected.has(r.key)).map((r) => r.key);
}

// Mark fulfillable only means something for an order that is not.
function markableKeys() {
  return state.view.filter((r) => state.selected.has(r.key) && !isFulfillable(r.o)).map((r) => r.key);
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
  if (n === 0) {
    closeSelectionMenu();
    closeBulkPopover();
    return;
  }
  if (bulkKeys && bulkKeys.join("\n") !== selectedKeys().join("\n")) closeBulkPopover();
  els.selectionCount.textContent = NUMBER.format(n) + " selected";
  const markable = markableKeys().length;
  els.selectionMark.textContent = "Mark " + NUMBER.format(markable || n) + " fulfillable";
  els.selectionMark.disabled = markable === 0;
  els.selectionHold.textContent = n === 1 ? "Hold this" : "Hold these " + NUMBER.format(n);
}

function bindSelectionBar() {
  els.selectionMark.addEventListener("click", () => {
    state.bridge.setStatus(markableKeys(), true);
  });
  els.selectionHold.addEventListener("click", () => {
    state.bridge.setStatus(selectedKeys(), false);
  });
  els.selectionMore.addEventListener("click", () => {
    if (els.selectionMenu.hidden) openSelectionMenu();
    else closeSelectionMenu();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest("#selection-menu, #selection-more")) closeSelectionMenu();
    if (!e.target.closest("#bulk-popover, #selection-menu, #selection-more")) closeBulkPopover();
  });
  els.selectionMore.insertAdjacentHTML("beforeend", svg(CHEVRON_DOWN, "glyph"));
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && (state.selected.size || state.cursorKey !== null)) {
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
    { separator: true },
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
    { id: "more-exclude", label: "Exclude " + theseOrders(n) + " from the run", danger: true, run: openExcludePopover },
  ];
}

// The checked orders, or with none checked the order the cursor is on.
function copySelection() {
  const keys = state.selected.size ? selectedKeys() : [state.cursorKey];
  state.bridge.copyText(keys.join("\n"));
  raiseToast(countedWord(keys.length, "order number") + " copied", false);
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
// The checked orders the open popover speaks for. It is the only confirmation
// a removal gets, so it commits these keys and no others, and it closes when
// the checked set or the orders under it change (renderSelectionBar, onOrders).
let bulkKeys = null;

function closeBulkPopover() {
  const open = document.getElementById("bulk-popover");
  if (open) open.remove();
  bulkPicked = null;
  bulkKeys = null;
}

// opts: title, danger, verb(value) -> {text, disabled}, onCommit(value, keys),
// and optionally fill(list, pick) for a picker, prompt (the verb's label
// before a pick) and changes(value) -> string[] for a verb that removes
// something.
function openBulkPopover(opts) {
  closeBulkPopover();
  bulkKeys = selectedKeys();
  const box = el("div", "popover bulk-popover");
  box.id = "bulk-popover";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", opts.title);
  // Never taller than the table under the bar, so the foot stays on screen.
  box.style.maxHeight = Math.max(200, els.tableArea.clientHeight - HEADER_PX - 12) + "px";

  const title = el("div", "bulk-title", opts.title);
  title.id = "bulk-title";

  const body = el("div", "bulk-body");
  body.id = "bulk-body";
  const list = el("div", "bulk-list");
  list.id = "bulk-list";
  list.hidden = !opts.fill;
  const changes = el("div", "bulk-changes");
  changes.id = "bulk-changes";
  changes.hidden = true;
  const hint = el("p", "bulk-hint", "You can undo this from the confirmation that follows.");
  hint.hidden = !opts.changes;
  body.append(list, changes, hint);

  const verb = document.createElement("button");
  verb.type = "button";
  verb.id = "bulk-verb";
  verb.className = "btn " + (opts.danger ? "critical" : "primary");
  verb.textContent = opts.prompt || "";
  verb.disabled = true;
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn secondary";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", closeBulkPopover);
  const footer = el("div", "bulk-footer");
  footer.append(cancel, verb);
  box.append(title, body, footer);

  const pick = (value, row) => {
    bulkPicked = value;
    if (row) {
      for (const other of list.querySelectorAll(".bulk-row")) other.classList.remove("picked");
      row.classList.add("picked");
    }
    const label = opts.verb(value);
    verb.textContent = label.text;
    verb.disabled = label.disabled;
    if (opts.changes) renderBulkChanges(changes, opts.changes(value));
  };
  if (opts.fill) opts.fill(list, pick);

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
    const keys = bulkKeys;
    closeBulkPopover();
    opts.onCommit(value, keys);
  });

  // Under More, which opened it (the anchor is the popover's positioned parent).
  els.selectionMore.parentElement.appendChild(box);
  if (!opts.fill) pick(null, null); // nothing to choose: say what will change at once
  const first = list.querySelector(".bulk-row");
  (first || cancel).focus();
  return box;
}

function renderBulkChanges(host, lines) {
  host.textContent = "";
  host.hidden = false;
  host.append(el("div", "bulk-changes-title", "What will change"));
  for (const line of lines) host.append(el("div", "bulk-change", line));
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
    prompt: "Pick a tag",
    fill: (host, onPick) => {
      renderTagList(host, rows, badge, onPick);
      if (!add) return;
      host.appendChild(el("div", "menu-group", "NEW"));
      const input = el("input", "field new-tag");
      input.id = "bulk-new-tag";
      input.placeholder = "New tag";
      input.setAttribute("aria-label", "New tag");
      input.addEventListener("keydown", (e) => {
        const tag = input.value.trim();
        if (e.key !== "Enter" || !tag) return;
        const keys = bulkKeys;
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
    onCommit: (tag, keys) => {
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

// Up to four order numbers in full; beyond that three and a count.
function orderList(orders) {
  const ids = orders.map((o) => str(o.Order_Number));
  if (ids.length <= 4) return ids.join(", ");
  return ids.slice(0, 3).join(", ") + " and " + NUMBER.format(ids.length - 3) + " more";
}

// `leaving` fulfillable orders drop out of the export.
function exportLine(leaving) {
  const s = (state.bridge && state.bridge.summary) || {};
  const from = num(s.fulfillable) || 0;
  if (leaving === 0) return "Export stays at " + countedWord(from, "order");
  return "Export goes from " + NUMBER.format(from) + " to " + countedWord(from - leaving, "order");
}

function skuLinesOf(o, sku) {
  return (o.lines || []).filter((line) => str(line.SKU).trim() === sku);
}

function unitsOf(lines) {
  return lines.reduce((sum, line) => sum + (num(line.Quantity) || 0), 0);
}

// Only a fulfillable order's SKU lines draw stock (ADR 0010), so only those
// give units back.
function skuRemovalChanges(sku) {
  const hit = selectedOrders().filter((o) => skuLinesOf(o, sku).length);
  if (!hit.length) return ["None of these orders contain " + sku];
  const lines = hit.reduce((sum, o) => sum + skuLinesOf(o, sku).length, 0);
  const emptied = hit.filter((o) => skuLinesOf(o, sku).length === (o.lines || []).length);
  const blocked = hit.filter((o) => !emptied.includes(o) && !isFulfillable(o));
  const units = unitsOf(hit.filter(isFulfillable).flatMap((o) => skuLinesOf(o, sku)));
  const out = [NUMBER.format(lines) + " " + sku + (lines === 1 ? " line" : " lines") + " removed from " + orderList(hit)];
  if (emptied.length) {
    out.push(orderList(emptied) + (emptied.length === 1
      ? " has no lines left and leaves the session"
      : " have no lines left and leave the session"));
  }
  if (units) out.push(countedWord(units, "unit") + " of " + sku + (units === 1 ? " goes" : " go") + " back to stock");
  if (blocked.length) {
    out.push(orderList(blocked) + (blocked.length === 1 ? " stays" : " stay") + " Blocked until marked fulfillable");
  }
  out.push(exportLine(emptied.filter(isFulfillable).length));
  return out;
}

function orderRemovalChanges(hit, sku) {
  if (!hit.length) return ["None of these orders contain " + sku];
  const ready = hit.filter(isFulfillable);
  const units = unitsOf(ready.flatMap((o) => (o.lines || []).filter((line) => str(line.SKU).trim())));
  const out = [orderList(hit) + (hit.length === 1 ? " leaves" : " leave") + " the session: results, export and labels"];
  if (units) {
    out.push(countedWord(units, "unit") + (units === 1 ? " goes" : " go") + " back to stock."
      + " Other orders do not get them until you mark them fulfillable or run the analysis again");
  }
  out.push(exportLine(ready.length));
  return out;
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
    prompt: "Pick a SKU",
    changes: (sku) =>
      line
        ? skuRemovalChanges(sku)
        : orderRemovalChanges(selectedOrders().filter((o) => skuLinesOf(o, sku).length), sku),
    fill: (host, onPick) => {
      if (skus.length > BULK_SEARCH_ABOVE) {
        const search = el("input", "field bulk-search");
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
        text: line ? "Remove " + sku + " from " + NUMBER.format(on) : "Remove " + countedWord(on, "order"),
        disabled: on === 0,
      };
    },
    onCommit: (sku, keys) => {
      if (line) state.bridge.removeSkuFromOrders(keys, sku);
      else state.bridge.removeOrdersWithSku(keys, sku);
    },
  });
}

// Exclude from the run: no picker, so the popover opens already saying what
// will change.
function openExcludePopover() {
  const n = state.selected.size;
  openBulkPopover({
    title: "Exclude " + theseOrders(n) + " from the run",
    danger: true,
    changes: () => orderRemovalChanges(selectedOrders(), ""),
    verb: () => ({ text: "Exclude " + countedWord(n, "order"), disabled: n === 0 }),
    onCommit: (_none, keys) => state.bridge.excludeOrders(keys),
  });
}

// The page's own toast (ADR 0007). It follows the web kit; the Qt toast in
// shared/components/toast.py keeps its look until its screens move.
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
  els.toastDismiss.innerHTML = svg(X_MARK, "glyph");
  els.toastDismiss.addEventListener("click", dismissToast);
}
