// The Client settings pages: General, Orders mapping and Stock mapping (phase
// 7 spec section 5), drawn here; Rules (phase 8 spec section 5), drawn by
// settings_rules.js; Sets, Weight, Reports and Tag categories (phase 9 spec
// sections 4 to 7), each drawn by its own settings_<page>.js. Python holds
// every value and words every sentence (gui/settings/*_state.py) and sends
// one page's view as bridge.state; this file renders it and reports each
// edit through bridge.edit(action, args). Nothing is validated or computed
// here. The page's own state is which menu is open.
"use strict";

// Lucide glyphs, each as one path.
const GLYPH = {
  chevron: "m6 9 6 6 6-6",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  plus: "M5 12h14M12 5v14",
  alert: "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0M12 8v4M12 16h.01",
  arrowLeft: "M19 12H5M12 19l-7-7 7-7",
  arrowRight: "M5 12h14M12 5l7 7-7 7",
};

const els = {};
const page = { bridge: null, state: null, renders: 0 };
// menu: "field-<internal name>", "courier-code-<row>", "column-add",
// "chip:<column>", a Rules menu ("rule-<uid>-..."), or null: always the
// data-key of the control that opens it. shown: the page the last render drew.
// pending: a data-key to focus once the state that creates it arrives, or one
// of the requests that start with "@": the Rules page's own, "@css:<selector>"
// (focus the first match), "@css-select:<selector>" (and select its text) and
// "@keys:<key>|<key>" (the first of these keys that can take focus). problem:
// the key the footer's link asked for while another page was still showing.
const view = { menu: null, shown: null, pending: null, problem: null };

// A carriage return too: the parser would turn a bare one into a line feed,
// and a column's name has to come back from a data- attribute as it was sent.
function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\r/g, "&#13;");
}

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function off(disabled) {
  return disabled ? " disabled" : "";
}

function own(map, key) {
  return Object.prototype.hasOwnProperty.call(map, key);
}

// --- what every page shares --------------------------------------------------

// The page head's action: what it does, and its data-key.
const HEAD_ACTION = {
  rules: ["rule-add", "rule-add"],
  sets: ["set-add", "set-add"],
  tags: ["cat-add", "cat-add"],
};

// state key -> [draw, click, input]: the pages phase 9 moved. Each one's
// script is loaded before this file.
const LIST_PAGES = {
  sets: [setsPage, setsClick, setsInput],
  weight: [weightPage, weightClick, weightInput],
  reports: [reportsPage, reportsClick, reportsInput],
  tags: [tagsPage, tagsClick, tagsInput],
};

// The LIST_PAGES key this state holds, or undefined.
function listPageOf(s) {
  return Object.keys(LIST_PAGES).find((name) => s[name]);
}

function head(s) {
  const [act, key] = HEAD_ACTION[s.page] || ["read", "read-columns"];
  const action = s.action
    ? `<button class="btn secondary" type="button" data-act="${act}" data-key="${key}">${svg(GLYPH.plus, "glyph")}${esc(s.action)}</button>`
    : "";
  return `<div class="page-head split">
    <div class="page-head-text"><span class="page-title">${esc(s.title)}</span><span class="page-sub">${esc(s.subtitle)}</span></div>
    ${action}
  </div>`;
}

// `text` and `action` are markup: the caller escapes what it puts in them.
function cardHead(title, text, action) {
  return `<div class="card-head">
    <div class="card-head-text"><span class="card-title">${title}</span><span class="card-text">${text}</span></div>
    ${action || ""}
  </div>`;
}

function problemLine(text, extra, cls) {
  return `<span class="problem${cls ? ` ${cls}` : ""}" role="alert">${svg(GLYPH.alert, "glyph")}<span>${esc(text)}${extra || ""}</span></span>`;
}

// Under a control: the problem when there is one, else the hint.
function below(problem, hint) {
  if (problem) return problemLine(problem);
  return hint ? `<span class="hint">${esc(hint)}</span>` : "";
}

function menuItem(act, data, label, hint, checked, key, mono) {
  const attrs = Object.keys(data)
    .map((name) => ` data-${name}="${esc(data[name])}"`)
    .join("");
  const meta = hint ? `<span class="menu-hint">${esc(hint)}</span>` : "";
  return `<button class="menu-item" type="button" role="menuitemradio" aria-checked="${Boolean(checked)}" data-act="${act}"${attrs} data-key="${esc(key)}">${svg(GLYPH.check, "check")}<span class="menu-label${mono ? " mono" : ""}">${esc(label)}</span>${meta}</button>`;
}

