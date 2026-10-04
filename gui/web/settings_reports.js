// The Reports page (phase 9 spec section 6): packing lists and stock
// exports, one card each. settings.js renders and routes; this file draws
// what bridge.state holds under `reports`. Python holds every report and
// words every sentence (gui/settings/reports_state.py).
//
// Loaded after settings_rules.js and settings_sets.js, before settings.js: a
// filter is the rule's condition row (conditionRow), a summary the rule's
// (summaryPart), and OPEN_NAME is the Sets page's.
"use strict";

// What a report's filter row sends: see RULE_CONDITION.
const REPORT_FILTER = {
  field: "filter-field",
  op: "filter-op",
  value: "filter_value",
  remove: "filter-remove",
  removeLabel: "Remove filter",
};

function reportMatch(match) {
  return `<span class="report-match${match.warn ? " warn" : ""}">${esc(match.text)}</span>`;
}

function reportColumns(uid, columns) {
  const key = `report-${uid}`;
  const menuName = `${key}-column-add`;
  const open = view.menu === menuName;
  const chips = columns.chips
    .map(
      (name) =>
        `<span class="chip"><span class="mono">${esc(name)}</span><button class="chip-remove" type="button" title="Remove" aria-label="Remove ${esc(name)}" data-act="report-column-remove" data-uid="${uid}" data-name="${esc(name)}" data-key="${esc(`${key}-column-remove:${name}`)}">${svg(GLYPH.x, "glyph")}</button></span>`,
    )
    .join("");
  const items = columns.candidates
    .map((name, n) => menuItem("report-column-add", { uid, name }, name, "", false, `${menuName}-item-${n}`, true))
    .join("");
  return `<div class="report-chips">
      ${chips}
      <div class="menu-anchor">
        <button class="btn ghost compact add-row" type="button" aria-haspopup="menu" aria-expanded="${open}" title="${esc(columns.add_title)}" data-act="menu" data-menu="${menuName}" data-key="${menuName}"${off(!columns.candidates.length)}>${svg(GLYPH.plus, "glyph")}Add column</button>
        ${open ? `<div class="menu editor-menu" role="menu">${items}</div>` : ""}
      </div>
    </div>
    <span class="hint">${esc(columns.hint)}</span>`;
}

function reportEditor(row) {
  const e = row.editor;
  const uid = row.uid;
  const key = `report-${uid}`;
  const filters = e.filters
    .map((filter, f) => conditionRow(e, `${key}-f${f}`, { uid, f }, REPORT_FILTER, filter))
    .join("");
  const exclude = e.exclude
    ? `<div class="editor-line">
        <span class="editor-label">Exclude SKUs</span>
        <div class="editor-content">
          <input class="field mono" type="text" value="${esc(e.exclude.value)}" placeholder="${esc(e.exclude.placeholder)}" aria-label="Exclude SKUs" data-input="report_exclude" data-uid="${uid}" data-key="${key}-exclude">
          <span class="hint">${esc(e.exclude.hint)}</span>
        </div>
      </div>`
    : "";
  const columns = e.columns
    ? `<div class="editor-line">
        <span class="editor-label">Columns</span>
        <div class="editor-content">${reportColumns(uid, e.columns)}</div>
      </div>`
    : "";
  return `<div class="list-editor">
    <div class="editor-line">
      <span class="editor-label">File name</span>
      <div class="editor-content">
        <div class="control-line"><input class="field mono report-filename" type="text" value="${esc(row.filename)}" aria-label="File name" data-input="report_filename" data-uid="${uid}" data-key="${key}-filename"><span class="hint">${esc(e.filename_hint)}</span></div>
        ${row.note ? problemLine(row.note) : ""}
      </div>
    </div>
    <div class="editor-line">
      <span class="editor-label">Filters</span>
      <div class="editor-content">
        ${filters}
        <button class="btn ghost compact add-row" type="button" data-act="filter-add" data-uid="${uid}" data-count="${e.filters.length}" data-key="${key}-filter-add">${svg(GLYPH.plus, "glyph")}Add filter</button>
        <span class="hint">${esc(e.filters_hint)}</span>
        ${reportMatch(row.match)}
      </div>
    </div>
    ${exclude}
    ${columns}
    <div class="editor-foot">
      <span class="spacer"></span>
      <button class="btn secondary" type="button" data-act="report-close" data-uid="${uid}" data-key="${key}-done">Done</button>
    </div>
  </div>`;
}

