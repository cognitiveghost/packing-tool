// Packer Mode's order document. The page renders what the bridge sends and
// decides nothing: item state and row actions are decided in
// gui/packer_bridge.py. Every string from the bridge goes in through
// textContent. Spec:
// docs/superpowers/specs/2026-10-08-ui-refresh-phase2-packer-mode-design.md
"use strict";

const els = {};
const state = { bridge: null };

function onTheme() {
  els.themeVars.textContent = state.bridge.themeCss;
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, action, kind) {
  const btn = el("button", "btn compact " + kind, label);
  btn.type = "button";
  btn.dataset.action = action;
  return btn;
}

function renderFeedback() {
  const fb = state.bridge.feedback || {};
  els.feedbackText.textContent = fb.text || "";
  els.feedbackRaw.textContent = fb.raw || "";
  els.feedbackRawBox.hidden = !fb.raw;
  els.feedback.className = "feedback" + (fb.role ? " feedback--" + fb.role : "");
}

function flash(role) {
  // Remove, force a reflow, re-add: an animation already running would
  // otherwise ignore the new scan.
  delete els.docMain.dataset.flash;
  void els.docMain.offsetWidth;
  els.docMain.dataset.flash = role;
}

const BADGE = {
  complete: { text: "Complete", cls: "badge success" },
  partial: { text: "Partial", cls: "badge info" },
  pending: { text: "Pending", cls: "badge neutral" },
};

function orderLabel(order) {
  // Same rule as packer_bridge.order_label, including the empty case.
  const text = String(order == null ? "" : order);
  if (!text) return "No order";
  return text.startsWith("#") ? text : "#" + text;
}

// One of a row's four fixed slots. `present` false: the act never applies to
// this row, and the slot is kept empty so the columns line up. `enabled`
// false: it does not apply right now.
function slot(label, action, r, kind, present, enabled, title) {
  const btn = button(label, action, kind);
  btn.dataset.row = r.row;
  btn.dataset.sku = r.sku;
  btn.disabled = !present || !enabled;
  if (!present) btn.dataset.absent = "";
  else if (title) btn.title = title;
  return btn;
}

function itemRow(r) {
  const row = el(
    "div",
    "sku-row sku-row--" + r.state + (r.just_changed ? " sku-row--just-changed" : "")
  );
  row.appendChild(el("span", "sku-row__sku", r.sku));
  row.appendChild(el("span", "sku-row__product", r.product));
  const qty = el("span", "sku-row__qty");
  qty.appendChild(el("span", "sku-row__num", String(r.packed)));
  qty.appendChild(el("span", "sku-row__of", "of " + r.required));
  row.appendChild(qty);
  const badge = BADGE[r.state] || BADGE.pending;
  const status = el("span", "sku-row__status");
  status.appendChild(el("span", badge.cls, badge.text));
  row.appendChild(status);
  const actions = el("span", "row-actions");
  actions.appendChild(slot("Confirm", "confirm", r, "secondary", true, r.confirm, "Confirm one unit"));
  actions.appendChild(
    slot("Force confirm", "force", r, "secondary", r.force_slot, r.force, "Confirm all remaining units")
  );
  actions.appendChild(slot("Undo", "undo", r, "ghost", true, r.undo, "Take one back"));
  actions.appendChild(slot("Map SKU", "map", r, "ghost", r.map, true, ""));
  row.appendChild(actions);
  return row;
}

function unknownRow(r) {
  const row = el("div", "sku-row sku-row--unknown");
  row.appendChild(el("span", "badge danger", "No match"));
  row.appendChild(el("span", "sku-row__code", r.sku));
  row.appendChild(el("span", "sku-row__why", "Not a SKU or barcode this client knows"));
  const btn = button("Map barcode…", "mapBarcode", "secondary");
  btn.dataset.sku = r.sku;
  row.appendChild(btn);
  return row;
}

// The card says "No order open" until it has a row of any kind.
function syncList() {
  const empty =
    els.skuList.children.length === 0 &&
    els.unmatched.children.length === 0 &&
    els.extras.hidden;
  els.listEmpty.hidden = !empty;
  els.listHead.hidden = empty;
  els.listScroll.hidden = empty;
}

