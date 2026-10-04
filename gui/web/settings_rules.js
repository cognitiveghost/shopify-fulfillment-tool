// The Rules page and the Test rule panel (phase 8 spec sections 5 and 6).
// settings.js renders and routes; this file draws what bridge.state holds
// under `rules` and `test`, and turns a click or a keystroke there into
// bridge.edit(action, args). Python holds every rule and words every sentence
// (gui/settings/rules_state.py, gui/settings/rule_test.py). The page's own
// state here is a drag in progress and whether the panel was showing.
//
// Loaded before settings.js: it calls that file's helpers (esc, svg, off,
// menuItem, problemLine, focusKey, closeMenu), but only once the page runs.
"use strict";

const RULE_GLYPH = {
  search: "M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0M20 20l-3.5-3.5",
  up: "m18 15-6-6-6 6",
  // Dots are zero-length strokes with round caps.
  more: "M5 12h.01M12 12h.01M19 12h.01",
  grip: "M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",
  rules: "M3 5h8M3 12h8M3 19h8M15 7l3 3 3-3M18 3v7M15 16h6",
};

// drag: the rule being dragged by its grip, the rows of its group, where it
// started and the place it would land. shown / uid: the Test panel as the
// last render drew it, to move focus in and back out.
const rulesView = { drag: null, shown: false, uid: null };

// --- the list ----------------------------------------------------------------

function summaryPart(part) {
  if (part.t === "chip") return `<span class="rule-chip mono" title="${esc(part.v)}">${esc(part.v)}</span>`;
  if (part.t === "bold") return `<span class="rule-word bold">${esc(part.v)}</span>`;
  if (part.t === "join" || part.t === "muted") return `<span class="rule-word muted">${esc(part.v)}</span>`;
  return `<span class="rule-word">${esc(part.v)}</span>`;
}

function summaryLines(row) {
  return row.summary
    .map(
      (line) =>
        `<div class="rule-line"><span class="rule-line-label">${esc(line.label)}</span>${line.parts.map(summaryPart).join("")}</div>`,
    )
    .join("");
}

function ruleMenu(row, key) {
  const edit = row.open ? "Close editor" : "Edit";
  const item = (act, label, cls) =>
    `<button class="menu-item${cls}" type="button" role="menuitem" data-act="${act}" data-uid="${row.uid}" data-key="${key}-${act.slice(5)}">${label}</button>`;
  return `<div class="menu rule-menu" role="menu">
    ${item("rule-edit", edit, "")}
    ${item("rule-duplicate", "Duplicate", "")}
    <div class="menu-separator"></div>
    ${item("rule-delete", "Delete", " danger")}
  </div>`;
}

function ruleActions(row) {
  const key = `rule-${row.uid}`;
  const menuName = `${key}-menu`;
  const open = view.menu === menuName;
  const move = (dir, glyph, able) => {
    const title = row.move_title || (dir === "up" ? "Move up" : "Move down");
    return `<button class="btn ghost compact icon rule-move" type="button" title="${esc(title)}" aria-label="${esc(title)}" data-act="rule-move" data-uid="${row.uid}" data-dir="${dir}" data-key="${key}-${dir}"${off(!able)}>${svg(glyph, "glyph")}</button>`;
  };
  return `<div class="rule-actions">
    <button class="btn secondary compact rule-test" type="button" title="${esc(row.test_title)}" data-act="rule-test" data-uid="${row.uid}" data-key="${key}-test"${off(!row.can_test)}>Test…</button>
    ${move("up", RULE_GLYPH.up, row.can_up)}
    ${move("down", GLYPH.chevron, row.can_down)}
    <div class="menu-anchor">
      <button class="btn ghost compact icon rule-more" type="button" title="Edit, duplicate, delete" aria-label="Edit, duplicate, delete" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="${menuName}" data-key="${menuName}">${svg(RULE_GLYPH.more, "glyph dots")}</button>
      ${open ? ruleMenu(row, menuName) : ""}
    </div>
  </div>`;
}

