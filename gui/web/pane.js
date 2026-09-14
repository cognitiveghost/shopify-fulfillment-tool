// The order detail pane (Bundle 13 spec §6.2-6.7): the cursor order's
// identity, verdict, lines, tags, notes and actions. One order, never the
// multi-selection. No optimistic updates: it changes when `orders` comes back.
"use strict";

const RUN_SOURCE = "Detected by the run, not set by a person.";
const HAND_SOURCE = "Set by a person, not detected by the run.";
const CHEVRON_RIGHT = "m9 18 6-6-6-6";
const CHEVRON_LEFT = "m15 18-6-6 6-6";
const FLAG_CHIPS = [["_repeat", "Repeat"], ["Unknown_SKU", "Unknown SKU"], ["Low_Stock", "Low stock"]];
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
  if (hit) {
    head.append(
      el("span", "pane-order", str(hit.o.Order_Number)),
      el("span", "pane-age", ageMs(hit.o.Created_At) === null ? "" : fmtAge(hit.o.Created_At) + " old"),
    );
  }
  head.append(el("span", "spacer"));
  if (hit) head.append(el("span", "pane-position", NUMBER.format(hit.index + 1) + " of " + NUMBER.format(state.view.length)));
  const hide = paneButton("ghost icon pane-icon", undefined, "Hide the pane");
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
  pane.append(paneWho(o), paneVerdict(o), paneNumbers(o), paneLines(o), paneTags(o), paneNotes(o), paneActions(o));
}

function paneWho(o) {
  const parts = [o.Customer, o.Destination_Country, o.Shipping_Provider].map((v) => str(v).trim()).filter(Boolean);
  return el("div", "pane-who", parts.length ? parts.join(" · ") : DASH);
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

function paneNumbers(o) {
  const parts = [plural((o.lines || []).length, "line"), plural(num(o.Units) || 0, "unit")];
  if (num(o.Total_Price) !== null) parts.push(fmtMoney(o.Total_Price));
  return el("div", "pane-numbers", parts.join(" · "));
}

function paneLines(o) {
  const order = str(o.Order_Number);
  const box = el("div", "lines");
  const head = el("div", "line line-head");
  for (const [text, cls] of [["SKU", ""], ["Product", ""], ["Want", " num"], ["Left", " num"], ["", ""]]) {
    head.append(el("span", "line-cell" + cls, text));
  }
  box.append(head);
  (o.lines || []).forEach((line, index) => {
    const sku = str(line.SKU);
    const row = el("div", "line" + (line.Short ? " short" : ""));
    row.dataset.index = String(index);
    const product = el("span", "line-cell product", str(line.Product_Name) || DASH);
    product.title = str(line.Product_Name);
    const more = paneButton("ghost icon line-menu-button", "⋯", "Actions for this line");
    more.addEventListener("click", () => openPaneMenu(more, "line-menu", [
      ["Remove this line", () => state.bridge.removeLine(order, index, sku)],
      ["Copy SKU", () => state.bridge.copyText(sku)],
    ]));
    const actions = el("span", "line-cell");
    actions.append(more);
    row.append(el("span", "line-cell sku", sku || DASH), product,
      el("span", "line-cell num", fmtInt(line.Quantity)), el("span", "line-cell num", fmtInt(line.Final_Stock)), actions);
    box.append(row);
  });
  return box;
}

function paneTags(o) {
  const order = str(o.Order_Number);
  const box = el("div", "pane-tags");
  for (const [field, label] of FLAG_CHIPS) if (o[field] === true) box.append(el("span", "flag-chip", label));
  for (const tag of (o.Tag_List || []).map(String)) {
    const chip = paneButton("", tag + "  ×", "Remove tag " + tag);
    chip.className = "chip-filter tag-chip";
    chip.dataset.tag = tag;
    chip.addEventListener("click", () => state.bridge && state.bridge.removeOrderTag(order, tag));
    box.append(chip);
  }
  const add = paneButton("ghost small", "+ Tag");
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

// Never a primary: the screen's one primary is Export (§6.6).
function paneActions(o) {
  const order = str(o.Order_Number);
  const fulfillable = isFulfillable(o);
  const box = el("div", "pane-actions");
  const verb = paneButton("secondary", fulfillable ? "Hold" : "Mark fulfillable");
  verb.id = "pane-status-verb";
  verb.addEventListener("click", () => {
    if (!state.bridge) return;
    if (fulfillable) state.bridge.holdOrder(order);
    else state.bridge.fulfillOrder(order);
  });
  const exclude = paneButton("danger", "Exclude from run");
  exclude.id = "pane-exclude";
  exclude.addEventListener("click", () => state.bridge && state.bridge.excludeOrder(order));
  const more = paneButton("ghost icon", "⋯", "More actions for this order");
  more.id = "pane-more";
  more.addEventListener("click", () => openPaneMenu(more, "order-menu", [
    ["Copy order number", () => state.bridge.copyText(order)],
  ]));
  box.append(verb, exclude, more);
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

function menuItem(label, act) {
  const item = el("button", "menu-item", label);
  item.type = "button";
  item.setAttribute("role", "menuitem");
  item.addEventListener("click", () => {
    closePaneMenus();
    if (state.bridge) act();
  });
  return item;
}

function openPaneMenu(anchor, id, items) {
  const menu = newMenu(id);
  for (const [label, act] of items) menu.append(menuItem(label, act));
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
  const input = el("input", "new-tag");
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
  els.paneShow.innerHTML = svg(CHEVRON_LEFT, "glyph");
  els.paneShow.addEventListener("click", showPane);
  els.pane.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !els.pane.querySelector(".pane-menu")) return;
    e.stopPropagation();
    closePaneMenus();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest(".pane-menu, .line-menu-button, #pane-add-tag, #pane-more")) closePaneMenus();
  });
}
