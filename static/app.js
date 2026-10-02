// Manuscript Labeler front end. Plain JS, no build step.
//
// The whole labels document lives in S.doc and is saved (debounced) with a
// PUT of the full document. The server refuses a save if the file changed
// since we loaded it (If-Match), so two tabs can't silently overwrite each other.
//
// Coordinates in S.doc are page fractions (0..1). The SVG works in image
// pixels: X = x * W, Y = y * H.

'use strict';

const PARTS = ['vn1', 'vn2', 'va', 'vc', 'score'];
const PART_NAMES = { vn1: 'Violin I', vn2: 'Violin II', va: 'Viola', vc: 'Cello', score: 'Score' };
const CLEFS = ['treble', 'alto', 'tenor', 'bass'];
const DEFAULT_CLEF = { vn1: 'treble', vn2: 'treble', va: 'alto', vc: 'bass', score: 'treble' };
const PAGE_KINDS = ['music', 'title', 'blank', 'other'];
const BARLINE_KINDS = ['single', 'double', 'repeat_start', 'repeat_end', 'repeat_both', 'final'];
const BARLINE_TAG = { double: '‖', repeat_start: '‖:', repeat_end: ':‖', repeat_both: ':‖:', final: 'fin' };
const MARK_KINDS = ['text', 'tempo', 'dynamic', 'stray', 'unclear', 'other'];
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];
// pitch of the bottom staff line: [letter index in CDEFGAB, octave]
const CLEF_BOTTOM = { treble: [2, 4], alto: [3, 3], tenor: [1, 3], bass: [4, 2] };

const $ = (s) => document.querySelector(s);
const svg = $('#canvas');
const overlay = $('#overlay');

const S = {
  sources: [],
  pdf: null,
  info: null,          // /api/source response minus labels
  doc: null,           // the labels document
  etag: null,
  readonly: null,
  numPages: 0,
  page: 1,
  W: 1, H: 1,          // current render size in px
  imgEl: null,         // loaded HTMLImageElement of the current page
  view: { x: 0, y: 0, w: 1, h: 1 },
  sel: null,           // { t: 'sys'|'bl'|'mark', id }
  mouse: { x: 0.5, y: 0.5 },
  drag: null,
  undo: [], redo: [],
  version: 0, savedVersion: 0, saving: false, saveTimer: null, conflict: false,
  bars: [], byBarline: new Map(),
  detail: false,
  placing: null,       // 'bl' | 'sys' | 'mark': the next click on the page adds one
  held: null,          // the key being held down to place ('b', 's', 'm')
  loadToken: 0,
};

// ------------------------------------------------------------------ helpers

async function getJSON(url) {
  const r = await fetch(url);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
const q = (pdf, page) => `pdf=${encodeURIComponent(pdf)}` + (page ? `&page=${page}` : '');
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const mid = (b) => (b.x0 + b.x1) / 2;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const roman = (n) => ROMAN[n - 1] || String(n);
const space = (s) => (s.bottom - s.top) / 4;
const pg = () => S.doc && S.doc.pages[S.page];
const inField = () => ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName);
// after picking from a menu, hand the keyboard back to the shortcuts
document.addEventListener('change', (e) => { if (e.target.tagName === 'SELECT' || e.target.type === 'checkbox') e.target.blur(); });

function banner(msg, action) {
  const b = $('#banner');
  if (!msg) { b.hidden = true; return; }
  b.innerHTML = esc(msg) + (action ? ` <button>${esc(action.label)}</button>` : '');
  if (action) b.querySelector('button').onclick = action.run;
  b.hidden = false;
}

// Staff offset at x. `bend` holds offsets at evenly spaced points from left
// to right, so a staff can follow a slanted or curled page. Mirrors
// labels.bend_at in Python.
function bendAt(s, x) {
  const b = s.bend;
  if (!b || b.length < 2) return 0;
  if (s.right <= s.left) return b[0];
  const t = clamp((x - s.left) / (s.right - s.left) * (b.length - 1), 0, b.length - 1);
  const i = Math.min(Math.floor(t), b.length - 2);
  return b[i] + (b[i + 1] - b[i]) * (t - i);
}
const topAt = (s, x) => s.top + bendAt(s, x);
const bottomAt = (s, x) => s.bottom + bendAt(s, x);
// how far the bar images reach beyond the staff, in staff spaces
const cropAbove = (s, b) => b?.above ?? s.above ?? 2.5;
const cropBelow = (s, b) => b?.below ?? s.below ?? 2.5;

// a bar's crop: corners TL TR BR BL, mirroring labels.bar_quad
function barQuad(s, left, right) {
  const sp = space(s), above = cropAbove(s, right), below = cropBelow(s, right);
  const side = (edge) => {
    const st = s.start ?? s.left;
    const b = edge || { x0: st, x1: st };
    const t = topAt(s, mid(b)) - above * sp, u = bottomAt(s, mid(b)) + below * sp;
    return [[xAt(b, s, t), t], [xAt(b, s, u), u]];
  };
  const [lt, lb] = side(left), [rt, rb] = side(right);
  return [lt, rt, rb, lb];
}

// Change a staff's left/right, keeping its bend where it was on the page
// (the bend points are spread over left..right, so they must be resampled).
function setExtent(s, left, right) {
  if (s.bend?.length > 1) {
    const n = s.bend.length - 1;
    const pts = Array.from({ length: n + 1 }, (_, i) => left + (right - left) * i / n);
    s.bend = pts.map((x) => bendAt(s, x));
  }
  s.left = left;
  s.right = right;
}

// end a staff just after its last bar line
function trimToLastBarline(s) {
  if (!s.barlines.length) return;
  const last = Math.max(...s.barlines.map((b) => Math.max(b.x0, b.x1)));
  const right = last + 0.5 * space(s) * S.H / S.W;
  if (right < s.right) setExtent(s, s.left, right);
}

// x of a bar line at height y (page fractions), following its lean:
// x0 is where it crosses the top staff line, x1 the bottom one
function xAt(b, s, y) {
  const t = topAt(s, mid(b)), h = s.bottom - s.top;
  return h > 0 ? b.x0 + (b.x1 - b.x0) * (y - t) / h : b.x0;
}

// polygon points for a stretch of a staff from x0 to x1, widened by
// `above` / `below` staff spaces, following its bend
function strip(s, x0, x1, above = 0, below = 0, n = 12) {
  const sp = space(s);
  const xs = Array.from({ length: n + 1 }, (_, i) => x0 + (x1 - x0) * i / n);
  const top = xs.map((x) => `${x * S.W},${(topAt(s, x) - above * sp) * S.H}`);
  const bot = xs.reverse().map((x) => `${x * S.W},${(bottomAt(s, x) + below * sp) * S.H}`);
  return top.concat(bot).join(' ');
}

// bar numbers after which Structure.ily puts a repeat sign, per movement
function repeatEnds(movement) {
  const e = S.info?.expected?.[movement];
  if (!e) return [];
  let cum = 0;
  const out = [];
  for (const seg of e.segments) { cum += seg.bars; if (seg.repeat) out.push(cum); }
  return out;
}
const lastBarOf = (nb) => nb.bar + Math.max(nb.count, 1) - 1;

function nextId(page, prefix) {
  let max = 0;
  const re = new RegExp('^' + prefix + '(\\d+)$');
  const scan = (id) => { const m = re.exec(id); if (m) max = Math.max(max, +m[1]); };
  for (const s of page.systems) { scan(s.id); s.barlines.forEach((b) => scan(b.id)); }
  page.marks.forEach((m) => scan(m.id));
  return prefix + (max + 1);
}

function find(sel, page = pg()) {
  if (!sel || !page) return null;
  if (sel.t === 'mark') return page.marks.find((m) => m.id === sel.id) || null;
  if (sel.t === 'page') return page.corners || null;
  for (const s of page.systems) {
    if (sel.t === 'sys' && s.id === sel.id) return s;
    if (sel.t === 'bl') { const b = s.barlines.find((b) => b.id === sel.id); if (b) return b; }
  }
  return null;
}
const systemOf = (bl, page = pg()) => page.systems.find((s) => s.barlines.includes(bl));

// ------------------------------------------------------------------ numbering
// Mirrors labels.number_bars in Python. Keep the two in step.

function numberBars(doc) {
  const state = {};
  const out = [];
  const pages = Object.keys(doc.pages).map(Number).sort((a, b) => a - b);
  for (const n of pages) {
    const page = doc.pages[n];
    const part = page.part;
    if (page.kind !== 'music' || !part) continue;
    const st = state[part] || (state[part] = { mvt: 1, bar: 1 });
    const systems = page.systems.filter((s) => (s.role || 'part') === 'part').sort((a, b) => a.top - b.top);
    for (const s of systems) {
      let prev = null;
      for (const b of [...s.barlines].sort((a, c) => mid(a) - mid(c))) {
        const count = b.bar_count ?? 1;
        out.push({ part, movement: roman(st.mvt), bar: count ? st.bar : st.bar - 1, count, page: n, system: s, left: prev, right: b });
        st.bar += count;
        if (b.ends_movement) { st.mvt += 1; st.bar = 1; }
        prev = b;
      }
    }
  }
  return out;
}