function ruleRow(row, level) {
  const key = `rule-${row.uid}`;
  const grip = row.can_drag ? "Drag to reorder" : row.move_title;
  const name = row.open
    ? `<input class="field rule-name-field" type="text" value="${esc(row.name)}" aria-label="Rule name" data-input="rule_name" data-uid="${row.uid}" data-key="${key}-name">`
    : `<button class="rule-name" type="button" data-act="rule-open" data-uid="${row.uid}" data-key="${key}-name">${esc(row.label)}</button>`;
  const badge = row.badge ? `<span class="badge neutral">${esc(row.badge)}</span>` : "";
  const below = row.open ? "" : summaryLines(row) + (row.problem ? problemLine(row.problem) : "");
  const cls = `rule${row.open ? " open" : ""}${row.on ? "" : " off"}${row.wide_labels ? " wide" : ""}`;
  return `<div class="${cls}" data-rule="${row.uid}" data-group="${level}" data-key="${key}">
    <span class="rule-grip${row.can_drag ? "" : " disabled"}" data-grip="${row.uid}" title="${esc(grip)}" aria-hidden="true">${svg(RULE_GLYPH.grip, "glyph dots")}</span>
    <button class="switch" type="button" role="switch" aria-checked="${Boolean(row.on)}" aria-label="${esc(row.label)}" title="${esc(row.switch_title)}" data-act="rule-enabled" data-uid="${row.uid}" data-key="${key}-switch"><span class="switch-knob"></span></button>
    <div class="rule-text">
      <div class="rule-head"><span class="rule-num mono">${esc(row.num)}</span>${name}${badge}</div>
      ${below}
    </div>
    ${ruleActions(row)}
    ${row.open ? ruleEditor(row) : ""}
  </div>`;
}

function rulesGroup(group) {
  const label = group.label
    ? `<div class="rules-group"><span class="rules-group-label">${esc(group.label)}</span><span>${esc(group.note)}</span></div>`
    : "";
  return label + group.rows.map((row) => ruleRow(row, group.level)).join("");
}

function rulesPage(r) {
  if (r.empty) {
    return `<section class="card state rules-empty" data-card="rules-empty">
      <span class="rules-empty-tile">${svg(RULE_GLYPH.rules, "state-glyph")}</span>
      <p class="state-title">${esc(r.empty.title)}</p>
      <p class="state-text">${esc(r.empty.text)}</p>
      <button class="btn primary" type="button" data-act="rule-add" data-key="rule-add">${svg(GLYPH.plus, "glyph")}${esc(r.empty.action)}</button>
    </section>`;
  }
  const none = r.no_hits ? `<div class="rules-none">${esc(r.no_hits)}</div>` : "";
  return `<section class="card rules-card" data-card="rules">
    <div class="rules-bar">
      <label class="input rules-filter">${svg(RULE_GLYPH.search, "glyph")}<input type="text" value="${esc(r.filter)}" placeholder="${esc(r.filter_placeholder)}" aria-label="${esc(r.filter_placeholder)}" data-input="filter" data-key="rules-filter"></label>
      <span class="spacer"></span>
      <span class="rules-count">${esc(r.count)}</span>
    </div>
    ${r.groups.map(rulesGroup).join("")}
    ${none}
  </section>`;
}

// --- the editor ----------------------------------------------------------------

// A .select and, while it is open, its menu. The menu's name is the select's
// own data-key, so closing it gives focus back to the select.
function ruleSelect(key, label, text, invalid, menu, cls) {
  const open = view.menu === key;
  const value = text
    ? `<span class="select-value">${esc(text)}</span>`
    : `<span class="select-value placeholder">Choose</span>`;
  return `<div class="menu-anchor ${cls}">
    <button class="select${invalid ? " invalid" : ""}" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="${esc(label)}" data-act="menu" data-menu="${key}" data-key="${key}">${value}${svg(GLYPH.chevron, "glyph")}</button>
    ${open ? `<div class="menu editor-menu" role="menu">${menu()}</div>` : ""}
  </div>`;
}

