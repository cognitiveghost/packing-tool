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

// --- Packing ------------------------------------------------------------------

const ORDER_BADGE = {
  packed: ["Packed", "badge success"],
  in_progress: ["In progress", "badge info"],
  not_started: ["Not started", "badge neutral"],
};
const ITEM_BADGE = {
  complete: ["Complete", "badge success"],
  partial: ["Partial", "badge info"],
  pending: ["Pending", "badge neutral"],
};
const SVG_NS = "http://www.w3.org/2000/svg";
const CHEVRON_DOWN = "m6 9 6 6 6-6";
const CHEVRON_RIGHT = "m9 18 6-6-6-6";

function glyph(d) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "glyph");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", d);
  svg.appendChild(path);
  return svg;
}

function badge(pair) {
  return el("span", pair[1], pair[0]);
}

// Text that an ellipsis may cut keeps its whole self in the tooltip.
function cut(cls, text) {
  const node = el("span", "app-cut " + cls, text);
  node.title = text;
  return node;
}

function isOpen(order) {
  return order.number in view.toggled ? view.toggled[order.number] : !!order.open;
}

function orderRow(order) {
  const open = isOpen(order);
  const row = el("button", "tbl-row app-order");
  row.type = "button";
  row.dataset.order = order.number;
  row.setAttribute("aria-expanded", String(open));

  const first = el("span", "app-order-no");
  first.appendChild(glyph(open ? CHEVRON_DOWN : CHEVRON_RIGHT));
  first.appendChild(el("span", "app-order-label", order.label));
  if (order.skipped) first.appendChild(el("span", "badge warning", "Skipped"));
  row.appendChild(first);

  row.appendChild(cut("app-order-summary", order.summary));
  row.appendChild(el("span", "app-qty", order.packed + " / " + order.units));
  const status = el("span", "app-status");
  status.appendChild(badge(ORDER_BADGE[order.status] || ORDER_BADGE.not_started));
  row.appendChild(status);
  row.appendChild(el("span", "app-courier", order.courier));
  return row;
}

function itemRow(item) {
  const row = el("div", "tbl-row app-item" + (item.hit ? " hit" : ""));
  row.appendChild(cut("app-item-sku", item.sku));
  row.appendChild(cut("", item.product));
  row.appendChild(el("span", "app-qty", item.packed + " / " + item.required));
  const status = el("span", "app-status");
  status.appendChild(badge(ITEM_BADGE[item.state] || ITEM_BADGE.pending));
  row.appendChild(status);
  row.appendChild(el("span"));
  return row;
}

function renderPacking() {
  syncSession();
  const packing = view.bridge.packing || {};
  const totals = packing.totals || {};
  const query = packing.query || "";
  // What the packer opened by hand belongs to one filter text.
  if (query !== view.query) {
    view.query = query;
    view.toggled = {};
  }
  const orders = totals.orders || 0;
  const done = totals.done || 0;
  const pct = totals.pct || 0;

  els.totDone.textContent = done;
  els.totOrders.textContent = "of " + orders;
  els.totPacked.textContent = totals.packed || 0;
  els.totUnits.textContent = "of " + (totals.units || 0);
  els.totSkipped.textContent = totals.skipped || 0;
  els.totSkippedNote.textContent = totals.skipped ? "still Not started" : "none";
  els.totPct.textContent = pct + "%";
  els.totFill.style.width = pct + "%";
  els.totLeft.textContent = totals.complete
    ? "All orders packed"
    : plural(orders - done, "order", "orders") + " left · " + (totals.in_progress || 0) + " in progress";

  show(els.complete, !!totals.complete);
  els.completeText.textContent = done + " of " + orders + " orders packed.";

  const hits = packing.hits || 0;
  show(els.filterLine, !!query && hits > 0);
  els.filterText.textContent = hits + " of " + orders + " orders contain ";
  els.filterQuery.textContent = query;
  show(els.noMatch, !!query && hits === 0);
  els.noMatchQuery.textContent = query;
  show(els.rows, !(query && hits === 0));

  // ponytail: the whole index is rebuilt on every push. Fine at a few hundred
  // orders; patch rows in place if a list ever reaches thousands.
  const rows = document.createDocumentFragment();
  (packing.groups || []).forEach(function (group) {
    const head = el("div", "tbl-group");
    head.appendChild(el("span", "tbl-group-label", group.label));
    head.appendChild(el("span", "tbl-group-count", group.count));
    head.appendChild(el("span", "tbl-group-note", group.note));
    rows.appendChild(head);
    group.orders.forEach(function (order) {
      rows.appendChild(orderRow(order));
      if (isOpen(order)) order.items.forEach(function (item) { rows.appendChild(itemRow(item)); });
    });
  });
  els.rows.replaceChildren(rows);
}

function toggleOrder(number) {
  const current = (view.bridge.packing.groups || [])
    .flatMap(function (group) { return group.orders; })
    .find(function (order) { return order.number === number; });
  if (!current) return;
  view.toggled[number] = !isOpen(current);
  renderPacking();
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
  const action = event.target.closest("[data-action]");
  if (action) {
    if (!action.disabled) ACTIONS[action.dataset.action](view.bridge);
    return;
  }
  const order = event.target.closest("[data-order]");
  if (order) toggleOrder(order.dataset.order);
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
  totDone: "tot-done", totOrders: "tot-orders", totPacked: "tot-packed", totUnits: "tot-units",
  totSkipped: "tot-skipped", totSkippedNote: "tot-skipped-note", totPct: "tot-pct",
  totFill: "tot-fill", totLeft: "tot-left",
  complete: "complete", completeText: "complete-text",
  filterLine: "filter-line", filterText: "filter-text", filterQuery: "filter-query",
  noMatch: "no-match", noMatchQuery: "no-match-query", rows: "rows",
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
  bridge.packingChanged.connect(renderPacking);
  renderPacking();
  els.root.addEventListener("click", onClick);

  // After the first render, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
