// The app document: Packing, Statistics, Sessions and Session details (ADR
// 0003). The page renders what the bridge sends. What Packing and Statistics
// say is decided in gui/app_bridge.py, what the Sessions pages say in
// gui/sessions_payload.py; the page keeps only which order rows were toggled,
// how the SKU table is sorted, which session is selected and which orders are
// open in details. Every string from the bridge goes in through textContent.
// Specs: docs/superpowers/specs/2026-10-08-ui-refresh-phase3-packing-statistics-design.md
// and 2026-10-08-ui-refresh-phase4-sessions-design.md
"use strict";

const els = {};
const view = {
  bridge: null,
  sessionId: null,
  query: null,
  toggled: Object.create(null),  // order numbers are data: no inherited keys
  sort: { key: "left", dir: -1 },
  toastTimer: 0,
  sel: null,             // the selected session's key
  tab: null,
  exportOpen: false,
  detailsKey: "",
  dOpen: Object.create(null),  // order numbers open in Session details
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
  view.toggled = Object.create(null);
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
  const stats = page === "statistics";
  const work = packing || stats;  // the two pages of the session open here
  const client = !!shell.client;
  const on = function (condition) { return !bridge.covered && condition; };

  show(els.noClient, on(!client));
  show(els.chooseClient, !!shell.clients);
  els.noClientTitle.textContent = work ? "Choose a client to begin" : "Choose a client";
  els.noClientText.textContent = work
    ? "Sessions, packing lists and SKU mapping all belong to one client."
    : "Pick a client in the bar above to see its sessions.";
  show(els.noSession, on(client && state === "none" && packing));
  els.openSession.disabled = !!shell.serverDown;
  show(els.statsEmpty, on(client && state === "none" && stats));
  show(els.head, on(client && work && state !== "none"));
  show(els.opening, on(client && work && state === "opening"));
  show(els.failed, on(client && work && state === "failed"));
  show(els.packing, on(client && state === "open" && packing));
  show(els.statistics, on(client && state === "open" && stats));
  show(els.sessions, on(client && page === "sessions"));
  show(els.details, on(client && page === "details"));
  if (bridge.covered) show(els.toast, false);
  renderConfirm();

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
  row.appendChild(el("span", "app-order-courier", order.courier));
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
    view.toggled = Object.create(null);
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
  // The redraw replaced the row: Enter or Space again must reach the new one.
  const row = Array.from(els.rows.querySelectorAll(".app-order"))
    .find(function (node) { return node.dataset.order === number; });
  if (row) row.focus();
}

// --- Statistics ---------------------------------------------------------------

// Column: its label and the direction a first click sorts it.
const SORT = {
  sku: ["SKU", 1],
  product: ["Product", 1],
  total: ["Total qty", -1],
  packed: ["Packed", -1],
  left: ["Left", -1],
  state: ["Status", 1],
};
const STATE_ORDER = { pending: 0, partial: 1, packed: 2 };
const SKU_BADGE = {
  packed: ["Packed", "badge success"],
  partial: ["Partial", "badge info"],
  pending: ["Pending", "badge neutral"],
};

function sortedSkus(skus) {
  const key = view.sort.key;
  const dir = view.sort.dir;
  const value = function (row) { return key === "state" ? STATE_ORDER[row.state] : row[key]; };
  return skus.slice().sort(function (a, b) {
    const va = value(a);
    const vb = value(b);
    const order = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return order * dir || a.sku.localeCompare(b.sku);
  });
}

function percent(done, total) {
  return (total ? Math.round(done / total * 100) : 0) + "%";
}

function courierBlock(courier) {
  const left = courier.total - courier.done;
  const block = el("div", "app-courier");
  const line = el("div", "app-courier-line");
  line.appendChild(el("span", "app-courier-name", courier.name));
  line.appendChild(el("span", "app-courier-done", courier.done + " done"));
  line.appendChild(el("span", "app-courier-of", "of " + courier.total));
  block.appendChild(line);
  const track = el("div", "track tall");
  const fill = el("div", "track-fill");
  fill.style.width = percent(courier.done, courier.total);
  track.appendChild(fill);
  block.appendChild(track);
  block.appendChild(el("span", "app-courier-left",
    left ? plural(left, "order", "orders") + " left" : "All packed"));
  return block;
}