function segments(options, label, act, data, key) {
  const attrs = Object.keys(data)
    .map((name) => ` data-${name}="${esc(data[name])}"`)
    .join("");
  const buttons = options
    .map(
      (o) =>
        `<button class="segment" type="button" role="radio" aria-checked="${Boolean(o.checked)}" tabindex="${o.checked ? 0 : -1}" data-act="${act}"${attrs} data-value="${o.value}" data-key="${key}-${o.value}">${esc(o.label)}</button>`,
    )
    .join("");
  return `<div class="segmented" role="radiogroup" aria-label="${esc(label)}">${buttons}</div>`;
}

// An <input list> and its <datalist>: any text can be typed.
function suggestions(key, options) {
  if (!options.length) return ["", ""];
  const id = `dl-${key}`;
  return [` list="${id}"`, `<datalist id="${id}">${options.map((o) => `<option value="${esc(o)}"></option>`).join("")}</datalist>`];
}

function under(problem, hint) {
  if (problem) return problemLine(problem);
  return hint ? `<span class="hint">${esc(hint)}</span>` : "";
}

function conditionRow(e, uid, s, c, cond) {
  const key = `rule-${uid}-s${s}-c${c}`;
  const at = { uid, s, c };
  const fieldMenu = () => {
    const items = [];
    let n = 0;
    const item = (field, note) =>
      menuItem("cond-field", { ...at, value: field }, field, note, field === cond.field, `${key}-field-item-${n++}`, false);
    if (cond.extra_field) items.push(item(cond.extra_field.value, cond.extra_field.note));
    e.field_groups.forEach((group) => {
      items.push(`<div class="menu-group">${esc(group.label)}</div>`);
      group.fields.forEach((field) => items.push(item(field, "")));
    });
    return items.join("");
  };
  const operatorMenu = () => {
    const listed = cond.extra_operator ? [cond.extra_operator].concat(e.operators) : e.operators;
    return listed
      .map((operator, n) =>
        menuItem("cond-op", { ...at, value: operator }, operator, n === 0 && cond.extra_operator ? "Not available" : "", operator === cond.operator, `${key}-op-item-${n}`, false),
      )
      .join("");
  };
  const v = cond.value;
  const input = `data-input="cond_value" data-uid="${uid}" data-s="${s}" data-c="${c}" data-key="${key}-value" aria-label="Value"`;
  let value = `<span class="cond-none"></span>`;
  if (v.kind === "date") {
    value = `<input class="field${cond.invalid ? " invalid" : ""}" type="date" value="${esc(v.text)}" ${input}>`;
  } else if (v.kind === "text") {
    const [list, datalist] = suggestions(key, v.suggestions);
    value = `<input class="field${cond.invalid ? " invalid" : ""}" type="text" value="${esc(v.text)}" placeholder="${esc(v.placeholder)}"${list} ${input}>${datalist}`;
  }
  return `<div class="cond" data-cond="${c}">
    <div class="cond-row">
      ${ruleSelect(`${key}-field`, "Field", cond.field, cond.field_invalid, fieldMenu, "cond-field")}
      ${ruleSelect(`${key}-op`, "Operator", cond.operator, Boolean(cond.extra_operator), operatorMenu, "cond-op")}
      <div class="cond-value">${value}</div>
      <button class="btn ghost compact icon" type="button" title="Remove condition" aria-label="Remove condition" data-act="cond-remove" data-uid="${uid}" data-s="${s}" data-c="${c}" data-key="${key}-remove">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${under(cond.problem, cond.hint)}
  </div>`;
}

