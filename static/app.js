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
const MARK_KINDS = ['text', 'tempo', 'dynamic', 'stray', 'unclear', 'other', 'signature'];
// what a staff's start, or a signature mark, records as written (labels.py SIG_FIELDS)
const SIG_FIELDS = ['clef', 'key', 'time'];
const KEYS = [-7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7];  // flats < 0 < sharps
const keyName = (k) => (k === 0 ? 'no ♯/♭' : k > 0 ? `${k}♯` : `${-k}♭`);
const TIMES = ['2/4', '3/4', '4/4', '3/8', '6/8', '9/8', '12/8', '2/2', '3/2', 'C', 'C/'];
const sigValid = (f, v) => (f === 'clef' ? CLEFS.includes(v) : f === 'key' ? Number.isInteger(v) && v >= -7 && v <= 7
  : typeof v === 'string' && /^(\d+\/\d+|C|C\/)$/.test(v));
// "tenor · 2♯ · 2/4": what a staff's start or a signature mark records
const sigText = (o) => [o.clef, o.key != null ? keyName(o.key) : null, o.time].filter((v) => v != null && v !== '').join(' · ');
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];
// pitch of the bottom staff line: [letter index in CDEFGAB, octave]
const CLEF_BOTTOM = { treble: [2, 4], alto: [3, 3], tenor: [1, 3], bass: [4, 2] };

const $ = (s) => document.querySelector(s);

// small per-browser preferences (a closed panel stays closed); storage may be unavailable
function loadPref(key, fallback) {
  try { const v = localStorage.getItem('labeler.' + key); return v === null ? fallback : JSON.parse(v); }
  catch { return fallback; }
}
function savePref(key, value) {
  try { localStorage.setItem('labeler.' + key, JSON.stringify(value)); } catch { /* fine */ }
}
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
  detail: loadPref('detail', true),  // the detail view: open unless closed last time
  heldCrop: null,
  markTexts: [],       // [{text, n, kind}] used anywhere in the edition, most used first      // 'above' | 'below' while t / g is held: arrows move that crop edge
  handle: null,        // { h, for }: the handle the arrow keys move (clicked, highlighted)
  placing: null,       // 'bl' | 'sys' | 'mark': the next click on the page adds one
  held: null,          // the key being held down to place ('b', 's', 'm')
  loadToken: 0,
};
// Selecting anything forgets where a delete left Tab (S.tabFrom)
{
  let sel = S.sel;
  Object.defineProperty(S, 'sel', {
    get: () => sel,
    set: (v) => { sel = v; S.tabFrom = null; },
    enumerable: true,
  });
}

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

// Signatures (labels.py sig_changes / clefs_between, the authority): a
// staff's own clef, key or time is written at its start; a signature mark
// belongs to the staff nearest its centre (one on a cue staff changes only
// the cue), and counts from its centre or the bar line it starts at. The
// page's clef holds from its top until a change, and a change holds
// through later staves until the next.
// the staff a mark (a box) is on: the nearest to its centre
function markStaff(page, m) {
  const systems = page.systems || [];
  if (!systems.length) return null;
  const cx = m.x + m.w / 2, cy = m.y + m.h / 2;
  const dist = (s) => { const d = bendAt(s, cx); return Math.max(s.top + d - cy, 0, cy - s.bottom - d); };
  return systems.reduce((a, b) => (dist(b) < dist(a) || (dist(b) === dist(a) && b.top < a.top) ? b : a));
}

function sigChanges(page, field, { cue = false } = {}) {
  const out = [];
  const onCue = (s) => (s.role || 'part') !== 'part';
  for (const s of page.systems || []) {
    if (onCue(s) === cue && sigValid(field, s[field])) out.push([s, -Infinity, s[field]]);
  }
  for (const m of page.marks || []) {
    if (m.kind !== 'signature' || !sigValid(field, m[field])) continue;
    const s = markStaff(page, m);
    if (!s || onCue(s) !== cue) continue;
    const cx = m.x + m.w / 2;
    // a change written at the start of a bar governs the whole bar: its box
    // starting within its own width after a bar line (half that before)
    // counts from the bar line
    const at = (s.barlines || []).map(mid).filter((b) => b - m.w / 2 <= m.x && m.x <= b + m.w);
    out.push([s, at.length ? at.reduce((a, b) => (Math.abs(m.x - b) < Math.abs(m.x - a) ? b : a)) : cx, m[field]]);
  }
  return out.sort((a, b) => a[0].top - b[0].top || a[1] - b[1]);
}
const clefMarks = (page, opts) => sigChanges(page, 'clef', opts);

// the clefs in force on a counted staff from x0 to x1; x0 null: the line's
// first bar, which a clef before the music start governs from its beginning
function clefsBetween(page, system, x0, x1) {
  let marks = clefMarks(page);
  if (page.part === 'score') marks = marks.filter(([s]) => s === system);  // each staff its own instrument
  const start = x0 == null ? (system.start ?? system.left) : x0;
  let now = page.clef;
  for (const [s, x, clef] of marks) {
    if ((s.top < system.top && s !== system) || (s === system && x <= start)) now = clef;
  }
  const out = now ? [now] : [];
  for (const [s, x, clef] of marks) {
    if (s === system && start < x && x < x1 && out[out.length - 1] !== clef) out.push(clef);
  }
  return out;
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
  // the music start moves with the left end (the clef and key move with it)
  if (s.start != null && left !== s.left) s.start = clamp(s.start + left - s.left, left, right);
  s.left = left;
  s.right = right;
}

// Clef and key take the same room on every line until the key changes,
// but reading where they end from the ink is unreliable across hands. So
// the editor fixes one line, and this carries its left end and music start
// to the lines below it: the left end at the same place on the page, the
// start too but snapped to the nearest clear paper (where the key
// signature ends). Lines above are left alone, so at
// a key change: fix that line and apply again. Backtested on KHM 602/603
// against the editor's starts: better than measuring from each line's
// left edge, whose detection is the weak part. One undo step.
async function applyStartToPage(src) {
  const n = S.page;
  const x = src.start ?? src.left;
  const below = pg().systems.filter((s) => s !== src && s.top > src.top && (s.role || 'part') === 'part');
  const snapped = await Promise.all(below.map(async (s) => {
    const params = `top=${topAt(s, x)}&bottom=${bottomAt(s, x)}&x=${x}`;
    try { return (await getJSON(`/api/snapstart?${q(S.pdf, n)}&${params}`)).x ?? x; }
    catch { return x; }
  }));
  if (n !== S.page) return;
  mutate(() => {
    below.forEach((s, i) => {
      if (src.left < s.right) setExtent(s, src.left, s.right);
      s.start = clamp(snapped[i], s.left, s.right);
      s.auto = false;
    });
    src.auto = false;
  });
}

// end a staff just after its last bar line: shortened if it runs on,
// lengthened if it stops short of it
function trimToLastBarline(s) {
  if (!s.barlines.length) return;
  const last = Math.max(...s.barlines.map((b) => Math.max(b.x0, b.x1)));
  const right = Math.min(1, last + 0.5 * space(s) * S.H / S.W);
  if (right > s.left) setExtent(s, s.left, right);
}

// x of a bar line at height y (page fractions), following its lean:
// x0 is where it crosses the top staff line, x1 the bottom one
function xAt(b, s, y) {
  const t = topAt(s, mid(b)), h = s.bottom - s.top;
  return h > 0 ? b.x0 + (b.x1 - b.x0) * (y - t) / h : b.x0;
}

