// The Sets page (phase 9 spec section 4). settings.js renders and routes;
// this file draws what bridge.state holds under `sets` and turns a click or a
// keystroke there into bridge.edit(action, args). Python holds every set and
// words every sentence (gui/settings/sets_state.py).
//
// Loaded after settings_rules.js and before settings.js: it uses their
// helpers (esc, svg, off, problemLine, GLYPH, RULE_GLYPH), but only once the
// page runs. The list's filter is a data-input="filter" field, which
// settings_rules.js reports as edit("filter", [text]).
"use strict";

// The open row's name field, whatever its uid: where focus goes after Add.
const OPEN_NAME = "@css:.list-row.open .list-name-field";

function setEditor(row) {
  const e = row.editor;
  const uid = row.uid;
  const key = `set-${uid}`;
  const components = e.components
    .map(
      (part, c) => `<div class="list-part" data-comp="${c}">
        <div class="comp-row">
          <input class="field mono" type="text" value="${esc(part.sku)}" placeholder="Component SKU" aria-label="Component SKU" data-input="comp_sku" data-uid="${uid}" data-c="${c}" data-key="${key}-c${c}-sku">
          <span class="times">×</span>
          <input class="field mono amount${part.invalid ? " invalid" : ""}" type="text" inputmode="numeric" value="${esc(part.quantity)}" aria-label="Quantity" data-input="comp_quantity" data-uid="${uid}" data-c="${c}" data-key="${key}-c${c}-quantity">
          <button class="btn ghost compact icon" type="button" title="Remove component" aria-label="Remove component" data-act="comp-remove" data-uid="${uid}" data-c="${c}" data-key="${key}-c${c}-remove">${svg(GLYPH.x, "glyph")}</button>
        </div>
        ${part.problem ? problemLine(part.problem) : ""}
      </div>`,
    )
    .join("");
  return `<div class="list-editor">
    ${e.sku_problem ? problemLine(e.sku_problem) : ""}
    <div class="editor-line">
      <span class="editor-label">Components</span>
      <div class="editor-content">
        ${components}
        ${e.components_problem ? problemLine(e.components_problem) : ""}
        <button class="btn ghost compact add-row" type="button" data-act="comp-add" data-uid="${uid}" data-count="${e.components.length}" data-key="${key}-comp-add">${svg(GLYPH.plus, "glyph")}Add component</button>
      </div>
    </div>
    <div class="editor-foot">
      <span class="spacer"></span>
      <button class="btn secondary" type="button" data-act="set-close" data-uid="${uid}" data-key="${key}-done">Done</button>
    </div>
  </div>`;
}

function setRow(row) {
  const key = `set-${row.uid}`;
  const name = row.open
    ? `<input class="field mono list-name-field${row.editor.sku_problem ? " invalid" : ""}" type="text" value="${esc(row.sku)}" placeholder="Set SKU" aria-label="Set SKU" data-input="set_sku" data-uid="${row.uid}" data-key="${key}-sku">`
    : `<button class="list-name mono" type="button" data-act="set-open" data-uid="${row.uid}" data-key="${key}-sku">${esc(row.label)}</button>`;
  const chips = row.open
    ? ""
    : row.chips.map((chip) => `<span class="rule-chip mono" title="${esc(chip)}">${esc(chip)}</span>`).join("") +
      (row.more_chips ? `<span class="list-muted">${esc(row.more_chips)}</span>` : "");
  return `<div class="list-row${row.open ? " open" : ""}" data-set="${row.uid}" data-key="${key}">
    <div class="list-text">
      <div class="list-head">${name}${chips}</div>
      ${!row.open && row.problem ? problemLine(row.problem) : ""}
    </div>
    <div class="list-actions">
      <button class="btn ghost compact icon" type="button" title="Delete set" aria-label="Delete set" data-act="set-delete" data-uid="${row.uid}" data-key="${key}-delete">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${row.open ? setEditor(row) : ""}
  </div>`;
}

