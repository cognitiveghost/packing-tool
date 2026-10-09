// The setup document: Worker selection and SKU mapping, the two full-window
// pages (ADR 0002). The page renders what the bridge sends; what the cards,
// rows and sentences say is decided in gui/setup_payload.py. The page keeps
// only what is being typed, the search text, which row is being edited and
// which question is open. Every string from the bridge goes in through
// textContent.
// Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
"use strict";

const els = {};
const view = {
  bridge: null,
  creating: false,  // the New worker form is open
  search: "",
  draft: null,      // {id}: 0 for the add draft, else the row being edited
  ask: null,        // {kind: "delete" | "reload" | "leave", id}
  stray: "",        // keys that reached no field (ADR 0004)
};

const SVG_NS = "http://www.w3.org/2000/svg";
const ARROW = "M5 12h14M12 5l7 7-7 7";
const PENCIL = "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352"
  + "a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z";
const TRASH = "M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2";

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

function glyph(d) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "glyph");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", d);
  svg.appendChild(path);
  return svg;
}

// Text that an ellipsis may cut keeps its whole self in the tooltip.
function cut(cls, text) {
  const node = el("span", cls, text);
  node.title = text;
  return node;
}

// packer_logic.normalize_sku: letters and digits only, lower case.
function key(text) {
  return String(text).toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
}

// --- which page -----------------------------------------------------------------

function renderPage() {
  const page = view.bridge.page;
  view.stray = "";
  if (page !== "workers") closeForm();
  if (page !== "mapping") {
    view.search = "";
    els.mSearch.value = "";
    view.draft = null;
    view.ask = null;
  }
  show(els.workers, page === "workers");
  show(els.mapping, page === "mapping");
  renderWorkers();
  renderMapping();
}

// --- Worker selection -------------------------------------------------------------

function workerCard(card) {
  const node = el("button", "card su-card" + (card.picked ? " picked" : ""));
  node.type = "button";
  node.dataset.worker = card.id;
  const top = el("div", "su-card-top");
  top.appendChild(el("span", "su-avatar", card.initials));
  if (card.badge) top.appendChild(el("span", "badge neutral", card.badge));
  const text = el("div", "su-card-text");
  text.appendChild(cut("su-card-name", card.name));
  text.appendChild(el("span", "su-card-line", card.stats));
  text.appendChild(el("span", "su-card-line", card.last));
  node.appendChild(top);
  node.appendChild(text);
  return node;
}

function renderWorkers() {
  const data = view.bridge.workers || {};
  const cards = data.cards || [];
  const failed = data.mode === "failed";
  const error = data.error || {};
  els.wLeave.textContent = data.leave || "";
  show(els.wFailed, failed);
  els.wFailedTitle.textContent = error.title || "";
  els.wFailedText.textContent = error.text || "";
  els.wFailedPath.textContent = error.path || "";
  show(els.wEmpty, !failed && !cards.length);
  show(els.wGrid, !failed);
  els.wGrid.querySelectorAll("[data-worker]").forEach(function (node) { node.remove(); });
  cards.forEach(function (card) { els.wGrid.insertBefore(workerCard(card), els.wNew); });
  els.wGrid.style.setProperty("--su-cols", String(Math.min(4, cards.length + 1)));
  els.wGrid.classList.toggle("lone", !cards.length);
  show(els.wNew, !view.creating);
  show(els.wForm, view.creating);
}

function nameProblem(text) {
  els.wNameError.textContent = text;
  show(els.wNameError, !!text);
  els.wName.classList.toggle("invalid", !!text);
}

function openForm() {
  view.creating = true;
  els.wName.value = "";
  nameProblem("");
  renderWorkers();
  els.wName.focus();
}

function closeForm() {
  view.creating = false;
  els.wName.value = "";
  nameProblem("");
}

function createWorker() {
  view.bridge.createWorker(els.wName.value, function (problem) {
    if (problem) {
      nameProblem(problem);
      els.wName.focus();
    } else {
      closeForm();
      renderWorkers();
    }
  });
}

// --- SKU mapping ------------------------------------------------------------------

function mapping() {
  return view.bridge.mapping || {};
}

// The quick map: the page was opened from Packer Mode for one add (ADR 0004).
function quick() {
  const q = mapping().quick || {};
  return q.kind ? q : null;
}

function rowById(id) {
  return (mapping().rows || []).find(function (row) { return row.id === id; }) || null;
}

