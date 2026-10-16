// The Time panel: the time spent on the source in view, from the activity
// log (GET /api/activity, activity.py source_report). app.js opens it
// (openTimePanel), which logs "pause" first: none of the time it is open
// counts. Uses app.js's S, esc, PART_NAMES and openPage.

const TP = { el: null, pdf: null };

function showTimePanel(pdf) {
  TP.pdf = pdf;
  if (!TP.el) {
    TP.el = document.createElement('div');
    TP.el.id = 'timepanel';
    TP.el.addEventListener('click', (e) => {
      if (e.target === TP.el || e.target.closest('.tp-close')) closeTimePanel();
      const go = e.target.closest('[data-page]');
      if (go) { e.preventDefault(); closeTimePanel(); openPage(+go.dataset.page); }
    });
    document.body.appendChild(TP.el);
  }
  TP.el.hidden = false;
  TP.el.innerHTML = `<div class="tp-card">${tpHead()}<p class="muted">Loading…</p></div>`;
  fetch(`/api/activity?pdf=${encodeURIComponent(pdf)}`)
    .then((r) => r.json().then((j) => { if (!r.ok) throw new Error(j.error || r.statusText); return j; }))
    .then((r) => { if (TP.pdf === pdf && !TP.el.hidden) TP.el.innerHTML = `<div class="tp-card">${tpHead()}${tpBody(r)}</div>`; })
    .catch((e) => { TP.el.innerHTML = `<div class="tp-card">${tpHead()}<p class="error">Couldn't load the log: ${esc(e.message)}</p></div>`; });
}

function hideTimePanel() {
  if (TP.el) TP.el.hidden = true;
}

function tpHead() {
  const s = S.sources?.find((x) => x.pdf === TP.pdf)?.source;
  const name = s ? `${s.gerard ? `G${s.gerard} · ` : ''}${s.siglum} ${s.shelfmark}` : TP.pdf;
  return `<div class="tp-head"><h2>Time on ${esc(name)}</h2>
    <span class="muted">Counting is paused while this is open.</span>
    <button class="tp-close" title="Close (Esc)">×</button></div>`;
}

