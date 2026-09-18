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

function renderItems() {
  const rows = state.bridge.items || [];
  els.skuList.textContent = "";
  els.skuList.hidden = rows.length === 0;
  rows.forEach(function (r) {
    const row = document.createElement("div");
    row.className =
      "sku-row sku-row--" + r.state + (r.just_changed ? " sku-row--just-changed" : "");
    row.appendChild(span("sku-row__product", r.product));
    row.appendChild(span("sku-row__sku", r.sku));
    row.appendChild(span("sku-row__qty", r.packed + " / " + r.required));
    const chip = CHIP[r.state];
    row.appendChild(span(chip.cls, chip.text));
    const actions = document.createElement("span");
    actions.className = "row-actions";
    // Label "Force", not "Force confirm": three buttons have to share the
    // row's 190px actions slot (spec S2).
    if (r.confirm) actions.appendChild(actionButton("Confirm", "confirm", r.row, r.sku));
    if (r.undo) actions.appendChild(actionButton("Undo", "undo", r.row, r.sku));
    if (r.force) actions.appendChild(actionButton("Force", "force", r.row, r.sku));
    if (r.map) actions.appendChild(actionButton("Map SKU", "map", r.row, r.sku));
    row.appendChild(actions);
    els.skuList.appendChild(row);
  });
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

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.packer;
  state.bridge = bridge;
  els.themeVars = document.getElementById("theme-vars");
  els.docMain = document.getElementById("doc-main");
  els.feedback = document.getElementById("feedback");
  els.feedbackText = document.getElementById("feedback-text");
  els.feedbackRaw = document.getElementById("feedback-raw");
  els.skuList = document.getElementById("sku-list");
  els.banner = document.getElementById("banner");

  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.feedbackChanged.connect(renderFeedback);
  bridge.scanFlashed.connect(flash);
  bridge.itemsChanged.connect(renderItems);
  bridge.bannerChanged.connect(renderBanner);
  els.docMain.addEventListener("animationend", function () {
    delete els.docMain.dataset.flash;
  });
  els.skuList.addEventListener("click", function (event) {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;
    const row = Number(btn.dataset.row);
    if (btn.dataset.action === "confirm") bridge.confirmItem(row);
    else if (btn.dataset.action === "undo") bridge.undoItem(row);
    else if (btn.dataset.action === "force") bridge.forceItem(row);
    else if (btn.dataset.action === "map") bridge.mapSku(btn.dataset.sku);
  });

  renderFeedback();
  renderItems();
  renderBanner();
  window.packerBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