// --- General -----------------------------------------------------------------

function delimiterRow(d) {
  const segments = d.options
    .map(
      (o) =>
        `<button class="segment" type="button" role="radio" aria-checked="${Boolean(o.checked)}" tabindex="${o.checked ? 0 : -1}" data-act="delimiter" data-kind="${d.kind}" data-value="${o.value}" data-key="segment-${d.kind}-${o.value}">${esc(o.label)}</button>`,
    )
    .join("");
  const other = d.other
    ? `<input class="field mono other-char${d.problem ? " invalid" : ""}" type="text" maxlength="1" value="${esc(d.char)}" aria-label="Delimiter character" data-input="delimiter_char" data-kind="${d.kind}" data-key="char-${d.kind}">`
    : "";
  return `<div class="card-row" data-row="delimiter-${d.kind}">
    <span class="card-label">${esc(d.label)}</span>
    <div class="card-control">
      <div class="control-line"><div class="segmented" role="radiogroup" aria-label="${esc(d.label)}">${segments}</div>${other}</div>
      ${below(d.problem, d.hint)}
    </div>
  </div>`;
}

function generalPage(g) {
  const t = g.threshold;
  return `<section class="card" data-card="csv">
    ${cardHead("CSV files", esc(g.csv_text))}
    ${g.delimiters.map(delimiterRow).join("")}
  </section>
  <section class="card" data-card="alerts">
    ${cardHead("Stock alerts", esc(g.alerts_text))}
    <div class="card-row" data-row="threshold">
      <span class="card-label">Low-stock threshold</span>
      <div class="card-control">
        <div class="control-line"><input class="field mono threshold${t.problem ? " invalid" : ""}" type="text" inputmode="numeric" value="${esc(t.value)}" aria-label="Low-stock threshold" data-input="threshold" data-key="threshold"><span>${esc(t.unit)}</span></div>
        ${below(t.problem, t.hint)}
      </div>
    </div>
  </section>`;
}

// --- the Fields card ---------------------------------------------------------

function fieldMenu(m, f) {
  const items = [];
  if (!f.required) {
    items.push(menuItem("column", { field: f.name, value: "" }, f.placeholder, "", !f.column, `field-${f.name}-item-none`, false));
  }
  // A saved column the file lacks is still the choice: it is listed first.
  const columns = f.sample_missing ? [f.column].concat(m.columns) : m.columns;
  columns.forEach((column, n) => {
    let note = "";
    if (f.sample_missing && n === 0) note = f.sample;
    else if (own(m.held, column) && m.held[column] !== f.label) note = m.held[column];
    items.push(menuItem("column", { field: f.name, value: column }, column, note, column === f.column, `field-${f.name}-item-${n}`, true));
  });
  return `<div class="menu field-menu" role="menu">${items.join("")}</div>`;
}

function fieldRow(m, f) {
  const menuName = `field-${f.name}`;
  const open = view.menu === menuName;
  const bad = Boolean(f.problem);
  const value = f.column
    ? `<span class="select-value mono">${esc(f.column)}</span>`
    : `<span class="select-value placeholder${bad ? " danger" : ""}">${esc(f.placeholder)}</span>`;
  const required = f.required ? `<span class="field-required">Required</span>` : "";
  let under = "";
  if (f.problem) {
    const example = f.example ? ` <span class="mono">${esc(f.example)}</span>.` : "";
    under = problemLine(f.problem, example, "field-below");
  } else if (f.hint) {
    under = `<span class="hint field-below">${esc(f.hint)}</span>`;
  }
  return `<div class="field-row" data-field="${esc(f.name)}">
    <div class="field-name"><span class="field-label">${esc(f.label)}</span>${required}</div>
    ${svg(GLYPH.arrowLeft, "glyph arrow")}
    <div class="menu-anchor">
      <button class="select${bad ? " invalid" : ""}" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="${esc(f.label)} column" data-act="menu" data-menu="${menuName}" data-key="${menuName}"${off(!m.can_pick)}>${value}${svg(GLYPH.chevron, "glyph")}</button>
      ${open ? fieldMenu(m, f) : ""}
    </div>
    <span class="field-sample mono${f.sample_missing ? " missing" : ""}" title="${esc(f.sample)}">${esc(f.sample)}</span>
    ${under}
  </div>`;
}