function actionParam(uid, s, a, p) {
  const key = `rule-${uid}-s${s}-a${a}-${p.name}`;
  const at = { uid, s, a, name: p.name };
  const lead = p.lead ? `<span class="param-lead">${esc(p.lead)}</span>` : "";
  const input = `data-input="action_param" data-uid="${uid}" data-s="${s}" data-a="${a}" data-name="${p.name}" data-key="${key}" aria-label="${esc(p.placeholder || p.name)}"`;
  if (p.kind === "field") {
    const listed = p.extra ? [p.extra].concat(p.options) : p.options;
    const menu = () =>
      listed
        .map((field, n) =>
          menuItem("action-param", { ...at, value: field }, field, n === 0 && p.extra ? "Not available" : "", field === p.value, `${key}-item-${n}`, false),
        )
        .join("");
    return lead + ruleSelect(key, p.name, p.value, Boolean(p.extra), menu, "param-field");
  }
  if (p.kind === "choice") {
    const chosen = p.options.find((o) => o.value === p.value);
    const menu = () =>
      p.options
        .map((o, n) => menuItem("action-param", { ...at, value: o.value }, o.label, "", o.value === p.value, `${key}-item-${n}`, false))
        .join("");
    return lead + ruleSelect(key, p.name, chosen ? chosen.label : p.value, false, menu, "param-choice");
  }
  if (p.kind === "number") {
    return `${lead}<input class="field mono param-number${p.invalid ? " invalid" : ""}" type="text" inputmode="numeric" value="${esc(p.value)}" ${input}>`;
  }
  const [list, datalist] = p.kind === "suggest" ? suggestions(key, p.options) : ["", ""];
  return `${lead}<input class="field param-text" type="text" value="${esc(p.value)}" placeholder="${esc(p.placeholder)}"${list} ${input}>${datalist}`;
}

function actionRow(e, uid, s, a, action) {
  const key = `rule-${uid}-s${s}-a${a}`;
  const typeMenu = () => {
    const listed = action.extra_type ? [action.extra_type].concat(e.action_types) : e.action_types;
    return listed
      .map((t, n) => menuItem("action-type", { uid, s, a, value: t.value }, t.label, "", t.value === action.type, `${key}-type-item-${n}`, false))
      .join("");
  };
  return `<div class="action" data-action="${a}">
    <div class="action-row">
      <div class="action-controls">
        ${ruleSelect(`${key}-type`, "Action", action.label, false, typeMenu, "action-type")}
        ${action.params.map((p) => actionParam(uid, s, a, p)).join("")}
      </div>
      <button class="btn ghost compact icon" type="button" title="Remove action" aria-label="Remove action" data-act="action-remove" data-uid="${uid}" data-s="${s}" data-a="${a}" data-key="${key}-remove">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${under(action.problem, action.hint)}
  </div>`;
}

function addRow(act, label, uid, s, count, key) {
  return `<button class="btn ghost compact add-row" type="button" data-act="${act}" data-uid="${uid}" data-s="${s}" data-count="${count}" data-key="${key}">${svg(GLYPH.plus, "glyph")}${label}</button>`;
}

function editorStep(e, uid, s, step) {
  const key = `rule-${uid}-s${s}`;
  const remove = step.removable
    ? `<button class="btn ghost compact danger" type="button" data-act="step-remove" data-uid="${uid}" data-s="${s}" data-key="${key}-remove">Remove step</button>`
    : "";
  const head = step.title
    ? `<div class="step-head"><span class="step-title">${esc(step.title)}</span><span class="step-note">${esc(step.note)}</span><span class="spacer"></span>${remove}</div>`
    : "";
  const match = step.match.show
    ? `<div class="match-line">${segments(step.match.options, "Match", "step-match", { uid, s }, `${key}-match`)}<span>${esc(step.match.tail)}</span></div>`
    : "";
  return `<div class="editor-step${step.title ? " titled" : ""}" data-step="${s}">
    ${head}
    <div class="editor-line">
      <span class="editor-label">When</span>
      <div class="editor-content">
        ${match}
        ${step.conditions.map((cond, c) => conditionRow(e, uid, s, c, cond)).join("")}
        ${addRow("cond-add", "Add condition", uid, s, step.conditions.length, `${key}-cond-add`)}
      </div>
    </div>
    <div class="editor-line">
      <span class="editor-label">Then</span>
      <div class="editor-content">
        ${step.actions.map((action, a) => actionRow(e, uid, s, a, action)).join("")}
        ${addRow("action-add", "Add action", uid, s, step.actions.length, `${key}-action-add`)}
      </div>
    </div>
  </div>`;
}