function renumber() {
  S.bars = numberBars(S.doc);
  S.byBarline = new Map(S.bars.map((b) => [b.right.id, b]));
}

const barLabel = (nb) => nb.count > 1 ? `${nb.bar}–${nb.bar + nb.count - 1}` : nb.count === 0 ? `(${nb.bar})` : `${nb.bar}`;

// ------------------------------------------------------------------ saving

// An edit makes an untouched (auto) page "edited". A reviewed page stays
// reviewed: fixes made while reviewing shouldn't silently undo the review.
// Clicking the status badge un-reviews a page on purpose.
function touchPage(page = pg()) {
  if (page && page.status === 'auto') page.status = 'edited';
}

function snapshot() {
  return { page: S.page, json: JSON.stringify(S.doc.pages[S.page] ?? null) };
}

function pushUndo() {
  S.undo.push(snapshot());
  if (S.undo.length > 200) S.undo.shift();
  S.redo = [];
}

function restore(from, to) {
  const snap = from.pop();
  if (!snap) return;
  if (snap.page !== S.page) { from.push(snap); openPage(snap.page); return; }  // press again to undo there
  to.push(snapshot());
  const p = JSON.parse(snap.json);
  if (p) S.doc.pages[S.page] = p; else delete S.doc.pages[S.page];
  if (!find(S.sel)) S.sel = null;
  changed();
}

// Every edit goes through here: snapshot for undo, apply, mark the page edited, save.
function mutate(fn, { status = true } = {}) {
  if (S.readonly || !pg()) return;
  pushUndo();
  fn(pg());
  if (status) touchPage();
  changed();
}

function changed() {
  S.version++;
  renumber();
  renderAll();
  scheduleSave();
}

function setSaveStatus(text, error = false) {
  const el = $('#savestatus');
  el.textContent = text;
  el.classList.toggle('error', error);
}

function scheduleSave() {
  if (S.readonly || S.conflict) return;
  setSaveStatus('unsaved');
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(saveNow, 400);
}