function tpTime(sec) {
  if (sec < 60) return `${Math.round(sec)} s`;
  const m = Math.round(sec / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

const tpClock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const tpDay = (t) => new Date(t * 1000).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
const tpHue = (where) => (parseInt(where.slice(1), 10) * 47) % 360;

function tpBody(r) {
  if (!r.timeline.length) {
    return '<p class="muted">Nothing logged for this source yet. The log began on 16 October 2026; earlier time wasn\'t recorded.</p>';
  }
  const fp = r.pages.reduce((a, p) => a + p.first_pass, 0), rv = r.pages.reduce((a, p) => a + p.review, 0);
  const per100 = r.bars ? tpTime(r.seconds / r.bars * 100) : '–';
  const stat = (v, k) => `<div class="tp-stat"><b>${v}</b><span>${k}</span></div>`;
  return `<div class="tp-stats">
      ${stat(tpTime(r.seconds), 'active')}
      ${stat(r.stretches, r.stretches === 1 ? 'session' : 'sessions')}
      ${stat(Object.keys(r.days).length, Object.keys(r.days).length === 1 ? 'day' : 'days')}
      ${stat(`${r.reviewed}/${r.pages_total}`, 'pages reviewed')}
      ${stat(r.bars, 'bars')}
      ${stat(per100, 'per 100 bars')}
      ${stat(tpTime(fp), 'first pass')}
      ${stat(tpTime(rv), 'after review')}
    </div>
    <p class="muted tp-note">Since ${esc(tpDay(r.first_logged))}. Active time: gaps over 10 minutes, time away from the tab and time with this panel open don't count.</p>
    <h3>Sessions</h3>${tpTimeline(r)}
    <h3>Pages</h3>${tpPages(r)}
    <div class="tp-cols">
      <div><h3>Edits</h3>${tpCounts(r.edits)}</div>
      <div><h3>Corrections of detection</h3>${tpCounts(r.corrections, 'auto')}</div>
    </div>
    <div class="tp-cols">
      <div><h3>Undone and redone</h3>${tpCounts(r.undone, '', 8)}</div>
      <div><h3>Changed by detection or Claude</h3>${tpCounts(r.machine, '', 8)}</div>
    </div>
    <div class="tp-cols">
      <div><h3>Waiting on the server</h3>${tpWaits(r.waits)}${Object.keys(r.background || {}).length
        ? `<p class="muted tp-note">In the background (not waited on): ${tpWaitText(r.background)}</p>` : ''}</div>
      <div><h3>Commands</h3>${tpCounts(r.commands, '', 8)}</div>
      <div><h3>Keys</h3>${tpCounts(r.keys, '', 8)}</div>
    </div>`;
}

// One row per day; the day's sessions laid end to end (the gaps between
// them left out), each piece coloured by its page, edits ticked above.
function tpTimeline(r) {
  const days = new Map();
  for (const s of r.timeline) {
    const d = tpDay(s.start);
    if (!days.has(d)) days.set(d, []);
    days.get(d).push(s);
  }
  const W = 820, H = 30, GAPW = 10;
  return [...days].map(([day, runs]) => {
    const total = runs.reduce((a, s) => a + (s.end - s.start), 0);
    const scale = (W - GAPW * (runs.length - 1)) / Math.max(total, 1);
    let x = 0;
    const parts = [];
    for (const s of runs) {
      const X = (t) => x + (t - s.start) * scale;
      for (const [a, b, w] of s.pieces) {
        parts.push(`<rect x="${X(a).toFixed(1)}" y="8" width="${Math.max(0.8, (b - a) * scale).toFixed(1)}" height="14"
          fill="hsl(${tpHue(w)} 55% 62%)"><title>${esc(w)} · ${tpClock(a)}–${tpClock(b)} · ${tpTime(b - a)}</title></rect>`);
      }
      for (const [t, kind, w, what, n] of s.marks) {
        if (kind !== 'edit') continue;
        const corr = what.includes('(detected)');
        parts.push(`<line x1="${X(t).toFixed(1)}" x2="${X(t).toFixed(1)}" y1="0" y2="7" class="${corr ? 'tp-corr' : 'tp-edit'}">
          <title>${esc(w)} ${tpClock(t)}: ${esc(what)}${n > 1 ? ` ×${n}` : ''}</title></line>`);
      }
      for (const [a, b, kind, w] of s.waits) {
        parts.push(`<rect x="${X(a).toFixed(1)}" y="24" width="${Math.max(1, (b - a) * scale).toFixed(1)}" height="4" class="tp-wait">
          <title>${esc(kind)} ${esc(w)}: ${(b - a).toFixed(1)} s</title></rect>`);
      }
      parts.push(`<text x="${x.toFixed(1)}" y="${H + 10}" class="tp-tick">${tpClock(s.start)}</text>`);
      x += (s.end - s.start) * scale + GAPW;
    }
    return `<div class="tp-day"><span>${esc(day)}<br><b>${tpTime(total)}</b></span>
      <svg viewBox="0 0 ${W} ${H + 12}" preserveAspectRatio="none">${parts.join('')}</svg></div>`;
  }).join('') + '<p class="muted tp-key">Coloured by page · <span class="tp-edit-k">|</span> edit · <span class="tp-corr-k">|</span> correction of detection · <span class="tp-wait-k">▬</span> waiting on the server</p>';
}

function tpPages(r) {
  const rows = r.pages.filter((p) => p.page != null && p.seconds > 0);
  const max = Math.max(...rows.map((p) => p.seconds), 1);
  return `<table class="tp-pages"><thead><tr><th>page</th><th></th><th>status</th><th class="tp-bar">time (first pass, after review)</th>
    <th class="n">bars</th><th class="n">per bar</th><th class="n">edits</th><th class="n">corrections</th></tr></thead><tbody>
    ${rows.map((p) => `<tr>
      <td><a href="#" data-page="${p.page}" title="Open page ${p.page}"><span class="tp-sw" style="background:hsl(${tpHue('p' + p.page)} 55% 62%)"></span>${p.page}</a></td>
      <td class="muted">${esc(p.kind === 'music' ? (PART_NAMES[p.part] || p.part || '') : (p.kind || ''))}</td>
      <td class="tp-status ${esc(p.status || '')}">${esc(p.status || '')}</td>
      <td class="tp-bar"><span class="tp-fp" style="width:${(p.first_pass / max * 100).toFixed(1)}%"></span><span class="tp-rv" style="width:${(p.review / max * 100).toFixed(1)}%"></span>
        <em>${tpTime(p.seconds)}</em></td>
      <td class="n">${p.bars || ''}</td>
      <td class="n">${p.bars ? tpTime(p.seconds / p.bars) : ''}</td>
      <td class="n">${p.edits || ''}</td>
      <td class="n">${p.corrections || ''}</td></tr>`).join('')}
    </tbody></table>`;
}

function tpCounts(c, cls = '', top = 12) {
  const rows = Object.entries(c || {}).sort((a, b) => b[1] - a[1]).slice(0, top);
  if (!rows.length) return '<p class="muted">None.</p>';
  const max = rows[0][1];
  return `<ul class="tp-counts">${rows.map(([k, n]) => `<li><span class="tp-cbar ${cls}" style="width:${(n / max * 100).toFixed(0)}%"></span>
    <b>${n}</b> ${esc(k.replace(' (detected)', ''))}</li>`).join('')}</ul>`;
}

const TP_WAIT = { detect: 'Detection', read: "Claude's reads", 'read-ahead': "Claude's reads of the next page" };

function tpWaits(w) {
  const rows = Object.entries(w || {});
  if (!rows.length) return '<p class="muted">None.</p>';
  return `<ul class="tp-counts">${rows.map(([k, [n, sec]]) => `<li><b>${tpTime(sec)}</b> ${esc(TP_WAIT[k] || k)}, ${n} ${n === 1 ? 'time' : 'times'}</li>`).join('')}</ul>`;
}

function tpWaitText(w) {
  return Object.entries(w).map(([k, [n, sec]]) => `${esc(TP_WAIT[k] || k)}, ${n} (${tpTime(sec)})`).join('; ');
}
