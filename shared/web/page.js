// What every web page does besides drawing itself (shared/web_page.py).
// Loaded before the page's own script; no module, no build step.

// Tell Python which revision of the bridge's state this page has painted.
// Two frames: the first callback runs before the frame that holds the new
// DOM is painted. Pages render synchronously in their signal handlers, so
// the DOM is current by then whatever order the handlers ran in.
function reportPaints(bridge) {
  let sent = -1;
  const report = () => {
    const revision = bridge.revision;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (revision <= sent) return;
      sent = revision;
      document.documentElement.dataset.painted = String(revision);
      bridge.paintedRevision(revision);
    }));
  };
  bridge.revisionChanged.connect(report);
  report();
}

// The page in the PC's language (shared/i18n.py, ADR 0021). English text is the
// key; a key the catalogue lacks shows its English. Call applyStrings(bridge)
// once the bridge is ready and before the page first draws.
let STRINGS = {};

function formatText(text, vars) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (field, name) => (name in vars ? String(vars[name]) : field));
}

function t(text, vars) {
  const found = STRINGS[text];
  return formatText(typeof found === "string" ? found : text, vars);
}

function tn(one, other, n, vars) {
  const found = STRINGS[one];
  const forms = Array.isArray(found) && found.length === 2 ? found : [one, other];
  return formatText(n === 1 ? forms[0] : forms[1], Object.assign({ n }, vars));
}

function applyStrings(bridge) {
  STRINGS = JSON.parse(bridge.strings || "{}");
  document.documentElement.lang = bridge.language || "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.textContent.replace(/\s+/g, " ").trim());
  });
  document.querySelectorAll("[data-i18n-attr]").forEach((el) => {
    for (const name of el.dataset.i18nAttr.split(",")) {
      const attr = name.trim();
      if (el.hasAttribute(attr)) el.setAttribute(attr, t(el.getAttribute(attr)));
    }
  });
}