async function saveNow() {
  if (S.readonly || S.conflict || S.version === S.savedVersion) return;
  if (S.saving) { S.saveTimer = setTimeout(saveNow, 200); return; }
  S.saving = true;
  const version = S.version;
  setSaveStatus('saving…');
  try {
    const r = await fetch(`/api/labels?${q(S.pdf)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'If-Match': S.etag },
      body: JSON.stringify(S.doc),
    });
    const j = await r.json().catch(() => ({}));
    if (r.status === 409) {
      S.conflict = true;
      setSaveStatus('not saved', true);
      banner(`Not saved: ${j.error}. Reload to get the current file.`, { label: 'Reload', run: () => location.reload() });
      return;
    }
    if (!r.ok) throw new Error(j.error || r.statusText);
    S.etag = j.etag;
    S.savedVersion = version;
    setSaveStatus(S.version === version ? 'saved' : 'unsaved');
  } catch (e) {
    setSaveStatus('save failed', true);
    banner(`Save failed: ${e.message}. Your changes are still in this tab; it will retry.`);
    S.saveTimer = setTimeout(() => { banner(null); saveNow(); }, 3000);
  } finally {
    S.saving = false;
  }
}

window.addEventListener('beforeunload', (e) => {
  if (S.version !== S.savedVersion && !S.readonly) { saveNow(); e.preventDefault(); }
});

// ------------------------------------------------------------------ loading

async function loadSources() {
  const j = await getJSON('/api/sources');
  S.sources = j.sources;
  const sel = $('#source');
  sel.innerHTML = j.sources.map((s) => {
    const done = s.statuses.reviewed || 0;
    const g = s.source.gerard ? `G${s.source.gerard} · ` : '';
    return `<option value="${esc(s.pdf)}">${esc(g + s.source.siglum + ' ' + s.source.shelfmark)} (${done}/${s.pages})</option>`;
  }).join('');
  const h = parseHash();
  const pdf = S.sources.some((s) => s.pdf === h.pdf) ? h.pdf : S.sources[0]?.pdf;
  if (!pdf) { banner('No PDFs found under sources/.'); return; }
  sel.value = pdf;
  await loadSource(pdf, h.page);
}

function parseHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  return { pdf: p.get('pdf'), page: +p.get('page') || null };
}

async function loadSource(pdf, page) {
  if (S.pdf && S.version !== S.savedVersion) await saveNow();
  const j = await getJSON(`/api/source?${q(pdf)}`);
  S.pdf = pdf;
  S.doc = j.labels;
  S.etag = j.etag;
  S.readonly = j.readonly;
  S.numPages = j.pages;
  S.info = j;
  S.version = S.savedVersion = 0;
  S.conflict = false;
  S.undo = []; S.redo = [];
  if (S.readonly) banner(`Read-only: ${S.readonly}`);
  renumber();
  renderMeta();
  setSaveStatus(j.etag === 'none' ? 'no labels file yet' : 'saved');
  await openPage(clamp(page || firstUnreviewed(), 1, S.numPages));
}

function firstUnreviewed() {
  for (let n = 1; n <= S.numPages; n++) if (S.doc.pages[n]?.status !== 'reviewed') return n;
  return 1;
}

async function openPage(n) {
  if (!S.doc || n < 1 || n > S.numPages) return;
  const token = ++S.loadToken;
  S.page = n;
  S.sel = null;
  history.replaceState(null, '', `#${q(S.pdf, n)}`);
  $('#loading').hidden = false;
  renderAll();

  const img = new Image();
  img.src = `/api/page?${q(S.pdf, n)}`;
  try { await img.decode(); } catch { if (token === S.loadToken) banner(`Could not render page ${n}.`); return; }
  if (token !== S.loadToken) return;
  S.imgEl = img;
  S.W = img.naturalWidth; S.H = img.naturalHeight;
  const scan = $('#scan');
  scan.setAttribute('href', img.src);
  scan.setAttribute('width', S.W);
  scan.setAttribute('height', S.H);
  fitPage();

  if (!S.doc.pages[n] && !S.readonly) await autoLabel(n, token);
  if (token !== S.loadToken) return;
  $('#loading').hidden = true;
  renderAll();
}

// ------------------------------------------------------------------ detection

function previousPage(n, pred = () => true) {
  for (let k = n - 1; k >= 1; k--) { const p = S.doc.pages[k]; if (p && pred(p)) return p; }
  return null;
}

function clefFor(n, part) {
  const prev = previousPage(n, (p) => p.part === part && p.clef);
  return prev ? prev.clef : (DEFAULT_CLEF[part] || null);
}

function newSystem(page, d) {
  const s = {
    id: nextId(page, `p${S.page}s`),
    top: d.top, bottom: d.bottom, left: d.left, right: d.right,
    start: d.start ?? d.left,
    auto: true, barlines: [],
  };
  if (d.bend) s.bend = d.bend;
  if (d.above != null) s.above = d.above;  // how far this staff's own ink reaches
  if (d.below != null) s.below = d.below;
  page.systems.push(s);
  for (const b of d.barlines) newBarline(page, s, b);
  return s;
}

function newBarline(page, s, d, auto = true) {
  const b = { id: nextId(page, `${s.id}b`), x0: d.x0, x1: d.x1, kind: d.kind || 'single', auto, bar_count: 1, ends_movement: false };
  s.barlines.push(b);
  return b;
}

async function autoLabel(n, token) {
  let systems = [], corners = null;
  try { ({ systems, corners } = await getJSON(`/api/detect?${q(S.pdf, n)}`)); }
  catch (e) { banner(`Detection failed on page ${n}: ${e.message}`); }
  if (token !== S.loadToken || S.doc.pages[n]) return;
  const prev = previousPage(n);
  const part = prev ? prev.part : null;
  // staves but (almost) no bar lines: a title page on ruled paper
  const music = systems.reduce((k, d) => k + d.barlines.length, 0) >= 2;
  const page = {
    status: 'auto', kind: music ? 'music' : 'title', part,
    clef: clefFor(n, part), notes: '', systems: [], marks: [],
  };
  if (corners) page.corners = { points: corners, auto: true };
  S.doc.pages[n] = page;
  if (music) for (const d of systems) newSystem(page, d);
  // a double bar where Structure.ily expects a repeat is almost surely one
  renumber();
  for (const nb of S.bars) {
    if (nb.page === n && nb.right.kind === 'double' && repeatEnds(nb.movement).includes(lastBarOf(nb))) nb.right.kind = 'repeat_end';
  }
  changed();
}

// Re-run detection without disturbing anything the editor touched:
// edited staves keep their geometry, edited bar lines stay, auto bar lines
// are replaced by fresh proposals, and nothing the editor deleted (kept in
// `rejected` / `rejected_staves`) comes back.
async function redetect() {
  if (S.readonly || !pg()) return;
  const n = S.page;
  let systems, corners;
  try { ({ systems, corners } = await getJSON(`/api/detect?${q(S.pdf, n)}`)); }
  catch (e) { banner(`Detection failed: ${e.message}`); return; }
  if (n !== S.page) return;
  mutate((page) => {
    const overlaps = (a, b) => Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5 * Math.min(a.bottom - a.top, b.bottom - b.top);
    const used = new Set();
    if (corners && (!page.corners || page.corners.auto)) page.corners = { points: corners, auto: true };
    const rejectedStaff = (d) => (page.rejected_staves || []).some((y) => y > d.top && y < d.bottom);
    for (const d of systems) {
      const ex = page.systems.find((s) => !used.has(s) && overlaps(s, d));
      if (!ex) { if (!rejectedStaff(d)) used.add(newSystem(page, d)); continue; }
      used.add(ex);
      if (ex.auto) Object.assign(ex, { top: d.top, bottom: d.bottom, left: d.left, right: d.right, start: d.start ?? d.left, bend: d.bend, above: d.above, below: d.below });
      else if (!ex.bend && d.bend) ex.bend = d.bend;  // labeled before bends existed
      const manual = ex.barlines.filter((b) => !b.auto);
      ex.barlines = manual;
      const taken = manual.map(mid).concat(ex.rejected || []);
      for (const b of d.barlines) if (!taken.some((x) => Math.abs(x - mid(b)) < 0.008)) newBarline(page, ex, b);
    }
    page.systems = page.systems.filter((s) => used.has(s) || !s.auto || s.barlines.some((b) => !b.auto));
  }, { status: false });
}

// detected corners for this page, replacing any the editor moved
async function resetCorners() {
  const n = S.page;
  let corners;
  try { ({ corners } = await getJSON(`/api/detect?${q(S.pdf, n)}`)); }
  catch (e) { banner(`Detection failed: ${e.message}`); return; }
  if (n !== S.page || !corners) return;
  mutate((page) => { page.corners = { points: corners, auto: true }; });
  S.sel = { t: 'page' };
  renderAll();
}

// ------------------------------------------------------------------ view

function setView(v) {
  S.view = v;
  svg.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
  renderOverlay();
}
function fitPage() { setView({ x: 0, y: 0, w: S.W, h: S.H }); }
function fitWidth() {
  const r = svg.getBoundingClientRect();
  const h = S.W * r.height / r.width;
  setView({ x: 0, y: clamp(S.view.y, 0, Math.max(0, S.H - h)), w: S.W, h });
}
function zoomAt(f, px, py) {
  const v = S.view;
  const w = clamp(v.w * f, S.W / 40, S.W * 4);
  f = w / v.w;
  setView({ x: px - (px - v.x) * f, y: py - (py - v.y) * f, w, h: v.h * f });
}
// px per screen pixel; with "meet" the larger ratio wins
function unit() {
  const r = svg.getBoundingClientRect();
  return Math.max(S.view.w / r.width, S.view.h / r.height) || 1;
}
function toImage(e) {
  const p = svg.createSVGPoint();
  p.x = e.clientX; p.y = e.clientY;
  const m = svg.getScreenCTM();
  return m ? p.matrixTransform(m.inverse()) : { x: 0, y: 0 };
}

// ------------------------------------------------------------------ rendering

function renderAll() {
  renderOverlay();
  renderPageForm();
  renderInspector();
  renderPages();
  renderCounts();
  renderDetail();
  $('#pagelabel').textContent = `Page ${S.page} / ${S.numPages}`;
  renderReviewButton();
}

function renderOverlay() {
  const page = pg();
  if (!page) { overlay.innerHTML = ''; return; }
  const { W, H } = S;
  const u = unit();
  const r = 6 * u;
  const out = [];
  const sel = S.sel;
  const isSel = (t, id) => sel && sel.t === t && sel.id === id;

  // the paper: dim everything outside its corners; click there to edit them
  if (page.corners) {
    const c = page.corners.points.map(([x, y]) => `${x * W},${y * H}`);
    out.push(`<path class="offpage" data-t="page" fill-rule="evenodd" d="M0,0 H${W} V${H} H0 Z M${c.join(' L')} Z"/>`);
    out.push(`<polygon class="pageedge${sel?.t === 'page' ? ' sel' : ''}${page.corners.auto ? ' auto' : ''}" points="${c.join(' ')}"/>`);
  }

  for (const s of page.systems) {
    const cue = (s.role || 'part') === 'cue';
    const sp = space(s);
    const st = s.start ?? s.left;
    const bls = [...s.barlines].sort((a, b) => mid(a) - mid(b));
    // what the bar images will include, above and below the staff
    out.push(`<polygon class="crop${isSel('sys', s.id) ? ' sel' : ''}" points="${strip(s, s.left, s.right, cropAbove(s), cropBelow(s))}"/>`);
    const cls = ['staff', s.auto ? 'auto' : '', cue ? 'cue' : '', isSel('sys', s.id) ? 'sel' : ''].join(' ');
    out.push(`<polygon class="${cls}" data-t="sys" data-id="${s.id}" points="${strip(s, s.left, s.right)}"/>`);
    // dim what lies in no bar: clef and key before the music start, and
    // anything after the last bar line
    if (st > s.left) out.push(`<polygon class="outside" points="${strip(s, s.left, st, 0, 0, 2)}"/>`);
    const end = bls.length ? Math.max(bls[bls.length - 1].x0, bls[bls.length - 1].x1) : st;
    if (end < s.right) out.push(`<polygon class="outside" points="${strip(s, end, s.right, 0, 0, 4)}"/>`);
    out.push(`<line class="start" x1="${st * W}" x2="${st * W}" y1="${(topAt(s, st) - sp) * H}" y2="${(bottomAt(s, st) + sp) * H}"/>`);

    let firstOnLine = null;
    for (const b of bls) {
      const nb = S.byBarline.get(b.id);
      if (nb && !firstOnLine) firstOnLine = nb;
      const ya = topAt(s, mid(b)) - 1.2 * sp, yb = bottomAt(s, mid(b)) + 1.2 * sp;
      const cls = ['bl', b.auto ? 'auto' : '', isSel('bl', b.id) ? 'sel' : '', b.ends_movement || b.kind === 'final' ? 'end' : ''].join(' ');
      const pts = `x1="${xAt(b, s, ya) * W}" y1="${ya * H}" x2="${xAt(b, s, yb) * W}" y2="${yb * H}"`;
      out.push(`<line class="${cls}" ${pts}/>`);
      out.push(`<line class="hit" data-t="bl" data-id="${b.id}" ${pts}/>`);
      // this bar has its own crop: draw it
      if (b.above != null || b.below != null) {
        const qd = barQuad(s, nb ? nb.left : null, b).map(([x, y]) => `${x * W},${y * H}`);
        out.push(`<polygon class="barcrop" points="${qd.join(' ')}"/>`);
      }
      // repeat dots in the 2nd and 3rd spaces, on the repeated side
      const sides = { repeat_end: [-1], repeat_start: [1], repeat_both: [-1, 1] }[b.kind] || [];
      for (const side of sides) {
        for (const k of [1.5, 2.5]) {
          const y = topAt(s, mid(b)) + k * sp;
          out.push(`<circle class="rdot" cx="${(xAt(b, s, y) + side * 0.8 * sp * H / W) * W}" cy="${y * H}" r="${0.32 * sp * H}"/>`);
        }
      }
      const tag = [BARLINE_TAG[b.kind], b.ends_movement ? '■' : ''].filter(Boolean).join(' ');
      if (tag) out.push(`<text class="kindtag" x="${b.x1 * W}" y="${(bottomAt(s, mid(b)) + 2.4 * sp) * H}" font-size="${1.6 * sp * H}">${esc(tag)}</text>`);
      if (nb && !cue) {
        const xl = nb.left ? mid(nb.left) : st;
        const xm = (xl + mid(b)) / 2;
        const first = nb.bar === 1 || (nb.bar === 0 && nb.count === 0);
        const label = (first ? nb.movement + ': ' : '') + barLabel(nb);
        out.push(`<text class="barno${first ? ' mvt' : ''}" x="${xm * W}" y="${(topAt(s, xm) - 0.8 * sp) * H}" font-size="${1.9 * sp * H}">${esc(label)}</text>`);
        // Structure.ily expects a repeat sign here and there isn't one
        if (repeatEnds(nb.movement).includes(lastBarOf(nb)) && !['repeat_end', 'repeat_both'].includes(b.kind)) {
          out.push(`<text class="hint" x="${b.x1 * W}" y="${(bottomAt(s, mid(b)) + 3.8 * sp) * H}" font-size="${1.5 * sp * H}">repeat expected?</text>`);
        }
      }
    }
    // the first bar's number before the staff, as in a printed part
    if (firstOnLine && !cue) {
      out.push(`<text class="lineno" x="${s.left * W - 0.8 * sp * H}" y="${(topAt(s, s.left) + 2 * sp) * H}" font-size="${2.4 * sp * H}">${esc(firstOnLine.bar)}</text>`);
    }
  }
  for (const m of page.marks) {
    const cls = `mark${isSel('mark', m.id) ? ' sel' : ''}`;
    out.push(`<rect class="${cls}" data-t="mark" data-id="${m.id}" x="${m.x * W}" y="${m.y * H}" width="${m.w * W}" height="${m.h * H}"/>`);
    const label = m.text || m.kind;
    out.push(`<text class="marklabel" x="${m.x * W}" y="${m.y * H - 4 * u}" font-size="${13 * u}">${esc(label)}</text>`);
  }

  // handles for the selection, drawn last so they sit on top
  const item = find(sel);
  const circle = (h, x, y, title) => `<circle class="handle h-${h.replace(/\d/, '')}" data-h="${h}" cx="${x * W}" cy="${y * H}" r="${r}"><title>${title}</title></circle>`;
  const label = (x, y, text, cls = '') => `<text class="handlelabel ${cls}" x="${x * W + 1.6 * r}" y="${y * H + 0.5 * r}" font-size="${11 * u}">${text}</text>`;
  if (item && sel.t === 'bl') {
    const s = systemOf(item);
    out.push(circle('x0', item.x0, topAt(s, mid(item)), 'top end'));
    out.push(circle('x1', item.x1, bottomAt(s, mid(item)), 'bottom end'));
  } else if (item && sel.t === 'sys') {
    const s = item, sp = space(s), w = s.right - s.left;
    const st = s.start ?? s.left;
    const at = (f) => s.left + w * f;
    out.push(circle('top', at(1 / 8), topAt(s, at(1 / 8)), 'top line'));
    out.push(circle('bottom', at(1 / 8), bottomAt(s, at(1 / 8)), 'bottom line'));
    out.push(circle('left', s.left, (topAt(s, s.left) + bottomAt(s, s.left)) / 2, 'left end'));
    out.push(circle('right', s.right, (topAt(s, s.right) + bottomAt(s, s.right)) / 2, 'right end'));
    out.push(`<rect class="handle h-start" data-h="start" x="${st * W - r}" y="${(bottomAt(s, st) + sp) * H - r}" width="${2 * r}" height="${2 * r}"><title>music start: after clef, key and time signature</title></rect>`);
    // bend: drag these up or down where the staff rises or falls
    for (let i = 0; i < 5; i++) {
      const x = at(i / 4) * W, y = topAt(s, at(i / 4)) * H;
      out.push(`<rect class="handle bend" data-h="bend${i}" x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" transform="rotate(45 ${x} ${y})"><title>bend: drag to follow the staff</title></rect>`);
    }
    out.push(circle('above', at(3 / 8), topAt(s, at(3 / 8)) - cropAbove(s) * sp, 'crop above the staff'));
    out.push(circle('below', at(3 / 8), bottomAt(s, at(3 / 8)) + cropBelow(s) * sp, 'crop below the staff'));
    // the crop handles take the dashed band's green, with a dot to show it
    for (const y of [topAt(s, at(3 / 8)) - cropAbove(s) * sp, bottomAt(s, at(3 / 8)) + cropBelow(s) * sp]) {
      out.push(`<circle class="cropdot" cx="${at(3 / 8) * W}" cy="${y * H}" r="${0.45 * r}"/>`);
      out.push(label(at(3 / 8), y, 'crop', 'croplabel'));
    }
    out.push(label(at(1 / 8), topAt(s, at(1 / 8)), 'staff'));
    out.push(label(st, bottomAt(s, st) + sp, 'start'));
  } else if (item && sel.t === 'mark') {
    out.push(circle('br', item.x + item.w, item.y + item.h, 'resize'));
  } else if (item && sel.t === 'page') {
    item.points.forEach(([x, y], i) => out.push(circle(`c${i}`, x, y, 'page corner')));
  }
  overlay.innerHTML = out.join('');
}

function options(list, value, names = {}, blank = false) {
  return (blank ? `<option value="">—</option>` : '') +
    list.map((v) => `<option value="${v}"${v === value ? ' selected' : ''}>${esc(names[v] || v)}</option>`).join('');
}

function renderMeta() {
  const { source: s, display: d } = S.info;
  const rows = [
    ['Siglum', s.siglum], ['Shelfmark', s.shelfmark],
    ['Work', d.work || (s.gerard ? `G ${s.gerard}` : '')],
    ['RISM', d.rism_url ? `<a href="${esc(d.rism_url)}" target="_blank">${esc(s.rism)}</a>` : esc(s.rism)],
    ['Online', d.online ? `<a href="${esc(d.online)}" target="_blank">${esc(d.online_label || 'link')}</a>` : esc(d.online_label || '')],
    ['Bars from', esc(S.info.structure || 'no Structure.ily found')],
  ];
  $('#meta').innerHTML = '<dl>' + rows.filter((r) => r[1]).map(([k, v]) =>
    `<dt>${k}</dt><dd>${k === 'RISM' || k === 'Online' || k === 'Bars from' ? v : esc(v)}</dd>`).join('') + '</dl>' +
    (d.description ? `<p class="desc">${esc(d.description)}</p>` : '');
}

// The toolbar button shows whether this page is done: red until reviewed,
// then green. Clicking a reviewed page's button takes the review back.
function renderReviewButton() {
  const btn = $('#review');
  const page = pg();
  const done = page?.status === 'reviewed';
  btn.classList.toggle('done', done);
  btn.classList.toggle('todo', !!page && !done);
  btn.disabled = !page || !!S.readonly;
  btn.textContent = done ? '✓ Reviewed' : 'Not reviewed · mark ⏎';
  btn.title = done ? 'This page is reviewed. Click to mark it not reviewed.'
    : 'Mark this page reviewed and go to the next (Enter)';
}

function renderPageForm() {
  const page = pg();
  $('#pagenum').textContent = S.page;
  const st = $('#pagestatus');
  st.textContent = page ? page.status : 'not labeled';
  st.className = 'pill ' + (page ? page.status : '');
  const dis = !page || !!S.readonly;
  for (const id of ['#f-kind', '#f-part', '#f-clef', '#f-notes']) $(id).disabled = dis;
  if (!page) return;
  $('#f-kind').innerHTML = options(PAGE_KINDS, page.kind);
  $('#f-part').innerHTML = options(PARTS, page.part, PART_NAMES, true);
  $('#f-clef').innerHTML = options(CLEFS, page.clef, {}, true);
  if (document.activeElement !== $('#f-notes')) $('#f-notes').value = page.notes || '';
}

function renderInspector() {
  const el = $('#inspector');
  const item = find(S.sel);
  if (!item) {
    el.innerHTML = `<h2>Selection</h2><p class="muted">Click a staff, bar line or mark to edit it.</p>
      <p class="muted">To add a bar line, hold <b>b</b> and click where it goes, or double-click on the staff.
      Hold <b>s</b> and click to add a staff; hold <b>m</b> and drag a box around a marking.</p>`;
    return;
  }
  const dis = S.readonly ? ' disabled' : '';
  if (S.sel.t === 'page') {
    el.innerHTML = `<h2>Page corners ${item.auto ? '<span class="pill auto">auto</span>' : ''}</h2>
      <p class="muted">Drag the four corners onto the corners of the paper. They're saved with the bars,
      for cropping and straightening the page. Delete (d) removes them.</p>
      <button data-act="reset-corners"${S.readonly ? ' disabled' : ''}>Reset to detected</button>
      <p class="muted">Re-detect keeps corners you've moved; this replaces them (⌘Z undoes it).</p>`;
    return;
  }
  if (S.sel.t === 'bl') {
    const nb = S.byBarline.get(item.id);
    const what = nb ? `Ends ${PART_NAMES[nb.part] || nb.part} ${nb.movement}, bar ${barLabel(nb)}` : 'Not counted (page isn’t music or has no part)';
    el.innerHTML = `<h2>Bar line ${item.auto ? '<span class="pill auto">auto</span>' : ''}</h2>
      <p>${esc(what)}</p>
      <label>Kind <select data-f="kind"${dis}>${options(BARLINE_KINDS, item.kind)}</select></label>
      <label>Bars it ends <input data-f="bar_count" type="number" min="0" step="1" value="${item.bar_count ?? 1}"${dis}></label>
      <p class="muted">2+ for a multi-bar rest; 0 for a pickup.</p>
      <label class="check"><input data-f="ends_movement" type="checkbox"${item.ends_movement ? ' checked' : ''}${dis}> Movement ends here</label>
      <p class="muted">This bar's crop, in staff spaces (blank: the staff's ${cropAbove(systemOf(item))} / ${cropBelow(systemOf(item))}):</p>
      <label>Above <input data-f="bar_above" type="number" min="0" step="0.5" value="${item.above ?? ''}"${dis}></label>
      <label>Below <input data-f="bar_below" type="number" min="0" step="0.5" value="${item.below ?? ''}"${dis}></label>`;
  } else if (S.sel.t === 'sys') {
    el.innerHTML = `<h2>Staff ${item.auto ? '<span class="pill auto">auto</span>' : ''}</h2>
      <p>${item.barlines.length} bar lines</p>
      <label>Role <select data-f="role"${dis}>${options(['part', 'cue'], item.role || 'part', { part: 'part (counted)', cue: 'cue staff (not counted)' })}</select></label>
      <button data-act="trim"${dis}${item.barlines.length ? '' : ' disabled'}>End at last bar line</button>
      <label>Crop above (staff spaces) <input data-f="above" type="number" min="0" step="0.5" value="${cropAbove(item)}"${dis}></label>
      <label>Crop below (staff spaces) <input data-f="below" type="number" min="0" step="0.5" value="${cropBelow(item)}"${dis}></label>
      <p class="muted">The dashed band is what each bar's image includes; drag its round handles or set it here.
      The square handle under the staff is where the music starts: after the clef, key and time signature.
      The diamonds on the top line bend the staff to follow the page.</p>`;
  } else {
    el.innerHTML = `<h2>Mark</h2>
      <label>Kind <select data-f="kind"${dis}>${options(MARK_KINDS, item.kind)}</select></label>
      <label>Text <input data-f="text" value="${esc(item.text || '')}" placeholder="e.g. dolcis."${dis}></label>
      <label>Note <textarea data-f="note" rows="3"${dis}>${esc(item.note || '')}</textarea></label>`;
  }
}

function renderPages() {
  const byPage = {};
  for (const nb of S.bars) (byPage[nb.page] ||= []).push(nb);
  const items = [];
  for (let n = 1; n <= S.numPages; n++) {
    const p = S.doc?.pages[n];
    let what = '<span class="muted">not labeled</span>';
    if (p) {
      what = p.kind === 'music' ? esc(p.part || 'no part') : esc(p.kind) + (p.part ? ' · ' + esc(p.part) : '');
      const bs = byPage[n];
      if (bs) {
        const runs = [];
        for (const b of bs) {
          const last = runs[runs.length - 1];
          if (last && last.mvt === b.movement) last.to = b.bar + Math.max(b.count, 1) - 1;
          else runs.push({ mvt: b.movement, from: b.bar, to: b.bar + Math.max(b.count, 1) - 1 });
        }
        what += ' · ' + runs.map((r) => `${r.mvt} ${r.from}–${r.to}`).join(', ');
      }
    }
    items.push(`<li data-page="${n}" class="${n === S.page ? 'current' : ''}"><span class="dot ${p ? p.status : ''}"></span><span class="n">${n}</span><span class="what">${what}</span></li>`);
  }
  $('#pages').innerHTML = items.join('');
  $('#pages li.current')?.scrollIntoView({ block: 'nearest' });
}

// Counted vs expected bars per part and movement, plus repeat positions.
function renderCounts() {
  const exp = S.info?.expected || {};
  const runs = {};
  for (const nb of S.bars) {
    const r = (runs[nb.part] ||= {})[nb.movement] ||= { bars: 0, repeats: [], pickup: false, ended: false };
    r.bars += nb.count;
    if (nb.count === 0 && nb.bar === 0) r.pickup = true;
    if (['repeat_end', 'repeat_both'].includes(nb.right.kind)) r.repeats.push(nb.bar + Math.max(nb.count, 1) - 1);
    if (nb.right.ends_movement) r.ended = true;
  }
  // tempo marks: each belongs to the first bar of the nearest staff below it
  const tempos = {};
  for (const [n, page] of Object.entries(S.doc?.pages || {})) {
    for (const m of page.marks || []) {
      if (m.kind !== 'tempo' || !m.text) continue;
      const cy = m.y + m.h / 2;
      const nb = S.bars.filter((b) => b.page === +n && b.system.top > cy).sort((a, b) => a.system.top - b.system.top)[0];
      if (nb) ((tempos[nb.part] ||= {})[nb.movement] ||= []).push(m.text);
    }
  }
  const warnings = [];
  const rows = [];
  for (const part of PARTS.filter((p) => runs[p])) {
    rows.push(`<tr><td colspan="3" class="part">${esc(PART_NAMES[part])}</td></tr>`);
    const mvts = new Set([...Object.keys(exp), ...Object.keys(runs[part])]);
    for (const m of [...mvts].sort((a, b) => ROMAN.indexOf(a) - ROMAN.indexOf(b))) {
      const r = runs[part][m];
      const e = exp[m];
      const counted = r ? r.bars : 0;
      const cls = !e ? '' : counted === e.total ? 'ok' : (r && r.ended) ? 'bad' : '';
      rows.push(`<tr><td>${m}</td><td class="${cls}">${counted}</td><td class="muted">${e ? '/ ' + e.total : ''}</td></tr>`);
      const marked = tempos[part]?.[m] || [];
      if (marked.length || e?.tempos?.length) {
        const txt = (marked.length ? `<i>${esc(marked.join(' · '))}</i>` : '') +
          (e?.tempos?.length ? ` <span class="muted">(expected ${esc(e.tempos.join(' · '))})</span>` : '');
        rows.push(`<tr><td></td><td colspan="2" class="tempo">${txt}</td></tr>`);
      }
      if (!e || !r) continue;
      if (r.ended && counted !== e.total) warnings.push(`${PART_NAMES[part]} ${m}: ${counted} bars counted, ${e.total} expected`);
      let cum = 0;
      const want = [];
      for (const seg of e.segments) { cum += seg.bars; if (seg.repeat) want.push(cum); }
      for (const at of r.repeats) {
        if (want.length && !want.includes(at)) warnings.push(`${PART_NAMES[part]} ${m}: repeat sign after bar ${at}, expected after ${want.join(' or ')}`);
      }
    }
  }
  $('#counts').innerHTML = rows.length ? `<table>${rows.join('')}</table>` : '<p class="muted">No bars yet.</p>';
  $('#warnings').innerHTML = warnings.length ? `<h2>Warnings</h2><ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul>` : '';
}

// ------------------------------------------------------------------ bar detail view
// The selected bar, enlarged, with every staff line and space named for the clef.

function pitchName(clef, step) {
  const [l, o] = CLEF_BOTTOM[clef] || CLEF_BOTTOM.treble;
  const t = o * 7 + l + step;
  return 'CDEFGAB'[((t % 7) + 7) % 7] + Math.floor(t / 7);
}

function renderDetail() {
  const box = $('#detail');
  box.hidden = !S.detail;
  if (!S.detail) return;
  const cv = $('#detailcanvas');
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const cw = cv.clientWidth, ch = cv.clientHeight;
  cv.width = cw * dpr; cv.height = ch * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, cw, ch);

  const view = detailView();
  if (!view || !S.imgEl) {
    $('#detaillabel').textContent = 'Select a bar line, staff, mark or the page corners to see exactly what it covers.';
    return;
  }
  $('#detaillabel').textContent = view.label;

  // each row's pieces sit side by side, each straightened into a rectangle
  const len = (p, q) => Math.hypot(q[0] - p[0], q[1] - p[1]);
  const rows = view.rows.map((row) => row.map((q) => q.map(([x, y]) => [x * S.W, y * S.H])));
  const widthOf = ([tl, tr, br, bl]) => (len(tl, tr) + len(bl, br)) / 2;
  const heightOf = ([tl, tr, br, bl]) => (len(tl, bl) + len(tr, br)) / 2;
  const srcW = Math.max(...rows.map((r) => r.reduce((a, q) => a + widthOf(q), 0)));
  const srcH = Math.max(...rows.flat().map(heightOf));
  const gutter = view.staff ? 44 : 8, rowGap = 10;
  const scale = Math.min((ch - 8 - rowGap * (rows.length - 1)) / (srcH * rows.length), (cw - 2 * gutter) / srcW);
  const dh = srcH * scale;
  rows.forEach((row, ri) => {
    const dy = 4 + ri * (dh + rowGap);
    let x = gutter;
    for (const q of row) {
      const w = widthOf(q) * scale;
      drawQuad(ctx, S.imgEl, q, [x, dy, w, dh]);
      x += w;
    }
    ctx.strokeStyle = '#999';
    ctx.lineWidth = 1;
    ctx.strokeRect(gutter - 0.5, dy - 0.5, x - gutter + 1, dh + 1);
    if (view.staff) pitchGuides(ctx, view.staff, gutter, dy, x - gutter, dh);
  });
}

// pitch names for every staff line and space, for the page's clef
function pitchGuides(ctx, { above, below, clef }, dx, dy, dw, dh) {
  const lineGap = dh / (above + 4 + below);
  if (lineGap < 5) return;  // too small to read
  const yBottom = dy + (above + 4) * lineGap;
  ctx.font = `${Math.min(12, Math.max(8, lineGap * 0.9))}px -apple-system, sans-serif`;
  ctx.textBaseline = 'middle';
  for (let step = -15; step <= 23; step++) {
    const y = yBottom - step * lineGap / 2;
    if (y < dy - 1 || y > dy + dh + 1) continue;
    const isLine = step % 2 === 0;
    if (lineGap < 14 && !isLine) continue;  // crowded: lines only
    ctx.fillStyle = isLine ? '#b71c1c' : '#1565c0';
    const name = pitchName(clef, step);
    ctx.textAlign = 'right'; ctx.fillText(name, dx - 6, y);
    ctx.textAlign = 'left'; ctx.fillText(name, dx + dw + 6, y);
    if (!isLine) {
      ctx.strokeStyle = 'rgba(21,101,192,.35)';
      ctx.setLineDash([3, 5]);
      ctx.beginPath(); ctx.moveTo(dx, y); ctx.lineTo(dx + dw, y); ctx.stroke();
      ctx.setLineDash([]);
    }
  }
}

// What the detail view shows for the selection: quads (page fractions,
// TL TR BR BL) laid side by side, a label, and staff info for pitch names.
function detailView() {
  const item = find(S.sel);
  if (!item) return null;
  const page = pg();
  const clef = page.clef || 'treble';
  if (S.sel.t === 'bl') {
    // exactly the bar's crop (barQuad, as exported)
    const s = systemOf(item);
    const nb = S.byBarline.get(item.id);
    const sorted = [...s.barlines].sort((p, q) => mid(p) - mid(q));
    const prev = sorted[sorted.indexOf(item) - 1] || null;
    return {
      rows: [[barQuad(s, prev, item)]],
      label: (nb ? `${PART_NAMES[nb.part] || nb.part} ${nb.movement}, bar ${barLabel(nb)} · ` : '') +
        `${clef} clef · exactly the exported crop`,
      staff: { above: cropAbove(s, item), below: cropBelow(s, item), clef },
    };
  }
  if (S.sel.t === 'sys') {
    // the whole staff's crop band, straightened piece by piece along its
    // bend, and wrapped onto as many rows as fill the panel best
    const s = item, sp = space(s), a = cropAbove(s), b = cropBelow(s);
    const cv = $('#detailcanvas');
    const longW = (s.right - s.left) * S.W, tallH = (4 + a + b) * sp * S.H;
    let k = 1, best = 0;
    for (let n = 1; n <= 8; n++) {
      const sc = Math.min((cv.clientHeight - 8 - 10 * (n - 1)) / (tallH * n), (cv.clientWidth - 88) / (longW / n));
      if (sc > best) { best = sc; k = n; }
    }
    const nb = s.bend?.length > 1 ? s.bend.length - 1 : 1;
    const bendXs = Array.from({ length: nb + 1 }, (_, i) => s.left + (s.right - s.left) * i / nb);
    const piece = (x0, x1) => [[x0, topAt(s, x0) - a * sp], [x1, topAt(s, x1) - a * sp], [x1, bottomAt(s, x1) + b * sp], [x0, bottomAt(s, x0) + b * sp]];
    const rows = [];
    for (let r = 0; r < k; r++) {
      const r0 = s.left + (s.right - s.left) * r / k, r1 = s.left + (s.right - s.left) * (r + 1) / k;
      const cuts = [r0, ...bendXs.filter((x) => x > r0 && x < r1), r1];
      rows.push(cuts.slice(0, -1).map((x, i) => piece(x, cuts[i + 1])));
    }
    return { rows, label: `Staff, with its crop band (${a} / ${b} staff spaces) · ${clef} clef${k > 1 ? ` · wrapped onto ${k} rows` : ''}`, staff: { above: a, below: b, clef } };
  }
  if (S.sel.t === 'mark') {
    const m = item;
    return {
      rows: [[[[m.x, m.y], [m.x + m.w, m.y], [m.x + m.w, m.y + m.h], [m.x, m.y + m.h]]]],
      label: `Mark (${m.kind})${m.text ? ': ' + m.text : ''} · exactly its box`,
    };
  }
  if (S.sel.t === 'page') {
    return { rows: [[item.points]], label: 'The page inside its corners, straightened' };
  }
  return null;
}

// Draw the image area inside quad [TL, TR, BR, BL] (image px) into the
// rectangle [x, y, w, h], in vertical strips of two triangles, each mapped
// with an affine transform. Close enough to the build's warp for a preview.
function drawQuad(ctx, img, quad, [x, y, w, h], strips = 12) {
  const [tl, tr, br, bl] = quad;
  if (tl[1] === tr[1] && bl[1] === br[1] && tl[0] === bl[0] && tr[0] === br[0]) {
    ctx.drawImage(img, tl[0], tl[1], tr[0] - tl[0], bl[1] - tl[1], x, y, w, h);  // a plain rectangle
    return;
  }
  const lerp = (p, q, t) => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
  for (let i = 0; i < strips; i++) {
    const t0 = i / strips, t1 = (i + 1) / strips;
    const s = [lerp(tl, tr, t0), lerp(tl, tr, t1), lerp(bl, br, t1), lerp(bl, br, t0)];
    // a hair of overlap hides seams between strips
    const x0 = x + w * t0 - 0.5, x1 = x + w * t1 + 0.5;
    const d = [[x0, y], [x1, y], [x1, y + h], [x0, y + h]];
    for (const [a, b, c] of [[0, 1, 2], [0, 2, 3]]) {
      triangle(ctx, img, [s[a], s[b], s[c]], [d[a], d[b], d[c]]);
    }
  }
}

function triangle(ctx, img, [[x0, y0], [x1, y1], [x2, y2]], [[u0, v0], [u1, v1], [u2, v2]]) {
  const den = x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1);
  if (!den) return;
  const a = (u0 * (y1 - y2) + u1 * (y2 - y0) + u2 * (y0 - y1)) / den;
  const b = (v0 * (y1 - y2) + v1 * (y2 - y0) + v2 * (y0 - y1)) / den;
  const c = (u0 * (x2 - x1) + u1 * (x0 - x2) + u2 * (x1 - x0)) / den;
  const d = (v0 * (x2 - x1) + v1 * (x0 - x2) + v2 * (x1 - x0)) / den;
  const e = (u0 * (x1 * y2 - x2 * y1) + u1 * (x2 * y0 - x0 * y2) + u2 * (x0 * y1 - x1 * y0)) / den;
  const f = (v0 * (x1 * y2 - x2 * y1) + v1 * (x2 * y0 - x0 * y2) + v2 * (x0 * y1 - x1 * y0)) / den;
  // clip to the triangle grown by about a pixel, so neighbours overlap and
  // no hairline seam shows between them
  const cx = (u0 + u1 + u2) / 3, cy = (v0 + v1 + v2) / 3;
  const grow = ([u, v]) => { const d = Math.hypot(u - cx, v - cy) || 1; return [u + (u - cx) / d, v + (v - cy) / d]; };
  const [[p0, q0], [p1, q1], [p2, q2]] = [[u0, v0], [u1, v1], [u2, v2]].map(grow);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(p0, q0); ctx.lineTo(p1, q1); ctx.lineTo(p2, q2); ctx.closePath();
  ctx.clip();
  ctx.transform(a, b, c, d, e, f);
  ctx.drawImage(img, 0, 0);
  ctx.restore();
}