function skuRow(sku) {
  const row = el("div", "tbl-row app-sku");
  row.appendChild(el("span", "app-sku-code", sku.sku));
  row.appendChild(cut("", sku.product));
  row.appendChild(el("span", "app-num", sku.total));
  row.appendChild(el("span", "app-num", sku.packed));
  row.appendChild(el("span", "app-num app-left" + (sku.left ? "" : " zero"), sku.left));
  const status = el("span");
  status.appendChild(badge(SKU_BADGE[sku.state] || SKU_BADGE.pending));
  row.appendChild(status);
  return row;
}

function renderStatistics() {
  syncSession();
  const stats = view.bridge.statistics || {};
  const couriers = stats.couriers || [];
  const skus = stats.skus || [];
  const pct = stats.pct || 0;

  els.kpiOrders.textContent = stats.orders || 0;
  els.kpiOrdersNote.textContent = plural(couriers.length, "courier", "couriers");
  els.kpiCompleted.textContent = stats.completed || 0;
  els.kpiCompletedNote.textContent = (stats.in_progress || "none") + " in progress";
  els.kpiItems.textContent = stats.items || 0;
  els.kpiItemsNote.textContent = (stats.packed || 0) + " packed";
  els.kpiSkus.textContent = stats.unique_skus || 0;
  els.kpiSkusNote.textContent = (stats.fully_packed || 0) + " fully packed";
  els.kpiPct.textContent = pct + "%";
  els.kpiFill.style.width = pct + "%";
  els.kpiPctNote.textContent = (stats.completed || 0) + " of " + (stats.orders || 0) + " orders complete";

  els.couriers.replaceChildren.apply(els.couriers, couriers.map(courierBlock));

  const key = view.sort.key;
  const dir = view.sort.dir;
  els.skuMeta.textContent = plural(skus.length, "SKU", "SKUs") + " · sorted by " + SORT[key][0]
    + (dir === -1 ? ", most first" : "");
  els.sortHeads.forEach(function (head) {
    const on = head.dataset.col === key;
    if (on) head.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
    else head.removeAttribute("aria-sort");
    const button = head.firstElementChild;
    button.textContent = SORT[head.dataset.col][0] + (on ? (dir === 1 ? " ↑" : " ↓") : "");
  });
  els.skuRows.replaceChildren.apply(els.skuRows, sortedSkus(skus).map(skuRow));
}

function sortBy(key) {
  view.sort = { key: key, dir: view.sort.key === key ? -view.sort.dir : SORT[key][1] };
  renderStatistics();
}

// --- Sessions -----------------------------------------------------------------

// An input shows what Python last said, unless the packer is typing in it.
function setInput(input, value) {
  if (document.activeElement !== input && input.value !== value) input.value = value;
}

// The status chip: the word on its tone, and a dot that is solid when a
// person set the status and hollow when the system inferred it.
function chip(row) {
  const node = el("span", "badge " + (row.tone || "neutral"));
  node.appendChild(el("span", "dot" + (row.manual ? " solid" : "")));
  node.appendChild(document.createTextNode(row.label || ""));
  return node;
}

function fillClass(row) {
  if (row.status === "completed") return "app-bar-fill success";
  if (row.status === "incomplete") return "app-bar-fill danger";
  return "app-bar-fill";
}

function sessionRows() {
  return (view.bridge.sessions || {}).rows || [];
}

function selectedRow() {
  return sessionRows().find(function (row) { return row.key === view.sel; }) || null;
}

function sessionRow(row) {
  const node = el("button", "tbl-row app-srow");
  node.type = "button";
  node.dataset.session = row.key;
  node.title = row.actionLabel ? "Double-click: " + row.actionLabel : "";
  const status = el("span");
  status.appendChild(chip(row));
  node.appendChild(status);
  node.appendChild(el("span", "mono app-s-id", row.id));
  node.appendChild(el("span", "mono app-s-r app-s-age", row.age));
  node.appendChild(cut("", row.list));
  const orders = el("span", "app-s-orders");
  const bar = el("span", "app-bar");
  const fill = el("span", fillClass(row));
  fill.style.width = (row.pct || 0) + "%";
  bar.appendChild(fill);
  orders.appendChild(bar);
  orders.appendChild(el("span", "mono", row.orders));
  node.appendChild(orders);
  node.appendChild(el("span", "mono app-s-r app-s-wide app-s-items" + (row.items === "—" ? " none" : ""), row.items));
  node.appendChild(cut("app-s-wide app-s-touched", row.touched));
  return node;
}