// The row the draft's barcode collides with: the same key to the scan matcher.
function clashRow() {
  if (!view.draft) return null;
  const typed = key(els.dBarcode.value);
  if (!typed) return null;
  return (mapping().rows || []).find(function (row) {
    return row.key === typed && row.id !== view.draft.id;
  }) || null;
}

function draftProblem(text) {
  els.dProblem.textContent = text;
  show(els.dProblem, !!text);
}

function iconButton(action, id, label, d) {
  const button = el("button", "btn ghost compact icon su-plain");
  button.type = "button";
  button.dataset.rowAction = action;
  button.dataset.id = id;
  button.title = label;
  button.setAttribute("aria-label", label);
  button.appendChild(glyph(d));
  return button;
}

function mappingRow(row, actions) {
  const node = el("div", "tbl-row su-row");
  node.dataset.row = row.id;
  const dot = el("span", row.status ? "su-undot" : "");
  if (row.status === "new") dot.title = "Added, not saved";
  if (row.status === "edited") dot.title = "Edited, not saved";
  node.appendChild(dot);
  node.appendChild(cut("mono su-cut", row.barcode));
  node.appendChild(glyph(ARROW));
  node.appendChild(cut("mono su-sku su-cut", row.sku));
  const acts = el("span", "su-row-actions");
  if (actions) {
    acts.appendChild(iconButton("edit", row.id, "Edit", PENCIL));
    acts.appendChild(iconButton("delete", row.id, "Delete", TRASH));
  }
  node.appendChild(acts);
  return node;
}

// The draft sits above the rows for an add, and where the row was for an edit.
function placeDraft() {
  const id = view.draft ? view.draft.id : 0;
  const row = id ? els.mRows.querySelector('[data-row="' + id + '"]') : null;
  if (row) {
    row.hidden = true;
    els.mRows.insertBefore(els.mDraft, row);
  } else {
    els.mScroll.insertBefore(els.mDraft, els.mRows);
  }
}

function renderDraft() {
  const open = !!view.draft;
  const q = quick();
  show(els.mDraft, open);
  if (!open) return;
  const hit = clashRow();
  const barcode = els.dBarcode.value.trim();
  const sku = els.dSku.value.trim();
  els.dBarcode.classList.toggle("invalid", !!hit);
  show(els.dClash, !!hit);
  if (hit) {
    els.dClashSku.textContent = hit.sku;
    els.dClashAsk.textContent = sku ? " Replace it with " + sku + "?" : " Enter a SKU to replace it.";
    els.dReplace.disabled = !sku;
  }
  els.mRows.querySelectorAll("[data-row]").forEach(function (node) {
    node.classList.toggle("clash", !!hit && Number(node.dataset.row) === hit.id);
  });
  els.dCommit.textContent = view.draft.id ? "Update" : "Add";
  els.dCommit.disabled = !barcode || !sku || !!hit;
  show(els.dCancel, !q);
  els.dBarcode.disabled = !!q && q.kind === "barcode";
  els.dSku.disabled = !!q && q.kind === "sku";
  els.dHint.textContent = q ? q.hint : "";
  show(els.dHint, !!q && !hit);
  show(els.dChoices, !!q && q.kind === "barcode");
}

function renderRows() {
  const rows = mapping().rows || [];
  const needle = view.search.trim().toLowerCase();
  const focused = document.activeElement;
  // Out of the row list before it is rebuilt, or the draft goes with it.
  els.mScroll.insertBefore(els.mDraft, els.mRows);
  els.mRows.replaceChildren();
  let shownRows = 0;
  // ponytail: every row is drawn; the largest client has under 200 mappings.
  // Window the list if one ever passes a few thousand.
  rows.forEach(function (row) {
    const editing = !!view.draft && view.draft.id === row.id;
    const matches = !needle || row.barcode.toLowerCase().includes(needle)
      || row.sku.toLowerCase().includes(needle);
    if (!matches && !editing) return;
    shownRows += 1;
    els.mRows.appendChild(mappingRow(row, !quick()));
  });
  placeDraft();
  // Moving the draft took the focus off its field.
  if (focused && els.mDraft.contains(focused)) focused.focus();
  const total = plural(rows.length, "mapping", "mappings");
  els.mCount.textContent = needle ? shownRows + " of " + total : total;
  els.mNohitsQ.textContent = view.search.trim();
  show(els.mNohits, !!needle && !shownRows);
  renderDraft();
}