function renderItems() {
  // Unmatched scans ride in the same property with state "unknown"; they are
  // drawn under the extras, not among the items.
  const rows = state.bridge.items || [];
  els.skuList.textContent = "";
  els.unmatched.textContent = "";
  let changed = null;
  rows.forEach(function (r) {
    if (r.state === "unknown") {
      els.unmatched.appendChild(unknownRow(r));
      return;
    }
    const row = itemRow(r);
    if (r.just_changed) changed = row;
    els.skuList.appendChild(row);
  });
  els.skuList.hidden = els.skuList.children.length === 0;
  syncList();
  if (changed) changed.scrollIntoView({ block: "nearest" });
}

function renderExtras() {
  const rows = state.bridge.extras || [];
  els.extrasRows.textContent = "";
  els.extras.hidden = rows.length === 0;
  rows.forEach(function (r) {
    // An extra is a normalised SKU and a count: there is no product name.
    const row = el("div", "extras-row");
    row.appendChild(el("span", "sku-row__sku", r.sku));
    row.appendChild(el("span", "sku-row__product", ""));
    const qty = el("span", "sku-row__qty");
    qty.appendChild(el("span", "sku-row__num", "× " + r.count));
    row.appendChild(qty);
    const status = el("span", "sku-row__status");
    status.appendChild(el("span", "badge warning", "Extra"));
    row.appendChild(status);
    const actions = el("span", "row-actions");
    ["keep", "remove"].forEach(function (action) {
      const btn = button(action === "keep" ? "Keep" : "Remove", action, "secondary");
      btn.dataset.sku = r.sku;
      actions.appendChild(btn);
    });
    row.appendChild(actions);
    els.extrasRows.appendChild(row);
  });
  syncList();
}

function renderBanner() {
  // The order number itself is in the Qt bar above the page.
  const b = state.bridge.banner || {};
  const chips = b.chips || [];
  els.bannerChips.textContent = "";
  chips.forEach(function (c) {
    els.bannerChips.appendChild(el("span", "badge neutral", c));
  });
  els.bannerNotesText.textContent = b.notes || "";
  els.bannerNotes.hidden = !b.notes;
  els.bannerRepeat.hidden = !b.repeat;
  els.banner.hidden = chips.length === 0 && !b.notes && !b.repeat;
}

function renderProgress() {
  const p = state.bridge.progress || {};
  const done = p.orders_done || 0;
  const total = p.orders_total || 0;
  const pct = total > 0 ? (done / total) * 100 : 0;
  // Trailing zeroes trimmed so a whole percentage reads as "50%".
  els.progressFill.style.width = String(Number(pct.toFixed(4))) + "%";
  els.progressNumbers.textContent =
    done + " / " + total + " orders · " +
    (p.items_packed || 0) + " / " + (p.items_total || 0) + " items";
  els.summarySkus.textContent = (p.skus_packed || 0) + " / " + (p.skus_total || 0);
}

function renderHistory() {
  const rows = state.bridge.history || [];
  els.historyRows.textContent = "";
  if (rows.length === 0) {
    const empty = el("div", "history-row");
    empty.appendChild(el("span", "history-row__order side-empty", "No orders yet"));
    els.historyRows.appendChild(empty);
    return;
  }
  rows.forEach(function (r) {
    const skipped = r.status === "skipped";
    const row = el("div", "history-row");
    row.appendChild(el("span", "history-row__order", orderLabel(r.order)));
    row.appendChild(
      el(
        "span",
        "history-row__status" + (skipped ? " history-row__status--skipped" : ""),
        skipped ? "Skipped" : "Packed"
      )
    );
    els.historyRows.appendChild(row);
  });
}

function renderRollup() {
  const rows = state.bridge.skuRollup || [];
  els.rollupRows.textContent = "";
  if (rows.length === 0) {
    els.rollupRows.appendChild(el("span", "side-empty", "No order open"));
    return;
  }
  rows.forEach(function (r) {
    const row = el("div", "rollup-row");
    row.appendChild(el("span", "dot dot--" + r.state));
    row.appendChild(el("span", "rollup-row__sku", r.sku));
    row.appendChild(el("span", "rollup-row__qty", r.packed + " / " + r.required));
    els.rollupRows.appendChild(row);
  });
}

function renderSessionEnd() {
  const s = state.bridge.sessionEnd || {};
  // One class decides the whole swap; CSS hides the regions the panel
  // replaces, so there is no per-region bookkeeping to get out of step.
  els.docMain.classList.toggle("doc-state", Boolean(s.title));
  els.stateTitle.textContent = s.title || "";
  els.stateBody.textContent = s.body || "";
}