function ruleEditor(row) {
  const e = row.editor;
  const uid = row.uid;
  const key = `rule-${uid}`;
  return `<div class="rule-editor">
    <div class="editor-line">
      <span class="editor-label">Level</span>
      <div class="editor-content level-line">${segments(e.level.options, "Level", "rule-level", { uid }, `${key}-level`)}<span class="hint">${esc(e.level.hint)}</span></div>
    </div>
    ${e.steps.map((step, s) => editorStep(e, uid, s, step)).join("")}
    <div class="editor-foot">
      <button class="btn ghost compact add-row" type="button" data-act="step-add" data-uid="${uid}" data-key="${key}-step-add">${svg(GLYPH.plus, "glyph")}Add step</button>
      <span class="spacer"></span>
      <button class="btn secondary" type="button" data-act="rule-close" data-uid="${uid}" data-key="${key}-done">Done</button>
    </div>
  </div>`;
}

// --- the Test panel ------------------------------------------------------------

function testPanel(t) {
  const session = t.intro.session ? `<span class="mono">${esc(t.intro.session)}</span>` : "";
  let body = "";
  if (t.status === "running") {
    body = `<div class="test-message">${esc(t.message)}</div>`;
  } else if (t.status === "failed") {
    body = problemLine(t.message);
  } else {
    const rows = t.rows
      .map(
        (row) =>
          `<div class="test-row"><span class="test-order mono">${esc(row.order)}</span><span class="test-why mono" title="${esc(row.why)}">${esc(row.why)}</span><span class="test-change mono${row.changed ? "" : " same"}" title="${esc(row.change)}">${esc(row.change)}</span></div>`,
      )
      .join("");
    const table = t.rows.length
      ? `<div class="test-table">
          <div class="test-row heads">${t.heads.map((head) => `<span>${esc(head)}</span>`).join("")}</div>
          ${rows}
          ${t.more ? `<div class="test-more">${esc(t.more)}</div>` : ""}
        </div>`
      : `<div class="test-message">${esc(t.empty)}</div>`;
    body = `<div class="test-count"><span class="test-matched mono">${esc(t.matched)}</span><span>${esc(t.total)}</span></div>
      ${table}
      ${t.note ? `<span class="hint">${esc(t.note)}</span>` : ""}`;
  }
  return `<div class="scrim" data-test="${esc(t.status)}">
    <div class="test-panel" role="dialog" aria-modal="true" aria-labelledby="test-title">
      <div class="test-head">
        <span class="test-title" id="test-title">${esc(t.title)}</span>
        <button class="btn ghost icon" type="button" title="Close" aria-label="Close" data-act="test-close" data-key="test-x">${svg(GLYPH.x, "glyph")}</button>
      </div>
      <div class="test-body">
        <span class="test-intro">${esc(t.intro.lead)}${session}${esc(t.intro.tail)}</span>
        ${body}
      </div>
      <div class="test-foot"><button class="btn secondary" type="button" data-act="test-close" data-key="test-close">Close</button></div>
    </div>
  </div>`;
}

// --- render hooks ----------------------------------------------------------------

function ruleRowOf(r, uid) {
  for (const group of r.groups) {
    const row = group.rows.find((candidate) => candidate.uid === uid);
    if (row) return row;
  }
  return null;
}

// A rule's "…" menu needs its row; a menu inside the editor needs it open.
function rulesMenuStillOpens(r, name) {
  const found = /^rule-(\d+)-(.*)$/.exec(name);
  if (!found) return false;
  const row = ruleRowOf(r, found[1]);
  return Boolean(row) && (found[2] === "menu" || row.open);
}