function setsImportMenu(s) {
  const item = (kind, label, key) =>
    `<button class="menu-item" type="button" role="menuitem" data-act="sets-import" data-kind="${kind}" data-key="${key}"><span class="menu-label">${label}</span></button>`;
  return `<div class="menu add-menu" role="menu">
    <div class="menu-group">${esc(s.import_hint)}</div>
    ${item("sets-merge", "Add and update sets…", "sets-import-merge")}
    ${item("sets-replace", "Replace all sets…", "sets-import-replace")}
  </div>`;
}

function setsPage(s) {
  if (s.empty) {
    return `<section class="card state rules-empty" data-card="sets-empty">
      <p class="state-title">${esc(s.empty.title)}</p>
      <p class="state-text">${esc(s.empty.text)}</p>
      <div class="state-actions">
        <button class="btn primary" type="button" data-act="set-add" data-key="set-add">${svg(GLYPH.plus, "glyph")}${esc(s.empty.action)}</button>
        <button class="btn secondary" type="button" data-act="sets-import" data-kind="sets-merge" data-key="sets-import-merge">${esc(s.empty.import)}</button>
      </div>
    </section>`;
  }
  const open = view.menu === "sets-import";
  const none = s.no_hits ? `<div class="list-none">${esc(s.no_hits)}</div>` : "";
  const more = s.more ? `<div class="list-more">${esc(s.more)}</div>` : "";
  return `<section class="card" data-card="sets">
    <div class="list-bar">
      <label class="input list-filter">${svg(RULE_GLYPH.search, "glyph")}<input type="text" value="${esc(s.filter)}" placeholder="${esc(s.filter_placeholder)}" aria-label="${esc(s.filter_placeholder)}" data-input="filter" data-key="sets-filter"></label>
      <span class="spacer"></span>
      <span class="list-count">${esc(s.count)}</span>
      <div class="menu-anchor">
        <button class="btn secondary compact" type="button" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="sets-import" data-key="sets-import">Import${svg(GLYPH.chevron, "glyph")}</button>
        ${open ? setsImportMenu(s) : ""}
      </div>
      <button class="btn secondary compact" type="button" data-act="sets-export" data-key="sets-export"${off(!s.can_export)}>Export</button>
    </div>
    ${s.rows.map(setRow).join("")}
    ${none}
    ${more}
  </section>`;
}

// Whether the click was one of this page's.
function setsClick(data, el, bridge) {
  const uid = data.uid;
  switch (data.act) {
    case "set-add":
      view.pending = OPEN_NAME;
      bridge.edit("set_add", []);
      return true;
    case "set-open":
      view.pending = OPEN_NAME;
      bridge.edit("open", [uid]);
      return true;
    case "set-close":
      view.pending = `set-${uid}-sku`;
      bridge.edit("close", []);
      return true;
    case "set-delete":
      view.pending = "sets-filter";
      bridge.edit("set_delete", [uid]);
      return true;
    case "comp-add":
      // The new row is the next position: focus its SKU once it arrives.
      view.pending = `set-${uid}-c${data.count}-sku`;
      bridge.edit("comp_add", [uid]);
      return true;
    case "comp-remove":
      view.pending = `set-${uid}-comp-add`;
      bridge.edit("comp_remove", [uid, data.c]);
      return true;
    case "sets-import":
      closeMenu();
      bridge.importFile(data.kind);
      return true;
    case "sets-export":
      bridge.exportFile("sets");
      return true;
  }
  return false;
}

// Whether the keystroke was in one of this page's fields.
function setsInput(data, el, bridge) {
  switch (data.input) {
    case "set_sku":
      bridge.edit("set_sku", [data.uid, el.value]);
      return true;
    case "comp_sku":
      bridge.edit("comp_sku", [data.uid, data.c, el.value]);
      return true;
    case "comp_quantity":
      bridge.edit("comp_quantity", [data.uid, data.c, el.value]);
      return true;
  }
  return false;
}
