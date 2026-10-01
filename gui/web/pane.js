// The order detail pane (phase 2 spec section 5.9): the cursor order's
// header, verdict, reason codes, lines, tags, notes and footer. One order,
// never the checked set. No optimistic updates: it changes when `orders`
// comes back.
"use strict";

const RUN_SOURCE = "Detected by the run, not set by a person.";
const HAND_SOURCE = "Set by a person, not detected by the run.";
const CHEVRON_RIGHT = "m9 18 6-6-6-6";
const CHEVRON_LEFT = "m15 18-6-6 6-6";
const FLAG_CODES = [["_repeat", "REPEAT_CUSTOMER"], ["Unknown_SKU", "UNKNOWN_SKU"], ["Low_Stock", "LOW_STOCK"]];
const PROBLEM_CODES = {
  short: "STOCK_SHORT",
  out_of_stock: "OUT_OF_STOCK",
  invalid_quantity: "INVALID_QUANTITY",
  no_sku: "NO_SKU",
  rule_hold: "HELD_BY_RULE",
  other: "OTHER",
};
const MENU_WIDTH = 220;
let paneMenuOpener = null;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function paneButton(cls, text, label) {
  const b = el("button", "btn " + cls, text);
  b.type = "button";
  if (label) {
    b.setAttribute("aria-label", label);
    b.title = label;
  }
  return b;
}

function problemSentence(p) {
  if (p.code === "short") {
    return "There were " + NUMBER.format(p.have) + " units of " + p.sku +
      " left for this order, and it wants " + NUMBER.format(p.need) + ".";
  }
  if (p.code === "out_of_stock") return p.sku + " had none left.";
  if (p.code === "invalid_quantity") return p.sku + " has no valid quantity in the orders file.";
  if (p.code === "no_sku") {
    return p.lines === 1
      ? "1 line has no SKU, so no stock can be matched to it."
      : NUMBER.format(p.lines) + " lines have no SKU, so no stock can be matched to them.";
  }
  if (p.code === "rule_hold") return "Rule “" + p.rule + "” held this order.";
  const text = str(p.text).trim();
  return /[.!?]$/.test(text) ? text : text + ".";
}

// One template per reason code, with the run's numbers in it (§6.3).
function verdictCopy(o) {
  const v = o.Verdict || { state: "ready", by_hand: false, problems: [] };
  const lines = o.lines || [];
  const n = lines.length;
  const k = lines.filter((line) => line.Short).length;
  const sentences = (v.problems || []).map(problemSentence).join(" ");
  if (v.state === "ready") {
    const value = num(o.Total_Price) === null ? "" : ", " + fmtMoney(o.Total_Price);
    const opening = n === 1
      ? "Its one line is in stock and reserved for this order."
      : "All " + NUMBER.format(n) + " lines are in stock and reserved for this order.";
    return { role: "success", title: "Ships complete", source: "",
      text: opening + " One parcel, " + plural(num(o.Units) || 0, "unit") + value + ". Nothing is waiting on anyone." };
  }
  if (v.state === "short") {
    const rest = n - k === 1 ? " The other line is covered."
      : n > k ? " The other " + NUMBER.format(n - k) + " lines are covered." : "";
    return { role: "danger", source: "", text: sentences + rest,
      title: "Cannot ship: " + NUMBER.format(k) + " of " + plural(n, "line") + (k === 1 ? " is short" : " are short") };
  }
  if (!v.by_hand && (v.problems || []).some((p) => p.code === "rule_hold")) {
    return { role: "warning", title: "Held by a rule", source: RUN_SOURCE,
      text: sentences + " Change the rule, or mark the order fulfillable if it should ship." };
  }
  if (!v.by_hand) return { role: "warning", title: "Fix the data before this ships", text: sentences, source: RUN_SOURCE };
  if (isFulfillable(o)) {
    return { role: "warning", title: "Marked fulfillable by hand", source: HAND_SOURCE,
      text: "The run could not ship it. " + sentences + " Someone marked it fulfillable anyway." };
  }
  return { role: "warning", title: "On hold", source: HAND_SOURCE,
    text: "Nothing in this order is short now. It stays blocked until someone marks it fulfillable." };
}

function paneRecord() {
  if (state.cursorKey === null) return null;
  const index = state.view.findIndex((r) => r.key === state.cursorKey);
  return index < 0 ? null : { o: state.view[index].o, index: index };
}