function fieldsCard(m) {
  const src = m.source;
  const file = src.file ? ` <span class="mono">${esc(src.file)}</span>` : "";
  return `<section class="card" data-card="fields">
    ${cardHead("Fields", `${esc(src.lead)}${file}${esc(src.tail)}`)}
    <div class="field-row field-heads"><span>Field</span><span></span><span>CSV column</span><span>First row</span></div>
    ${m.fields.map((f) => fieldRow(m, f)).join("")}
  </section>`;
}

// --- Courier names -----------------------------------------------------------

function courierMenu(c, row, n) {
  const items = c.codes
    .map((code, i) => menuItem("courier-code", { index: n, value: code }, code, "", code === row.code, `courier-code-${n}-item-${i}`, false))
    .join("");
  const rule = c.codes.length ? `<div class="menu-separator"></div>` : "";
  return `<div class="menu courier-menu" role="menu">${items}${rule}<input class="field new-courier" type="text" placeholder="New courier" aria-label="New courier" data-new-courier="${n}" data-key="courier-new-${n}"></div>`;
}

function courierRow(c, row, n) {
  const menuName = `courier-code-${n}`;
  const open = view.menu === menuName;
  const value = row.code
    ? `<span class="select-value">${esc(row.code)}</span>`
    : `<span class="select-value placeholder">Choose courier</span>`;
  return `<div class="courier-row" data-courier="${n}">
    <input class="field mono" type="text" value="${esc(row.text)}" placeholder="dhl express" aria-label="Shipping method contains" data-input="courier_pattern" data-index="${n}" data-key="courier-text-${n}">
    ${svg(GLYPH.arrowRight, "glyph arrow")}
    <div class="menu-anchor">
      <button class="select" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="Courier" data-act="menu" data-menu="${menuName}" data-key="${menuName}">${value}${svg(GLYPH.chevron, "glyph")}</button>
      ${open ? courierMenu(c, row, n) : ""}
    </div>
    <button class="btn ghost icon" type="button" title="Remove" aria-label="Remove" data-act="courier-remove" data-index="${n}" data-key="courier-remove-${n}">${svg(GLYPH.x, "glyph")}</button>
  </div>`;
}

function couriersCard(c) {
  const add = `<button class="btn secondary" type="button" data-act="courier-add" data-key="courier-add">Add name</button>`;
  const body = c.rows.length
    ? `<div class="courier-row courier-heads"><span>Shipping method contains</span><span></span><span>Courier</span><span></span></div>${c.rows.map((row, n) => courierRow(c, row, n)).join("")}`
    : `<div class="card-empty">${esc(c.empty)}</div>`;
  return `<section class="card" data-card="couriers">
    ${cardHead("Courier names", esc(c.text), add)}
    ${body}
  </section>`;
}

// --- Additional columns ------------------------------------------------------

function chip(item) {
  const menuName = `chip:${item.name}`;
  const open = view.menu === menuName;
  const note = item.note ? `<span class="chip-note">${esc(item.note)}</span>` : "";
  const menu = open
    ? `<div class="menu" role="menu"><button class="menu-item" type="button" role="menuitemcheckbox" aria-checked="${Boolean(item.fill)}" data-act="column-fill" data-name="${esc(item.name)}" data-key="${esc(`chip-fill:${item.name}`)}">${svg(GLYPH.check, "check")}<span class="menu-label">Fill down onto every line of the order</span></button></div>`
    : "";
  return `<span class="menu-anchor chip-anchor" data-chip="${esc(item.name)}">
    <span class="chip"><button class="chip-name mono" type="button" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="${esc(menuName)}" data-key="${esc(menuName)}">${esc(item.name)}</button>${note}<button class="chip-remove" type="button" title="Remove" aria-label="Remove ${esc(item.name)}" data-act="column-remove" data-name="${esc(item.name)}" data-key="${esc(`chip-remove:${item.name}`)}">${svg(GLYPH.x, "glyph")}</button></span>
    ${menu}
  </span>`;
}

