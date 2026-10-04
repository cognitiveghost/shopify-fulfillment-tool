// The Tag categories page (phase 9 spec section 7). settings.js renders and
// routes; this file draws what bridge.state holds under `tags`. Python holds
// every category and words every sentence (gui/settings/tags_state.py).
//
// Loaded after settings_rules.js and settings_sets.js, before settings.js: it
// uses ruleSelect and OPEN_NAME from them. Enter in the tag field is
// settings.js's: a field with data-enter reports edit(data.enter, [uid, text]).
"use strict";

function writeoffRow(e, uid, m, row) {
  const key = `cat-${uid}-m${m}`;
  const menu = () =>
    e.tags
      .map((tag, n) => menuItem("map-tag", { uid, m, value: tag }, tag, "", tag === row.tag, `${key}-tag-item-${n}`, true))
      .join("");
  return `<div class="list-part" data-map="${m}">
    <div class="map-row">
      ${ruleSelect(`${key}-tag`, "Tag", row.tag, false, menu, "map-tag")}
      <input class="field mono${row.invalid === "sku" ? " invalid" : ""}" type="text" value="${esc(row.sku)}" placeholder="SKU to write off" aria-label="SKU to write off" data-input="map_sku" data-uid="${uid}" data-m="${m}" data-key="${key}-sku">
      <span class="times">×</span>
      <input class="field mono amount${row.invalid === "quantity" ? " invalid" : ""}" type="text" inputmode="decimal" value="${esc(row.quantity)}" aria-label="Quantity" data-input="map_quantity" data-uid="${uid}" data-m="${m}" data-key="${key}-quantity">
      <button class="btn ghost compact icon" type="button" title="Remove write-off" aria-label="Remove write-off" data-act="map-remove" data-uid="${uid}" data-m="${m}" data-key="${key}-remove">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${row.problem ? problemLine(row.problem) : ""}
  </div>`;
}

function categoryEditor(row) {
  const e = row.editor;
  const uid = row.uid;
  const key = `cat-${uid}`;
  const w = e.writeoff;
  const chips = e.tags
    .map(
      (tag) =>
        `<span class="chip"><span class="mono">${esc(tag)}</span><button class="chip-remove" type="button" title="Remove" aria-label="Remove ${esc(tag)}" data-act="tag-remove" data-uid="${uid}" data-tag="${esc(tag)}" data-key="${esc(`${key}-tag-remove:${tag}`)}">${svg(GLYPH.x, "glyph")}</button></span>`,
    )
    .join("");
  return `<div class="list-editor">
    ${e.label_problem ? problemLine(e.label_problem) : ""}
    <div class="editor-line">
      <span class="editor-label">Tags</span>
      <div class="editor-content">
        <div class="report-chips">
          ${chips}
          <input class="field mono tag-input" type="text" placeholder="${esc(e.tag_placeholder)}" aria-label="${esc(e.tag_placeholder)}" data-enter="tag_add" data-uid="${uid}" data-key="${key}-tag-input">
        </div>
        ${under(e.tag_problem, e.tag_hint)}
      </div>
    </div>
    <div class="editor-line">
      <span class="editor-label">${esc(w.label)}</span>
      <div class="editor-content">
        <div class="control-line">
          <button class="switch" type="button" role="switch" aria-checked="${Boolean(w.on)}" aria-label="${esc(w.label)}" data-act="cat-writeoff" data-uid="${uid}" data-key="${key}-writeoff"><span class="switch-knob"></span></button>
          <span class="hint">${esc(w.hint)}</span>
        </div>
        ${w.rows.map((mapping, m) => writeoffRow(e, uid, m, mapping)).join("")}
        <button class="btn ghost compact add-row" type="button" title="${esc(w.add_title)}" data-act="map-add" data-uid="${uid}" data-count="${w.rows.length}" data-key="${key}-map-add"${off(!w.can_add)}>${svg(GLYPH.plus, "glyph")}Add write-off</button>
      </div>
    </div>
    <div class="editor-foot">
      <span class="spacer"></span>
      <button class="btn secondary" type="button" data-act="cat-close" data-uid="${uid}" data-key="${key}-done">Done</button>
    </div>
  </div>`;
}