// After every render: the focus an edit asked for, and the panel's.
function rulesRendered(s) {
  const pending = view.pending;
  if (pending === "@open-name" || pending === "@new-name") {
    const field = els.root.querySelector(".rule.open .rule-name-field");
    if (field) {
      field.focus();
      if (pending === "@new-name") field.select();
      view.pending = null;
    }
  } else if (typeof pending === "string" && pending.startsWith("@move:")) {
    // The button pressed may have reached its group's edge: the other one
    // then takes the focus, so the keyboard can keep moving the rule.
    const [, uid, dir] = pending.split(":");
    const other = dir === "up" ? "down" : "up";
    if (focusKey(`rule-${uid}-${dir}`) || focusKey(`rule-${uid}-${other}`)) view.pending = null;
  }
  const shown = Boolean(s.test);
  if (shown && !rulesView.shown) focusKey("test-close");
  if (!shown && rulesView.shown) focusKey(`rule-${rulesView.uid}-test`);
  rulesView.shown = shown;
  if (shown) rulesView.uid = s.test.uid;
}

// --- input -------------------------------------------------------------------------

// Whether the click was one of this page's.
function rulesClick(data, el, bridge) {
  const uid = data.uid;
  switch (data.act) {
    case "rule-add":
      view.pending = "@new-name";
      bridge.edit("rule_add", []);
      return true;
    case "rule-open":
      view.pending = "@open-name";
      bridge.edit("open", [uid]);
      return true;
    case "rule-edit": {
      const open = Boolean(el.closest(".rule.open"));
      view.menu = null;
      view.pending = open ? `rule-${uid}-name` : "@open-name";
      bridge.edit(open ? "close" : "open", open ? [] : [uid]);
      return true;
    }
    case "rule-close":
      view.pending = `rule-${uid}-name`;
      bridge.edit("close", []);
      return true;
    case "rule-enabled":
      bridge.edit("rule_enabled", [uid, el.getAttribute("aria-checked") !== "true"]);
      return true;
    case "rule-move":
      view.pending = `@move:${uid}:${data.dir}`;
      bridge.edit("rule_move", [uid, data.dir]);
      return true;
    case "rule-duplicate":
      bridge.edit("rule_duplicate", [uid]);
      closeMenu();
      return true;
    case "rule-delete":
      view.menu = null;
      view.pending = "rules-filter";
      bridge.edit("rule_delete", [uid]);
      return true;
    case "rule-test":
      bridge.testRule(uid);
      return true;
    case "test-close":
      bridge.closeTest();
      return true;
    case "rule-level":
      view.pending = `rule-${uid}-level-${data.value}`;
      bridge.edit("rule_level", [uid, data.value]);
      return true;
    case "step-add":
      bridge.edit("step_add", [uid]);
      return true;
    case "step-remove":
      view.pending = `rule-${uid}-step-add`;
      bridge.edit("step_remove", [uid, data.s]);
      return true;
    case "step-match":
      view.pending = `rule-${uid}-s${data.s}-match-${data.value}`;
      bridge.edit("step_match", [uid, data.s, data.value]);
      return true;
    case "cond-add":
      // The new row is the next position: focus its field once it arrives.
      view.pending = `rule-${uid}-s${data.s}-c${data.count}-field`;
      bridge.edit("cond_add", [uid, data.s]);
      return true;
    case "cond-remove":
      view.pending = `rule-${uid}-s${data.s}-cond-add`;
      bridge.edit("cond_remove", [uid, data.s, data.c]);
      return true;
    case "cond-field":
      bridge.edit("cond_field", [uid, data.s, data.c, data.value]);
      closeMenu();
      return true;
    case "cond-op":
      bridge.edit("cond_operator", [uid, data.s, data.c, data.value]);
      closeMenu();
      return true;
    case "action-add":
      view.pending = `rule-${uid}-s${data.s}-a${data.count}-type`;
      bridge.edit("action_add", [uid, data.s]);
      return true;
    case "action-remove":
      view.pending = `rule-${uid}-s${data.s}-action-add`;
      bridge.edit("action_remove", [uid, data.s, data.a]);
      return true;
    case "action-type":
      bridge.edit("action_type", [uid, data.s, data.a, data.value]);
      closeMenu();
      return true;
    case "action-param":
      bridge.edit("action_param", [uid, data.s, data.a, data.name, data.value]);
      closeMenu();
      return true;
  }
  return false;
}