// the top and bottom edges ("x,y" screen points, left to right) of a
// stretch of a staff from x0 to x1, widened by `above` / `below` staff
// spaces, following its bend
function edges(s, x0, x1, above = 0, below = 0, n = 12) {
  const sp = space(s);
  const xs = Array.from({ length: n + 1 }, (_, i) => x0 + (x1 - x0) * i / n);
  return { top: xs.map((x) => `${x * S.W},${(topAt(s, x) - above * sp) * S.H}`),
           bot: xs.map((x) => `${x * S.W},${(bottomAt(s, x) + below * sp) * S.H}`) };
}
// that stretch as polygon points
function strip(s, x0, x1, above = 0, below = 0, n = 12) {
  const e = edges(s, x0, x1, above, below, n);
  return e.top.concat(e.bot.reverse()).join(' ');
}
// its outline as a path: the top and bottom edges, the left end, and the
// right end only when no bar line is within a staff space of it (there
// it would read as a second stroke beside the bar line)
function outline(s, x0, x1, above = 0, below = 0) {
  const e = edges(s, x0, x1, above, below);
  const near = s.barlines.some((b) => Math.abs(mid(b) - x1) < space(s) * S.H / S.W);
  const last = e.top.length - 1;
  return `M${e.top.join(' L')} M${e.bot.join(' L')} M${e.top[0]} L${e.bot[0]}`
    + (near ? '' : ` M${e.top[last]} L${e.bot[last]}`);
}

// Bars much wider or narrower than their line's typical bar: a missed bar
// line merges two bars (about twice as wide), an extra one splits one.
// Widths vary with how many notes a bar holds, so it's a hint. Thresholds
// from the reviewed pages of KHM 602/603 (correct bars): 2.2% flagged
// anyway; a removed bar line flagged 57% of the time. A line's first bar
// is left out (its width depends on the music start), as are bars that
// stand for several bars or none. Music after the last bar line more than
// half a typical bar long (detection trims a blank end) suggests a missed
// final bar line. Two bar lines closer than ODD_STACKED staff spaces are
// one stroke labelled twice (an editor's bar line snapped onto a detected
// one): always an error, flagged even on reviewed pages.
const ODD_WIDE = 1.8, ODD_NARROW = 0.4, ODD_TAIL = 0.5, ODD_STACKED = 0.5;
// bar lines closer than this (page widths) are one stroke
const stackedGap = (s) => ODD_STACKED * space(s) * S.H / S.W;
function oddBars(s) {
  if ((s.role || 'part') !== 'part') return [];
  const bls = [...s.barlines].sort((a, c) => mid(a) - mid(c));
  const close = stackedGap(s);
  const bars = bls.slice(1).map((b, k) => ({ b, prev: bls[k], w: mid(b) - mid(bls[k]), one: (b.bar_count ?? 1) === 1, pos: k + 2 }));
  const stacked = bars.filter((x) => x.w < close)
    .map((x) => ({ barline: x.b, prev: x.prev, kind: 'stacked', ratio: 0, pos: x.pos }));
  const ws = bars.filter((x) => x.one && x.w >= close).map((x) => x.w).sort((a, c) => a - c);
  if (ws.length < 3) return stacked;
  const n = ws.length;
  const med = n % 2 ? ws[(n - 1) / 2] : (ws[n / 2 - 1] + ws[n / 2]) / 2;
  const out = stacked.concat(bars.filter((x) => x.one && x.w >= close && (x.w > ODD_WIDE * med || x.w < ODD_NARROW * med))
    .map((x) => ({ barline: x.b, prev: x.prev, kind: x.w > med ? 'wide' : 'narrow', ratio: x.w / med, pos: x.pos })));
  const last = bls[bls.length - 1];
  const tail = s.right - Math.max(last.x0, last.x1);
  if (tail > ODD_TAIL * med) out.push({ barline: null, prev: last, kind: 'tail', ratio: tail / med, pos: bls.length + 1 });
  return out;
}

// The odd bars of the open page, once per redraw; on a reviewed page only
// stacked bar lines (the other flagged bars are just dense with notes).
function pageOddBars() {
  const page = pg();
  const key = `${S.pdf}:${S.page}:${S.version}:${S.W}x${S.H}`;
  if (S.oddCache?.key !== key) {
    const lines = page ? [...page.systems].sort((a, b) => a.top - b.top) : [];
    const keep = (o) => page.status !== 'reviewed' || o.kind === 'stacked';
    S.oddCache = { key, items: lines.flatMap((s, i) => oddBars(s).filter(keep).map((o) => ({ ...o, staff: s, line: i + 1 }))) };
  }
  return S.oddCache.items;
}

// bar numbers after which Structure.ily puts a repeat sign, per movement
// (a repeat in mid-bar ends the bar's first part; the part after it is a
// pickup, count 0, sharing the number: see repeatHere)
function repeatEnds(movement) {
  const e = S.info?.expected?.[movement];
  if (!e) return [];
  let cum = 0;
  const out = [];
  for (const seg of e.segments) { cum += seg.bars; if (seg.repeat) out.push(cum); }
  return out;
}
const lastBarOf = (nb) => nb.bar + Math.max(nb.count, 1) - 1;
// the numbered bar a bar line ends: none for a pickup (count 0), which
// shares the number before it (the rest of a bar split by a repeat in its
// middle, or a movement's upbeat)
const endsBar = (nb) => (nb.count === 0 ? null : nb.bar + nb.count - 1);
// does Structure.ily put a repeat sign at the end of this bar?
const repeatHere = (nb) => endsBar(nb) !== null && repeatEnds(nb.movement).includes(endsBar(nb));

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
  // each part's first bar of each movement: "part movement" -> bar
  S.firsts = new Map();
  for (const nb of S.bars) if (!S.firsts.has(nb.part + ' ' + nb.movement)) S.firsts.set(nb.part + ' ' + nb.movement, nb);
  // each page's lines, by their first bar: page -> [bar]
  S.lineFirsts = new Map();
  for (const nb of S.bars) if (!nb.left) (S.lineFirsts.get(nb.page) || S.lineFirsts.set(nb.page, []).get(nb.page)).push(nb);
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
  S.tabFrom = null;  // the deleted item may be back
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
  if (S.markTextIndex) renderMarkTexts();
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
    if (S.info && j.structure_offers) {  // a review may complete a movement
      const changed = JSON.stringify(S.info.structure_offers) !== JSON.stringify(j.structure_offers);
      S.info.structure_offers = j.structure_offers;
      if (changed) renderAll();
    }
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
  S.structureOpen = null;
  S.version = S.savedVersion = 0;
  S.conflict = false;
  S.undo = []; S.redo = [];
  if (S.readonly) banner(`Read-only: ${S.readonly}`);
  renumber();
  renderMeta();
  loadMarkTexts();
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

