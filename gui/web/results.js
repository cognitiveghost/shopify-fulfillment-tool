// The page's end of the bridge (gui/results_bridge.py). Bundle 11 keeps the
// theme live and hands the bridge to the page; the results document (9.13)
// is built on top of this.
new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.results;
  const themeVars = document.getElementById("theme-vars");
  const applyTheme = function () {
    themeVars.textContent = bridge.themeCss;
  };
  applyTheme();
  bridge.themeCssChanged.connect(applyTheme);
  window.resultsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