// ------------------------------------------------------------------ editing actions

function systemAt(y, x = S.mouse.x) {
  const page = pg();
  if (!page || !page.systems.length) return null;
  let best = null, bestD = Infinity;
  for (const s of page.systems) {
    const t = topAt(s, x), b = bottomAt(s, x);
    const d = y < t ? t - y : y > b ? y - b : 0;
    if (d < bestD) { best = s; bestD = d; }
  }
  return bestD < 4 * space(best) ? best : null;
}

function addBarline() {
  const s = systemAt(S.mouse.y);
  if (!s) { banner('Click on a staff to add a bar line.'); setTimeout(() => banner(null), 1500); return; }
  // clicking right on an existing bar line selects it instead of stacking a duplicate
  const near = s.barlines.find((b) => Math.abs(xAt(b, s, S.mouse.y) - S.mouse.x) < 0.4 * space(s) * S.H / S.W);
  if (near) { S.sel = { t: 'bl', id: near.id }; renderAll(); return; }
  mutate((page) => {
    const b = newBarline(page, s, { x0: S.mouse.x, x1: S.mouse.x }, false);
    S.sel = { t: 'bl', id: b.id };
  });
}

function addSystem() {
  mutate((page) => {
    const ss = page.systems;
    const med = (f) => { const v = ss.map(f).sort((a, b) => a - b); return v[Math.floor(v.length / 2)]; };
    const h = ss.length ? med((s) => s.bottom - s.top) : 0.03;
    const left = ss.length ? med((s) => s.left) : 0.05;
    const right = ss.length ? med((s) => s.right) : 0.95;
    const start = ss.length ? med((s) => (s.start ?? s.left) - s.left) + left : left;
    const top = clamp(S.mouse.y - h / 2, 0, 1 - h);
    const s = { id: nextId(page, `p${S.page}s`), top, bottom: top + h, left, right, start, auto: false, barlines: [] };
    ss.push(s);
    S.sel = { t: 'sys', id: s.id };
  });
}