// a new page's clef at the top: the one in force at the end of the part's
// previous page (its clef marks included), else the part's usual clef
function clefFor(n, part) {
  const prev = previousPage(n, (p) => p.part === part && p.kind === 'music' && p.clef);
  if (!prev) return DEFAULT_CLEF[part] || null;
  const last = prev.systems.filter((s) => (s.role || 'part') === 'part').sort((a, b) => a.top - b.top).pop();
  return (last && part !== 'score' && clefsBetween(prev, last, last.right, Infinity).pop()) || prev.clef;
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

// The clef-and-key room (left edge to music start, in staff spaces) the
// editor set on their previous page of this part, if they've worked on
// it: lines after the first, median. Detection uses it to place each
// line's music start (it repeats from page to page until the key changes).
function roomFromPreviousPage(n) {
  let prev = null;
  for (let k = n - 1; k >= 1 && !prev; k--) {
    const p = S.doc.pages[k];
    // not opened yet: it might be the title page of a new part, so stop
    if (!p) return null;
    if (p.kind === 'title') return null;  // a new part starts: its clef and key may differ
    if (p.kind === 'music' && p.status !== 'auto') prev = p;
  }
  if (!prev) return null;
  const lines = prev.systems.filter((s) => (s.role || 'part') === 'part').sort((a, b) => a.top - b.top).slice(1);
  const rooms = lines.map((s) => ((s.start ?? s.left) - s.left) * S.W / (space(s) * S.H)).filter((r) => r > 1).sort((a, b) => a - b);
  return rooms.length ? rooms[Math.floor(rooms.length / 2)] : null;
}

async function autoLabel(n, token) {
  let systems = [], corners = null, look = null;
  const room = roomFromPreviousPage(n);
  try { ({ systems, corners, look } = await getJSON(`/api/detect?${q(S.pdf, n)}${room ? `&room=${room.toFixed(2)}` : ''}`)); }
  catch (e) { banner(`Detection failed on page ${n}: ${e.message}`); }
  if (token !== S.loadToken || S.doc.pages[n]) return;
  // Music: staves with bar lines. Otherwise a blank page has no dark ink,
  // a photographer's colour chart has strong colour (both: no part, no
  // clef), and anything else is a title page, which keeps the part so the
  // editor can set the next part there and have later pages inherit it.
  const music = systems.reduce((k, d) => k + d.barlines.length, 0) >= 2;
  const kind = music ? 'music'
    : look && look.colour > 0.02 ? 'other'
    : look && look.dark < 0.001 ? 'blank' : 'title';
  const prev = previousPage(n, (p) => p.kind === 'music' || p.kind === 'title');
  const part = kind === 'music' || kind === 'title' ? (prev ? prev.part : null) : null;
  const page = {
    status: 'auto', kind, part,
    clef: part && kind === 'music' ? clefFor(n, part) : null,  // a title page has no clef
    notes: '', systems: [], marks: [],
  };
  if (corners) page.corners = { points: corners, auto: true };
  S.doc.pages[n] = page;
  if (music) for (const d of systems) newSystem(page, d);
  // a double bar where Structure.ily expects a repeat is almost surely one
  renumber();
  for (const nb of S.bars) {
    if (nb.page === n && nb.right.kind === 'double' && repeatHere(nb)) nb.right.kind = 'repeat_end';
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
  const room = roomFromPreviousPage(n);
  // the editor's corners, if they moved them, bound the staves
  const own = pg().corners && !pg().corners.auto ? `&corners=${encodeURIComponent(JSON.stringify(pg().corners.points))}` : '';
  try { ({ systems, corners } = await getJSON(`/api/detect?${q(S.pdf, n)}${room ? `&room=${room.toFixed(2)}` : ''}${own}`)); }
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

  const odd = pageOddBars();
  for (const s of page.systems) {
    const cue = (s.role || 'part') === 'cue';
    const sp = space(s);
    const st = s.start ?? s.left;
    const bls = [...s.barlines].sort((a, b) => mid(a) - mid(b));
    // what the bar images will include, above and below the staff
    out.push(`<path class="crop${isSel('sys', s.id) ? ' sel' : ''}" d="${outline(s, s.left, s.right, cropAbove(s), cropBelow(s))}"/>`);
    // the staff: a fill (what's clicked and dragged) and its outline
    const mods = [s.auto ? 'auto' : '', cue ? 'cue' : '', isSel('sys', s.id) ? 'sel' : ''].join(' ');
    out.push(`<polygon class="staff ${mods}" data-t="sys" data-id="${s.id}" points="${strip(s, s.left, s.right)}"/>`);
    out.push(`<path class="staffedge ${mods}" d="${outline(s, s.left, s.right)}"/>`);
    // dim what lies in no bar: clef and key before the music start, and
    // anything after the last bar line
    if (st > s.left) out.push(`<polygon class="outside" points="${strip(s, s.left, st, 0, 0, 2)}"/>`);
    const end = bls.length ? Math.max(bls[bls.length - 1].x0, bls[bls.length - 1].x1) : st;
    if (end < s.right) out.push(`<polygon class="outside" points="${strip(s, end, s.right, 0, 0, 4)}"/>`);
    out.push(`<line class="start" x1="${st * W}" x2="${st * W}" y1="${(topAt(s, st) - sp) * H}" y2="${(bottomAt(s, st) + sp) * H}"/>`);

    for (const o of odd.filter((o) => o.staff === s)) {
      if (o.kind === 'stacked') {  // a zero-width bar has no outline: ring the bar line
        const m = mid(o.barline), y = (topAt(s, m) + bottomAt(s, m)) / 2;
        out.push(`<ellipse class="oddbar" cx="${m * W}" cy="${y * H}" rx="${1.5 * sp * H}" ry="${3.5 * sp * H}"/>`);
        continue;
      }
      const right = o.barline || { x0: s.right, x1: s.right };  // 'tail': to the staff's end
      const q = barQuad(s, o.prev, right).map(([x, y]) => `${x * W},${y * H}`);
      out.push(`<polygon class="oddbar" points="${q.join(' ')}"/>`);
    }

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
        if (!['repeat_end', 'repeat_both'].includes(b.kind) && repeatHere(nb)) {
          out.push(`<text class="hint" x="${b.x1 * W}" y="${(bottomAt(s, mid(b)) + 3.8 * sp) * H}" font-size="${1.5 * sp * H}">repeat expected?</text>`);
        }
      }
    }
    // the first bar's number before the staff, as in a printed part
    if (firstOnLine && !cue) {
      out.push(`<text class="lineno" x="${s.left * W - 0.8 * sp * H}" y="${(topAt(s, s.left) + 2 * sp) * H}" font-size="${2.4 * sp * H}">${esc(firstOnLine.bar)}</text>`);
    }
  }
  // a staff's own clef, key and time, small, under its start region; the
  // movement's key and time it will take on review, dimmed
  const pending = new Map();
  for (const [s, f, v] of pendingDefaults()) pending.set(s, { ...pending.get(s), [f]: v });
  for (const s of page.systems) {
    const t = sigText(s), d = pending.has(s) ? sigText(pending.get(s)) : '';
    if (!t && !d) continue;
    const sp = space(s), x = (s.left + (s.start ?? s.left)) / 2;
    out.push(`<text class="siglabel" x="${x * W}" y="${(bottomAt(s, x) + 1.6 * sp) * H}" font-size="${Math.max(10 * u, 1.3 * sp * H)}">${esc(t)}`
      + (d ? `<tspan class="dflt">${t ? ' · ' : ''}${esc(d)}</tspan>` : '') + '</text>');
  }
  for (const m of page.marks) {
    const cls = `mark${m.kind === 'signature' ? ' sig' : ''}${isSel('mark', m.id) ? ' sel' : ''}`;
    out.push(`<rect class="${cls}" data-t="mark" data-id="${m.id}" x="${m.x * W}" y="${m.y * H}" width="${m.w * W}" height="${m.h * H}"/>`);
    const label = m.kind === 'signature' ? sigText(m) || '?' : m.text || m.kind;
    out.push(`<text class="marklabel${m.kind === 'signature' ? ' sig' : ''}" x="${m.x * W}" y="${m.y * H - 4 * u}" font-size="${13 * u}">${esc(label)}</text>`);
  }

  // handles for the selection, drawn last so they sit on top
  const item = find(sel);
  const act = (h) => (activeHandle() === h ? ' active' : '');
  const circle = (h, x, y, title) => `<circle class="handle h-${h.replace(/\d/, '')}${act(h)}" data-h="${h}" cx="${x * W}" cy="${y * H}" r="${r}"><title>${title}</title></circle>`;
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
    out.push(`<rect class="handle h-start${act('start')}" data-h="start" x="${st * W - r}" y="${(bottomAt(s, st) + sp) * H - r}" width="${2 * r}" height="${2 * r}"><title>music start: after clef, key and time signature</title></rect>`);
    // bend: drag these up or down where the staff rises or falls
    for (let i = 0; i < 5; i++) {
      const x = at(i / 4) * W, y = topAt(s, at(i / 4)) * H;
      out.push(`<rect class="handle bend${act(`bend${i}`)}" data-h="bend${i}" x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" transform="rotate(45 ${x} ${y})"><title>bend: drag to follow the staff</title></rect>`);
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

// the menus; `before` (a staff's): what its blank choice stands for, shown
// on it: what is in force before the line ("— (treble)"), or a movement's
// key and time from where they're stated ("— (2♯, as Violin I)")
const sigMenus = (o, dis, before = {}) => {
  const blank = (f, show) => {
    const b = before[f];
    if (b == null) return true;
    return b.from ? `— (${show(b.value)}, ${fromText(b.from)})` : `— (${show(b)})`;
  };
  return `<div class="sigrow">
      <label>Clef <select data-f="clef"${dis}>${options(CLEFS, o.clef, {}, blank('clef', (v) => v))}</select></label>
      <label>Key <select data-f="key"${dis}>${options(KEYS.map(String), o.key != null ? String(o.key) : null, Object.fromEntries(KEYS.map((k) => [String(k), keyName(k)])), blank('key', keyName))}</select></label>
      <label>Time <select data-f="time"${dis}>${options(TIMES.includes(o.time) || o.time == null ? TIMES : [...TIMES, o.time], o.time, { C: 'C (common)', 'C/': '¢ (cut)' }, blank('time', (v) => v))}</select></label></div>`;
};

// What a staff's blank menus stand for: what is in force before it; on a
// line that begins a movement, the movement's key and time from where
// they're stated (movementDefault), or nothing: the line is asked for them.
function sigDefaults(s) {
  const out = Object.fromEntries(SIG_FIELDS.map((f) => [f, sigBefore(S.page, s, f)]));
  const nb = lineStartsMovement(s);
  if (nb) for (const f of ['key', 'time']) out[f] = movementDefault(nb, f);
  const first = !nb && S.bars.find((b) => b.system === s && !b.left);
  if (first) for (const f of ['key', 'time']) out[f] = structureChange(first, f) || out[f];
  return out;
}

// the movement's first bar, if a counted staff begins one at its start
function lineStartsMovement(s) {
  for (const nb of S.firsts.values()) if (nb.system === s && !nb.left) return nb;
  return null;
}

// The defaults the page's lines would take and don't state: a movement's
// key and time where it begins, and Structure.ily's changes where a line
// begins: [staff, field, value, from]. Shown dimmed on the page;
// marking the page reviewed writes them (reviewing confirms what's shown).
function pendingDefaults(n = S.page) {
  const key = `${S.pdf} ${S.version} ${n}`;
  if (S.pendingCache?.key === key) return S.pendingCache.items;
  const out = [];
  for (const nb of S.lineFirsts.get(n) || []) {  // each line's first bar on the page
    const starts = S.firsts.get(nb.part + ' ' + nb.movement) === nb;
    for (const f of ['key', 'time']) {
      // stated on the staff, or in a box before its music start: nothing to write
      const d = statedAtStart(nb, f) != null ? null : starts ? movementDefault(nb, f) : structureChange(nb, f);
      if (d) out.push([nb.system, f, d.value, d.from]);
    }
  }
  S.pendingCache = { key, items: out };
  return out;
}

// The clef, key or time in force just before a counted staff's start: the
// last change on an earlier line of its page (a movement's start counting
// the key and time another part states for it), else (the clef) the
// page's clef at the top, else the last on the part's earlier pages.
function sigBefore(n, s, field) {
  const page = S.doc.pages[n];
  if (!page || page.part === 'score' || (s.role || 'part') !== 'part') return null;
  const firsts = field === 'clef' ? [] : [...S.firsts.values()];
  // changes on page k above `top` (all of them when top is Infinity), last first
  const last = (k, top) => {
    const ch = sigChanges(S.doc.pages[k], field).filter(([t]) => t.top < top).map(([t, x, v]) => [t.top, x, v]);
    for (const nb of firsts) {
      if (nb.page !== k || nb.system.top >= top) continue;
      // a movement's key and time don't carry into the next: unstated, it's a blank
      ch.push([nb.system.top, nb.left ? mid(nb.left) : -Infinity, movementSig(nb, field) ?? NONE]);
    }
    for (const nb of field === 'clef' ? [] : S.lineFirsts.get(k) || []) {
      if (nb.system.top >= top) continue;
      const c = structureChange(nb, field);  // a change Structure.ily puts where this line begins
      if (c) ch.push([nb.system.top, -Infinity, c.value]);
    }
    ch.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    return ch.length ? ch[ch.length - 1][2] : null;
  };
  const NONE = sigBefore.NONE;
  const here = last(n, s.top);
  if (here === NONE) return null;
  if (here != null) return here;
  if (field === 'clef') return page.clef || null;  // a music page's clef at its top (clefFor carries it over)
  for (let k = n - 1; k >= 1; k--) {
    const p = S.doc.pages[k];
    if (!p || p.kind !== 'music') continue;
    if (p.part !== page.part) return null;  // another part's pages: this part starts after them
    const v = last(k, Infinity);
    if (v === NONE) return null;
    if (v != null) return v;
  }
  return null;
}
sigBefore.NONE = Symbol('nothing stated');


// the key or time written where a movement begins in a part: on the staff,
// or on a signature mark at the movement's first bar (it may begin mid-line)
function statedAtStart(nb, field) {
  const page = S.doc.pages[nb.page];
  const s0 = nb.system.start ?? nb.system.left;
  // at a line's start: the staff's own, or a box before its music start;
  // mid-line: a box at the movement's first bar line
  const here = nb.left ? (x) => Math.abs(x - mid(nb.left)) < 1e-6 : (x) => x <= s0;
  const ch = sigChanges(page, field).filter(([s, x]) => s === nb.system && here(x));
  return ch.length ? ch[ch.length - 1][2] : null;
}

// A movement's key and time for a part's first bar that doesn't state
// them: {value, from}. As another part of this source states them (the
// same manuscript; a part that differs states its own); else from
// Structure.ily, the work's, so every source of it.
function movementDefault(nb, field) {
  if (nb.part === 'score') return null;  // a score's movements needn't line up with the parts'
  for (const other of S.firsts.values()) {
    if (other.movement !== nb.movement || other.part === nb.part || other.part === 'score') continue;
    const v = statedAtStart(other, field);
    if (v != null) return { value: v, from: PART_NAMES[other.part] || other.part };
  }
  const e = S.info?.expected?.[nb.movement];
  return e && e[field] != null ? { value: e[field], from: 'Structure.ily' } : null;
}
const fromText = (from) => (from === 'Structure.ily' ? 'from Structure.ily' : `as ${from}`);

// a change of key or time Structure.ily puts where a line begins (a Trio's
// new key on its first line): {value, from} if the line doesn't state it
function structureChange(nb, field) {
  if (nb.part === 'score' || nb.left) return null;
  const c = (S.info?.expected?.[nb.movement]?.changes || [])
    .filter((c) => field in c && c.bar === nb.bar && (c.on_bar_line ? nb.count !== 0 : nb.count === 0)).pop();
  return c && statedAtStart(nb, field) == null ? { value: c[field], from: 'Structure.ily' } : null;
}

// what a movement's first bar has for key or time: its own, else the default
const movementSig = (nb, field) => statedAtStart(nb, field) ?? movementDefault(nb, field)?.value ?? null;

function options(list, value, names = {}, blank = false) {
  return (blank ? `<option value="">${esc(blank === true ? '—' : blank)}</option>` : '') +
    list.map((v) => `<option value="${v}"${v === value ? ' selected' : ''}>${esc(names[v] || v)}</option>`).join('');
}

// Texts already used for marks, anywhere in the edition, offered as you
// type (a datalist on the text field), most used first. A mark of a
// particular kind (tempo, dynamic...) is offered only texts usually of that
// kind; a plain text mark, all of them.
async function loadMarkTexts() {
  try { S.markTexts = (await getJSON('/api/marktexts')).texts; } catch { S.markTexts = []; }
  renderMarkTexts();
}
function renderMarkTexts() {
  const counts = new Map(S.markTexts.map((e) => [e.text, e]));
  // this source's latest marks too, before they reach the server's list
  for (const p of Object.values(S.doc?.pages || {})) {
    for (const m of p.marks || []) {
      const t = (m.text || '').trim();
      if (t && !counts.has(t)) counts.set(t, { text: t, n: 1, kind: m.kind, kinds: [m.kind] });
    }
  }
  S.markTextIndex = counts;
  const all = [...counts.values()].sort((a, b) => b.n - a.n);
  const sig = all.map((e) => `${e.text}\t${e.n}\t${e.kinds || e.kind}`).join('\n');
  if (sig === S.markTextSig) return;  // unchanged: keep the lists
  S.markTextSig = sig;
  const opts = (es) => es.map((e) => `<option value="${esc(e.text)}">`).join('');
  const of = (k) => all.filter((e) => (e.kinds || [e.kind]).includes(k));
  $('#marktexts').innerHTML = opts(all);
  S.markKindsWithTexts = new Set(MARK_KINDS.filter((k) => k !== 'text' && of(k).length));
  $('#marktexts-kinds').innerHTML = [...S.markKindsWithTexts]
    .map((k) => `<datalist id="marktexts-${k}">${opts(of(k))}</datalist>`).join('');
}
// a tempo (dynamic...) mark is offered texts used with that kind; a plain
// text mark, or a kind with none yet, every text
const markTextList = (kind) => (S.markKindsWithTexts?.has(kind) ? `marktexts-${kind}` : 'marktexts');

function renderMeta() {
  const { source: s, display: d } = S.info;
  const rows = [
    ['Siglum', s.siglum], ['Shelfmark', s.shelfmark],
    ['Work', d.work || (s.gerard ? `G ${s.gerard}` : '')],
    ['RISM', d.rism_url ? `<a href="${esc(d.rism_url)}" target="_blank">${esc(s.rism)}</a>` : esc(s.rism)],
    ['Online', d.online ? `<a href="${esc(d.online)}" target="_blank">${esc(d.online_label || 'link')}</a>` : esc(d.online_label || '')],
    ['Bars from', esc(S.info.structure || 'no Structure.ily found')],
    ['Bar lines', `${esc(S.info.barline_model || '')} · <a href="/static/models/index.html" target="_blank">model cards</a>`],
  ];
  $('#meta').innerHTML = '<dl>' + rows.filter((r) => r[1]).map(([k, v]) =>
    `<dt>${k}</dt><dd>${k === 'RISM' || k === 'Online' || k === 'Bars from' || k === 'Bar lines' ? v : esc(v)}</dd>`).join('') + '</dl>' +
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
      <button data-act="snap"${dis}>Snap to the ink (a)</button>
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
      <h3 title="What is written at this line's start, where it sets or changes something (each movement's first line: key and time). Leave the rest at —.">Written at its start</h3>
      ${sigMenus(item, dis, sigDefaults(item))}
      <button data-act="trim"${dis}${item.barlines.length ? '' : ' disabled'}>End at last bar line</button>
      <button data-act="start-all"${dis} title="Carry this line's left end and music start to the lines below it (the start snapped to clear paper). At a key change, fix that line and click again.">Apply Start Below</button>
      <label>Crop above (staff spaces) <input data-f="above" type="number" min="0" step="0.5" value="${cropAbove(item)}"${dis}></label>
      <label>Crop below (staff spaces) <input data-f="below" type="number" min="0" step="0.5" value="${cropBelow(item)}"${dis}></label>
      <p class="muted">The dashed band is what each bar's image includes; drag its round handles or set it here.
      The square handle under the staff is where the music starts: after the clef, key and time signature.
      The diamonds on the top line bend the staff to follow the page.</p>`;
  } else {
    el.innerHTML = `<h2>Mark</h2>
      <label>Kind <select data-f="kind"${dis}>${options(MARK_KINDS, item.kind)}</select></label>
      ${item.kind === 'signature'
        ? `${sigMenus(item, dis)}
      <p class="muted">A change written mid-line: it holds from here, through later staves, until the next. At a line's start, set it on the staff instead. Keys 1–4: ${CLEFS.join(', ')}.</p>`
        : `<label>Text <input data-f="text" list="${markTextList(item.kind)}" autocomplete="off" value="${esc(item.text || '')}" placeholder="e.g. dolcis."${dis}></label>`}
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
          if (last && last.mvt === b.movement) last.to = lastBarOf(b);
          else runs.push({ mvt: b.movement, from: b.bar, to: lastBarOf(b) });
        }
        what += ' · ' + runs.map((r) => `${r.mvt} ${r.from}–${r.to}`).join(', ');
      }
    }
    items.push(`<li data-page="${n}" class="${n === S.page ? 'current' : ''}"><span class="dot ${p ? p.status : ''}"></span><span class="n">${n}</span><span class="what">${what}</span></li>`);
  }
  $('#pages').innerHTML = items.join('');
  $('#pages li.current')?.scrollIntoView({ block: 'nearest' });
}