function renderPane() {
  const pane = els.pane;
  pane.textContent = ""; // also drops any open pane menu
  const hit = paneRecord();

  const head = el("div", "pane-head");
  const title = el("span", "pane-title", hit ? "Order " : "Order detail");
  if (hit) title.append(el("span", "pane-order", str(hit.o.Order_Number)));
  head.append(title);
  if (hit) head.append(statusBadge(hit.o));
  const hide = paneButton("ghost icon compact", undefined, "Hide detail");
  hide.id = "pane-hide";
  hide.innerHTML = svg(CHEVRON_RIGHT, "glyph");
  hide.addEventListener("click", hidePane);
  head.append(hide);
  pane.append(head);

  if (!hit) {
    const empty = el("div", "pane-empty");
    empty.id = "pane-empty";
    empty.append(
      el("p", "state-title", "No order selected"),
      el("p", "state-text", "Click a row to see whether it can ship and, if it cannot, why. ↑ ↓ moves through the " +
        NUMBER.format(state.view.length) + " shown."),
    );
    pane.append(empty);
    return;
  }
  const o = hit.o;
  const body = el("div", "pane-body");
  body.append(paneVerdict(o), paneMeta(o), paneCodes(o), paneLines(o), paneTags(o), paneNotes(o));
  pane.append(body, paneFooter(o, hit.index));
}

function paneVerdict(o) {
  const v = o.Verdict || {};
  const copy = verdictCopy(o);
  const box = el("div", "verdict");
  box.dataset.state = v.state || "ready";
  box.dataset.role = copy.role;
  box.dataset.byHand = String(Boolean(v.by_hand));
  const title = el("div", "verdict-title");
  // The mark: hollow when the run detected it, solid when a person set it.
  title.append(el("span", "mark" + (v.by_hand ? " solid" : "")), document.createTextNode(copy.title));
  box.append(title, el("p", "verdict-text", copy.text));
  if (copy.source) box.append(el("p", "verdict-source", copy.source));
  return box;
}

function paneMeta(o) {
  const parts = [o.Customer, o.Destination_Country, o.Shipping_Provider].map((v) => str(v).trim()).filter(Boolean);
  if (ageMs(o.Created_At) !== null) parts.push(fmtAge(o.Created_At) + " old");
  if (num(o.Total_Price) !== null) parts.push(fmtMoney(o.Total_Price));
  return el("div", "pane-meta", parts.length ? parts.join(" · ") : DASH);
}

// The verdict's causes as machine words, then the order's flags.
function reasonCodes(o) {
  const v = o.Verdict || { state: "ready", by_hand: false, problems: [] };
  const codes = [];
  if (v.state === "ready") codes.push("ALL_LINES_IN_STOCK");
  if (v.by_hand) codes.push(isFulfillable(o) ? "MARKED_FULFILLABLE" : "HELD_BY_USER");
  for (const p of v.problems || []) codes.push(PROBLEM_CODES[p.code] || PROBLEM_CODES.other);
  for (const [field, code] of FLAG_CODES) if (o[field] === true) codes.push(code);
  return [...new Set(codes)];
}

function paneCodes(o) {
  const box = el("div", "pane-codes");
  for (const code of reasonCodes(o)) box.append(el("span", "code", code));
  return box;
}

// What the run saw for a short line; stock left for every other.
function stockSentence(o, line) {
  if (line.Short) {
    const sku = str(line.SKU);
    const p = ((o.Verdict && o.Verdict.problems) || []).find((x) => x.sku === sku);
    if (p && p.code === "short") {
      return { short: true, text: NUMBER.format(p.have) + " of " + NUMBER.format(p.need) +
        " in stock, short " + NUMBER.format(p.need - p.have) };
    }
    return { short: true, text: "None in stock" };
  }
  const left = num(line.Final_Stock);
  return left === null ? null : { short: false, text: NUMBER.format(left) + " left in stock" };
}

// The run writes "1" where the stock file has no lot; that is not a label.
function lotWord(value) {
  const text = str(value).trim();
  return text === "1" ? "" : text;
}