// A mark covers the box dragged out with m held (or after + Mark); a plain
// click makes a small default box there.
function addMark(box = null) {
  const b = box || { x: clamp(S.mouse.x - 0.02, 0, 0.96), y: clamp(S.mouse.y - 0.01, 0, 0.98), w: 0.04, h: 0.02 };
  mutate((page) => {
    const m = { id: nextId(page, `p${S.page}m`), ...b, kind: 'text', text: '', note: '' };
    page.marks.push(m);
    S.sel = { t: 'mark', id: m.id };
  });
  if (!S.held) $('#inspector [data-f="text"]')?.focus();  // with m held, key repeats would type into it
}

function deleteSelection() {
  const item = find(S.sel);
  if (!item) return;
  const sel = S.sel;
  mutate((page) => {
    // remember what was deleted, so re-detection doesn't bring it back
    if (sel.t === 'mark') page.marks = page.marks.filter((m) => m !== item);
    else if (sel.t === 'page') delete page.corners;
    else if (sel.t === 'sys') {
      page.systems = page.systems.filter((s) => s !== item);
      (page.rejected_staves ||= []).push((item.top + item.bottom) / 2);
    } else {
      const s = systemOf(item, page);
      s.barlines = s.barlines.filter((b) => b !== item);
      (s.rejected ||= []).push(mid(item));
    }
    S.sel = null;
  });
}