// Structure.ily from these labels: the server offers a movement complete
// in every part (all pages reviewed through its end) that Structure.ily has
// no real block for yet; it shows the block, asks what the page doesn't
// show, and writes only what was shown.
function structureOffer() {
  const want = S.info?.structure_offers || [];
  const open = S.structureOpen;
  let html = want.length && !open ? `<p class="muted">${esc(S.info.structure)}: ${want.map((m) =>
    `<button class="link" data-structure="${esc(m)}">write movement ${esc(m)}</button>`).join(' ')}</p>` : '';
  if (open) {
    const r = open.r;
    html += `<div class="structure"><h3>Movement ${esc(open.movement)} for ${esc(S.info.structure)}</h3>`
      + (r.problems?.length ? `<ul class="bad">${r.problems.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>` : '')
      + (r.notes?.length ? `<ul class="muted">${r.notes.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>` : '')
      + (r.questions || []).map((q) => `<label>${esc(q.ask)} <select data-q="${esc(q.id)}">${options(q.choices, q.value)}</select></label>`).join('')
      + (r.text ? `<pre>${esc(r.text)}</pre>` : '')
      + (r.writable ? '' : `<p class="muted">${esc(r.why || '')}</p>`)
      + `<button data-structure-write${r.writable ? '' : ' disabled'}>Write it</button> <button data-structure-cancel>Cancel</button></div>`;
  }
  return html;
}

