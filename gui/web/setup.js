// The setup document: Worker selection and SKU mapping. Filled in by the
// next task; this much connects the bridge and reports paints.
"use strict";

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.setup;
  window.setupBridge = bridge;
  const themeVars = document.getElementById("theme-vars");
  const onTheme = function () { themeVars.textContent = bridge.themeCss; };
  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