function nudge(dx, dy, topOnly) {
  const item = find(S.sel);
  if (!item) return;
  const t = S.sel.t;
  if (t === 'page') return;
  mutate(() => {
    if (t === 'bl') { item.x0 += dx; if (!topOnly) item.x1 += dx; item.auto = false; }
    else if (t === 'sys') { item.top += dy; item.bottom += dy; item.left += dx; item.right += dx; if (item.start != null) item.start += dx; item.auto = false; }
    else { item.x += dx; item.y += dy; }
  });
}

function setBarline(fn) {
  const item = find(S.sel);
  if (!item || S.sel.t !== 'bl') return;
  mutate(() => { fn(item); item.auto = false; });
}

function cycleBarline(dir) {
  const order = numberBars({ pages: { [S.page]: { ...pg(), kind: 'music', part: pg().part || 'x' } } }).map((nb) => nb.right.id);
  const page = pg();
  const all = order.length ? order : page.systems.flatMap((s) => s.barlines.map((b) => b.id));
  if (!all.length) return;
  const i = S.sel && S.sel.t === 'bl' ? all.indexOf(S.sel.id) : -1;
  S.sel = { t: 'bl', id: all[(i + dir + all.length) % all.length] };
  renderAll();
}

function markReviewedAndNext() {
  if (!pg() || S.readonly) return;
  mutate((page) => { page.status = 'reviewed'; }, { status: false });
  if (S.page < S.numPages) openPage(S.page + 1);
}