function renderUnsaved() {
  els.unsaved.hidden = !state.bridge.unsaved;
}

function renderQuestion() {
  const q = state.bridge.question || {};
  const open = q.sku !== undefined;
  els.question.hidden = !open;
  els.questionSku.textContent = open ? q.sku : "";
  els.questionRemaining.textContent = open ? String(q.remaining) : "";
  els.questionRest.textContent = open
    ? " of " + q.required + " × " + q.product +
      " as packed without scanning. This cannot be undone."
    : "";
}

function renderTakeover() {
  const t = state.bridge.takeover || {};
  els.takeover.hidden = !t.holder;
  els.takeoverHolder.textContent = t.holder || "";
  els.takeoverList.textContent = t.list || "";
}

// One entry per action a button can ask for.
const ACTIONS = {
  confirm: function (btn, bridge) { bridge.confirmItem(Number(btn.dataset.row)); },
  undo: function (btn, bridge) { bridge.undoItem(Number(btn.dataset.row)); },
  force: function (btn, bridge) { bridge.forceItem(Number(btn.dataset.row)); },
  map: function (btn, bridge) { bridge.mapSku(btn.dataset.sku); },
  mapBarcode: function (btn, bridge) { bridge.mapBarcode(btn.dataset.sku); },
  keep: function (btn, bridge) { bridge.keepExtra(btn.dataset.sku); },
  remove: function (btn, bridge) { bridge.removeExtra(btn.dataset.sku); },
  endSession: function (btn, bridge) { bridge.endSession(); },
  exitPacking: function (btn, bridge) { bridge.exitPacking(); },
  answerYes: function (btn, bridge) { bridge.answerQuestion(true); },
  answerNo: function (btn, bridge) { bridge.answerQuestion(false); },
};

function onActionClick(event) {
  const btn = event.target.closest("[data-action]");
  if (!btn || btn.disabled) return;
  const run = ACTIONS[btn.dataset.action];
  if (run) run(btn, state.bridge);
}

const IDS = {
  themeVars: "theme-vars", root: "pm", docMain: "doc-main",
  feedback: "feedback", feedbackText: "feedback-text",
  feedbackRaw: "feedback-raw", feedbackRawBox: "feedback-raw-box",
  banner: "banner", bannerChips: "banner-chips", bannerNotes: "banner-notes",
  bannerNotesText: "banner-notes-text", bannerRepeat: "banner-repeat",
  listEmpty: "list-empty", listHead: "list-head", listScroll: "list-scroll",
  skuList: "sku-list", extras: "extras", extrasRows: "extras-rows",
  unmatched: "unmatched-rows",
  progressFill: "progress-fill", progressNumbers: "progress-numbers",
  summarySkus: "summary-skus", historyRows: "history-rows", rollupRows: "rollup-rows",
  stateTitle: "state-title", stateBody: "state-body", unsaved: "unsaved",
  question: "question", questionSku: "question-sku",
  questionRemaining: "question-remaining", questionRest: "question-rest",
  takeover: "takeover", takeoverHolder: "takeover-holder", takeoverList: "takeover-list",
};

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.packer;
  state.bridge = bridge;
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.packerBridge = bridge;
  Object.keys(IDS).forEach(function (key) {
    els[key] = document.getElementById(IDS[key]);
  });

  const renders = [
    [bridge.feedbackChanged, renderFeedback],
    [bridge.itemsChanged, renderItems],
    [bridge.extrasChanged, renderExtras],
    [bridge.bannerChanged, renderBanner],
    [bridge.progressChanged, renderProgress],
    [bridge.historyChanged, renderHistory],
    [bridge.skuRollupChanged, renderRollup],
    [bridge.sessionEndChanged, renderSessionEnd],
    [bridge.unsavedChanged, renderUnsaved],
    [bridge.questionChanged, renderQuestion],
    [bridge.takeoverChanged, renderTakeover],
  ];

  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.scanFlashed.connect(flash);
  renders.forEach(function (pair) {
    pair[0].connect(pair[1]);
    pair[1]();
  });
  // The flash frame's animation ends on a child; the event bubbles here.
  els.docMain.addEventListener("animationend", function () {
    delete els.docMain.dataset.flash;
  });
  // One listener at the root: the row buttons, the panel's buttons and the
  // two taking-over panels are all under it.
  els.root.addEventListener("click", onActionClick);

  // After the first renders, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
