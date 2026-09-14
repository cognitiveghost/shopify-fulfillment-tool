// The column registry (Bundle 13 spec §6.8). Keys are persisted per client,
// so never rename one. Python stores only names; titles, groups, defaults and
// pinning live here. Loaded before results.js: nothing at top level may call
// into it, only function bodies.
"use strict";

const COLUMN_GROUPS = ["Order", "Customer", "Money", "Shipping", "Tags & notes", "Other"];

const REGISTRY = [
  { key: "status", title: "Status", group: "Order", width: 132, pinned: true, shown: true,
    text: (o) => (isFulfillable(o) ? FULFILLABLE : "Blocked"), sortValue: (o) => (isFulfillable(o) ? 0 : 1) },
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

function renderColumnsPanel() {} // Task 9
function bindColumns() {} // Task 9