function renderChoices(q) {
  els.dChoices.replaceChildren();
  ((q && q.choices) || []).forEach(function (choice) {
    const button = el("button", "btn secondary compact", choice.label);
    button.type = "button";
    button.dataset.choice = choice.sku;
    els.dChoices.appendChild(button);
  });
}

const ASK = {
  delete: { title: "Delete this mapping?", yes: "Delete", no: "Cancel" },
  reload: { title: "Reload from server?", yes: "Discard and reload", no: "Cancel" },
  leave: { title: "Discard unsaved changes?", yes: "Discard", no: "Keep editing" },
};

function renderAsk() {
  let ask = view.ask;
  const row = ask && ask.kind === "delete" ? rowById(ask.id) : null;
  if (ask && ask.kind === "delete" && !row) ask = view.ask = null;
  show(els.mAsk, !!ask);
  if (!ask) return;
  const copy = ASK[ask.kind];
  els.mAskTitle.textContent = copy.title;
  els.mAskYes.textContent = copy.yes;
  els.mAskNo.textContent = copy.no;
  show(els.mAskPair, !!row);
  if (row) {
    els.mAskBarcode.textContent = row.barcode;
    els.mAskSku.textContent = row.sku;
    els.mAskText.textContent = "Once you save, scanning this barcode on any PC will no longer"
      + " count as " + row.sku + ".";
  } else {
    els.mAskText.textContent = (mapping().lost || "") + (ask.kind === "reload"
      ? " The list is replaced with the copy on the file server." : "");
  }
}

function focusQuick() {
  const q = quick();
  if (!q || view.bridge.page !== "mapping") return;
  (q.kind === "sku" ? els.dBarcode : els.dSku).focus();
}

function renderMapping() {
  const data = mapping();
  const q = quick();
  const rows = data.rows || [];
  const failed = data.mode === "failed";
  const error = data.error || {};

  if (view.draft && view.draft.id && !rowById(view.draft.id)) view.draft = null;
  if (q && !view.draft && view.bridge.page === "mapping") {
    // A quick map is its draft: open, the known side filled. Only while the
    // page shows: Python blanks `page` before it empties this payload, and a
    // draft opened then would outlive the quick map.
    view.draft = { id: 0 };
    els.dBarcode.value = q.barcode || "";
    els.dSku.value = q.sku || "";
    draftProblem("");
  }

  els.mClient.textContent = data.client || "";
  show(els.mError, !!error.title);
  els.mErrorTitle.textContent = error.title || "";
  els.mErrorText.textContent = error.text || "";
  els.mErrorCause.textContent = error.cause || "";
  els.mErrorPath.textContent = error.path || "";
  els.mErrorAction.textContent = error.action === "load" ? "Retry" : "Try again";
  show(els.mErrorAction, !!error.action);

  const empty = !failed && !rows.length && !view.draft;
  show(els.mEmpty, empty);
  show(els.mTable, !failed && !empty);
  show(els.mAdd, !failed && !empty && !q);
  show(els.mReload, !q);
  show(els.mUnsaved, !!data.dirty && !error.title);
  els.mSummary.textContent = data.summary || "";
  show(els.mSaved, !!data.saved);
  show(els.mSave, !q);
  els.mSave.disabled = !data.dirty;
  els.mCancel.textContent = q ? "Back to packing" : "Cancel";

  renderChoices(q);
  renderRows();
  renderAsk();
  if (q && document.activeElement === document.body) focusQuick();
}

function startAdd() {
  view.search = "";
  els.mSearch.value = "";
  view.draft = { id: 0 };
  els.dBarcode.value = "";
  els.dSku.value = "";
  draftProblem("");
  renderMapping();
  els.dBarcode.focus();
}

function startEdit(id) {
  const row = rowById(id);
  if (!row) return;
  view.draft = { id: id };
  els.dBarcode.value = row.barcode;
  els.dSku.value = row.sku;
  draftProblem("");
  renderMapping();
  els.dSku.focus();
}

function leaveMapping() {
  if (mapping().dirty) {
    view.ask = { kind: "leave" };
    renderAsk();
  } else {
    view.bridge.closeMapping();
  }
}

function cancelDraft() {
  if (quick()) {
    leaveMapping();
    return;
  }
  view.draft = null;
  draftProblem("");
  renderMapping();
}