// The pane, the selection mark and the Export menu: the page's own state,
// redrawn without rebuilding the rows (a double-click needs its row to stay).
function renderPane() {
  const row = selectedRow();
  els.sMain.classList.toggle("pane-open", !!row);
  show(els.sPane, !!row);
  show(els.sExportMenu, view.exportOpen);
  els.sExport.setAttribute("aria-expanded", String(view.exportOpen));
  Array.from(els.sRows.children).forEach(function (node) {
    node.setAttribute("aria-pressed", String(node.dataset.session === view.sel));
  });
  if (!row) return;

  els.pChip.replaceChildren(chip(row));
  els.pId.textContent = row.id;
  els.pList.textContent = row.list;
  els.pList.title = row.list;
  els.pWhy.textContent = row.setBy + " · " + row.why;
  els.pOrders.textContent = row.orders;
  els.pFill.className = fillClass(row);
  els.pFill.style.width = (row.pct || 0) + "%";
  els.pOrdersNote.textContent = row.ordersNote;
  els.pFacts.replaceChildren.apply(els.pFacts, (row.facts || []).map(function (fact) {
    const line = el("div", "app-p-fact");
    line.appendChild(el("span", "app-p-label", fact.label));
    const value = el("span", "app-p-value", fact.value);
    value.title = fact.value;
    line.appendChild(value);
    return line;
  }));
  show(els.pNote, !!row.note);
  els.pNote.classList.toggle("warn", !!row.warn);
  els.pNoteText.textContent = row.note || "";
  show(els.pAction, !!row.actionLabel);
  els.pAction.textContent = row.actionLabel || "";
  els.pAction.disabled = !row.enabled;
  show(els.pDetails, !!row.canDetails);
}

function renderSessions() {
  const s = view.bridge.sessions || {};
  const loading = s.mode === "loading";
  const rows = s.rows || [];
  const focused = document.activeElement && document.activeElement.dataset
    ? document.activeElement.dataset : {};
  const focusedTab = focused.tab;
  const focusedSession = focused.session;

  if (s.tab !== view.tab) {
    view.tab = s.tab;
    view.sel = null;
  }
  if (!rows.some(function (row) { return row.key === view.sel; })) view.sel = null;

  els.sTabs.replaceChildren.apply(els.sTabs, (s.tabs || []).map(function (tab) {
    const button = el("button", "segment");
    button.type = "button";
    button.dataset.tab = tab.key;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(tab.key === s.tab));
    button.appendChild(document.createTextNode(tab.label));
    button.appendChild(el("span", "segment-count", loading ? "–" : tab.count));
    return button;
  }));
  setInput(els.sQuery, s.query || "");
  setInput(els.sFrom, s.dateFrom || "");
  setInput(els.sTo, s.dateTo || "");
  show(els.sQueryClear, !!s.query);
  els.sRefresh.disabled = !!s.refreshing;
  els.sStampLabel.textContent = s.refreshing ? "Refreshing…" : s.stamp ? "Last refreshed" : "";
  els.sStamp.textContent = s.refreshing ? "" : s.stamp || "";
  els.sStampLine.classList.toggle("failed", !!s.failed);
  els.sAuto.setAttribute("aria-checked", String(!!s.auto));
  els.sExport.disabled = !(s.shown > 0);
  if (els.sExport.disabled) view.exportOpen = false;
  els.sExportTitle.textContent = s.exportTitle || "";

  const failure = s.failure || {};
  show(els.sFailed, !!s.failed);
  els.sFailedPath.textContent = failure.path || "";
  els.sFailedAt.textContent = failure.at || "";
  els.sFailedCause.textContent = failure.cause || "";
  els.sFailedFrom.textContent = failure.from || "";
  show(els.sFailedFromLine, !!failure.from);

  show(els.sLoading, loading);
  show(els.sSkeleton, loading);
  // With the server away an empty list is not a fact about the client.
  show(els.sEmpty, s.mode === "empty" && !s.failed);
  show(els.sNoMatch, !!s.noMatch);
  els.sNoMatchText.textContent = s.noMatchText || "";
  els.sCount.textContent = s.count || "";

  // ponytail: every row is rebuilt on every push. Fine at a few hundred
  // sessions; patch rows in place if a client ever lists thousands.
  const built = document.createDocumentFragment();
  rows.forEach(function (row) { built.appendChild(sessionRow(row)); });
  els.sRows.replaceChildren(built);
  renderPane();

  // The redraw replaced what had the focus: give it back.
  const again = focusedTab
    ? Array.from(els.sTabs.children).find(function (n) { return n.dataset.tab === focusedTab; })
    : focusedSession
      ? Array.from(els.sRows.children).find(function (n) { return n.dataset.session === focusedSession; })
      : null;
  if (again) again.focus();
}

