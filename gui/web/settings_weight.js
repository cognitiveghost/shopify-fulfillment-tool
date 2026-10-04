// The Weight page (phase 9 spec section 5): the divisor, the products table
// and the boxes table. settings.js renders and routes; this file draws what
// bridge.state holds under `weight`. Python holds every value and words every
// sentence (gui/settings/weight_state.py).
//
// Loaded before settings.js: it uses that file's helpers, but only once the
// page runs.
"use strict";

// One field of a products or boxes row. `kind` is "product" or "box".
function weightField(kind, row, name, label, cls) {
  const invalid = row.invalid.includes(name) ? " invalid" : "";
  const mode = name === "l" || name === "w" || name === "h" ? ` inputmode="decimal"` : "";
  return `<input class="field ${cls}${invalid}" type="text"${mode} value="${esc(row[name])}" aria-label="${label}" data-input="${kind}_text" data-uid="${row.uid}" data-name="${name}" data-key="${kind}-${row.uid}-${name}">`;
}

// Under a row: what blocks the save, else what the operator should know.
function weightBelow(row) {
  if (row.problem) return problemLine(row.problem, "", "weight-below");
  return row.hint ? `<span class="hint weight-below">${esc(row.hint)}</span>` : "";
}

function productRow(row) {
  const key = `product-${row.uid}`;
  return `<div class="weight-row product-row" data-product="${row.uid}" data-key="${key}">
    ${weightField("product", row, "sku", "SKU", "mono weight-first")}
    ${weightField("product", row, "name", "Name", "")}
    ${weightField("product", row, "l", "Length in cm", "mono amount")}
    ${weightField("product", row, "w", "Width in cm", "mono amount")}
    ${weightField("product", row, "h", "Height in cm", "mono amount")}
    <span class="weight-value mono">${esc(row.weight)}</span>
    <button class="switch" type="button" role="switch" aria-checked="${Boolean(row.no_packaging)}" aria-label="No packaging" data-act="product-no-packaging" data-uid="${row.uid}" data-key="${key}-no-packaging"><span class="switch-knob"></span></button>
    <button class="btn ghost compact icon" type="button" title="Remove product" aria-label="Remove product" data-act="product-remove" data-uid="${row.uid}" data-key="${key}-remove">${svg(GLYPH.x, "glyph")}</button>
    ${weightBelow(row)}
  </div>`;
}

function boxRow(row) {
  const key = `box-${row.uid}`;
  return `<div class="weight-row box-row" data-box="${row.uid}" data-key="${key}">
    ${weightField("box", row, "name", "Box name", "weight-first")}
    ${weightField("box", row, "l", "Length in cm", "mono amount")}
    ${weightField("box", row, "w", "Width in cm", "mono amount")}
    ${weightField("box", row, "h", "Height in cm", "mono amount")}
    <span class="weight-value mono">${esc(row.weight)}</span>
    <button class="btn ghost compact icon" type="button" title="Remove box" aria-label="Remove box" data-act="box-remove" data-uid="${row.uid}" data-key="${key}-remove">${svg(GLYPH.x, "glyph")}</button>
    ${weightBelow(row)}
  </div>`;
}

function weightHeads(heads, cls) {
  return `<div class="weight-row weight-heads ${cls}">${heads.map((head) => `<span>${esc(head)}</span>`).join("")}<span></span></div>`;
}