// What a slot answered: "" when the thing was done, else the sentence.
function draftDone(problem) {
  if (problem) {
    draftProblem(problem);
    return;
  }
  if (quick()) return;  // Python is leaving the page
  if (view.draft && !view.draft.id) {
    // The add row stays open for the next one.
    els.dBarcode.value = "";
    els.dSku.value = "";
    draftProblem("");
    renderMapping();
    els.dBarcode.focus();
  } else {
    view.draft = null;
    renderMapping();
  }
}

function commitDraft() {
  if (!view.draft) return;
  const barcode = els.dBarcode.value;
  const sku = els.dSku.value;
  if (!barcode.trim()) { els.dBarcode.focus(); return; }
  if (!sku.trim()) { els.dSku.focus(); return; }
  if (clashRow()) return;  // only Replace goes on from a collision
  if (view.draft.id) view.bridge.updateMapping(view.draft.id, barcode, sku, draftDone);
  else view.bridge.addMapping(barcode, sku, draftDone);
}

function replaceDraft() {
  if (!view.draft || !els.dSku.value.trim()) return;
  view.bridge.replaceMapping(view.draft.id, els.dBarcode.value, els.dSku.value, draftDone);
}

// Enter in the barcode field, which is also how a scan ends.
function barcodeEnter() {
  if (!els.dBarcode.value.trim() || clashRow()) return;
  const q = quick();
  if (q && q.kind === "sku") commitDraft();
  else els.dSku.focus();
}

function deleteRow(id) {
  const row = rowById(id);
  if (!row) return;
  if (row.status === "new") {
    // Never saved: nothing on the server changes, so nothing to ask.
    if (view.draft && view.draft.id === id) view.draft = null;
    view.bridge.deleteMapping(id);
    return;
  }
  view.ask = { kind: "delete", id: id };
  renderAsk();
}

function reload() {
  if (mapping().dirty) {
    view.ask = { kind: "reload" };
    renderAsk();
  } else {
    view.bridge.reloadMappings();
  }
}

function save() {
  if (view.bridge.page === "mapping" && !quick() && mapping().dirty) view.bridge.saveMappings();
}

function askYes() {
  const ask = view.ask;
  view.ask = null;
  renderAsk();
  if (!ask) return;
  if (ask.kind === "delete") {
    if (view.draft && view.draft.id === ask.id) view.draft = null;
    view.bridge.deleteMapping(ask.id);
  } else if (ask.kind === "reload") {
    view.draft = null;
    view.bridge.reloadMappings();
  } else {
    view.bridge.closeMapping();
  }
}

// --- keys and clicks --------------------------------------------------------------

function escapePressed() {
  const page = view.bridge.page;
  if (page === "workers") {
    if (view.creating) {
      closeForm();
      renderWorkers();
    }
    return;
  }
  if (page !== "mapping") return;
  if (view.ask) {
    view.ask = null;
    renderAsk();
  } else if (view.draft && !quick()) {
    cancelDraft();
  } else {
    leaveMapping();
  }
}

function onKey(event) {
  const target = event.target;
  const inField = target instanceof HTMLInputElement && !target.disabled;
  if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "s") {
    event.preventDefault();
    save();
    return;
  }
  if (event.ctrlKey || event.altKey || event.metaKey) return;
  if (event.key === "Escape") {
    event.preventDefault();
    escapePressed();
    return;
  }
  if (inField) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (target === els.wName) createWorker();
    else if (target === els.dBarcode) barcodeEnter();
    else if (target === els.dSku) commitDraft();
    return;
  }
  // No field has this key, so it is a scan in flight (ADR 0004): buffered,
  // and handed to Python whole when its Enter arrives. An Enter with nothing
  // buffered is a person pressing a focused button, and is left alone.
  // ponytail: the buffer is dropped on a click or a page change, not on a
  // timer; a timer is the upgrade if lone keys ever pollute a scan.
  if (event.key === "Enter") {
    if (!view.stray) return;
    event.preventDefault();
    const text = view.stray;
    view.stray = "";
    view.bridge.strayScan(text);
  } else if (event.key.length === 1) {
    event.preventDefault();
    view.stray += event.key;
  }
}

const ACTIONS = {
  leaveWorkers: function () { view.bridge.leaveWorkers(); },
  retryWorkers: function () { view.bridge.retryWorkers(); },
  newWorker: openForm,
  createWorker: createWorker,
  cancelWorker: function () { closeForm(); renderWorkers(); },
  startAdd: startAdd,
  commitDraft: commitDraft,
  cancelDraft: cancelDraft,
  replaceDraft: replaceDraft,
  reload: reload,
  save: save,
  leaveMapping: leaveMapping,
  errorAction: function () {
    if ((mapping().error || {}).action === "load") view.bridge.reloadMappings();
    else view.bridge.saveMappings();
  },
  askYes: askYes,
  askNo: function () { view.ask = null; renderAsk(); },
};