function reportRow(row) {
  const key = `report-${row.uid}`;
  const name = row.open
    ? `<input class="field list-name-field" type="text" value="${esc(row.name)}" placeholder="Report name" aria-label="Report name" data-input="report_name" data-uid="${row.uid}" data-key="${key}-name">`
    : `<button class="list-name" type="button" data-act="report-open" data-uid="${row.uid}" data-key="${key}-name">${esc(row.label)}</button><span class="list-muted mono">${esc(row.filename)}</span>`;
  const below = row.open
    ? ""
    : `<div class="rule-line">${row.summary.map(summaryPart).join("")}</div>
       ${reportMatch(row.match)}
       ${row.note ? problemLine(row.note) : ""}`;
  const move = (dir, glyph, able, title) =>
    `<button class="btn ghost compact icon" type="button" title="${title}" aria-label="${title}" data-act="report-move" data-uid="${row.uid}" data-dir="${dir}" data-key="${key}-${dir}"${off(!able)}>${svg(glyph, "glyph")}</button>`;
  return `<div class="list-row${row.open ? " open" : ""}" data-report="${row.uid}" data-key="${key}">
    <div class="list-text">
      <div class="list-head">${name}</div>
      ${below}
    </div>
    <div class="list-actions">
      ${move("up", RULE_GLYPH.up, row.can_up, "Move up")}
      ${move("down", GLYPH.chevron, row.can_down, "Move down")}
      <button class="btn ghost compact icon" type="button" title="Delete report" aria-label="Delete report" data-act="report-delete" data-uid="${row.uid}" data-key="${key}-delete">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${row.open ? reportEditor(row) : ""}
  </div>`;
}

function reportsGroup(group) {
  const add = `<button class="btn secondary" type="button" data-act="report-add" data-kind="${group.kind}" data-key="report-add-${group.kind}">${svg(GLYPH.plus, "glyph")}${esc(group.add)}</button>`;
  const body = group.rows.length
    ? group.rows.map(reportRow).join("")
    : `<div class="card-empty">${esc(group.empty)}</div>`;
  return `<section class="card" data-card="reports-${group.kind}" data-kind="${group.kind}">
    ${cardHead(esc(group.title), esc(group.text), add)}
    ${body}
  </section>`;
}

function reportsPage(r) {
  return r.groups.map(reportsGroup).join("");
}

// Whether the click was one of this page's.
function reportsClick(data, el, bridge) {
  const uid = data.uid;
  switch (data.act) {
    case "report-add":
      view.pending = OPEN_NAME;
      bridge.edit("report_add", [data.kind]);
      return true;
    case "report-open":
      view.pending = OPEN_NAME;
      bridge.edit("open", [uid]);
      return true;
    case "report-close":
      view.pending = `report-${uid}-name`;
      bridge.edit("close", []);
      return true;
    case "report-delete": {
      const card = el.closest("[data-kind]");
      view.pending = `report-add-${card.dataset.kind}`;
      bridge.edit("report_delete", [uid]);
      return true;
    }
    case "report-move": {
      // The button pressed may have reached the edge: its opposite then
      // takes the focus, so the keyboard can keep moving the report.
      const other = data.dir === "up" ? "down" : "up";
      view.pending = `@keys:report-${uid}-${data.dir}|report-${uid}-${other}`;
      bridge.edit("report_move", [uid, data.dir]);
      return true;
    }
    case "filter-add":
      view.pending = `report-${uid}-f${data.count}-field`;
      bridge.edit("filter_add", [uid]);
      return true;
    case "filter-remove":
      view.pending = `report-${uid}-filter-add`;
      bridge.edit("filter_remove", [uid, data.f]);
      return true;
    case "filter-field":
      bridge.edit("filter_field", [uid, data.f, data.value]);
      closeMenu();
      return true;
    case "filter-op":
      bridge.edit("filter_operator", [uid, data.f, data.value]);
      closeMenu();
      return true;
    case "report-column-add":
      bridge.edit("column_add", [uid, data.name]);
      closeMenu();
      return true;
    case "report-column-remove":
      view.pending = `report-${uid}-column-add`;
      bridge.edit("column_remove", [uid, data.name]);
      return true;
  }
  return false;
}

// Whether the keystroke was in one of this page's fields.
function reportsInput(data, el, bridge) {
  switch (data.input) {
    case "report_name":
      bridge.edit("report_name", [data.uid, el.value]);
      return true;
    case "report_filename":
      bridge.edit("report_filename", [data.uid, el.value]);
      return true;
    case "report_exclude":
      bridge.edit("report_exclude", [data.uid, el.value]);
      return true;
    case "filter_value":
      bridge.edit("filter_value", [data.uid, data.f, el.value]);
      return true;
  }
  return false;
}