// One caption per lot. A cell read back from disk as text is shown as it is.
function lotTexts(line) {
  const lots = line.Lot_Details;
  if (!lots) return [];
  if (!Array.isArray(lots)) return [str(lots)];
  const real = lots.filter((lot) => lot && typeof lot === "object");
  return real.map((lot) => {
    const parts = [];
    if (lotWord(lot.batch)) parts.push("Lot " + lotWord(lot.batch));
    if (lotWord(lot.expiry)) parts.push("exp " + lotWord(lot.expiry));
    if (parts.length && real.length > 1 && num(lot.qty_allocated) !== null) {
      parts.push("×" + NUMBER.format(lot.qty_allocated));
    }
    return parts.join(" · ");
  }).filter(Boolean);
}

function paneLines(o) {
  const order = str(o.Order_Number);
  const lines = o.lines || [];
  const wrap = el("div", "pane-lines");
  wrap.append(el("div", "pane-numbers", plural(lines.length, "line") + " · " + plural(num(o.Units) || 0, "unit")));
  const box = el("div", "lines");
  lines.forEach((line, index) => {
    const sku = str(line.SKU);
    const row = el("div", "line" + (line.Short ? " short" : ""));
    row.dataset.index = String(index);
    const main = el("div", "line-main");
    const top = el("div", "line-top");
    top.append(el("span", "line-sku", sku || DASH), el("span", "line-qty", "× " + fmtInt(line.Quantity)));
    main.append(top);
    if (str(line.Product_Name)) {
      const product = el("div", "line-product", str(line.Product_Name));
      product.title = str(line.Product_Name);
      main.append(product);
    }
    const stock = stockSentence(o, line);
    if (stock) main.append(el("div", "line-stock" + (stock.short ? " short" : ""), stock.text));
    for (const text of lotTexts(line)) main.append(el("div", "line-lot", text));
    const more = paneButton("ghost icon compact line-menu-button", "⋯", "Actions for this line");
    more.addEventListener("click", () => openPaneMenu(more, "line-menu", [
      ["Remove this line", () => state.bridge.removeLine(order, index, sku),
        lines.length < 2 ? "Last line: exclude the order instead" : ""],
      ["Change quantity…", () => openQtyMenu(more, order, index, sku, line.Quantity)],
      ["Copy SKU", () => state.bridge.copyText(sku)],
    ]));
    row.append(main, more);
    box.append(row);
  });
  wrap.append(box);
  return wrap;
}

function paneTags(o) {
  const order = str(o.Order_Number);
  const box = el("div", "pane-tags");
  for (const tag of (o.Tag_List || []).map(String)) {
    const chip = paneButton("", tag + "  ×", "Remove tag " + tag);
    chip.className = "chip-filter tag-chip";
    chip.dataset.tag = tag;
    chip.addEventListener("click", () => state.bridge && state.bridge.removeOrderTag(order, tag));
    box.append(chip);
  }
  const add = paneButton("ghost compact", "+ Tag");
  add.id = "pane-add-tag";
  add.addEventListener("click", () => openTagMenu(add, o));
  box.append(add);
  return box;
}

function paneNotes(o) {
  const parts = [str(o.Notes).trim(), str(o.Status_Note).trim()].filter(Boolean);
  if (str(o.Tags).trim()) parts.push("Shopify tags: " + str(o.Tags).trim());
  return el("p", "pane-notes", parts.length ? parts.join("\n") : "No notes on this order.");
}

// Never a primary: the screen's one primary is Export. Copy order number
// left with its menu: Ctrl+C copies the cursor's order (bulk.js).
function paneFooter(o, index) {
  const order = str(o.Order_Number);
  const fulfillable = isFulfillable(o);
  const box = el("div", "pane-actions");
  const verb = paneButton("secondary compact", fulfillable ? "Hold" : "Mark fulfillable");
  verb.id = "pane-status-verb";
  verb.addEventListener("click", () => {
    if (!state.bridge) return;
    if (fulfillable) state.bridge.holdOrder(order);
    else state.bridge.fulfillOrder(order);
  });
  const exclude = paneButton("ghost danger compact", "Exclude order");
  exclude.id = "pane-exclude";
  exclude.addEventListener("click", () => state.bridge && state.bridge.excludeOrder(order));
  const position = el("span", "pane-position",
    "↑ ↓  " + NUMBER.format(index + 1) + " / " + NUMBER.format(state.view.length));
  box.append(verb, exclude, position);
  return box;
}