function additionalCard(a) {
  const open = view.menu === "column-add";
  const items = a.candidates
    .map((candidate, n) => menuItem("column-add", { name: candidate.name }, candidate.name, candidate.note, false, `column-add-item-${n}`, true))
    .join("");
  const menu = open
    ? `<div class="menu add-menu" role="menu"><div class="menu-group">${esc(a.group)}</div>${items}</div>`
    : "";
  const add = `<div class="menu-anchor">
      <button class="btn secondary" type="button" aria-haspopup="menu" aria-expanded="${open}" title="${esc(a.add_title)}" data-act="menu" data-menu="column-add" data-key="column-add"${off(!a.candidates.length)}>Add column</button>
      ${menu}
    </div>`;
  const notice = a.notice ? `<div class="card-notice">${esc(a.notice)}</div>` : "";
  const chips = a.chips.length
    ? a.chips.map(chip).join("")
    : `<span class="chips-empty">${esc(a.empty)}</span>`;
  return `<section class="card" data-card="additional">
    ${cardHead("Additional columns", esc(a.text), add)}
    ${notice}
    <div class="chips">${chips}</div>
  </section>`;
}

function mappingPage(m) {
  return (
    fieldsCard(m) +
    (m.couriers ? couriersCard(m.couriers) : "") +
    (m.additional ? additionalCard(m.additional) : "")
  );
}

// --- render ------------------------------------------------------------------

// A menu whose opener a new state removed or disabled must not stay open.
function menuStillOpens(s) {
  const name = view.menu;
  if (s.rules) return rulesMenuStillOpens(s.rules, name);
  // A list page's menu whose opener is gone is dropped after the morph.
  if (listPageOf(s)) return true;
  const m = s.mapping;
  if (!m) return false;
  if (name.startsWith("field-")) {
    return m.can_pick && m.fields.some((f) => `field-${f.name}` === name);
  }
  if (name.startsWith("courier-code-")) {
    return Boolean(m.couriers) && Number(name.slice("courier-code-".length)) < m.couriers.rows.length;
  }
  if (name === "column-add") {
    return Boolean(m.additional) && m.additional.candidates.length > 0;
  }
  if (name.startsWith("chip:")) {
    return Boolean(m.additional) && m.additional.chips.some((item) => `chip:${item.name}` === name);
  }
  return false;
}

function keyOf(node) {
  return node.dataset ? node.dataset.key : undefined;
}

// Bring `old` to match `fresh`, keeping every node that is still the same
// control. Every keystroke in a field comes back as a new state: the field
// being typed in must stay the node the caret is in, with the text the
// operator sees, and a press that began on a button must find that button
// there at its release.
function morph(old, fresh) {
  const was = Array.from(old.childNodes);
  const now = Array.from(fresh.childNodes);
  now.forEach((node, n) => {
    const at = was[n];
    if (!at) {
      old.appendChild(node);
    } else if (at.nodeName !== node.nodeName || keyOf(at) !== keyOf(node)) {
      old.replaceChild(node, at);
    } else if (at.nodeType !== Node.ELEMENT_NODE) {
      if (at.data !== node.data) at.data = node.data;
    } else {
      for (const name of at.getAttributeNames()) {
        if (!node.hasAttribute(name)) at.removeAttribute(name);
      }
      for (const name of node.getAttributeNames()) {
        const value = node.getAttribute(name);
        if (at.getAttribute(name) !== value) at.setAttribute(name, value);
      }
      if (at.nodeName === "INPUT") {
        // The attributes are only the defaults once a field has been used.
        if (at !== document.activeElement) at.value = node.value;
      } else {
        morph(at, node);
      }
    }
  });
  was.slice(now.length).forEach((node) => node.remove());
}

// By comparison, not by selector: a key can hold a column's name, and a
// column's name can hold any character.
function byKey(key) {
  return Array.from(els.root.querySelectorAll("[data-key]")).find((el) => el.dataset.key === key) || null;
}

function focusKey(key) {
  const el = byKey(key);
  if (!el || el.disabled) return false;
  el.focus();
  return true;
}

