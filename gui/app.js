"use strict";

// ---------------------------------------------------------------------------
// State. `slots` is a dense ordered list of real entries only -- a trailing
// "add deck" tile is appended purely for rendering, never stored here. This
// keeps reorder/remove simple array splices with no positional holes.
// ---------------------------------------------------------------------------
const state = {
  slots: [],       // {token, id, status:'loading'|'ok'|'error', info, cardHtml, error}
  flags: {
    paper: "letter", gap: 3.0, cardScale: 1.0,
    useArt: true, showPrice: false, useQr: true,
    allFormats: false, out: "deck_cards.html",
  },
  layout: null,     // {m, page_size, css, crop_html}
  editingIndex: null,
};

let dragIndex = null;
let toastTimer = null;

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function $(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

async function apiPost(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

function showToast(msg, kind = "ok", ms = 4000) {
  const el = $("toast");
  el.textContent = msg;
  el.className = `toast ${kind}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

function cardFlags() {
  return { use_art: state.flags.useArt, show_price: state.flags.showPrice, use_qr: state.flags.useQr };
}

// ---------------------------------------------------------------------------
// Layout (paper / gap / card scale) -- drives the injected <style> and the
// crop-guide markup. Card content itself is untouched by this.
// ---------------------------------------------------------------------------
async function refreshLayout() {
  const data = await apiPost("/api/layout", {
    paper: state.flags.paper, gap: state.flags.gap, card_scale: state.flags.cardScale,
  });
  state.layout = data;
  $("card-style").textContent = data.css;

  const note = $("layoutNote");
  const got = Math.min(data.m.gx, data.m.gy);
  if (data.m.want - got > 0.01 / 25.4) {
    note.hidden = false;
    note.textContent = `Gap clamped to ~${(got * 25.4).toFixed(1)}mm to fit the page. `
      + `Try A4 or a smaller card scale for a larger gap.`;
  } else {
    note.hidden = true;
  }
  renderGrid();
}
const debouncedRefreshLayout = debounce(refreshLayout, 150);

// Re-render only the card markup (art/price/QR toggles) without re-fetching
// from Archidekt -- cheap, backend just replays render_card() on cached info.
async function rerenderCards() {
  const ids = [...new Set(state.slots.filter((s) => s.status === "ok").map((s) => s.id))];
  if (!ids.length) return;
  const res = await apiPost("/api/rerender", { ids, flags: cardFlags() });
  state.slots.forEach((s) => {
    if (s.status === "ok" && res.cards[s.id]) s.cardHtml = res.cards[s.id];
  });
  renderGrid();
}

// ---------------------------------------------------------------------------
// Slot resolution
// ---------------------------------------------------------------------------
async function resolveSlot(index, token) {
  try {
    const res = await apiPost("/api/resolve", { token, flags: cardFlags() });
    if (res.ok) {
      state.slots[index] = { token, id: res.id, status: "ok", info: res.info, cardHtml: res.card_html };
    } else {
      state.slots[index] = { token, status: "error", error: res.error || "Unknown error" };
    }
  } catch (err) {
    state.slots[index] = { token, status: "error", error: String(err) };
  }
  renderGrid();
}

// Chunked rather than one request for the whole list: a username import can
// mean 100+ decks, and the server paces uncached Archidekt fetches ~0.4s
// apart to be polite -- bundled into a single request that's a minute-plus
// held open, all-or-nothing if anything along the way trips. Chunking bounds
// each request's blast radius and gives incremental progress/results instead
// of one long silent wait.
const BULK_CHUNK_SIZE = 15;

async function bulkAdd(tokens) {
  const total = tokens.length;
  let okTotal = 0;
  showToast(`Fetching ${total} deck(s)...`, "ok", 60000);
  for (let i = 0; i < tokens.length; i += BULK_CHUNK_SIZE) {
    const chunk = tokens.slice(i, i + BULK_CHUNK_SIZE);
    const startIndex = state.slots.length;
    chunk.forEach((t) => state.slots.push({ token: t, status: "loading" }));
    renderGrid();
    try {
      const res = await apiPost("/api/bulk", { tokens: chunk, flags: cardFlags() });
      res.results.forEach((r, j) => {
        const idx = startIndex + j;
        if (r.ok) {
          state.slots[idx] = { token: chunk[j], id: r.id, status: "ok", info: r.info, cardHtml: r.card_html };
          okTotal += 1;
        } else {
          state.slots[idx] = { token: chunk[j], status: "error", error: r.error || "Unknown error" };
        }
      });
    } catch (err) {
      // Whole chunk request failed (network error, etc) -- mark just this
      // chunk's slots as failed rather than leaving them spinning forever,
      // and keep going with the remaining chunks.
      chunk.forEach((t, j) => {
        state.slots[startIndex + j] = { token: t, status: "error", error: String(err) };
      });
    }
    renderGrid();
    showToast(`Fetching decks... ${Math.min(i + BULK_CHUNK_SIZE, total)}/${total}`, "ok", 60000);
  }
  showToast(`Added ${okTotal}/${total} deck(s).`, okTotal === total ? "ok" : "err");
}

function removeSlot(index) {
  if (index >= state.slots.length) return;
  state.slots.splice(index, 1);
  renderGrid();
}

// ---------------------------------------------------------------------------
// Inline edit mode
// ---------------------------------------------------------------------------
function enterEdit(index) {
  state.editingIndex = index;
  renderGrid();
  requestAnimationFrame(() => {
    const el = document.querySelector(`.slot-edit[data-index="${index}"] textarea`);
    if (el) { el.focus(); el.select(); }
  });
}

function cancelEdit() {
  state.editingIndex = null;
  renderGrid();
}

async function submitEdit(el) {
  if (state.editingIndex === null) return;
  const index = state.editingIndex;
  const raw = el.value;
  state.editingIndex = null;

  const lines = raw.split("\n").map((s) => s.split("#")[0].trim()).filter(Boolean);
  if (lines.length === 0) {
    if (index < state.slots.length) removeSlot(index); else renderGrid();
    return;
  }

  const [first, ...rest] = lines;
  if (index < state.slots.length) {
    state.slots[index] = { token: first, status: "loading" };
  } else {
    state.slots.push({ token: first, status: "loading" });
  }
  renderGrid();
  await resolveSlot(index < state.slots.length ? index : state.slots.length - 1, first);

  if (rest.length) await bulkAdd(rest);
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function renderSlotHtml(slot, index) {
  if (state.editingIndex === index) {
    const val = slot && slot.token ? escapeHtml(slot.token) : "";
    return `<div class="slot-edit" data-index="${index}">
      <textarea data-role="edit-input" placeholder="Paste Archidekt deck URL/ID (one or more lines)">${val}</textarea>
      <span class="hint">Enter to save &middot; Esc to cancel</span>
    </div>`;
  }

  if (!slot || slot.virtual) {
    return `<div class="slot-placeholder" data-action="add" data-index="${index}">
      <span class="plus">+</span><span>Add deck</span>
    </div>`;
  }

  if (slot.status === "loading") {
    return `<div class="slot-loading" data-index="${index}"><div class="spinner"></div></div>`;
  }

  if (slot.status === "error") {
    return `<div class="slot-error" data-action="edit" data-index="${index}">
      <span>&#9888; Couldn't load deck</span>
      <span class="err-msg">${escapeHtml(slot.error || "")}</span>
      <span class="hint">Click to edit</span>
    </div>`;
  }

  const hideTag = (!state.flags.allFormats && slot.info && slot.info.format_code !== 3)
    ? `<span class="card-tag">Hidden: not Commander</span>` : "";
  return `<div class="card-wrap" draggable="true" data-index="${index}">
      ${slot.cardHtml}
      ${hideTag}
      <div class="card-actions">
        <button class="edit" data-action="edit" data-index="${index}" title="Edit">&#9998;</button>
        <button class="remove" data-action="remove" data-index="${index}" title="Remove">&times;</button>
      </div>
    </div>`;
}

function renderGrid() {
  const items = state.slots.concat([{ virtual: true }]);
  const cropHtml = state.layout ? state.layout.crop_html : "";
  let html = "";
  for (let i = 0; i < items.length; i += 9) {
    const chunk = items.slice(i, i + 9);
    const cells = chunk.map((slot, j) => renderSlotHtml(slot, i + j)).join("");
    html += `<div class="sheet">${cropHtml}${cells}</div>`;
  }
  $("sheets").innerHTML = html;
}

// ---------------------------------------------------------------------------
// Grid event delegation (click / edit / drag-reorder)
// ---------------------------------------------------------------------------
function onGridClick(e) {
  const actionEl = e.target.closest("[data-action]");
  if (!actionEl) return;
  const action = actionEl.dataset.action;
  const index = parseInt(actionEl.dataset.index, 10);
  if (action === "add" || action === "edit") {
    e.stopPropagation();
    enterEdit(index);
  } else if (action === "remove") {
    e.stopPropagation();
    removeSlot(index);
  }
}

function onGridKeydown(e) {
  if (e.target.tagName !== "TEXTAREA" || e.target.dataset.role !== "edit-input") return;
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitEdit(e.target);
  } else if (e.key === "Escape") {
    e.preventDefault();
    cancelEdit();
  }
}

function onGridFocusOut(e) {
  if (e.target.tagName !== "TEXTAREA" || e.target.dataset.role !== "edit-input") return;
  const el = e.target;
  setTimeout(() => { if (state.editingIndex !== null) submitEdit(el); }, 120);
}

function onDragStart(e) {
  const wrap = e.target.closest(".card-wrap");
  if (!wrap) return;
  dragIndex = parseInt(wrap.dataset.index, 10);
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", String(dragIndex));
}

function onDragOver(e) {
  const wrap = e.target.closest(".card-wrap");
  if (!wrap || dragIndex === null) return;
  e.preventDefault();
  wrap.classList.add("drag-over");
}

function onDragLeave(e) {
  const wrap = e.target.closest(".card-wrap");
  if (wrap) wrap.classList.remove("drag-over");
}

function onDrop(e) {
  const wrap = e.target.closest(".card-wrap");
  if (!wrap || dragIndex === null) return;
  e.preventDefault();
  wrap.classList.remove("drag-over");
  const dropIndex = parseInt(wrap.dataset.index, 10);
  if (dropIndex !== dragIndex && dragIndex < state.slots.length && dropIndex < state.slots.length) {
    const [moved] = state.slots.splice(dragIndex, 1);
    state.slots.splice(dropIndex, 0, moved);
  }
  dragIndex = null;
  renderGrid();
}

// ---------------------------------------------------------------------------
// Import / generate actions
// ---------------------------------------------------------------------------
async function importUser() {
  const input = $("importUser");
  const username = input.value.trim();
  if (!username) return;
  const btn = $("importUserBtn");
  btn.disabled = true;
  showToast(`Listing public decks for ${username}...`, "ok", 60000);
  try {
    const res = await apiPost("/api/user-decks", { username, all_formats: state.flags.allFormats });
    if (res.error) { showToast(res.error, "err"); return; }
    if (!res.ids.length) { showToast("No public decks found.", "err"); return; }
    await bulkAdd(res.ids);
  } catch (err) {
    showToast(`Import failed: ${err}`, "err");
  } finally {
    btn.disabled = false;
  }
}

function importPaste() {
  const ta = $("importPaste");
  const lines = ta.value.split("\n").map((s) => s.split("#")[0].trim()).filter(Boolean);
  if (!lines.length) return;
  ta.value = "";
  bulkAdd(lines);
}

async function generate() {
  const tokens = state.slots.map((s) => s.token).filter(Boolean);
  if (!tokens.length) { showToast("Add at least one deck first.", "err"); return; }
  const btn = $("generateBtn");
  btn.disabled = true;
  showToast("Generating...", "ok", 60000);
  try {
    const res = await apiPost("/api/render", {
      slots: tokens,
      flags: {
        paper: state.flags.paper, gap: state.flags.gap, card_scale: state.flags.cardScale,
        use_art: state.flags.useArt, show_price: state.flags.showPrice, use_qr: state.flags.useQr,
        all_formats: state.flags.allFormats, out: state.flags.out,
      },
    });
    if (!res.ok) { showToast(res.error || "Render failed.", "err"); return; }
    let msg = `Wrote ${res.count} card(s) across ${res.sheets} sheet(s) -> ${res.path}.`;
    if (res.skipped && res.skipped.length) msg += ` (${res.skipped.length} skipped)`;
    showToast(msg, "ok", 8000);
    window.open(res.url, "_blank");
  } catch (err) {
    showToast(`Render failed: ${err}`, "err");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
function initToolbar() {
  $("paper").addEventListener("change", (e) => { state.flags.paper = e.target.value; refreshLayout(); });

  $("gap").addEventListener("input", (e) => {
    state.flags.gap = parseFloat(e.target.value);
    $("gapVal").textContent = state.flags.gap.toFixed(1);
    debouncedRefreshLayout();
  });

  $("cardScale").addEventListener("input", (e) => {
    state.flags.cardScale = parseFloat(e.target.value);
    $("scaleVal").textContent = state.flags.cardScale.toFixed(2);
    debouncedRefreshLayout();
  });

  $("allFormats").addEventListener("change", (e) => {
    state.flags.allFormats = e.target.checked;
    renderGrid();
  });
  $("useArt").addEventListener("change", (e) => { state.flags.useArt = e.target.checked; rerenderCards(); });
  $("showPrice").addEventListener("change", (e) => { state.flags.showPrice = e.target.checked; rerenderCards(); });
  $("useQr").addEventListener("change", (e) => { state.flags.useQr = e.target.checked; rerenderCards(); });

  $("outName").addEventListener("input", (e) => {
    state.flags.out = e.target.value.trim() || "deck_cards.html";
  });

  $("generateBtn").addEventListener("click", generate);
  $("importUserBtn").addEventListener("click", importUser);
  $("importUser").addEventListener("keydown", (e) => { if (e.key === "Enter") importUser(); });
  $("importPasteBtn").addEventListener("click", importPaste);
}

function initGrid() {
  const sheets = $("sheets");
  sheets.addEventListener("click", onGridClick);
  sheets.addEventListener("keydown", onGridKeydown, true);
  sheets.addEventListener("focusout", onGridFocusOut, true);
  sheets.addEventListener("dragstart", onDragStart);
  sheets.addEventListener("dragover", onDragOver);
  sheets.addEventListener("dragleave", onDragLeave);
  sheets.addEventListener("drop", onDrop);
}

function init() {
  initToolbar();
  initGrid();
  refreshLayout();
}

document.addEventListener("DOMContentLoaded", init);
