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

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.packer;
  state.bridge = bridge;
  els.themeVars = document.getElementById("theme-vars");
  els.docMain = document.getElementById("doc-main");
  els.feedback = document.getElementById("feedback");
  els.feedbackText = document.getElementById("feedback-text");
  els.feedbackRaw = document.getElementById("feedback-raw");

  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.feedbackChanged.connect(renderFeedback);
  bridge.scanFlashed.connect(flash);
  els.docMain.addEventListener("animationend", function () {
    delete els.docMain.dataset.flash;
  });

  renderFeedback();
  window.packerBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