function sendFilter(change) {
  const s = view.bridge.sessions || {};
  const next = Object.assign({
    tab: s.tab || "all",
    query: els.sQuery.value,
    dateFrom: els.sFrom.value,
    dateTo: els.sTo.value,
  }, change || {});
  view.bridge.setSessionsFilter(next.tab, next.query, next.dateFrom, next.dateTo);
}

// 7c. Drawn over whichever page is showing; never under Packer Mode.
function renderConfirm() {
  const confirm = view.bridge.confirm || {};
  const open = !view.bridge.covered && !!confirm.key;
  const was = !els.confirm.hidden;
  show(els.confirm, open);
  els.confirmId.textContent = confirm.id || "";
  els.confirmBody.textContent = confirm.body || "";
  els.confirmCarry.textContent = confirm.carry || "";
  if (open && !was) els.confirmCancel.focus();
}

function onDoubleClick(event) {
  const node = event.target.closest("[data-session]");
  if (!node) return;
  const row = sessionRows().find(function (r) { return r.key === node.dataset.session; });
  if (row && row.enabled && row.action) view.bridge.sessionAction(row.key);
}

// These reach the page only while it has the focus, which a click gives it.
function onKey(event) {
  const bridge = view.bridge;
  const page = bridge.page;
  if (event.key === "Escape") {
    if ((bridge.confirm || {}).key) bridge.answerTakeOver(false);
    else if (view.exportOpen) { view.exportOpen = false; renderPane(); }
    else if (page === "sessions" && view.sel) { view.sel = null; renderPane(); }
    else return;
    event.preventDefault();
  } else if (event.key === "F5" && page === "sessions") {
    event.preventDefault();
    bridge.refreshSessions();
  } else if (event.key === "ArrowLeft" && event.altKey && page === "details") {
    event.preventDefault();
    bridge.closeDetails();
  }
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
  refreshSessions: function (bridge) { bridge.refreshSessions(); },
  clearSessionsFilter: function (bridge) { bridge.clearSessionsFilter(); },
  clearQuery: function () { els.sQuery.value = ""; sendFilter(); els.sQuery.focus(); },
  toggleAuto: function (bridge) {
    bridge.setAutoRefresh(els.sAuto.getAttribute("aria-checked") !== "true");
  },
  toggleExport: function () { view.exportOpen = !view.exportOpen; renderPane(); },
  exportCsv: function (bridge) { view.exportOpen = false; renderPane(); bridge.exportSessions("csv"); },
  exportXlsx: function (bridge) { view.exportOpen = false; renderPane(); bridge.exportSessions("xlsx"); },
  closePane: function () { view.sel = null; renderPane(); },
  paneAction: function (bridge) { if (view.sel) bridge.sessionAction(view.sel); },
  paneDetails: function (bridge) { if (view.sel) bridge.sessionDetails(view.sel); },
  cancelTakeOver: function (bridge) { bridge.answerTakeOver(false); },
  confirmTakeOver: function (bridge) { bridge.answerTakeOver(true); },
};

