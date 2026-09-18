// Packer Mode's order document (Bundle 4). The page renders what the bridge
// sends and decides nothing: item state and row actions are decided in
// gui/packer_bridge.py. Spec:
// docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md
"use strict";

const els = {};
const state = { bridge: null };

function onTheme() {
  els.themeVars.textContent = state.bridge.themeCss;
}

function renderFeedback() {
  const fb = state.bridge.feedback || {};
  els.feedbackText.textContent = fb.text || "";
  els.feedbackRaw.textContent = fb.raw || "";
  els.feedback.className = "feedback" + (fb.role ? " feedback--" + fb.role : "");
}

function flash(role) {
  // Remove, force a reflow, re-add: an animation already running would
  // otherwise ignore the new scan.
  delete els.docMain.dataset.flash;
  void els.docMain.offsetWidth;
  els.docMain.dataset.flash = role;
}

const CHIP = {
  complete: { text: "Complete", cls: "chip chip--success chip--hollow" },
  partial: { text: "Partial", cls: "chip chip--warning chip--tint chip--hollow" },
  pending: { text: "Pending", cls: "chip chip--neutral chip--hollow" },
};

function span(cls, text) {
  const el = document.createElement("span");
  el.className = cls;
  el.textContent = text;
  return el;
}

function actionButton(label, action, row, sku) {
  const btn = document.createElement("button");
  btn.className = "btn btn--ghost";
  btn.type = "button";
  btn.textContent = label;
  btn.dataset.action = action;
  btn.dataset.row = row;
  btn.dataset.sku = sku;
  return btn;
}

function rowEl(cls, cells, buttons) {
  const row = document.createElement("div");
  row.className = cls;
  cells.forEach(function (cell) {
    row.appendChild(span(cell[0], cell[1]));
  });
  const actions = document.createElement("span");
  actions.className = "row-actions";
  buttons.forEach(function (btn) {
    actions.appendChild(btn);
  });
  row.appendChild(actions);
  return row;
}

function renderItems() {
  const rows = state.bridge.items || [];
  els.skuList.textContent = "";
  els.skuList.hidden = rows.length === 0;
  let changed = null;
  rows.forEach(function (r) {
    const chip = CHIP[r.state] || CHIP.pending;
    const buttons = [];
    // Label "Force", not "Force confirm": three buttons have to share the
    // row's 190px actions slot (spec S2).
    if (r.confirm) buttons.push(actionButton("Confirm", "confirm", r.row, r.sku));
    if (r.undo) buttons.push(actionButton("Undo", "undo", r.row, r.sku));
    if (r.force) buttons.push(actionButton("Force", "force", r.row, r.sku));
    if (r.map) buttons.push(actionButton("Map SKU", "map", r.row, r.sku));
    const row = rowEl(
      "sku-row sku-row--" + r.state + (r.just_changed ? " sku-row--just-changed" : ""),
      [
        ["sku-row__product", r.product],
        ["sku-row__sku", r.sku],
        ["sku-row__qty", r.packed + " / " + r.required],
        [chip.cls, chip.text],
      ],
      buttons
    );
    if (r.just_changed) changed = row;
    els.skuList.appendChild(row);
  });
  if (changed) changed.scrollIntoView({ block: "nearest" });
}