// ------------------------------------------------------------------ placing
// Hold b (bar line), s (staff) or m (mark) and click where it goes; or use
// a toolbar button, which places one on the next click. The cursor shows
// what will be placed.

const PLACE = { bl: addBarline, sys: addSystem, mark: addMark };
const PLACE_KEY = { b: 'bl', s: 'sys', m: 'mark' };

function setPlacing(kind) {
  S.placing = kind;
  svg.dataset.placing = kind || '';
  for (const btn of document.querySelectorAll('[data-place]')) btn.classList.toggle('on', btn.dataset.place === kind);
}

// ------------------------------------------------------------------ pointer

svg.addEventListener('pointerdown', (e) => {
  if (e.button !== 0 || !pg()) return;
  const p = toImage(e);
  const fx = p.x / S.W, fy = p.y / S.H;
  const t = e.target.dataset || {};
  svg.setPointerCapture(e.pointerId);

  // Double-click on a staff (or empty page) adds a bar line. Detected here
  // rather than with 'dblclick', which is lost when the first click redraws
  // the overlay under the pointer.
  const now = performance.now(), last = S.lastDown;
  S.lastDown = { t: now, x: e.clientX, y: e.clientY, target: t.t || (t.h ? 'handle' : '') };
  if (last && now - last.t < 400 && Math.hypot(e.clientX - last.x, e.clientY - last.y) < 6
      && !['bl', 'mark'].includes(last.target) && !S.readonly && !S.placing) {
    S.lastDown = null;
    S.mouse = { x: fx, y: fy };
    addBarline();
    return;
  }

  if ((S.placing || e.shiftKey) && !t.h && !S.readonly) {
    S.mouse = { x: fx, y: fy };
    const kind = S.placing || 'bl';
    if (!S.held) setPlacing(null);  // a toolbar button places one; a held key keeps going
    if (kind === 'mark') {  // drag out the box; the mark is made on release
      S.drag = { kind: 'draw', start: { x: fx, y: fy } };
      return;
    }
    PLACE[kind]();
    return;
  }
  if (t.h && S.sel) {
    S.drag = { kind: 'handle', h: t.h, start: { x: fx, y: fy }, moved: false };
  } else if (t.t === 'page') {
    S.sel = { t: 'page' };
    renderAll();
    S.drag = { kind: 'pan', sx: e.clientX, sy: e.clientY, view: { ...S.view }, moved: false, keepSel: true };
  } else if (t.t) {
    S.sel = { t: t.t, id: t.id };
    const item = find(S.sel);
    S.drag = { kind: 'move', start: { x: fx, y: fy }, orig: JSON.parse(JSON.stringify(item)), moved: false };
    renderAll();
  } else {
    S.drag = { kind: 'pan', sx: e.clientX, sy: e.clientY, view: { ...S.view }, moved: false };
  }
});

svg.addEventListener('pointermove', (e) => {
  const p = toImage(e);
  S.mouse = { x: p.x / S.W, y: p.y / S.H };
  const d = S.drag;
  if (!d) return;
  if (d.kind === 'draw') {
    const { W, H } = S;
    const x0 = Math.min(d.start.x, S.mouse.x), y0 = Math.min(d.start.y, S.mouse.y);
    const w = Math.abs(S.mouse.x - d.start.x), h = Math.abs(S.mouse.y - d.start.y);
    let r = overlay.querySelector('.drawing');
    if (!r) { r = document.createElementNS('http://www.w3.org/2000/svg', 'rect'); r.setAttribute('class', 'mark drawing'); overlay.appendChild(r); }
    r.setAttribute('x', x0 * W); r.setAttribute('y', y0 * H);
    r.setAttribute('width', w * W); r.setAttribute('height', h * H);
    return;
  }
  if (d.kind === 'pan') {
    const u = unit();
    const dx = (e.clientX - d.sx) * u, dy = (e.clientY - d.sy) * u;
    if (Math.abs(dx) + Math.abs(dy) > 2 * u) d.moved = true;
    setView({ ...d.view, x: d.view.x - dx, y: d.view.y - dy });
    return;
  }
  if (S.readonly) return;
  const item = find(S.sel);
  if (!item) return;
  if (!d.moved) {
    if (Math.hypot(S.mouse.x - d.start.x, S.mouse.y - d.start.y) * S.W < 2 * unit()) return;
    pushUndo();
    d.moved = true;
  }
  const mx = clamp(S.mouse.x, 0, 1), my = clamp(S.mouse.y, 0, 1);
  const dx = mx - d.start.x, dy = my - d.start.y;
  const t = S.sel.t;
  if (d.kind === 'move') {
    const o = d.orig;
    if (t === 'bl') { item.x0 = o.x0 + dx; item.x1 = o.x1 + dx; }
    else if (t === 'sys') {
      Object.assign(item, { top: o.top + dy, bottom: o.bottom + dy, left: o.left + dx, right: o.right + dx });
      if (o.start != null) item.start = o.start + dx;
    } else { item.x = o.x + dx; item.y = o.y + dy; }
  } else {
    const h = d.h;
    const w = item.right - item.left;
    const at = (f) => item.left + w * f;
    if (/^c\d$/.test(h)) item.points[+h[1]] = [mx, my];
    else if (h === 'x0') item.x0 = mx;
    else if (h === 'x1') item.x1 = mx;
    else if (h === 'top') item.top = Math.min(my - bendAt(item, at(1 / 8)), item.bottom - 0.004);
    else if (h === 'bottom') item.bottom = Math.max(my - bendAt(item, at(1 / 8)), item.top + 0.004);
    else if (h.startsWith('bend')) {
      if (!item.bend) item.bend = [0, 0, 0, 0, 0];
      item.bend[+h.slice(4)] = my - item.top;
    }
    else if (h === 'above') item.above = Math.max(0, Math.round((topAt(item, at(3 / 8)) - my) / space(item) * 2) / 2);
    else if (h === 'below') item.below = Math.max(0, Math.round((my - bottomAt(item, at(3 / 8))) / space(item) * 2) / 2);
    else if (h === 'left') setExtent(item, Math.min(mx, item.right - 0.01), item.right);
    else if (h === 'right') setExtent(item, item.left, Math.max(mx, item.left + 0.01));
    else if (h === 'start') item.start = clamp(mx, item.left, item.right);
    else if (h === 'br') { item.w = Math.max(0.005, mx - item.x); item.h = Math.max(0.005, my - item.y); }
  }
  if (t !== 'mark') item.auto = false;
  renumber();
  renderOverlay();
  if (S.detail) renderDetail();  // watch the crop change while dragging
});

