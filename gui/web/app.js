// The app document: Packing and Statistics (ADR 0003). The page renders what
// the bridge sends. Totals, groups, filter hits and failure sentences are
// decided in gui/app_bridge.py; the page keeps only which order rows were
// toggled and how the SKU table is sorted. Every string from the bridge goes
// in through textContent. Spec:
// docs/superpowers/specs/2026-10-08-ui-refresh-phase3-packing-statistics-design.md
"use strict";

const els = {};
const view = {
  bridge: null,
  sessionId: null,
  query: null,
  toggled: {},
  sort: { key: "left", dir: -1 },
  toastTimer: 0,
};

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function show(node, on) {
  node.hidden = !on;
}

function plural(count, one, many) {
  return count + " " + (count === 1 ? one : many);
}

// The page's own state belongs to one session: a new id drops it.
function syncSession() {
  const id = (view.bridge.session || {}).id || "";
  if (id === view.sessionId) return;
  view.sessionId = id;
  view.toggled = {};
  view.sort = { key: "left", dir: -1 };
}

// --- which block shows, the header, 3b and 3c --------------------------------

function renderFrame() {
  syncSession();
  const bridge = view.bridge;
  const shell = bridge.shell || {};
  const session = bridge.session || {};
  const state = session.state || "none";
  const page = bridge.page;
  const packing = page === "packing";
  const client = !!shell.client;
  const on = function (condition) { return !bridge.covered && condition; };

  show(els.noClient, on(!client));
  show(els.chooseClient, !!shell.clients);
  show(els.noSession, on(client && state === "none" && packing));
  els.openSession.disabled = !!shell.serverDown;
  show(els.statsEmpty, on(client && state === "none" && !packing));
  show(els.head, on(client && state !== "none"));
  show(els.opening, on(client && state === "opening"));
  show(els.failed, on(client && state === "failed"));
  show(els.packing, on(client && state === "open" && packing));
  show(els.statistics, on(client && state === "open" && !packing));
  if (bridge.covered) show(els.toast, false);

  const open = state === "open";
  els.headTitle.textContent = packing || !open ? session.list || "" : "Statistics";
  els.headTitle.title = els.headTitle.textContent;
  show(els.headBadge, open);
  show(els.headId, open && packing);
  show(els.headDot, open && packing);
  els.headId.textContent = session.id || "";
  els.headMeta.textContent = !open ? "" : packing ? session.meta || "" : session.list || "";
  show(els.headStart, open && packing);
  els.headStart.disabled = !!session.complete;

  const step = session.step || 0;
  els.stepCount.textContent = "Working · step " + step + " of 3";
  els.stepName.textContent = session.stepName || "";
  els.stepList.textContent = session.list || "";
  els.stepId.textContent = session.id || "";
  els.stepBars.forEach(function (bar, index) {
    bar.classList.toggle("done", index < step);
  });

  els.failedTitle.textContent = session.title || "";
  els.failedText.textContent = session.text || "";
}

// --- toast --------------------------------------------------------------------

function hideToast() {
  clearTimeout(view.toastTimer);
  show(els.toast, false);
}

function toast(message) {
  els.toastText.textContent = message;
  show(els.toast, true);
  clearTimeout(view.toastTimer);
  view.toastTimer = setTimeout(hideToast, 4000);
}

// --- clicks -------------------------------------------------------------------

const ACTIONS = {
  chooseClient: function (bridge) { bridge.chooseClient(); },
  openSession: function (bridge) { bridge.openSession(); },
  goPacking: function (bridge) { bridge.showPage("packing"); },
  startPacking: function (bridge) { bridge.startPacking(); },
  endSession: function (bridge) { bridge.endSession(); },
  retryStart: function (bridge) { bridge.retryStart(); },
  closeFailure: function (bridge) { bridge.closeFailure(); },
  clearFilter: function (bridge) { bridge.clearFilter(); },
};

function onClick(event) {
  const target = event.target.closest("[data-action]");
  if (target && !target.disabled) ACTIONS[target.dataset.action](view.bridge);
}

const IDS = {
  root: "app", themeVars: "theme-vars",
  noClient: "no-client", chooseClient: "choose-client",
  noSession: "no-session", openSession: "open-session", statsEmpty: "stats-empty",
  head: "head", headTitle: "head-title", headBadge: "head-badge", headId: "head-id",
  headDot: "head-dot", headMeta: "head-meta", headStart: "head-start",
  opening: "opening", stepCount: "step-count", stepName: "step-name",
  stepList: "step-list", stepId: "step-id",
  failed: "failed", failedTitle: "failed-title", failedText: "failed-text",
  packing: "packing", statistics: "statistics",
  toast: "toast", toastText: "toast-text", toastClose: "toast-close",
};

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.app;
  view.bridge = bridge;
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.appBridge = bridge;
  Object.keys(IDS).forEach(function (key) {
    els[key] = document.getElementById(IDS[key]);
  });
  els.stepBars = Array.from(document.querySelectorAll(".app-step-bar"));

  const onTheme = function () { els.themeVars.textContent = bridge.themeCss; };
  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.toastRaised.connect(toast);
  els.toastClose.addEventListener("click", hideToast);

  [bridge.pageChanged, bridge.coveredChanged, bridge.shellChanged, bridge.sessionChanged]
    .forEach(function (signal) { signal.connect(renderFrame); });
  renderFrame();
  els.root.addEventListener("click", onClick);

  // After the first render, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