function render() {
  const s = page.state;
  if (!s || !s.page) return;
  if (s.page !== view.shown) {
    view.menu = null;
    view.pending = null;
  }
  if (view.menu !== null && !menuStillOpens(s)) view.menu = null;
  // A new state under a drag: the rows it was measuring may be gone.
  endDrag();
  const active = document.activeElement;
  const key = active ? keyOf(active) : null;
  const listPage = listPageOf(s);
  const fresh = document.createElement("template");
  // The Test panel takes the page over: what is under it cannot be reached.
  fresh.innerHTML =
    `<div class="settings-page" data-page="${esc(s.page)}"${s.test ? " inert" : ""}>` +
    head(s) +
    (s.general ? generalPage(s.general) : "") +
    (s.mapping ? mappingPage(s.mapping) : "") +
    (s.rules ? rulesPage(s.rules) : "") +
    (listPage ? LIST_PAGES[listPage][0](s[listPage]) : "") +
    "</div>" +
    (s.test ? testPanel(s.test) : "");
  morph(els.root, fresh.content);
  // A menu whose opener this state no longer draws (a removed row).
  if (view.menu !== null && !byKey(view.menu)) view.menu = null;
  if (s.page !== view.shown) {
    view.shown = s.page;
    els.root.scrollTop = 0;
    // Its "Update them" belongs to the page just left.
    dismissToast();
  } else if (key && keyOf(document.activeElement) !== key) {
    // Where the layout itself changed, the focused control is a new node.
    focusKey(key);
  }
  if (view.pending !== null && focusKey(view.pending)) view.pending = null;
  focusPending();
  rulesRendered(s);
  if (view.problem !== null) {
    const problem = view.problem;
    view.problem = null;
    focusProblem(problem, true);
  }
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// The "@css:", "@css-select:" and "@keys:" requests (see `view`): focus for
// a control whose key the page could not know when it asked.
function focusPending() {
  const pending = view.pending;
  if (typeof pending !== "string") return;
  if (pending.startsWith("@css:") || pending.startsWith("@css-select:")) {
    const el = els.root.querySelector(pending.slice(pending.indexOf(":") + 1));
    if (!el) return;
    el.focus();
    if (pending.startsWith("@css-select:")) el.select();
    view.pending = null;
  } else if (pending.startsWith("@keys:")) {
    if (pending.slice("@keys:".length).split("|").some((key) => focusKey(key))) view.pending = null;
  }
}

// --- the toast (phase 9 spec section 8.3) --------------------------------------

const TOAST_MS = 4000;
const TOAST_ACTION_MS = 8000;
let toastTimer = null;

function dismissToast() {
  if (toastTimer !== null) clearTimeout(toastTimer);
  toastTimer = null;
  els.toast.hidden = true;
}

// A new toast replaces the one showing. `update` puts "Update them" on it,
// and such a toast stays longer.
function raiseToast(text, update) {
  els.toastText.textContent = text;
  els.toastAction.hidden = !update;
  els.toast.hidden = false;
  if (toastTimer !== null) clearTimeout(toastTimer);
  toastTimer = setTimeout(dismissToast, update ? TOAST_ACTION_MS : TOAST_MS);
}

// --- input -------------------------------------------------------------------

function closeMenu(focus) {
  const menu = view.menu;
  if (menu === null) return;
  view.menu = null;
  render();
  focusKey(focus || menu);
}

function onClick(event) {
  const el = event.target.closest("[data-act]");
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const data = el.dataset;
  if (rulesClick(data, el, bridge)) return;
  if (Object.values(LIST_PAGES).some((fns) => fns[1](data, el, bridge))) return;
  switch (data.act) {
    case "read": bridge.readColumns(); break;
    case "delimiter": bridge.edit("delimiter", [data.kind, data.value]); break;
    case "menu":
      view.menu = view.menu === data.menu ? null : data.menu;
      render();
      focusKey(data.menu);
      break;
    case "column":
      bridge.edit("column", [data.field, data.value]);
      closeMenu();
      break;
    case "courier-add":
      // The new row is the next index: focus its text once it arrives.
      view.pending = `courier-text-${page.state.mapping.couriers.rows.length}`;
      bridge.edit("courier_add", []);
      break;
    case "courier-code":
      bridge.edit("courier_code", [data.index, data.value]);
      closeMenu();
      break;
    case "courier-remove": bridge.edit("courier_remove", [data.index]); break;
    case "column-add":
      bridge.edit("column_add", [data.name]);
      closeMenu();
      break;
    case "column-remove": bridge.edit("column_remove", [data.name]); break;
    case "column-fill":
      bridge.edit("column_fill", [data.name, el.getAttribute("aria-checked") !== "true"]);
      break;
  }
}

// A text field reports every keystroke: the unsaved mark and Save follow the
// typing, and Python answers with a state the render folds in around the caret.
function onInput(event) {
  const el = event.target;
  const bridge = page.bridge;
  if (!bridge || !el.dataset || !el.dataset.input) return;
  const data = el.dataset;
  if (rulesInput(data, el, bridge)) return;
  if (Object.values(LIST_PAGES).some((fns) => fns[2](data, el, bridge))) return;
  if (data.input === "threshold") bridge.edit("threshold", [el.value]);
  else if (data.input === "delimiter_char") bridge.edit("delimiter_char", [data.kind, el.value]);
  else if (data.input === "courier_pattern") bridge.edit("courier_pattern", [data.index, el.value]);
}

function onKey(event) {
  const target = event.target;
  if (event.key === "Escape") {
    // With no menu open, no drag and no Test panel, the page leaves Escape
    // alone, and the dialog takes it.
    if (view.menu !== null) {
      event.preventDefault();
      closeMenu();
    } else if (rulesEscape()) {
      event.preventDefault();
    }
    return;
  }
  if (event.key === "Enter" && target.dataset && target.dataset.newCourier !== undefined) {
    event.preventDefault();
    if (page.bridge) page.bridge.edit("courier_code", [target.dataset.newCourier, target.value]);
    closeMenu();
    return;
  }
  // A field that adds on Enter (a category's tag): report it and empty it.
  if (event.key === "Enter" && target.dataset && target.dataset.enter) {
    event.preventDefault();
    if (page.bridge) page.bridge.edit(target.dataset.enter, [target.dataset.uid, target.value]);
    target.value = "";
    return;
  }
  const vertical = event.key === "ArrowUp" || event.key === "ArrowDown";
  if (vertical && view.menu !== null) {
    // Up and Down walk the open menu, from its opener or from an item.
    const items = Array.from(els.root.querySelectorAll(".menu .menu-item, .menu .new-courier"));
    if (!items.length) return;
    const at = items.indexOf(document.activeElement);
    const step = event.key === "ArrowUp" ? -1 : 1;
    const next = at < 0 ? (step > 0 ? 0 : items.length - 1) : (at + step + items.length) % items.length;
    event.preventDefault();
    items[next].focus();
    return;
  }
  // Left and Right move between a delimiter's segments; Space and Enter are
  // the button's own.
  const segment = target.closest ? target.closest(".segment") : null;
  if (!segment || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
  const group = Array.from(segment.parentElement.querySelectorAll(".segment"));
  const step = event.key === "ArrowLeft" ? -1 : 1;
  event.preventDefault();
  group[(group.indexOf(segment) + step + group.length) % group.length].focus();
}

// The footer's link: put the operator on the control that blocks the save.
// When the link also changed the page, the request gets here before the state
// that draws the control: it waits for the next render, and no longer.
function focusProblem(key, drawn) {
  const el = byKey(key);
  if (!el) {
    if (!drawn) view.problem = key;
    return;
  }
  el.scrollIntoView({ block: "center" });
  if (!el.disabled) el.focus();
}

// --- boot --------------------------------------------------------------------

function bind() {
  els.root = document.getElementById("settings");
  els.themeVars = document.getElementById("theme-vars");
  els.toast = document.getElementById("toast");
  els.toastText = document.getElementById("toast-text");
  els.toastAction = document.getElementById("toast-action");
  const toastClose = document.getElementById("toast-dismiss");
  toastClose.innerHTML = svg(GLYPH.x, "glyph");
  toastClose.addEventListener("click", dismissToast);
  els.toastAction.addEventListener("click", () => {
    dismissToast();
    if (page.bridge) page.bridge.toastAction();
  });
  els.root.addEventListener("click", onClick);
  els.root.addEventListener("input", onInput);
  document.addEventListener("keydown", onKey);
  // After the page's own handler: a click anywhere but a menu's anchor closes
  // the open menu.
  document.addEventListener("click", (event) => {
    if (view.menu === null || event.target.closest(".menu-anchor")) return;
    view.menu = null;
    render();
  });
  // A file dropped on the page must not navigate the view. It loads nothing.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => event.preventDefault());
  bindRules();
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.settings;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => {
    els.themeVars.textContent = bridge.themeCss;
    // Two frames: the first callback runs before this frame is painted.
    requestAnimationFrame(() => requestAnimationFrame(() => bridge.themeApplied()));
  });
  bridge.stateChanged.connect(() => { page.state = bridge.state; render(); });
  bridge.problemFocusRequested.connect((key) => focusProblem(key));
  bridge.toastRaised.connect(raiseToast);
  page.state = bridge.state;
  render();
  window.settingsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