function onClick(event) {
  view.stray = "";
  const action = event.target.closest("[data-action]");
  if (action) {
    if (!action.disabled) ACTIONS[action.dataset.action]();
    return;
  }
  const rowAction = event.target.closest("[data-row-action]");
  if (rowAction) {
    const id = Number(rowAction.dataset.id);
    if (rowAction.dataset.rowAction === "edit") startEdit(id);
    else deleteRow(id);
    return;
  }
  const choice = event.target.closest("[data-choice]");
  if (choice) {
    els.dSku.value = choice.dataset.choice;
    commitDraft();
    return;
  }
  const worker = event.target.closest("[data-worker]");
  if (worker) view.bridge.pickWorker(worker.dataset.worker);
}

const IDS = {
  root: "setup", themeVars: "theme-vars",
  workers: "workers", wLeave: "w-leave", wFailed: "w-failed", wFailedTitle: "w-failed-title",
  wFailedText: "w-failed-text", wFailedPath: "w-failed-path", wEmpty: "w-empty",
  wGrid: "w-grid", wNew: "w-new", wForm: "w-form", wName: "w-name",
  wNameError: "w-name-error",
  mapping: "mapping", mClient: "m-client", mAdd: "m-add", mError: "m-error",
  mErrorTitle: "m-error-title", mErrorText: "m-error-text", mErrorPath: "m-error-path",
  mErrorCause: "m-error-cause", mErrorAction: "m-error-action",
  mEmpty: "m-empty", mTable: "m-table", mSearch: "m-search", mCount: "m-count",
  mReload: "m-reload", mScroll: "m-scroll", mDraft: "m-draft", mRows: "m-rows",
  mNohits: "m-nohits", mNohitsQ: "m-nohits-q",
  dBarcode: "d-barcode", dSku: "d-sku", dCommit: "d-commit", dCancel: "d-cancel",
  dClash: "d-clash", dClashSku: "d-clash-sku", dClashAsk: "d-clash-ask",
  dReplace: "d-replace", dProblem: "d-problem", dHint: "d-hint", dChoices: "d-choices",
  mUnsaved: "m-unsaved", mSummary: "m-summary", mSaved: "m-saved",
  mCancel: "m-cancel", mSave: "m-save",
  mAsk: "m-ask", mAskTitle: "m-ask-title", mAskPair: "m-ask-pair",
  mAskBarcode: "m-ask-barcode", mAskSku: "m-ask-sku", mAskText: "m-ask-text",
  mAskNo: "m-ask-no", mAskYes: "m-ask-yes",
};

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.setup;
  view.bridge = bridge;
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.setupBridge = bridge;
  Object.keys(IDS).forEach(function (name) {
    els[name] = document.getElementById(IDS[name]);
  });

  const onTheme = function () { els.themeVars.textContent = bridge.themeCss; };
  onTheme();
  bridge.themeCssChanged.connect(onTheme);

  bridge.pageChanged.connect(renderPage);
  bridge.workersChanged.connect(renderWorkers);
  bridge.mappingChanged.connect(renderMapping);
  bridge.leaveAsked.connect(function () {
    if (bridge.page !== "mapping" || !mapping().dirty) return;
    view.ask = { kind: "leave" };
    renderAsk();
  });
  renderPage();

  els.wName.addEventListener("input", function () { nameProblem(""); });
  els.mSearch.addEventListener("input", function () {
    view.search = els.mSearch.value;
    renderRows();
  });
  els.dBarcode.addEventListener("input", function () {
    // A barcode has no spaces, however it was pasted.
    const bare = els.dBarcode.value.replace(/\s/g, "");
    if (bare !== els.dBarcode.value) els.dBarcode.value = bare;
    draftProblem("");
    renderDraft();
  });
  els.dSku.addEventListener("input", function () {
    draftProblem("");
    renderDraft();
  });
  // In a quick map the focus is never left on nothing: a scan must have a
  // field to land in (ADR 0004).
  document.addEventListener("focusout", function () {
    setTimeout(function () {
      if (quick() && !view.ask && document.activeElement === document.body) focusQuick();
    }, 0);
  });
  document.addEventListener("keydown", onKey);
  els.root.addEventListener("click", onClick);

  // After the first render, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
