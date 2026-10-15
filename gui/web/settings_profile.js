// The Client > Profile page (spec A4). settings.js renders and routes; this
// file draws what bridge.state holds under `profile`. Python holds every
// value and words every sentence (gui/settings/profile_state.py).
//
// Loaded after settings_rules.js and settings_tags.js, before settings.js: it
// uses ruleSelect from settings_rules.js and LIST_PAGES in settings.js reads
// these functions when it loads.
"use strict";

function profilePage(p) {
  const group = p.groups.find((o) => o.checked) || p.groups[0];
  const groupMenu = () =>
    p.groups
      .map((o, n) => menuItem("profile-group", { value: o.value }, o.label, "", o.checked, `profile-group-item-${n}`))
      .join("");
  const stats = p.stats
    .map((s) => `<div class="card-row" data-stat><span class="card-label">${esc(s.label)}</span><span class="card-control mono">${esc(s.value)}</span></div>`)
    .join("");
  return `<section class="card" data-card="profile">
    ${cardHead(t("Client"), "")}
    <div class="card-row"><span class="card-label">${t("Name")}</span><div class="card-control">
      <input class="field${p.name.problem ? " invalid" : ""}" type="text" value="${esc(p.name.value)}" aria-label="${t("Client name")}" data-input="profile_name" data-key="profile-name">
      ${p.name.problem ? problemLine(p.name.problem) : ""}
    </div></div>
    <div class="card-row"><span class="card-label">${t("Client ID")}</span><div class="card-control">
      <span class="mono" data-key="profile-id">${esc(p.client_id)}</span>
    </div></div>
    <div class="card-row"><span class="card-label">${t("Group")}</span><div class="card-control">
      ${ruleSelect("profile-group", t("Group"), group.label, false, groupMenu, "profile-group")}
    </div></div>
    <div class="card-row"><span class="card-label">${t("Colour")}</span><div class="card-control">
      <input type="color" value="${esc(p.colour)}" aria-label="${t("Client colour")}" data-input="profile_colour" data-key="profile-colour">
    </div></div>
    <div class="card-row"><span class="card-label">${t("Pinned")}</span><div class="card-control">
      <button class="switch" type="button" role="switch" aria-checked="${Boolean(p.pinned)}" aria-label="${t("Pinned")}" data-act="profile-pin" data-key="profile-pin"><span class="switch-knob"></span></button>
    </div></div>
  </section>
  <section class="card" data-card="stats">
    ${cardHead(t("Statistics"), "")}
    ${stats}
  </section>
  <section class="card" data-card="danger">
    ${cardHead(t("Danger zone"), "")}
    <div class="card-row"><span class="card-label"></span><div class="card-control">
      <button class="btn secondary" type="button" data-act="profile-archive" data-key="profile-archive">${esc(p.archive.label)}</button>
      <span class="hint">${esc(p.archive.hint)}</span>
    </div></div>
    <div class="card-row"><span class="card-label"></span><div class="card-control">
      <button class="btn secondary" type="button" data-act="profile-delete" data-key="profile-delete"${off(!p.delete.enabled)}>${esc(p.delete.label)}</button>
      <span class="hint">${esc(p.delete.hint)}</span>
    </div></div>
  </section>`;
}

function profileClick(data, el, bridge) {
  switch (data.act) {
    case "profile-pin": bridge.edit("profile_pin", []); return true;
    case "profile-group": bridge.edit("profile_group", [data.value]); closeMenu(); return true;
    case "profile-archive": bridge.clientAction("archive"); return true;
    case "profile-delete": bridge.clientAction("delete"); return true;
  }
  return false;
}

function profileInput(data, el, bridge) {
  if (data.input === "profile_name") { bridge.edit("profile_name", [el.value]); return true; }
  if (data.input === "profile_colour") { bridge.edit("profile_colour", [el.value]); return true; }
  return false;
}