function onClick(event) {
  // A click anywhere but the Export button and its menu closes the menu.
  if (view.exportOpen && !event.target.closest(".menu-anchor")) {
    view.exportOpen = false;
    renderPane();
  }
  const action = event.target.closest("[data-action]");
  if (action) {
    if (!action.disabled) ACTIONS[action.dataset.action](view.bridge);
    return;
  }
  const order = event.target.closest("[data-order]");
  if (order) {
    toggleOrder(order.dataset.order);
    return;
  }
  const sort = event.target.closest("[data-sort]");
  if (sort) {
    sortBy(sort.dataset.sort);
    return;
  }
  const tab = event.target.closest("[data-tab]");
  if (tab) {
    sendFilter({ tab: tab.dataset.tab });
    return;
  }
  const session = event.target.closest("[data-session]");
  if (session) {
    view.sel = session.dataset.session;
    renderPane();
  }
}

const IDS = {
  root: "app", themeVars: "theme-vars",
  noClient: "no-client", noClientTitle: "no-client-title", noClientText: "no-client-text",
  chooseClient: "choose-client",
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
  kpiOrders: "kpi-orders", kpiOrdersNote: "kpi-orders-note",
  kpiCompleted: "kpi-completed", kpiCompletedNote: "kpi-completed-note",
  kpiItems: "kpi-items", kpiItemsNote: "kpi-items-note",
  kpiSkus: "kpi-skus", kpiSkusNote: "kpi-skus-note",
  kpiPct: "kpi-pct", kpiFill: "kpi-fill", kpiPctNote: "kpi-pct-note",
  couriers: "couriers", skuMeta: "sku-meta", skuRows: "sku-rows",
  sessions: "sessions", details: "details",
  sFailed: "s-failed", sFailedPath: "s-failed-path", sFailedAt: "s-failed-at",
  sFailedCause: "s-failed-cause", sFailedFromLine: "s-failed-from-line",
  sFailedFrom: "s-failed-from",
  sTabs: "s-tabs", sQuery: "s-query", sQueryClear: "s-query-clear", sFrom: "s-from",
  sTo: "s-to", sRefresh: "s-refresh", sStampLine: "s-stamp-line",
  sStampLabel: "s-stamp-label", sStamp: "s-stamp", sAuto: "s-auto",
  sExport: "s-export", sExportMenu: "s-export-menu", sExportTitle: "s-export-title",
  sMain: "s-main", sLoading: "s-loading", sSkeleton: "s-skeleton", sRows: "s-rows",
  sNoMatch: "s-no-match", sNoMatchText: "s-no-match-text", sEmpty: "s-empty",
  sCount: "s-count", sPane: "s-pane",
  pChip: "p-chip", pId: "p-id", pList: "p-list", pWhy: "p-why", pOrders: "p-orders",
  pFill: "p-fill", pOrdersNote: "p-orders-note", pFacts: "p-facts", pNote: "p-note",
  pNoteText: "p-note-text", pAction: "p-action", pDetails: "p-details",
  confirm: "confirm", confirmId: "confirm-id", confirmBody: "confirm-body",
  confirmCarry: "confirm-carry", confirmCancel: "confirm-cancel",
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
  els.sortHeads = Array.from(document.querySelectorAll("[role=columnheader]"));
  // 7e's skeleton: twelve still rows, built once.
  for (let index = 0; index < 12; index += 1) {
    const row = el("div", "tbl-row app-skel");
    for (let cell = 0; cell < 5; cell += 1) {
      const holder = el("span");
      holder.appendChild(el("span", "app-skel-bar"));
      row.appendChild(holder);
    }
    els.sSkeleton.appendChild(row);
  }

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
  bridge.statisticsChanged.connect(renderStatistics);
  renderStatistics();
  bridge.sessionsChanged.connect(renderSessions);
  renderSessions();
  bridge.confirmChanged.connect(renderConfirm);
  els.sQuery.addEventListener("input", function () { sendFilter(); });
  els.sFrom.addEventListener("change", function () { sendFilter(); });
  els.sTo.addEventListener("change", function () { sendFilter(); });
  els.root.addEventListener("dblclick", onDoubleClick);
  document.addEventListener("keydown", onKey);
  els.root.addEventListener("click", onClick);

  // After the first render, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