function categoryRow(row) {
  const key = `cat-${row.uid}`;
  const name = row.open
    ? `<input class="field list-name-field${row.editor.label_problem ? " invalid" : ""}" type="text" value="${esc(row.name)}" placeholder="Category name" aria-label="Category name" data-input="cat_label" data-uid="${row.uid}" data-key="${key}-label">`
    : `<button class="list-name" type="button" data-act="cat-open" data-uid="${row.uid}" data-key="${key}-label">${esc(row.label)}</button>`;
  let chips = "";
  if (!row.open) {
    chips = row.chips.length
      ? row.chips.map((tag) => `<span class="rule-chip mono" title="${esc(tag)}">${esc(tag)}</span>`).join("")
      : `<span class="list-muted">${esc(row.no_tags)}</span>`;
  }
  const badge = row.badge ? `<span class="badge neutral">${esc(row.badge)}</span>` : "";
  const move = (dir, glyph, able, title) =>
    `<button class="btn ghost compact icon" type="button" title="${title}" aria-label="${title}" data-act="cat-move" data-uid="${row.uid}" data-dir="${dir}" data-key="${key}-${dir}"${off(!able)}>${svg(glyph, "glyph")}</button>`;
  return `<div class="list-row${row.open ? " open" : ""}" data-category="${row.uid}" data-key="${key}">
    <div class="list-text">
      <div class="list-head">${name}${chips}${badge}</div>
      ${!row.open && row.problem ? problemLine(row.problem) : ""}
    </div>
    <div class="list-actions">
      ${move("up", RULE_GLYPH.up, row.can_up, "Move up")}
      ${move("down", GLYPH.chevron, row.can_down, "Move down")}
      <button class="btn ghost compact icon" type="button" title="Delete category" aria-label="Delete category" data-act="cat-delete" data-uid="${row.uid}" data-key="${key}-delete">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${row.open ? categoryEditor(row) : ""}
  </div>`;
}

function tagsPage(t) {
  if (t.empty) {
    return `<section class="card state rules-empty" data-card="tags-empty">
      <p class="state-title">${esc(t.empty.title)}</p>
      <p class="state-text">${esc(t.empty.text)}</p>
      <button class="btn primary" type="button" data-act="cat-add" data-key="cat-add">${svg(GLYPH.plus, "glyph")}${esc(t.empty.action)}</button>
    </section>`;
  }
  return `<section class="card" data-card="tags">
    <div class="list-bar"><span class="list-count">${esc(t.count)}</span></div>
    ${t.rows.map(categoryRow).join("")}
  </section>`;
}

// Whether the click was one of this page's.
function tagsClick(data, el, bridge) {
  const uid = data.uid;
  switch (data.act) {
    case "cat-add":
      // The new category's name is there to be typed over.
      view.pending = `@css-select:${OPEN_NAME.slice("@css:".length)}`;
      bridge.edit("cat_add", []);
      return true;
    case "cat-open":
      view.pending = OPEN_NAME;
      bridge.edit("open", [uid]);
      return true;
    case "cat-close":
      view.pending = `cat-${uid}-label`;
      bridge.edit("close", []);
      return true;
    case "cat-delete":
      view.pending = "cat-add";
      bridge.edit("cat_delete", [uid]);
      return true;
    case "cat-move": {
      const other = data.dir === "up" ? "down" : "up";
      view.pending = `@keys:cat-${uid}-${data.dir}|cat-${uid}-${other}`;
      bridge.edit("cat_move", [uid, data.dir]);
      return true;
    }
    case "tag-remove":
      view.pending = `cat-${uid}-tag-input`;
      bridge.edit("tag_remove", [uid, data.tag]);
      return true;
    case "cat-writeoff":
      bridge.edit("writeoff", [uid, el.getAttribute("aria-checked") !== "true"]);
      return true;
    case "map-add":
      view.pending = `cat-${uid}-m${data.count}-sku`;
      bridge.edit("map_add", [uid]);
      return true;
    case "map-remove":
      view.pending = `cat-${uid}-map-add`;
      bridge.edit("map_remove", [uid, data.m]);
      return true;
    case "map-tag":
      bridge.edit("map_tag", [uid, data.m, data.value]);
      closeMenu();
      return true;
  }
  return false;
}

// Whether the keystroke was in one of this page's fields.
function tagsInput(data, el, bridge) {
  switch (data.input) {
    case "cat_label":
      bridge.edit("cat_label", [data.uid, el.value]);
      return true;
    case "map_sku":
      bridge.edit("map_sku", [data.uid, data.m, el.value]);
      return true;
    case "map_quantity":
      bridge.edit("map_quantity", [data.uid, data.m, el.value]);
      return true;
  }
  return false;
}