// Whether the keystroke was in one of this page's fields.
function rulesInput(data, el, bridge) {
  switch (data.input) {
    case "filter":
      bridge.edit("filter", [el.value]);
      return true;
    case "rule_name":
      bridge.edit("rule_name", [data.uid, el.value]);
      return true;
    case "cond_value":
      bridge.edit("cond_value", [data.uid, data.s, data.c, el.value]);
      return true;
    case "action_param":
      bridge.edit("action_param", [data.uid, data.s, data.a, data.name, el.value]);
      return true;
  }
  return false;
}

// Escape ends a drag, else closes the Test panel. Whether it did either.
function rulesEscape() {
  if (rulesView.drag) {
    endDrag();
    return true;
  }
  if (page.state && page.state.test && page.bridge) {
    page.bridge.closeTest();
    return true;
  }
  return false;
}

// --- dragging a rule by its grip -------------------------------------------------

const DRAG_EDGE_PX = 40;
const DRAG_SCROLL_PX = 12;

function markDrop() {
  const d = rulesView.drag;
  d.rows.forEach((row) => row.classList.remove("drop-before", "drop-after"));
  if (d.to === d.from) return;
  const others = d.rows.filter((row, n) => n !== d.from);
  if (d.to < others.length) others[d.to].classList.add("drop-before");
  else others[others.length - 1].classList.add("drop-after");
}

function endDrag() {
  const d = rulesView.drag;
  if (!d) return;
  d.rows.forEach((row) => row.classList.remove("dragging", "drop-before", "drop-after"));
  document.body.classList.remove("is-dragging");
  rulesView.drag = null;
}

function onGripDown(event) {
  const grip = event.target.closest ? event.target.closest("[data-grip]") : null;
  if (!grip || event.button !== 0 || grip.classList.contains("disabled")) return;
  const row = grip.closest(".rule");
  const rows = Array.from(els.root.querySelectorAll(`.rule[data-group="${row.dataset.group}"]`));
  const from = rows.indexOf(row);
  rulesView.drag = { uid: grip.dataset.grip, rows, from, to: from };
  row.classList.add("dragging");
  document.body.classList.add("is-dragging");
  // So the drag keeps its events outside the view. A synthetic pointer has
  // nothing to capture.
  try {
    grip.setPointerCapture(event.pointerId);
  } catch (error) {
    /* not a live pointer */
  }
  event.preventDefault();
}

function onGripMove(event) {
  const d = rulesView.drag;
  if (!d) return;
  // The place it would land: how many of the other rows sit above the pointer.
  let to = 0;
  d.rows.forEach((row, n) => {
    if (n === d.from) return;
    const box = row.getBoundingClientRect();
    if (event.clientY > box.top + box.height / 2) to += 1;
  });
  d.to = to;
  markDrop();
  // ponytail: scrolls only while the pointer moves. A timer would keep it
  // going on a held pointer; add one if a client's list outgrows the window.
  const box = els.root.getBoundingClientRect();
  if (event.clientY < box.top + DRAG_EDGE_PX) els.root.scrollTop -= DRAG_SCROLL_PX;
  else if (event.clientY > box.bottom - DRAG_EDGE_PX) els.root.scrollTop += DRAG_SCROLL_PX;
}

function onGripUp() {
  const d = rulesView.drag;
  if (!d) return;
  const moved = d.to !== d.from;
  endDrag();
  if (moved && page.bridge) page.bridge.edit("rule_move_to", [d.uid, String(d.to)]);
}

function bindRules() {
  els.root.addEventListener("pointerdown", onGripDown);
  document.addEventListener("pointermove", onGripMove);
  document.addEventListener("pointerup", onGripUp);
  document.addEventListener("pointercancel", endDrag);
}