svg.addEventListener('pointerup', () => {
  const d = S.drag;
  S.drag = null;
  if (!d) return;
  if (d.kind === 'draw') {
    const x0 = clamp(Math.min(d.start.x, S.mouse.x), 0, 1), y0 = clamp(Math.min(d.start.y, S.mouse.y), 0, 1);
    const w = Math.abs(clamp(S.mouse.x, 0, 1) - d.start.x), h = Math.abs(clamp(S.mouse.y, 0, 1) - d.start.y);
    // a drag of a few pixels is a click: default box
    const tiny = w * S.W < 4 * unit() || h * S.H < 4 * unit();
    addMark(tiny ? null : { x: x0, y: y0, w, h });
    return;
  }
  if (d.kind === 'pan') {
    if (!d.moved && S.sel && !d.keepSel) { S.sel = null; renderAll(); }
    return;
  }
  if (d.moved) { touchPage(); changed(); }
});

svg.addEventListener('wheel', (e) => {
  e.preventDefault();
  if (e.ctrlKey || e.metaKey) {
    const p = toImage(e);
    zoomAt(Math.exp(e.deltaY * 0.002), p.x, p.y);
  } else {
    const u = unit();
    setView({ ...S.view, x: S.view.x + e.deltaX * u, y: S.view.y + e.deltaY * u });
  }
}, { passive: false });

window.addEventListener('resize', () => { renderOverlay(); renderDetail(); });

// ------------------------------------------------------------------ keyboard

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    setPlacing(null);
    if (inField()) document.activeElement.blur();
    else { S.sel = null; renderAll(); }
    return;
  }
  if (inField()) return;
  // a clicked button keeps focus; don't let Enter or Space also press it
  if (document.activeElement?.tagName === 'BUTTON') document.activeElement.blur();
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key.toLowerCase() === 'z') {
    e.preventDefault();
    if (e.shiftKey) restore(S.redo, S.undo); else restore(S.undo, S.redo);
    return;
  }
  if (mod) return;
  const step = (e.shiftKey ? 10 : 1);
  const k = e.key;
  const handled = () => e.preventDefault();
  if (PLACE_KEY[k]) { handled(); if (!e.repeat) { S.held = k; setPlacing(PLACE_KEY[k]); } }
  else if (k === 'Delete' || k === 'Backspace' || k === 'd') { handled(); deleteSelection(); }
  else if (k === 'ArrowLeft' || k === 'ArrowRight') { handled(); nudge((k === 'ArrowLeft' ? -step : step) / S.W, 0, e.altKey); }
  else if (k === 'ArrowUp' || k === 'ArrowDown') { handled(); nudge(0, (k === 'ArrowUp' ? -step : step) / S.H); }
  else if (k === 'Tab') { handled(); cycleBarline(e.shiftKey ? -1 : 1); }
  else if (k >= '1' && k <= '6') { handled(); setBarline((b) => { b.kind = BARLINE_KINDS[+k - 1]; }); }
  else if (k === 'e') { handled(); setBarline((b) => { b.ends_movement = !b.ends_movement; }); }
  else if (k === 'z') { handled(); S.detail = !S.detail; renderDetail(); renderOverlay(); }
  else if (k === 'Enter') { handled(); markReviewedAndNext(); }
  else if (k === '.' || k === 'PageDown') { handled(); openPage(S.page + 1); }
  else if (k === ',' || k === 'PageUp') { handled(); openPage(S.page - 1); }
  else if (k === 'f') { handled(); fitPage(); }
  else if (k === 'w') { handled(); fitWidth(); }
  else if (k === '+' || k === '=') { handled(); zoomAt(1 / 1.25, S.mouse.x * S.W, S.mouse.y * S.H); }
  else if (k === '-') { handled(); zoomAt(1.25, S.mouse.x * S.W, S.mouse.y * S.H); }
  else if (k === '?') { handled(); $('#help').hidden = !$('#help').hidden; }
});

document.addEventListener('keyup', (e) => {
  if (S.held && e.key.toLowerCase() === S.held) {
    S.held = null;
    setPlacing(null);
    if (S.sel?.t === 'mark') $('#inspector [data-f="text"]')?.focus();
  }
});
window.addEventListener('blur', () => { if (S.held) { S.held = null; setPlacing(null); } });

// ------------------------------------------------------------------ form wiring

for (const btn of document.querySelectorAll('[data-place]')) {
  btn.onclick = () => setPlacing(S.placing === btn.dataset.place ? null : btn.dataset.place);
}

$('#source').addEventListener('change', (e) => loadSource(e.target.value));
$('#pages').addEventListener('click', (e) => { const li = e.target.closest('li'); if (li) openPage(+li.dataset.page); });
$('#prev').onclick = () => openPage(S.page - 1);
$('#next').onclick = () => openPage(S.page + 1);
$('#fit').onclick = fitPage;
$('#fitw').onclick = fitWidth;
$('#redetect').onclick = redetect;
$('#review').onclick = () => {
  if (pg()?.status === 'reviewed') mutate((p) => { p.status = 'edited'; }, { status: false });
  else markReviewedAndNext();
};
$('#helpbtn').onclick = () => { $('#help').hidden = !$('#help').hidden; };
$('#detailclose').onclick = () => { S.detail = false; renderDetail(); };

$('#pagestatus').onclick = () => {
  if (!pg() || S.readonly) return;
  mutate((p) => { p.status = p.status === 'reviewed' ? 'edited' : 'reviewed'; }, { status: false });
};
$('#f-kind').addEventListener('change', (e) => mutate((p) => { p.kind = e.target.value; }));
$('#f-part').addEventListener('change', (e) => mutate((p) => {
  p.part = e.target.value || null;
  p.clef = clefFor(S.page, p.part) || p.clef;
}));
$('#f-clef').addEventListener('change', (e) => mutate((p) => { p.clef = e.target.value || null; }));
$('#f-corners').onclick = () => {
  if (!pg() || S.readonly) return;
  if (!pg().corners) mutate((p) => { p.corners = { points: [[0.02, 0.02], [0.98, 0.02], [0.98, 0.98], [0.02, 0.98]], auto: false }; });
  S.sel = { t: 'page' };
  renderAll();
};
$('#f-notes').addEventListener('change', (e) => mutate((p) => { p.notes = e.target.value; }));

$('#inspector').addEventListener('click', (e) => {
  const act = e.target.dataset?.act;
  const item = find(S.sel);
  if (act === 'trim' && item && S.sel.t === 'sys') mutate(() => { trimToLastBarline(item); item.auto = false; });
  if (act === 'reset-corners') resetCorners();
});

$('#inspector').addEventListener('change', (e) => {
  const f = e.target.dataset.f;
  const item = find(S.sel);
  if (!f || !item) return;
  const t = S.sel.t;
  mutate(() => {
    if (f === 'bar_count') item.bar_count = Math.max(0, Math.round(+e.target.value || 0));
    else if (f === 'above' || f === 'below') item[f] = Math.max(0, +e.target.value || 0);
    else if (f === 'bar_above' || f === 'bar_below') {
      const k = f.slice(4);
      if (e.target.value === '') delete item[k]; else item[k] = Math.max(0, +e.target.value);
    }
    else if (f === 'ends_movement') item.ends_movement = e.target.checked;
    else if (f === 'role') { if (e.target.value === 'part') delete item.role; else item.role = e.target.value; }
    else item[f] = e.target.value;
    if (t !== 'mark') item.auto = false;
  });
});

loadSources().catch((e) => banner(`Could not load: ${e.message}`));