function productsCard(p) {
  const open = view.menu === "products-import";
  const item = (kind, label, key) =>
    `<button class="menu-item" type="button" role="menuitem" data-act="weight-import" data-kind="${kind}" data-key="${key}"><span class="menu-label">${label}</span></button>`;
  const menu = open
    ? `<div class="menu add-menu" role="menu">
        ${item("products-stock", "SKUs from a stock CSV…", "products-import-stock")}
        ${item("products-dims", "Dimensions from a CSV…", "products-import-dims")}
      </div>`
    : "";
  const actions = `<div class="card-actions">
      <div class="menu-anchor">
        <button class="btn secondary" type="button" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="products-import" data-key="products-import">Import${svg(GLYPH.chevron, "glyph")}</button>
        ${menu}
      </div>
      <button class="btn secondary" type="button" data-act="weight-export" data-kind="products" data-key="products-export"${off(!p.can_export)}>Export</button>
      <button class="btn secondary" type="button" data-act="product-add" data-key="product-add">${svg(GLYPH.plus, "glyph")}Add product</button>
    </div>`;
  const body = p.empty
    ? `<div class="card-empty">${esc(p.empty)}</div>`
    : `<div class="list-bar">
        <label class="input list-filter">${svg(RULE_GLYPH.search, "glyph")}<input type="text" value="${esc(p.filter)}" placeholder="${esc(p.filter_placeholder)}" aria-label="${esc(p.filter_placeholder)}" data-input="product_filter" data-key="products-filter"></label>
        <span class="spacer"></span>
        <span class="list-count">${esc(p.count)}</span>
      </div>
      ${weightHeads(p.heads, "product-row")}
      <div class="product-rows">${p.rows.map(productRow).join("")}</div>
      ${p.no_hits ? `<div class="list-none">${esc(p.no_hits)}</div>` : ""}
      ${p.more ? `<div class="list-more">${esc(p.more)}</div>` : ""}`;
  return `<section class="card" data-card="products">
    ${cardHead("Products", esc(p.text), actions)}
    ${body}
  </section>`;
}

function boxesCard(b) {
  const actions = `<div class="card-actions">
      <button class="btn secondary" type="button" data-act="weight-import" data-kind="boxes" data-key="boxes-import">Import…</button>
      <button class="btn secondary" type="button" data-act="weight-export" data-kind="boxes" data-key="boxes-export"${off(!b.can_export)}>Export</button>
      <button class="btn secondary" type="button" data-act="box-add" data-key="box-add">${svg(GLYPH.plus, "glyph")}Add box</button>
    </div>`;
  const body = b.empty
    ? `<div class="card-empty">${esc(b.empty)}</div>`
    : `${weightHeads(b.heads, "box-row")}
      <div class="box-rows">${b.rows.map(boxRow).join("")}</div>`;
  return `<section class="card" data-card="boxes">
    ${cardHead("Boxes", esc(b.text), actions)}
    ${body}
    <div class="card-note"><span class="hint">${esc(b.note)}</span></div>
  </section>`;
}

function weightPage(w) {
  const d = w.divisor;
  return `<section class="card" data-card="divisor">
    ${cardHead("Volumetric weight", "")}
    <div class="card-row" data-row="divisor">
      <span class="card-label">Divisor</span>
      <div class="card-control">
        <div class="control-line"><input class="field mono divisor${d.problem ? " invalid" : ""}" type="text" inputmode="numeric" value="${esc(d.value)}" aria-label="Divisor" data-input="divisor" data-key="divisor"><span>${esc(d.unit)}</span></div>
        ${below(d.problem, d.hint)}
      </div>
    </div>
  </section>
  ${productsCard(w.products)}
  ${boxesCard(w.boxes)}`;
}

// Whether the click was one of this page's.
function weightClick(data, el, bridge) {
  switch (data.act) {
    case "product-add":
      // The new product is the first row: focus its SKU once it arrives.
      view.pending = "@css:.product-rows .product-row .weight-first";
      bridge.edit("product_add", []);
      return true;
    case "product-remove":
      view.pending = "product-add";
      bridge.edit("product_remove", [data.uid]);
      return true;
    case "product-no-packaging":
      bridge.edit("product_no_packaging", [data.uid, el.getAttribute("aria-checked") !== "true"]);
      return true;
    case "box-add":
      // The new box is the last row.
      view.pending = "@css:.box-rows .box-row:last-child .weight-first";
      bridge.edit("box_add", []);
      return true;
    case "box-remove":
      view.pending = "box-add";
      bridge.edit("box_remove", [data.uid]);
      return true;
    case "weight-import":
      closeMenu();
      bridge.importFile(data.kind);
      return true;
    case "weight-export":
      bridge.exportFile(data.kind);
      return true;
  }
  return false;
}

// Whether the keystroke was in one of this page's fields.
function weightInput(data, el, bridge) {
  switch (data.input) {
    case "divisor":
      bridge.edit("divisor", [el.value]);
      return true;
    case "product_filter":
      bridge.edit("product_filter", [el.value]);
      return true;
    case "product_text":
      bridge.edit("product_text", [data.uid, data.name, el.value]);
      return true;
    case "box_text":
      bridge.edit("box_text", [data.uid, data.name, el.value]);
      return true;
  }
  return false;
}