async function proposeStructure(movement, answers = {}) {
  if (S.version !== S.savedVersion) await saveNow();  // the server reads the saved labels
  if (S.version !== S.savedVersion) { banner('Save the labels first (not saved yet), then look again.'); return; }
  const qs = Object.entries(answers).map(([k, v]) => `&${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('');
  const r = await getJSON(`/api/structure?${q(S.pdf)}&movement=${encodeURIComponent(movement)}${qs}`);
  S.structureOpen = { movement, r, answers };
  renderAll();
}

async function writeStructure() {
  const { movement, r, answers } = S.structureOpen;
  // the block as shown (without its dated first line): the server writes only that
  const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(r.text.split('\n').slice(1).join('\n')));
  const shown = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
  const res = await fetch('/api/structure', { method: 'POST', headers: { 'Content-Type': 'application/json', 'If-Match': r.etag },
    body: JSON.stringify({ pdf: S.pdf, movement, answers, shown }) });
  if (!res.ok) { banner(`Not written: ${await res.text()}`); return; }
  const out = await res.json();
  S.info.expected = out.expected;
  S.info.structure_offers = out.offers;
  S.structureOpen = null;
  banner(`Wrote movement ${movement} to ${S.info.structure}.`);
  renderAll();
}

$('#counts').addEventListener('click', (e) => {
  const t = e.target;
  if (t.dataset.structure) proposeStructure(t.dataset.structure).catch((err) => banner(`Could not propose: ${err.message}`));
  else if ('structureWrite' in t.dataset) writeStructure().catch((err) => banner(`Not written: ${err.message}`));
  else if ('structureCancel' in t.dataset) { S.structureOpen = null; renderAll(); }
});
$('#counts').addEventListener('change', (e) => {
  const id = e.target.dataset.q;
  if (!id || !S.structureOpen) return;
  const { movement, answers } = S.structureOpen;
  proposeStructure(movement, { ...answers, [id]: e.target.value }).catch((err) => banner(`Could not propose: ${err.message}`));
});

// Counted vs expected bars per part and movement, plus repeat positions.
function renderCounts() {
  const exp = S.info?.expected || {};
  const runs = {};
  for (const nb of S.bars) {
    const r = (runs[nb.part] ||= {})[nb.movement] ||= { bars: 0, repeats: [], onPickup: [], pickup: false, ended: false, first: nb };
    r.bars += nb.count;
    if (nb.count === 0 && nb.bar === 0) r.pickup = true;
    if (['repeat_end', 'repeat_both'].includes(nb.right.kind)) {
      if (endsBar(nb) === null) r.onPickup.push(nb.bar); else r.repeats.push(endsBar(nb));
    }
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
      // a movement's first line records its key and time as written there
      // (on the staff, or on a signature mark where the movement starts
      // mid-line); asked on the page it's on, so the list doesn't flood
      const missing = r && r.first.page === S.page ? ['key', 'time'].filter((f) => statedAtStart(r.first, f) == null) : [];
      if (missing.length) {
        const d = r.first.left ? [] : missing.map((f) => [f, movementDefault(r.first, f)]).filter(([, v]) => v);
        const will = d.length ? '; review will write ' + d.map(([f, v]) => `${f === 'key' ? keyName(v.value) : v.value} (${fromText(v.from)})`).join(' and ')
          : r.first.left ? '; box them at its first bar (hold c)' : '';
        warnings.push(`${PART_NAMES[part]} ${m}: ${missing.join(' and ')} not set on its first line (page ${r.first.page})${will}`);
      }
      if (!e || !r) continue;
      if (r.ended && counted !== e.total) warnings.push(`${PART_NAMES[part]} ${m}: ${counted} bars counted, ${e.total} expected`);
      const want = repeatEnds(m);
      for (const at of r.onPickup) {
        warnings.push(`${PART_NAMES[part]} ${m}: repeat sign after the pickup sharing bar ${at}'s number; a repeat in mid-bar ends the bar's first part`);
      }
      for (const at of r.repeats) {
        if (want.length && !want.includes(at)) warnings.push(`${PART_NAMES[part]} ${m}: repeat sign after bar ${at}, expected after ${want.join(' or ')}`);
      }
    }
  }
  $('#counts').innerHTML = (rows.length ? `<table>${rows.join('')}</table>` : '<p class="muted">No bars yet.</p>')
    + structureOffer();
  // odd bar widths on this page, by bar number (with the movement if the
  // page has more than one), or by line and position if not yet numbered
  const odd = pageOddBars();
  const mvts = new Set(S.bars.filter((b) => b.page === S.page).map((b) => b.movement));
  const name = (o) => {
    const nb = o.barline ? S.byBarline.get(o.barline.id) : S.byBarline.get(o.prev.id);
    const ratio = o.kind === 'stacked' ? '' : ` (${o.ratio.toFixed(1)}×)`;
    if (!nb) return `line ${o.line}, bar ${o.pos} on the line${ratio}`;
    const mv = mvts.size > 1 ? `${nb.movement}:` : '';
    return (o.kind === 'tail' ? `after bar ${mv}${lastBarOf(nb)}` : `bar ${mv}${barLabel(nb)}`) + ratio;
  };
  const say = { wide: 'much wider than the line\'s typical bar: missed bar line?',
                narrow: 'much narrower than the line\'s typical bar: extra bar line?',
                tail: 'music after the last bar line: missed final bar line?',
                stacked: 'two bar lines on top of each other: delete one' };
  for (const kind of ['stacked', 'wide', 'tail', 'narrow']) {
    const these = odd.filter((o) => o.kind === kind);
    if (these.length) warnings.push(`This page, ${these.map(name).join('; ')}: ${say[kind]}`);
  }
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
  // pitch names follow the clef in force where the bar or staff begins
  const clefsOf = (s, x0, x1) => {
    if (s && (s.role || 'part') === 'part') return clefsBetween(page, s, x0, x1);
    // a cue staff: its own last clef box before x1, else the page's clef
    const own = clefMarks(page, { cue: true }).filter(([c, x]) => c === s && x < x1).pop();
    return [own ? own[2] : page.clef].filter(Boolean);
  };
  if (S.sel.t === 'bl') {
    // exactly the bar's crop (barQuad, as exported)
    const s = systemOf(item);
    const nb = S.byBarline.get(item.id);
    const sorted = [...s.barlines].sort((p, q) => mid(p) - mid(q));
    const prev = sorted[sorted.indexOf(item) - 1] || null;
    const cs = clefsOf(s, prev ? mid(prev) : null, mid(item));
    const clef = cs[0] || 'treble';
    return {
      rows: [[barQuad(s, prev, item)]],
      label: (nb ? `${PART_NAMES[nb.part] || nb.part} ${nb.movement}, bar ${barLabel(nb)} · ` : '') +
        `${(cs.length ? cs : ['treble']).join(' → ')} clef · exactly the exported crop`,
      staff: { above: cropAbove(s, item), below: cropBelow(s, item), clef },
    };
  }
  if (S.sel.t === 'sys') {
    // the whole staff's crop band, straightened piece by piece along its
    // bend, and wrapped onto as many rows as fill the panel best
    const s = item, sp = space(s), a = cropAbove(s), b = cropBelow(s);
    const clef = clefsOf(s, null, -Infinity)[0] || 'treble';
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
  const near = s.barlines.find((b) => Math.abs(xAt(b, s, S.mouse.y) - S.mouse.x) < stackedGap(s));
  if (near) { S.sel = { t: 'bl', id: near.id }; renderAll(); return; }
  mutate((page) => {
    const b = newBarline(page, s, { x0: S.mouse.x, x1: S.mouse.x }, false);
    S.sel = { t: 'bl', id: b.id };
    snapBarline(b, s, { fresh: true });
  });
}

// Fit a hand-placed bar line to the stroke under it: a fine adjustment of
// position and lean (detect.snap_barline searches about a staff space
// either side). Placing or dragging a line snaps it as part of that same
// edit; `undoable` makes it its own undo step (the a key, the button).
async function snapBarline(b, s, { undoable = false, fresh = false } = {}) {
  if (S.readonly) return;
  const n = S.page, m = mid(b);
  const params = `top=${topAt(s, m)}&bottom=${bottomAt(s, m)}&x0=${b.x0}&x1=${b.x1}`;
  let r;
  try { r = await getJSON(`/api/snap?${q(S.pdf, n)}&${params}`); }
  catch { return; }
  if (r.x0 == null || n !== S.page || !s.barlines.includes(b)) return;
  // a bar line just placed (nothing set on it yet) that snaps onto a stroke
  // already labelled: keep that one (now the editor's) rather than stack a
  // duplicate. A moved or edited bar line is never dropped.
  const x = (r.x0 + r.x1) / 2;
  const plain = fresh && b.kind === 'single' && (b.bar_count ?? 1) === 1 && !b.ends_movement && b.above == null && b.below == null;
  const others = plain ? s.barlines.filter((o) => o !== b && Math.abs(mid(o) - x) < stackedGap(s)) : [];
  const other = others.sort((a, c) => Math.abs(mid(a) - x) - Math.abs(mid(c) - x))[0];
  const apply = other
    ? () => {
      s.barlines.splice(s.barlines.indexOf(b), 1); other.auto = false; S.sel = { t: 'bl', id: other.id };
      banner('That stroke already has a bar line: selected it.'); setTimeout(() => banner(null), 1500);
    }
    : () => { b.x0 = r.x0; b.x1 = r.x1; b.auto = false; };
  if (undoable) mutate(apply);
  else { apply(); changed(); }
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
function addMark(box = null, kind = 'text') {
  const b = box || { x: clamp(S.mouse.x - 0.02, 0, 0.96), y: clamp(S.mouse.y - 0.01, 0, 0.98), w: 0.04, h: 0.02 };
  mutate((page) => {
    const m = { id: nextId(page, `p${S.page}m`), ...b, kind, text: '', note: '' };
    if (kind === 'signature') m.clef = likelyClef(page, m);
    page.marks.push(m);
    S.sel = { t: 'mark', id: m.id };
  });
  if (!S.held && kind !== 'signature') $('#inspector [data-f="text"]')?.focus();  // with m held, key repeats would type into it
}
const addSignature = (box = null) => addMark(box, 'signature');

// A new signature mark's first guess, mid-line most often a clef: a clef written where the part's usual
// clef is in force is likely its other one (cello tenor, viola treble);
// anywhere else, the return to the usual clef.
function likelyClef(page, m) {
  const cx = m.x + m.w / 2;
  const s = markStaff(page, m);
  if (s && (s.role || 'part') === 'cue') return 'treble';  // cues are mostly violin I
  const usual = DEFAULT_CLEF[page.part] || 'treble';
  const now = s ? clefsBetween(page, s, cx - 1e-6, cx - 1e-6)[0] : page.clef;
  if ((now || usual) !== usual) return usual;
  return { vc: 'tenor', va: 'treble' }[page.part] || (usual === 'treble' ? 'alto' : 'treble');
}

function deleteSelection() {
  const item = find(S.sel);
  if (!item) return;
  const sel = S.sel;
  // Tab carries on from here: the next Tab selects what came after the
  // deleted item, Shift-Tab what came before (nothing is selected now, so
  // a second d can't delete a neighbour by accident)
  const order = sel.t === 'bl' || sel.t === 'sys' || sel.t === 'mark' ? tabOrder(sel.t) : [];
  const at = order.indexOf(sel.id);
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
  if (at >= 0) S.tabFrom = { page: S.page, t: sel.t, next: order[at + 1] ?? null, prev: order[at - 1] ?? null };
}

// The clicked handle, if it still belongs to the current selection.
const selKey = () => JSON.stringify(S.sel);
function activeHandle() {
  if (S.heldCrop && S.sel?.t === 'sys') return S.heldCrop;  // t / g held
  return S.handle && S.handle.for === selKey() ? S.handle.h : null;
}

// Arrow keys move the active handle alone (a staff's left end carries its
// music start, as when dragged): a pixel per press (Shift: 10).
// Crop margins move a quarter staff space (Shift: a whole one).
function nudgeHandle(h, dx, dy, big) {
  const item = find(S.sel);
  if (!item) return;
  const t = S.sel.t;
  const px = (big ? 10 : 1);
  const mx = dx * px / S.W, my = dy * px / S.H;
  mutate(() => {
    if (/^c\d$/.test(h)) { const p = item.points[+h[1]]; item.points[+h[1]] = [clamp(p[0] + mx, 0, 1), clamp(p[1] + my, 0, 1)]; }
    else if (h === 'x0') item.x0 += mx;
    else if (h === 'x1') item.x1 += mx;
    else if (h === 'top') item.top = Math.min(item.top + my, item.bottom - 0.004);
    else if (h === 'bottom') item.bottom = Math.max(item.bottom + my, item.top + 0.004);
    else if (h === 'left') setExtent(item, Math.min(item.left + mx, item.right - 0.01), item.right);
    else if (h === 'right') setExtent(item, item.left, Math.max(item.right + mx, item.left + 0.01));
    else if (h === 'start') item.start = clamp((item.start ?? item.left) + mx, item.left, item.right);
    else if (h.startsWith('bend')) { if (!item.bend) item.bend = [0, 0, 0, 0, 0]; item.bend[+h.slice(4)] += my; }
    else if (h === 'above' || h === 'below') {
      // up grows the band above and shrinks the one below
      const step = (big ? 1 : 0.25) * (h === 'above' ? -dy : dy);
      item[h] = Math.max(0, (item[h] ?? 2.5) + step);
    } else if (h === 'br') { item.w = Math.max(0.005, item.w + mx); item.h = Math.max(0.005, item.h + my); }
    if (t !== 'mark' && 'auto' in item) item.auto = false;
  });
}

// t / g + up/down: a quarter staff space a press (Shift: one). Up moves the
// edge up: more room above, less below. A staff's crop, or with a bar line
// selected, that bar's own (starting from the staff's).
function nudgeCrop(edge, dy, big) {
  const item = find(S.sel);
  if (!item || (S.sel.t !== 'sys' && S.sel.t !== 'bl')) return;
  const s = S.sel.t === 'sys' ? item : systemOf(item);
  const step = (big ? 1 : 0.25) * (edge === 'above' ? -dy : dy);
  mutate(() => {
    const now = edge === 'above' ? cropAbove(s, S.sel.t === 'bl' ? item : null) : cropBelow(s, S.sel.t === 'bl' ? item : null);
    item[edge] = Math.max(0, now + step);
    if (S.sel.t === 'sys') item.auto = false;
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

// The open page's items of one kind in Tab order: staves top to bottom,
// marks in reading order, bar lines in bar order (those on staves that
// aren't counted, such as cue staves, after them, top to bottom)
function tabOrder(t) {
  const page = pg();
  if (t === 'sys') return [...page.systems].sort((a, b) => a.top - b.top).map((s) => s.id);
  if (t === 'mark') return [...page.marks].sort((a, b) => a.y - b.y || a.x - b.x).map((m) => m.id);
  const numbered = S.bars.filter((nb) => nb.page === S.page).map((nb) => nb.right.id);
  const seen = new Set(numbered);
  const rest = [...page.systems].sort((a, b) => a.top - b.top)
    .flatMap((s) => [...s.barlines].sort((a, b) => mid(a) - mid(b)).map((b) => b.id))
    .filter((id) => !seen.has(id));
  return numbered.concat(rest);
}

// Tab moves to the next item of the kind selected: bar line to bar line,
// staff to staff, mark to mark (see tabOrder). With nothing selected it
// starts at the first bar line, or, just after a delete, carries on from
// where the deleted item was.

function cycleSelection(dir) {
  const page = pg();
  if (!page) return;
  // just after a delete: carry on from where the deleted item was
  const from = !S.sel && S.tabFrom?.page === S.page ? S.tabFrom : null;
  S.tabFrom = null;
  const t = from ? from.t : S.sel?.t === 'sys' || S.sel?.t === 'mark' ? S.sel.t : 'bl';
  const all = tabOrder(t);
  if (!all.length) return;
  const target = from && (dir > 0 ? from.next : from.prev);
  if (target && all.includes(target)) S.sel = { t, id: target };
  else {
    // after deleting the last (first) item, or if its neighbour has gone
    // since: start again from the first (last)
    const i = from ? (dir > 0 ? -1 : 0) : S.sel && S.sel.t === t ? all.indexOf(S.sel.id) : -1;
    S.sel = { t, id: all[(i + dir + all.length) % all.length] };
  }
  renderAll();
}

// Reviewing a page confirms what it shows: the movement defaults on its
// lines are written into them, so each part's labels say what its page has.
function markReviewed(page) {
  const n = +Object.keys(S.doc.pages).find((k) => S.doc.pages[k] === page);
  for (const [s, f, v] of pendingDefaults(n)) { s[f] = v; s.auto = false; }
  page.status = 'reviewed';
}

function markReviewedAndNext() {
  if (!pg() || S.readonly) return;
  mutate((page) => markReviewed(page), { status: false });
  if (S.page < S.numPages) openPage(S.page + 1);
}

// ------------------------------------------------------------------ placing
// Hold b (bar line), s (staff) or m (mark) and click where it goes; or use
// a toolbar button, which places one on the next click. The cursor shows
// what will be placed.

const PLACE = { bl: addBarline, sys: addSystem, mark: addMark, sig: addSignature };
const PLACE_KEY = { b: 'bl', s: 'sys', m: 'mark', c: 'sig' };

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
    if (kind === 'mark' || kind === 'sig') {  // drag out the box; the mark is made on release
      S.drag = { kind: 'draw', start: { x: fx, y: fy }, sig: kind === 'sig' };
      return;
    }
    PLACE[kind]();
    return;
  }
  if (t.h && S.sel) {
    S.drag = { kind: 'handle', h: t.h, start: { x: fx, y: fy }, moved: false };
    // a click on a handle (no drag) makes it the one the arrow keys move;
    // clicking it again lets go
    S.drag.clickToggle = true;
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
    addMark(tiny ? null : { x: x0, y: y0, w, h }, d.sig ? 'signature' : 'text');
    return;
  }
  if (d.kind === 'handle' && !d.moved) {
    S.handle = activeHandle() === d.h ? null : { h: d.h, for: selKey() };
    renderOverlay();
    return;
  }
  if (d.kind === 'pan') {
    if (!d.moved && S.sel && !d.keepSel) { S.sel = null; renderAll(); }
    return;
  }
  if (d.moved) {
    touchPage();
    changed();
    // a bar line dragged to a new place snaps to the ink there; dragging
    // its end handles is setting the lean by hand, so that's left alone
    if (d.kind === 'move' && S.sel?.t === 'bl') { const b = find(S.sel); if (b) snapBarline(b, systemOf(b)); }
  }
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
    if (activeHandle() && !inField()) { S.handle = null; renderOverlay(); return; }
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
  // hold t (top) or g (the key below it: bottom) and press up/down to move
  // the selected staff's crop edge, or the selected bar's own crop
  else if (k === 't' || k === 'g') { handled(); if (!e.repeat) { S.heldCrop = k === 't' ? 'above' : 'below'; renderOverlay(); } }
  else if (S.heldCrop && (k === 'ArrowUp' || k === 'ArrowDown')) {
    handled();
    nudgeCrop(S.heldCrop, k === 'ArrowUp' ? -1 : 1, e.shiftKey);
  }
  else if (k === 'Delete' || k === 'Backspace' || k === 'd') { handled(); deleteSelection(); }
  else if (k.startsWith('Arrow') && activeHandle()) {
    handled();
    const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[k];
    nudgeHandle(activeHandle(), dir[0], dir[1], e.shiftKey);
  }
  else if (k === 'ArrowLeft' || k === 'ArrowRight') { handled(); nudge((k === 'ArrowLeft' ? -step : step) / S.W, 0, e.altKey); }
  else if (k === 'ArrowUp' || k === 'ArrowDown') { handled(); nudge(0, (k === 'ArrowUp' ? -step : step) / S.H); }
  else if (k === 'Tab') { handled(); cycleSelection(e.shiftKey ? -1 : 1); }
  else if (k >= '1' && k <= '4' && S.sel?.t === 'mark' && find(S.sel)?.kind === 'signature') {
    handled(); const m = find(S.sel); if (!S.readonly) mutate(() => { m.clef = CLEFS[+k - 1]; });
  }
  else if (k >= '1' && k <= '6') { handled(); setBarline((b) => { b.kind = BARLINE_KINDS[+k - 1]; }); }
  else if (k === 'a') { handled(); const b = find(S.sel); if (b && S.sel.t === 'bl') snapBarline(b, systemOf(b), { undoable: true }); }
  else if (k === 'e') { handled(); setBarline((b) => { b.ends_movement = !b.ends_movement; }); }
  else if (k === 'z') { handled(); S.detail = !S.detail; savePref('detail', S.detail); renderDetail(); renderOverlay(); }
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
  if (S.heldCrop && (e.key === 't' || e.key === 'g')) { S.heldCrop = null; renderOverlay(); }
  if (S.held && e.key.toLowerCase() === S.held) {
    S.held = null;
    setPlacing(null);
    if (S.sel?.t === 'mark' && find(S.sel)?.kind !== 'signature') $('#inspector [data-f="text"]')?.focus();
  }
});
window.addEventListener('blur', () => {
  if (S.held) { S.held = null; setPlacing(null); }
  if (S.heldCrop) { S.heldCrop = null; renderOverlay(); }
});

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
$('#detailclose').onclick = () => { S.detail = false; savePref('detail', false); renderDetail(); };

$('#pagestatus').onclick = () => {
  if (!pg() || S.readonly) return;
  mutate((p) => { if (p.status === 'reviewed') p.status = 'edited'; else markReviewed(p); }, { status: false });
};
$('#f-kind').addEventListener('change', (e) => mutate((p) => {
  p.kind = e.target.value;
  if (p.kind === 'blank' || p.kind === 'other') { p.part = null; p.clef = null; }  // nothing to carry
  if (p.kind === 'title') p.clef = null;  // a title page has no clef
  if (p.kind === 'music' && p.part && !p.clef) p.clef = clefFor(S.page, p.part);
}));
$('#f-part').addEventListener('change', (e) => mutate((p) => {
  p.part = e.target.value || null;
  if (p.kind === 'music') p.clef = clefFor(S.page, p.part) || p.clef;
  else if (p.kind === 'title') p.clef = null;
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
  if (act === 'start-all' && item && S.sel.t === 'sys') applyStartToPage(item);
  if (act === 'snap' && item && S.sel.t === 'bl') snapBarline(item, systemOf(item), { undoable: true });
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
    else if (SIG_FIELDS.includes(f)) {
      const v = e.target.value;
      // a signature mark keeps at least one field (the save checks it): its
      // last one can't be cleared (delete the mark instead)
      if (v === '' && t === 'mark' && SIG_FIELDS.every((g) => g === f || !(g in item))) return;
      if (v === '') delete item[f]; else item[f] = f === 'key' ? +v : v;  // saved as picked
    }
    else item[f] = e.target.value;
    // a clef mark always has a clef (the save checks it); other marks none
    if (t === 'mark' && f === 'kind') {
      if (item.kind === 'signature' && !SIG_FIELDS.some((g) => g in item)) item.clef = likelyClef(pg(), item);  // as when placed
      if (item.kind !== 'signature') for (const g of SIG_FIELDS) delete item[g];
    }
    // a text used before brings its usual kind, unless a kind was chosen
    if (t === 'mark' && f === 'text' && item.kind === 'text') {
      const known = S.markTextIndex?.get(e.target.value.trim());
      if (known && known.kind !== 'text' && known.kind !== 'signature') item.kind = known.kind;
    }
    if (t !== 'mark') item.auto = false;
  });
});

loadSources().catch((e) => banner(`Could not load: ${e.message}`));