// Spec 6.5: Esc, an outside click, or a choice all return focus to the opener.
// newMenu() passes restoreFocus=false -- it closes only to replace, and placeMenu
// focuses the new menu's first item straight after.
function closePaneMenus(restoreFocus = true) {
  const menus = els.pane.querySelectorAll(".pane-menu");
  if (!menus.length) return;
  for (const menu of menus) menu.remove();
  if (restoreFocus && paneMenuOpener && paneMenuOpener.isConnected) paneMenuOpener.focus();
  paneMenuOpener = null;
}

// Menus open upward inside the pane, which clips anything outside it.
function placeMenu(menu, anchor) {
  const pane = els.pane.getBoundingClientRect();
  const a = anchor.getBoundingClientRect();
  menu.style.left = Math.max(0, Math.min(a.left - pane.left, pane.width - MENU_WIDTH - 8)) + "px";
  menu.style.bottom = Math.round(pane.bottom - a.top + 4) + "px";
  els.pane.append(menu);
  paneMenuOpener = anchor;
  const first = menu.querySelector(".menu-item, input");
  if (first) first.focus();
}

function newMenu(id) {
  closePaneMenus(false);
  const menu = el("div", "menu pane-menu");
  menu.id = id;
  menu.setAttribute("role", "menu");
  return menu;
}

function menuItem(label, act, disabledTitle) {
  const item = el("button", "menu-item", label);
  item.type = "button";
  item.setAttribute("role", "menuitem");
  if (disabledTitle) {
    item.disabled = true;
    item.title = disabledTitle;
  }
  item.addEventListener("click", () => {
    closePaneMenus();
    if (state.bridge) act();
  });
  return item;
}

function openPaneMenu(anchor, id, items) {
  const menu = newMenu(id);
  for (const [label, act, disabledTitle] of items) menu.append(menuItem(label, act, disabledTitle));
  placeMenu(menu, anchor);
}

function openTagMenu(anchor, o) {
  const order = str(o.Order_Number);
  const own = new Set((o.Tag_List || []).map(String));
  const categories = (state.bridge && state.bridge.tagCategories) || {};
  const menu = newMenu("tag-menu");
  renderTagList(menu, tagRows(categories, own), null, (tag) => {
    closePaneMenus();
    if (state.bridge) state.bridge.addOrderTag(order, tag);
  });
  const input = el("input", "field new-tag");
  input.id = "new-tag";
  input.placeholder = "New tag";
  input.setAttribute("aria-label", "New tag");
  input.addEventListener("keydown", (e) => {
    const tag = input.value.trim();
    if (e.key !== "Enter" || !tag) return;
    closePaneMenus();
    if (state.bridge) state.bridge.addOrderTag(order, tag);
  });
  menu.append(input);
  placeMenu(menu, anchor);
}

// Change quantity (spec 2026-09-28 §4.5): the page's own number entry, as the
// tag menu's "New tag" -- actions_handler holds no Qt input dialog. Only a
// whole number from 1 that differs from the line's own is sent.
function openQtyMenu(anchor, order, index, sku, current) {
  const own = num(current);
  const menu = newMenu("qty-menu");
  const input = el("input", "field new-tag");
  input.id = "line-qty";
  input.type = "number";
  input.min = "1";
  input.step = "1";
  input.value = own === null ? "" : String(own);
  input.setAttribute("aria-label", "Quantity");
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const n = input.value.trim() === "" ? NaN : Number(input.value);
    closePaneMenus();
    if (Number.isInteger(n) && n >= 1 && n !== own && state.bridge) {
      state.bridge.changeLineQuantity(order, index, sku, n);
    }
  });
  menu.append(input);
  placeMenu(menu, anchor);
}

function hidePane() {
  state.paneHidden = true;
  state.paneForced = false;
  render();
  els.paneShow.focus();
}

function showPane() {
  state.paneHidden = false;
  if (state.narrow) state.paneForced = true; // the table scrolls sideways instead
  render();
  const hide = document.getElementById("pane-hide");
  if (hide) hide.focus();
}

function bindPane() {
  els.paneShow.insertAdjacentHTML("afterbegin", svg(CHEVRON_LEFT, "glyph"));
  els.paneShow.addEventListener("click", showPane);
  els.pane.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !els.pane.querySelector(".pane-menu")) return;
    e.stopPropagation();
    closePaneMenus();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest(".pane-menu, .line-menu-button, #pane-add-tag")) closePaneMenus();
  });
}
