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