function renderBanner() {
  const b = state.bridge.banner || {};
  const chips = b.chips || [];
  els.banner.textContent = "";
  els.banner.hidden = !b.order && chips.length === 0 && !b.notes;
  if (b.order) els.banner.appendChild(span("doc-banner-order", "#" + b.order));
  chips.forEach(function (c) {
    els.banner.appendChild(span("doc-banner-tag", c));
  });
  if (b.notes) els.banner.appendChild(span("doc-banner-notes", b.notes));
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

function renderExtras() {
  const rows = state.bridge.extras || [];
  els.extrasRows.textContent = "";
  els.extras.hidden = rows.length === 0;
  rows.forEach(function (r) {
    // The extras row reuses the SKU row's grid, but there is no product name
    // for a scan the order does not contain -- current_extra_items is
    // normalised-SKU-to-count. So the SKU spans the product and SKU tracks
    // (see .extras-row .sku-row__sku) and the status cell stays empty (P6).
    els.extrasRows.appendChild(
      rowEl(
        "extras-row",
        [["sku-row__sku", r.sku], ["sku-row__qty", "× " + r.count], ["", ""]],
        [
          actionButton("Keep", "keep", -1, r.sku),
          actionButton("Remove", "remove", -1, r.sku),
        ]
      )
    );
  });
}

const HISTORY_CHIP = {
  complete: { text: "Complete", cls: "chip chip--success chip--hollow" },
  skipped: { text: "Skipped", cls: "chip chip--danger" },
};

function renderHistory() {
  const rows = state.bridge.history || [];
  els.historyRows.textContent = "";
  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-row";
    empty.appendChild(span("history-row__order", "No orders yet"));
    els.historyRows.appendChild(empty);
    return;
  }
  rows.forEach(function (r) {
    const row = document.createElement("div");
    row.className = "history-row";
    row.appendChild(span("history-row__order", "#" + r.order));
    const chip = HISTORY_CHIP[r.status] || HISTORY_CHIP.complete;
    row.appendChild(span(chip.cls, chip.text));
    els.historyRows.appendChild(row);
  });
}

// One entry per action a row can offer. Both listeners share it, so a new
// action is one line here rather than a branch in each cascade.
const ACTIONS = {
  confirm: function (btn, bridge) { bridge.confirmItem(Number(btn.dataset.row)); },
  undo: function (btn, bridge) { bridge.undoItem(Number(btn.dataset.row)); },
  force: function (btn, bridge) { bridge.forceItem(Number(btn.dataset.row)); },
  map: function (btn, bridge) { bridge.mapSku(btn.dataset.sku); },
  keep: function (btn, bridge) { bridge.keepExtra(btn.dataset.sku); },
  remove: function (btn, bridge) { bridge.removeExtra(btn.dataset.sku); },
};

function onActionClick(event) {
  const btn = event.target.closest("[data-action]");
  const run = btn && ACTIONS[btn.dataset.action];
  if (run) run(btn, state.bridge);
}

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.packer;
  state.bridge = bridge;
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.packerBridge = bridge;
  els.themeVars = document.getElementById("theme-vars");
  els.docMain = document.getElementById("doc-main");
  els.feedback = document.getElementById("feedback");
  els.feedbackText = document.getElementById("feedback-text");
  els.feedbackRaw = document.getElementById("feedback-raw");
  els.skuList = document.getElementById("sku-list");
  els.banner = document.getElementById("banner");
  els.progressFill = document.getElementById("progress-fill");
  els.progressNumbers = document.getElementById("progress-numbers");
  els.summarySkus = document.getElementById("summary-skus");
  els.historyRows = document.getElementById("history-rows");
  els.extras = document.getElementById("extras");
  els.extrasRows = document.getElementById("extras-rows");

  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.feedbackChanged.connect(renderFeedback);
  bridge.scanFlashed.connect(flash);
  bridge.itemsChanged.connect(renderItems);
  bridge.bannerChanged.connect(renderBanner);
  bridge.progressChanged.connect(renderProgress);
  bridge.historyChanged.connect(renderHistory);
  bridge.extrasChanged.connect(renderExtras);
  els.docMain.addEventListener("animationend", function () {
    delete els.docMain.dataset.flash;
  });
  els.skuList.addEventListener("click", onActionClick);
  els.extrasRows.addEventListener("click", onActionClick);

  renderFeedback();
  renderItems();
  renderBanner();
  renderProgress();
  renderHistory();
  renderExtras();
  document.documentElement.dataset.bridge = "ready";
});
