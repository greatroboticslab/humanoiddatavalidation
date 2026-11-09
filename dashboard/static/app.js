// Validation dashboard: the Dataset grid with one Validate action, a per-video review page, and How it works.

// One verdict per video (validator/verdict.py): do the tasks match what is going on in the video?
const VERDICTS = {
  MATCHES:        { color: '#16a34a', label: 'Matches',         desc: 'What is going on in the video matches the tasks: most subtasks match their time range.' },
  PARTLY_MATCHES: { color: '#d97706', label: 'Partly matches',  desc: 'Some subtasks match what is going on at their time, others do not. See the corrections.' },
  DOES_NOT_MATCH: { color: '#dc2626', label: 'Does not match',  desc: 'Most subtasks do not match what is going on at their time, or the tasks describe a different video.' },
  UNAVAILABLE:    { color: '#6b7280', label: 'Unavailable',     desc: 'The video is private or deleted on YouTube, so the tasks cannot be checked.' },
  ERROR:          { color: '#111827', label: 'Error',           desc: 'Validation failed to run (see the job panel).' },
};
// Per subtask: does what is shown and said in its own time range match it?
const MATCH = {
  YES:    { color: '#16a34a', label: 'Matches',        desc: 'What is shown and said in this time range is what the subtask describes.' },
  PARTLY: { color: '#d97706', label: 'Partly',         desc: 'Related, but a different step, a different detail, or only part of it.' },
  NO:     { color: '#dc2626', label: 'Does not match', desc: 'What is shown and said in this time range is about something else.' },
};
const PER_PAGE = 20;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (s) => (s == null ? '' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`);
const mb = (b) => `${(b / 1048576).toFixed(b < 10485760 ? 1 : 0)} MB`;
const sget = (k, d) => { try { const v = JSON.parse(sessionStorage.getItem(k)); return v ?? d; } catch { return d; } };
const sset = (k, v) => { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } };

const S = {
  videos: [], filter: 'ALL', search: '', page: 1, selectedOnly: false, force: false, deleteAfter: false, storage: null,
  // the selection lives only in memory: kept while moving between pages, empty on every fresh load
  selected: new Set(), nav: sget('nav', []), detail: null, review: null,
};
try { sessionStorage.removeItem('selected'); } catch { /* storage unavailable */ }  // drop selections saved by older versions

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}
const postJSON = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function badge(v, precheck) {
  if (!v) {
    const pre = precheck ? ` title="Not validated yet. Quick pre-check from YouTube info only: ${esc(precheck)}"` : '';
    return `<span class="badge none"${pre}>Not validated</span>`;
  }
  const m = VERDICTS[v] || VERDICTS.ERROR;
  return `<span class="badge" style="background:${m.color}" title="${esc(m.desc)}">${esc(m.label)}</span>`;
}

/* ---------------- Dataset page ---------------- */

function filtered() {
  const q = S.search.toLowerCase();
  return S.videos.filter((v) => {
    if (q && !(v.title.toLowerCase().includes(q) || v.video_id.toLowerCase().includes(q))) return false;
    if (S.selectedOnly && !S.selected.has(v.video_id)) return false;
    if (S.filter === 'ALL') return true;
    if (S.filter === 'NONE') return !v.verdict;
    if (S.filter === 'REVIEWED') return v.reviewed;
    return v.verdict === S.filter;
  });
}

function renderDataset() {
  $('#page').innerHTML = `
    <div class="dataset-page">
      <h2>Dataset</h2>
      <p class="subtitle" id="ds-sub"></p>
      <div id="ds-storage"></div>
      <div class="verdict-filters" id="ds-verdicts"></div>
      <div class="dataset-filters">
        <input class="search-input" id="ds-search" placeholder="Search videos by title or ID..." value="${esc(S.search)}">
        <button class="filter-btn" data-act="sel-page">Select page</button>
        <button class="filter-btn" data-act="sel-sample" title="The same 20 videos every time (seed 42)">20-video sample</button>
        <button class="filter-btn" data-act="sel-random">Random 20</button>
        <a class="filter-btn" href="/api/export.csv" title="Every validated or reviewed video">Export CSV</a>
      </div>
      <div id="ds-grid"></div>
      <div id="ds-pages"></div>
      <div id="ds-bar"></div>
    </div>`;
  $('#ds-search').addEventListener('input', (e) => { S.search = e.target.value; S.page = 1; renderGrid(); });
  renderGrid();
  refreshStorage();
}

async function refreshStorage() {
  try { S.storage = await api('/api/storage'); } catch { return; }
  renderStorage();
}

function renderStorage() {
  const st = S.storage, el = $('#ds-storage');
  if (!st || !el) return;
  const local = st.videos_bytes + st.audio_bytes;
  el.innerHTML = `<div class="storage-panel">
    <div><b>Local storage</b> <span class="muted">${st.downloaded_ids.length} video(s) on disk: video ${mb(st.videos_bytes)} + audio ${mb(st.audio_bytes)}
      · frames ${mb(st.frames_bytes)}</span></div>
    <div class="storage-actions">
      <button class="btn danger-outline" data-act="storage-free" ${local ? '' : 'disabled'}
        title="Deletes downloaded video and audio files. Frames, results, transcripts and reviews stay.">🗑 Delete local videos · frees ${mb(local)}</button>
      <button class="btn danger-outline" data-act="storage-all" ${local + st.frames_bytes ? '' : 'disabled'}
        title="Also deletes the frames. Results, transcripts and reviews stay.">🗑 Delete videos + frames · frees ${mb(local + st.frames_bytes)}</button>
    </div></div>`;
}

function renderGrid() {
  const list = filtered();
  S.nav = list.map((v) => v.video_id);
  sset('nav', S.nav);
  const count = (f) => S.videos.filter((v) => (f === 'NONE' ? !v.verdict : f === 'REVIEWED' ? v.reviewed : v.verdict === f)).length;
  $('#ds-sub').textContent = `${S.videos.length} videos · ${S.videos.length - count('NONE')} validated · ${count('REVIEWED')} reviewed by you · showing ${list.length}`;

  // one row of filters; verdicts with no videos are hidden
  const chip = (f, label, color, desc) => {
    const n = f === 'ALL' ? S.videos.length : count(f);
    if (!n && !['ALL', 'NONE'].includes(f)) return '';
    return `<button class="filter-btn ${S.filter === f ? 'active' : ''}" data-filter="${f}" title="${esc(desc || '')}">
      ${color ? `<span class="dot" style="background:${color}"></span>` : ''}${esc(label)} <span class="n">${n}</span></button>`;
  };
  $('#ds-verdicts').innerHTML = chip('ALL', 'All') + chip('NONE', 'Not validated')
    + Object.entries(VERDICTS).map(([k, m]) => chip(k, m.label, m.color, m.desc)).join('')
    + chip('REVIEWED', 'Reviewed by you', '#16a34a');

  const pages = Math.max(1, Math.ceil(list.length / PER_PAGE));
  S.page = Math.min(S.page, pages);
  const slice = list.slice((S.page - 1) * PER_PAGE, S.page * PER_PAGE);
  $('#ds-grid').innerHTML = slice.length ? `<div class="video-grid">${slice.map((v) => `
    <div class="video-card ${S.selected.has(v.video_id) ? 'selected' : ''}" data-card="${v.video_id}">
      <img class="video-thumbnail" loading="lazy" src="https://img.youtube.com/vi/${v.video_id}/mqdefault.jpg" alt="">
      <label class="card-check" data-check="${v.video_id}" title="Select"><input type="checkbox" ${S.selected.has(v.video_id) ? 'checked' : ''}></label>
      <span class="card-verdict">${v.queue ? qbadge(v.queue) : badge(v.verdict, v.precheck)}</span>
      <div class="video-card-body">
        <h4 class="video-card-title">${esc(v.title)}</h4>
        <div class="video-card-meta"><span>${v.task_count} tasks</span><span>${v.subtask_count} subtasks</span>
          ${v.reviewed ? '<span class="reviewed-mark" title="You reviewed this video">✓ reviewed</span>' : ''}</div>
      </div>
    </div>`).join('')}</div>` : '<p class="no-results">No videos found.</p>';

  // pagination: 1 … p-1 p p+1 … last
  let nums = [];
  if (pages <= 7) nums = Array.from({ length: pages }, (_, i) => i + 1);
  else {
    nums.push(1);
    if (S.page > 3) nums.push('…');
    for (let i = Math.max(2, S.page - 1); i <= Math.min(pages - 1, S.page + 1); i++) nums.push(i);
    if (S.page < pages - 2) nums.push('…');
    nums.push(pages);
  }
  $('#ds-pages').innerHTML = pages > 1 ? `<div class="pagination">
    <button class="pagination-btn" data-page="${S.page - 1}" ${S.page === 1 ? 'disabled' : ''}>Previous</button>
    ${nums.map((p) => (p === '…' ? '<span class="muted">…</span>' : `<button class="page-btn ${p === S.page ? 'active' : ''}" data-page="${p}">${p}</button>`)).join('')}
    <button class="pagination-btn" data-page="${S.page + 1}" ${S.page === pages ? 'disabled' : ''}>Next</button></div>` : '';
  renderSelectBar();
}

// selected videos that are not already queued or validating
const toValidate = () => {
  const busy = new Set(S.videos.filter((v) => v.queue).map((v) => v.video_id));
  return [...S.selected].filter((id) => !busy.has(id));
};

function renderSelectBar() {
  const n = S.selected.size, bar = $('#ds-bar');
  if (!bar) return;
  if (!n) { bar.innerHTML = ''; return; }
  const done = S.videos.filter((v) => S.selected.has(v.video_id) && v.verdict).length;
  const todo = toValidate().length, busy = n - todo;  // videos already queued or validating are not queued again
  bar.innerHTML = `<div class="select-bar">
    <b>${n} selected</b>${done ? `<span style="color:#9ca3af">(${done} already validated)</span>` : ''}${busy ? `<span style="color:#9ca3af">(${busy} already in the queue)</span>` : ''}
    <label><input type="checkbox" id="sb-only" ${S.selectedOnly ? 'checked' : ''}> Show selected only</label>
    <label title="Redo videos that already have a result"><input type="checkbox" id="sb-force" ${S.force ? 'checked' : ''}> Re-validate</label>
    <label title="Delete each downloaded video and audio file after validating it (frames are kept)"><input type="checkbox" id="sb-del" ${S.deleteAfter ? 'checked' : ''}> Delete videos after</label>
    <button class="btn primary" data-act="validate-sel" ${todo ? '' : 'disabled'} title="${todo ? 'YouTube info + frames + speech for every subtask, one verdict per video' : 'All selected videos are already in the queue'}">Validate ${todo}</button>
    <a class="btn ghost" href="/api/export.csv?ids=${[...S.selected].join(',')}">Export CSV</a>
    <button class="btn ghost" data-act="sel-clear">Clear</button></div>`;
  $('#sb-only').onchange = (e) => { S.selectedOnly = e.target.checked; S.page = 1; renderGrid(); };
  $('#sb-force').onchange = (e) => { S.force = e.target.checked; };
  $('#sb-del').onchange = (e) => { S.deleteAfter = e.target.checked; };
}

async function deleteMedia(body) {
  const r = await postJSON('/api/storage/delete', body);
  S.videos = await api('/api/videos');
  await refreshStorage();
  return r.freed_bytes;
}

/* ---------------- Validation queue ---------------- */
// Jobs live on the server: they keep running whatever page is open, and survive a server restart.

const ago = (t) => { const s = Math.max(0, Date.now() / 1000 - t); return s < 60 ? `${Math.round(s)} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`; };
const dur = (a, b) => { const s = Math.max(0, (b || Date.now() / 1000) - a); return s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`; };
// queued/running status, shown instead of (or next to) the verdict
// a queued job that waits for a retry time (e.g. YouTube asked this computer to slow down)
const waitingJob = (it) => it.status === 'queued' && it.not_before && it.not_before * 1000 > Date.now();
const qbadge = (q) => (q === 'running' ? '<span class="badge running">Validating<span class="dots"></span></span>'
  : q === 'queued' ? '<span class="badge queued">In queue</span>' : '');

let toastTimer = null;
function toast(html) {
  const t = $('#toast');
  t.innerHTML = html; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 5000);
}

async function enqueue(ids, force) {
  try {
    const r = await postJSON('/api/queue', { ids, force, delete_after: S.deleteAfter });
    toast(`${r.added ? `Added ${r.added} video${r.added > 1 ? 's' : ''} to the queue` : 'Nothing new to add'}`
      + `${r.already_queued ? ` · ${r.already_queued} already queued` : ''} · <a href="#/jobs">View jobs</a>`);
    await pollQueue(true);
  } catch (e) { alert('Could not queue: ' + e.message); }
}

let lastQueueKey = '';
async function pollQueue(force = false) {
  let q;
  try { q = await api('/api/queue'); } catch { return; }
  S.queue = q;
  const active = q.counts.queued + q.counts.running;
  const nc = $('#jobs-count');
  nc.hidden = !active; nc.textContent = active;
  // re-render the rest of the app only when something changed (a job started, finished, or was added/removed)
  const key = q.items.map((it) => it.id + it.status).join('|');
  if (!force && key === lastQueueKey) {
    if ((location.hash || '').startsWith('#/jobs')) renderJobs();  // keep the "running for" times ticking
    return;
  }
  lastQueueKey = key;
  S.videos = await api('/api/videos');
  const h = location.hash || '#/';
  if (h.startsWith('#/jobs')) renderJobs();
  else if (h.startsWith('#/video/')) {
    const cur = h.slice(8), was = S.detail?.queue, now = S.videos.find((v) => v.video_id === cur)?.queue || null;
    if (S.detail && was !== now) reloadDetail(cur);  // started, or finished: refresh button and results
  } else if ($('#ds-grid')) { renderGrid(); if (!active) refreshStorage(); }
}

function renderJobs() {
  const q = S.queue || { items: [], counts: {} };
  const rank = { running: 0, queued: 1, error: 2, done: 3 };
  const items = [...q.items].sort((a, b) => rank[a.status] - rank[b.status]
    || (a.status === 'queued' ? a.added - b.added : (b.finished || b.started || b.added) - (a.finished || a.started || a.added)));
  const c = q.counts;
  const active = new Set(q.items.filter((it) => it.status === 'queued' || it.status === 'running').map((it) => it.video_id));
  $('#page').innerHTML = `<div class="dataset-page jobs-page">
    <h2>Jobs</h2>
    <p class="subtitle">${c.running || 0} validating · ${c.queued || 0} in queue · ${c.done || 0} done · ${c.error || 0} failed.
      Two videos are validated at a time; each takes about 1–3 minutes. Jobs keep running while you use other pages, and continue after a restart.</p>
    ${(c.done || c.error) ? '<button class="btn" data-act="queue-clear">Clear finished</button>' : ''}
    ${items.length ? `<div class="jobs-list">${items.map((it) => `
      <div class="job ${it.status}">
        <img src="https://img.youtube.com/vi/${esc(it.video_id)}/default.jpg" alt="" loading="lazy">
        <div class="job-main">
          <a href="#/video/${esc(it.video_id)}" class="job-title">${esc(it.title)}</a>
          <div class="muted">${esc(it.video_id)} · added ${ago(it.added)}${it.started ? ` · ${it.status === 'running' ? 'running for' : 'took'} ${dur(it.started, it.finished)}` : ''}${it.force ? ' · re-validate' : ''}</div>
          ${it.summary ? `<div class="job-summary">${esc(it.summary)}</div>` : ''}${it.error ? `<div class="job-summary vis-issue">${esc(it.error)}</div>` : ''}${waitingJob(it) && it.note ? `<div class="job-summary">${esc(it.note)}</div>` : ''}
        </div>
        <div class="job-side">
          ${waitingJob(it) ? '<span class="badge queued">Waiting</span>' : it.status === 'running' || it.status === 'queued' ? qbadge(it.status) : it.status === 'error' ? '<span class="badge" style="background:#111827">Failed</span>' : badge(it.verdict)}
          <div class="job-actions">
            ${it.status === 'queued' ? `<button class="btn small" data-queue-remove="${it.id}">Cancel</button>` : ''}
            ${it.status === 'error' || it.status === 'done' ? `${active.has(it.video_id)
              ? '<button class="btn small" disabled title="This video is already in the queue">Retry</button>'
              : `<button class="btn small" data-queue-retry="${it.id}" title="Validate again">Retry</button>`}
              <button class="btn small" data-queue-remove="${it.id}" title="Remove from this list (the result is kept)">Remove</button>` : ''}
          </div>
        </div>
      </div>`).join('')}</div>` : '<p class="no-results">No jobs yet. Select videos on the Dataset tab and click Validate.</p>'}
  </div>`;
}

/* ---------------- Video page ---------------- */

let player = null, playerReady = false, pendingSeek = null, currentVid = null, fallbackIframe = false;

function createPlayer(id) {
  playerReady = false; fallbackIframe = false; pendingSeek = null;
  const makeYT = () => {
    player = new YT.Player('yt', {
      videoId: id, playerVars: { rel: 0, modestbranding: 1 },
      events: { onReady: () => { playerReady = true; if (pendingSeek != null) { seek(pendingSeek); pendingSeek = null; } } },
    });
  };
  if (window.YT && window.YT.Player) { makeYT(); return; }
  // API still loading: wait for it, but fall back to a plain embed (seeking reloads it) if it is blocked
  let done = false;
  window.onYouTubeIframeAPIReady = () => { if (!done && currentVid === id) { done = true; makeYT(); } };
  setTimeout(() => {
    if (done || currentVid !== id) return;
    done = true; fallbackIframe = true;
    $('#yt').outerHTML = `<iframe id="yt" src="https://www.youtube.com/embed/${id}?rel=0" allow="autoplay; encrypted-media" allowfullscreen frameborder="0"></iframe>`;
  }, 4000);
}

function seek(t) {
  if (player && playerReady) { player.seekTo(t, true); player.playVideo(); return; }
  if (fallbackIframe) { $('#yt').src = `https://www.youtube.com/embed/${currentVid}?rel=0&autoplay=1&start=${Math.floor(t)}`; return; }
  pendingSeek = t;
}

function leaveVideo() {
  if (player) { try { player.destroy(); } catch { /* already gone */ } }
  player = null; playerReady = false; currentVid = null;
}

async function renderVideo(id) {
  if (currentVid !== id) {
    leaveVideo();
    currentVid = id;
    const nav = S.nav.length ? S.nav : S.videos.map((v) => v.video_id);
    const i = nav.indexOf(id);
    $('#page').innerHTML = `<div class="video-detail">
      <div class="detail-nav"><a href="#/" class="back-link">← Back to Dataset</a>
        <span>${i > 0 ? `<a class="btn" href="#/video/${nav[i - 1]}">← Prev</a>` : ''}
        ${i >= 0 ? `<span class="muted" style="margin:0 8px">${i + 1} / ${nav.length}</span>` : ''}
        ${i >= 0 && i < nav.length - 1 ? `<a class="btn" href="#/video/${nav[i + 1]}">Next →</a>` : ''}</span></div>
      <div class="detail-top">
        <div class="player-wrap"><div class="player"><div id="yt"></div></div><div id="chapters"></div></div>
        <div id="info"><div class="loading">Loading…</div></div>
      </div>
      <div id="tree"></div></div>`;
    createPlayer(id);
  }
  await reloadDetail(id);
}

async function reloadDetail(id) {
  let d;
  try { d = await api('/api/videos/' + id); } catch (e) { $('#info').innerHTML = `<p class="loading">${esc(e.message)}</p>`; return; }
  if (currentVid !== id) return;
  S.detail = d;
  S.review = Object.assign({ makes_sense: null, agree: null, correct_verdict: '', notes: '', tasks: {}, rewrites: {} }, d.review || {});
  renderInfo(); renderTree(); renderChapters();
}

function renderChapters() {
  const ch = S.detail.meta?.chapters;
  $('#chapters').innerHTML = ch && ch.length ? `<details class="chapters" open><summary>YouTube chapters (${ch.length}), the creator's own timeline</summary>
    <ol>${ch.map((c) => `<li><button class="ts" data-seek="${c.start_time}">${fmt(c.start_time)}</button> ${esc(c.title)}</li>`).join('')}</ol></details>`
    : '<p class="muted" style="margin-top:10px">This video has no chapters on YouTube.</p>';
}

function validationPanel() {
  const { final: fin, validation: txt, results: vis, media: m = {} } = S.detail;
  const full = fin?.stage === 'full';
  const t = txt?.llm;
  const c = vis?.match_counts || {};
  const local = (m.video_bytes || 0) + (m.audio_bytes || 0);
  return `<div class="panel">
    <h3><span>Validation ${badge(fin?.verdict, fin?.precheck)}</span>
      ${S.detail.queue === 'running' ? '<button class="btn primary" disabled>Validating<span class="dots"></span></button>'
        : S.detail.queue === 'queued' ? '<button class="btn primary" disabled title="Waiting for a free slot; see the Jobs tab">In queue</button>'
        : `<button class="btn primary" data-act="validate-one">${full ? 'Re-validate' : 'Validate'}</button>`}</h3>
    ${full ? `
      <p class="summary">${esc(VERDICTS[fin.verdict]?.desc || '')}</p>
      <ul class="reasons">${(fin.reasons || []).map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
      <div class="chips">${Object.entries(MATCH).map(([k, s]) => `<span class="chip" title="${esc(s.desc)}"><span class="dot" style="background:${s.color}"></span> Subtasks ${esc(s.label.toLowerCase())}: <b>${c[k] || 0}</b></span>`).join('')}</div>
      <details class="details"><summary>Evidence details</summary>
        ${vis?.overview?.description ? `<p><b>Whole video:</b> ${esc(vis.overview.description)}</p>` : ''}
        <p><b>Speech:</b> ${esc(vis?.speech_source || 'none, judged from the frames alone')} · <b>Model:</b> ${esc(vis?.llm ? `${vis.llm.provider} / ${vis.llm.model}` : '?')} · checked ${esc(vis?.judged || '')}</p>
        ${t ? `<p><b>YouTube info</b> (title, description, chapters${String(t.evidence).includes('transcript') ? ', transcript' : ''}): tasks vs topic ${esc(String(t.content_match).toLowerCase())};
          dataset title ${t.dataset_title_matches_video ? 'correct' : 'does not match the video'}. ${esc(t.summary || '')}</p>
          ${(t.problems || []).length ? `<ul class="problems">${t.problems.map((p) => `<li>${p.task_index != null ? `<button class="ts" data-goto-task="${p.task_index}">T${p.task_index + 1}</button> ` : ''}<span class="ptype">${esc(p.type || '')}</span>: ${esc(p.issue)}${p.correct_task ? ` <span class="fix">→ ${esc(p.correct_task)}</span>` : ''}</li>`).join('')}</ul>` : ''}` : ''}
        ${(txt?.flags || []).length ? `<div>${txt.flags.map(([k, d]) => `<span class="flag" title="${esc(d)}">${esc(k)}</span>`).join('')}</div>` : ''}
        ${vis?.errors ? `<p style="color:var(--red)">${vis.errors} subtask(s) could not be judged (model error); re-validate to retry.</p>` : ''}
      </details>`
    : `<p class="muted">Not validated yet${fin?.precheck ? ` (quick pre-check from YouTube info only: <b>${esc(VERDICTS[fin.precheck]?.label || fin.precheck)}</b>)` : ''}.
        Validate checks every subtask against what is shown and said in its own time range, and the tasks against the YouTube title and description,
        then gives one verdict and the correct task for every one that does not match. About 1–3 minutes.</p>`}
    <div class="storage-row">
      <span class="muted">On disk: video ${mb(m.video_bytes || 0)} · audio ${mb(m.audio_bytes || 0)} · frames ${mb(m.frames_bytes || 0)}</span>
      <span>${local ? `<button class="btn danger-outline" data-act="delete-media-keep" title="Frames, results, transcript and your review stay">🗑 Delete local video</button>` : ''}
        ${local || m.frames_bytes ? `<button class="btn danger-outline" data-act="delete-media" title="Results, transcript and your review stay">🗑 Delete video + frames</button>` : ''}</span>
    </div>
  </div>`;
}

function renderInfo() {
  const { record: rec, meta } = S.detail;
  const tasks = rec.tasks || [];
  const subs = tasks.reduce((s, t) => s + (t.subtasks || []).length, 0);
  const R = S.review;
  const seg = (field, value, cls, label) => `<button class="seg ${cls} ${R[field] === value ? 'on' : ''}" data-review="${field}" data-val="${value}">${label}</button>`;
  const full = S.detail.final?.stage === 'full';

  $('#info').innerHTML = `<div class="info">
    <div class="muted">Dataset title</div>
    <h2>${esc(rec.title)}</h2>
    ${meta && !meta.error ? `<p class="yt-title">YouTube: <b>${esc(meta.title)}</b> · ${esc(meta.channel)}</p>`
      : meta?.error ? `<p class="yt-title" style="color:var(--red)">${esc(meta.error)}</p>` : ''}
    <div class="video-meta"><span>${tasks.length} tasks</span><span>${subs} subtasks</span>
      ${meta?.duration ? `<span>${fmt(meta.duration)} long</span>` : ''}
      <a class="youtube-link" href="${esc(rec.url)}" target="_blank" rel="noopener">Watch on YouTube ↗</a></div>

    ${validationPanel()}

    <div class="panel">
      <h3><span>Your review</span><span class="saved" id="saved">${S.detail.review?.updated ? 'Saved ' + esc(S.detail.review.updated) : ''}</span></h3>
      <div class="muted" style="margin-bottom:6px">Watching the video, do the extracted tasks make sense?</div>
      <div class="review-row">${seg('makes_sense', 'yes', 'yes', 'Yes')}${seg('makes_sense', 'partly', 'unsure', 'Partly')}${seg('makes_sense', 'no', 'no', 'No')}</div>
      ${full ? `<div class="muted" style="margin-bottom:6px">Do you agree with the validator's verdict?</div>
      <div class="review-row">${seg('agree', 'yes', 'yes', 'Agree')}${seg('agree', 'no', 'no', 'Disagree')}${seg('agree', 'unsure', 'unsure', 'Unsure')}
        ${R.agree === 'no' ? `<select id="rv-correct"><option value="">Correct verdict…</option>${Object.entries(VERDICTS).filter(([k]) => k !== 'ERROR')
          .map(([k, m]) => `<option value="${k}" ${R.correct_verdict === k ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}</select>` : ''}</div>` : ''}
      <textarea id="rv-notes" rows="3" placeholder="Notes (what is wrong, at what time)…">${esc(R.notes)}</textarea>
      <div class="legend">Mark subtasks ✓/✗ and accept or edit suggested corrections in the task tree below. Everything saves automatically.</div>
    </div></div>`;
  const notes = $('#rv-notes');
  notes.addEventListener('input', () => { S.review.notes = notes.value; queueSave(); });
  const sel = $('#rv-correct');
  if (sel) sel.onchange = () => { S.review.correct_verdict = sel.value; queueSave(); };
}

function renderTree() {
  const { record: rec, validation: val, results, final: fin } = S.detail;
  const tasks = rec.tasks || [];
  const issues = {};
  for (const p of val?.llm?.problems || []) if (p.task_index != null) (issues[p.task_index] ||= []).push(p);
  const marks = S.review.tasks || {};
  const vis = {};
  if (fin?.stage === 'full') for (const s of results?.subtasks || []) vis[`${s.task}.${s.sub}`] = s;
  const framesOK = S.detail.media?.has_frames;

  const visBlock = (ti, sj) => {
    const v = vis[`${ti}.${sj}`];
    if (!v) return '';
    const mt = MATCH[v.match];
    const key = `t${ti}.s${sj}`;
    const rw = (S.review.rewrites || {})[key];
    const sug = (v.correct_task || '').trim();
    const thumbs = framesOK && v.frames?.length ? `<div class="thumbs">${v.frames.map((f, k) => `
      <button class="thumb" data-seek="${v.times?.[k] ?? v.start}" title="Play from ${fmt(v.times?.[k] ?? v.start)}">
        <img loading="lazy" src="/media/${esc(currentVid)}/raw/${esc(f)}" alt="" onerror="this.parentElement.remove()">
        <span>${fmt(v.times?.[k] ?? v.start)}</span></button>`).join('')}</div>` : '';
    return `<div class="vis-block">
      ${thumbs}
      <div class="vis-text">
        ${mt ? `<span class="badge" style="background:${mt.color}" title="${esc(mt.desc)}">${esc(mt.label)}</span>` : ''}
        ${v.what_is_happening ? `<span><b>What is going on:</b> ${esc(v.what_is_happening)}</span>` : ''}
        ${v.issue ? `<span class="vis-issue">${esc(v.issue)}</span>` : ''}${v.error ? `<span class="vis-issue">${esc(v.error)}</span>` : ''}</div>
      ${v.speech ? `<div class="vis-speech"><b>Said in this window:</b> “${esc(v.speech.length > 260 ? v.speech.slice(0, 260) + '…' : v.speech)}”</div>` : ''}
      ${v.correct_time ? `<div class="suggestion"><span><b>Correct time:</b> this is said at
        <button class="ts" data-seek="${v.correct_time[0]}" title="Play from here">${fmt(v.correct_time[0])} – ${fmt(v.correct_time[1])}</button>
        in the video, not at its dataset timestamp</span></div>` : ''}
      ${sug ? `<div class="suggestion"><span><b>Correct subtask:</b> ${esc(sug)}</span>
        ${rw == null ? `<button class="btn small" data-use-suggestion="${key}" data-text="${esc(sug)}">Use as correction</button>` : ''}</div>` : ''}
      ${rw != null ? `<div class="rewrite"><label>Your corrected subtask:</label>
        <input class="rewrite-input" data-rewrite="${key}" value="${esc(rw)}">
        <button class="btn small" data-clear-rewrite="${key}" title="Remove the correction">×</button></div>` : ''}
    </div>`;
  };
  const visCls = (ti, sj) => ({ YES: 'vis-yes', PARTLY: 'vis-partly', NO: 'vis-no' }[vis[`${ti}.${sj}`]?.match] || '');
  const markBtns = (key) => `<span class="marks">
    <button class="mark ok ${marks[key] === 'ok' ? 'on' : ''}" data-mark="${key}" data-val="ok" title="Makes sense">✓</button>
    <button class="mark wrong ${marks[key] === 'wrong' ? 'on' : ''}" data-mark="${key}" data-val="wrong" title="Does not make sense">✗</button></span>`;
  const ts = (o) => (o.start != null ? `<button class="ts" data-seek="${o.start}" title="Play from here">${fmt(o.start)} – ${fmt(o.end)}</button>` : '<span class="flag">no timestamp</span>');

  $('#tree').innerHTML = `<div class="tree-section"><h3>Task Tree</h3>
    <p class="tree-hint">Click a timestamp or frame to play that moment above. Each subtask shows its frames, what is said in its time range, and whether
      that matches it (green matches · amber partly · red does not match). Where it does not, the correct subtask is given; <b>Use as correction</b> copies it into your review.</p>
    <div class="tree-container">${tasks.map((t, i) => `
      <div class="tree-node" id="task-${i}">
        <div class="tree-label ${issues[i] ? 'flagged' : ''}">
          <button class="tree-toggle expanded" data-toggle="${i}">▶</button>
          <span class="tree-icon task">T${i + 1}</span>
          <span class="tree-text">${esc(t.task)}</span>${ts(t)}${markBtns('t' + i)}
        </div>
        ${(issues[i] || []).map((p) => `<div class="task-issue">⚠ ${esc(p.type)}: ${esc(p.issue)}${p.correct_task
          ? `<div class="fix">Correct task: ${esc(p.correct_task)}${(S.review.rewrites || {})['t' + i] == null
            ? ` <button class="btn small" data-use-suggestion="t${i}" data-text="${esc(p.correct_task)}">Use as correction</button>` : ''}</div>` : ''}</div>`).join('')}
        ${(S.review.rewrites || {})['t' + i] != null ? `<div class="rewrite task-rewrite"><label>Your corrected task:</label>
          <input class="rewrite-input" data-rewrite="t${i}" value="${esc(S.review.rewrites['t' + i])}">
          <button class="btn small" data-clear-rewrite="t${i}" title="Remove the correction">×</button></div>` : ''}
        <div class="tree-children" id="children-${i}">${(t.subtasks || []).map((s, j) => `
          <div class="subtask ${visCls(i, j)}">
            <div class="tree-label"><span class="tree-toggle"></span><span class="tree-icon subtask">${i + 1}.${j + 1}</span>
              <span class="tree-text">${esc(s.text)}</span>${ts(s)}${markBtns(`t${i}.s${j}`)}</div>
            ${visBlock(i, j)}
          </div>`).join('')}
        </div>
      </div>`).join('')}</div></div>`;
}

let saveTimer = null;
function queueSave() {
  clearTimeout(saveTimer);
  const el = $('#saved');
  if (el) el.textContent = 'Saving…';
  const vid = currentVid, body = JSON.parse(JSON.stringify(S.review));
  saveTimer = setTimeout(async () => {
    try {
      const r = await postJSON(`/api/videos/${vid}/review`, body);
      if (S.detail && currentVid === vid) S.detail.review = r;
      const e2 = $('#saved');
      if (e2) { e2.textContent = 'Saved ✓'; e2.style.color = ''; }
      const v = S.videos.find((x) => x.video_id === vid);
      if (v) v.reviewed = !!(body.makes_sense || body.agree);
    } catch (e) { const e3 = $('#saved'); if (e3) { e3.textContent = 'Not saved: ' + e.message; e3.style.color = 'var(--red)'; } }
  }, 400);
}

/* ---------------- How it works ---------------- */

function diagram() {
  // boxes: blue = evidence collected, purple = LLM, gray = exact code (no AI), green = you
  const box = (x, y, w, h, cls, title, body) => `
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" class="bx ${cls}"/>
    <foreignObject x="${x}" y="${y}" width="${w}" height="${h}">
      <div xmlns="http://www.w3.org/1999/xhtml" class="bx-text"><b>${title}</b><span>${body}</span></div></foreignObject>`;
  const line = (d, cls = 'ar') => `<path d="${d}" class="${cls}"/>`;
  const lane = (y, h, cls, label, right = false) => `<rect x="20" y="${y}" width="1070" height="${h}" rx="14" class="lane ${cls}"/>
    <text x="${right ? 1070 : 40}" y="${y + 24}" ${right ? 'text-anchor="end"' : ''} class="lane-label ${cls}">${label}</text>`;
  const P = [40, 310, 580, 850], PW = 220;   // the two 4-box rows
  const C = [40, 300, 560, 840];             // the four columns of the Validate lane
  const H = 96;
  return `<svg viewBox="0 0 1110 900" class="how-svg" role="img" aria-label="Diagram: how a video is validated">
    <title>How a video is validated: Validate collects tasks, YouTube info, frames and speech,
      checks them with exact rules and the LLM, and computes one verdict; then you review and export.</title>
    <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" class="ar-head"/></marker></defs>

    <text x="40" y="26" class="lane-label pipe">Input</text>
    ${box(P[0], 40, P[3] + PW - P[0], 84, 'pipe', 'Dataset: data/*.json', 'one file per YouTube video: its tasks, subtasks and their timestamps · <i>what we validate</i> (only read)')}

    ${lane(160, 520, 'txt', '① Validate: one click per video · runs in the Jobs queue, two videos at a time, about 1–3 minutes each')}
    ${line(`M${P[3] + PW / 2},124 V146 H28 V253 H${C[0] - 3}`, 'ar spine')}
    ${box(C[0], 205, 210, H, 'txt', 'Tasks + timestamps', 'every task and subtask with its start and end time, from the dataset JSON')}
    ${box(C[0], 318, 210, H, 'txt', 'YouTube page info', 'title, description and creator chapters (fetched once, saved)')}
    ${box(C[0], 431, 210, H, 'txt', 'Download video + sound', 'one 360p .mp4 per video (yt-dlp); can be deleted afterwards')}
    ${box(C[1], 431, 210, H, 'txt', 'Frames', 'a frame about every 5 s inside each subtask\'s time range (4–12 per subtask)')}
    ${box(C[1], 545, 210, 104, 'txt', 'Speech-to-text', 'Whisper on this PC: the whole video once, then the words inside each subtask\'s range')}
    ${box(C[2], 205, 230, H, 'code', 'Exact rules (code)', 'timestamps inside the video? tasks overlapping? subtasks inside the right YouTube chapter?')}
    ${box(C[2], 318, 230, H, 'llm', 'LLM: task list vs YouTube info', 'are these tasks about this video? is the dataset title right? correct task for every problem')}
    ${box(C[2], 470, 230, 120, 'llm', 'LLM: each subtask', 'its frames + its speech + its text → <b>matches?</b> yes / partly / no · what is going on · the <b>correct subtask</b> if not')}
    ${box(C[3], 250, 230, 120, 'code', 'One verdict (code, not the LLM)', 'Matches · Partly matches · Does not match · Unavailable, with the reasons')}
    ${box(C[3], 470, 230, 120, 'txt', 'Results per subtask', 'frames, what was said, the result, the correction, and the correct time if it is said elsewhere in the video')}
    ${line(`M${C[0] + 210},253 H${C[2] - 3}`)}
    ${line(`M${C[0] + 210},366 H${C[2] - 3}`)}
    ${line(`M${C[0] + 210},479 H${C[1] - 3}`)}
    ${line(`M${C[0] + 210},505 H${C[0] + 235} V597 H${C[1] - 3}`)}
    ${line(`M${C[1] + 210},479 H${C[1] + 235} V505 H${C[2] - 3}`)}
    ${line(`M${C[1] + 210},597 H${C[1] + 235} V560 H${C[2] - 3}`)}
    ${line(`M${C[2] + 230},253 H${C[2] + 255} V285 H${C[3] - 3}`)}
    ${line(`M${C[2] + 230},366 H${C[3] - 3}`)}
    ${line(`M${C[2] + 230},530 H${C[3] - 3}`)}
    ${line(`M${C[3] + 115},470 V${250 + 120 + 3}`)}
    <text x="${C[3] + 123}" y="425" class="note">counted into</text>
    <text x="40" y="665" class="note">blue: evidence collected · purple: the LLM set in .env · gray: exact code, no AI</text>

    ${lane(700, 148, 'hum', '② Your review: the ground truth', true)}
    ${line(`M${C[3] + 115},590 V690 H${P[0] + PW / 2} V738`, 'ar spine')}
    ${box(P[0], 740, PW, 92, 'hum', 'Watch here', 'click a timestamp or frame: the player jumps there')}
    ${box(P[1], 740, PW, 92, 'hum', 'Judge', 'do the tasks make sense? ✓/✗ each; accept or edit the corrections')}
    ${box(P[2], 740, PW, 92, 'hum', 'Saved automatically', 'kept with the video; survives deleting the download')}
    ${box(P[3], 740, PW, 92, 'hum', 'Export CSV', 'verdict, reasons, wrong subtasks, corrections, your notes')}
    ${[0, 1, 2].map((i) => line(`M${P[i] + PW},786 H${P[i + 1] - 3}`)).join('')}
    <text x="555" y="880" text-anchor="middle" class="foot">Whisper, downloads and rules run on this PC; only the LLM calls go to the model server.</text>
  </svg>`;
}

function renderHow() {
  const vrow = (o) => Object.entries(o).filter(([k]) => k !== 'ERROR')
    .map(([, m]) => `<tr><td><span class="badge" style="background:${m.color}">${esc(m.label)}</span></td><td>${esc(m.desc)}</td></tr>`).join('');
  $('#page').innerHTML = `<div class="how-page">
    <h2>How the validation works</h2>
    <p class="subtitle">One Validate per video, using every source of evidence, then your review.</p>
    <div class="how-diagram">${diagram()}</div>

    <div class="how-cards">
      <div class="how-card txt"><h3>What Validate looks at</h3>
        <p><b>YouTube info:</b> title, description and chapters, to catch tasks about a different video and wrong dataset titles.</p>
        <p><b>Frames:</b> the video is downloaded once (360p, with sound); a frame about every 5 seconds inside each subtask's own time range (4–12 per subtask).</p>
        <p><b>Speech:</b> every word said in that same time range. Whisper runs on this PC on the video's sound (non-English is translated);
          if transcript files are provided (<code>TRANSCRIPTS_DIR</code>), those are used instead, matched by segment id.</p></div>
      <div class="how-card vis"><h3>What it decides</h3>
        <p>For every subtask: does what is going on in its time range (shown in the frames and said in the speech) <b>match it</b>: yes, partly or no.
          It is lenient about wording (a task that says "observe X" matches if X is said) and strict about facts (a different crop, tool,
          number, name or step makes it partly).
          If not, it writes the <b>correct subtask</b> for that part of the video, and searches the whole transcript for where the subtask
          is actually said: if that is at another time, it gives the <b>correct time</b> (the dataset's timestamps are often shifted).</p>
        <p>For the video: one verdict (matches / partly matches / does not match), computed by fixed rules from all of the above, not chosen by the LLM, with the reasons listed.</p>
        <p><b>Limits:</b> very short actions can fall between frames; speech-to-text can mishear names; the LLM can be wrong, so confirm by watching.</p></div>
      <div class="how-card hum"><h3>Your review</h3>
        <p>You watch the real video with sound, the only check that sees and hears everything. Start with the videos the validator flags.</p>
        <p><b>Output:</b> the corrected task file of every validated video is saved in <code>output/tasks/</code>, in the same format as <code>data/</code>, with your corrections applied. Export CSV gives one row per video: verdict, reasons, corrections, notes.</p></div>
    </div>

    <h3 class="how-h3">Where the timestamps come from</h3>
    <p class="how-p">A subtask's timestamps usually mark when it is <i>talked about</i>. The action itself can happen a few seconds,
      or much more, before or after. That is why each subtask is judged on both the frames and the speech of its own time range.</p>

    <h3 class="how-h3">Which LLM does the judging</h3>
    <p class="how-p">Whichever the project's <code>.env</code> file names: <b>LLM_PROVIDER</b>, <b>LLM_URL</b>, <b>LLM_API_KEY</b>, <b>LLM_MODEL</b>. It works with the
      a local OpenAI-compatible server, OpenAI, or Anthropic's Claude: change those lines (see <code>.env.example</code>) and restart the dashboard.
      The LLM must accept images; it receives the speech as text, so it does not need to accept audio.
      Every instruction sent to the LLM is a plain text file in <code>validator/llm/prompts/</code>. In use now: <b id="how-llm">…</b></p>

    <h3 class="how-h3">Storage</h3>
    <p class="how-p">Validate downloads each video once as a 360p file with sound (roughly 2–10 MB per minute); the Whisper model (about 145 MB) is downloaded once into
      <code>work/models</code>. The <b>Local storage</b> panel on the Dataset tab shows the disk used and deletes all local videos in one click; each video page has
      <b>Delete local video</b>; or tick <b>Delete videos after</b> before validating. Deleting never touches verdicts, results, transcripts or your reviews.</p>

    <div class="how-legends">
      <div><h3 class="how-h3">Verdicts</h3><table class="legend-table">${vrow(VERDICTS)}</table></div>
      <div><h3 class="how-h3">Per-subtask results</h3><table class="legend-table">${vrow(MATCH)}</table></div>
    </div>
  </div>`;
  api('/api/settings').then((s) => {
    const el = $('#how-llm');
    if (el) el.textContent = `provider ${s.llm.provider}, model ${s.llm.model}${s.provided_transcripts ? ' · provided transcripts: on' : ''} · Whisper model: ${s.whisper_model}`;
  }).catch(() => {});
}

/* ---------------- events + routing ---------------- */

document.addEventListener('click', async (e) => {
  const el = (sel) => e.target.closest(sel);
  let x;
  if ((x = el('[data-check]'))) {
    e.preventDefault(); e.stopPropagation();
    const id = x.dataset.check;
    S.selected.has(id) ? S.selected.delete(id) : S.selected.add(id);
    renderGrid(); return;
  }
  if ((x = el('[data-card]'))) { location.hash = '#/video/' + x.dataset.card; return; }
  if ((x = el('[data-filter]'))) { S.filter = x.dataset.filter; S.page = 1; renderGrid(); return; }
  if ((x = el('[data-page]'))) { if (!x.disabled) { S.page = +x.dataset.page; renderGrid(); window.scrollTo(0, 0); } return; }
  if ((x = el('[data-seek]'))) { seek(+x.dataset.seek); return; }
  if ((x = el('[data-goto-task]'))) {
    const i = +x.dataset.gotoTask;
    const node = $('#task-' + i);
    if (node) node.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const st = S.detail.record.tasks?.[i]?.start;
    if (st != null) seek(st);
    return;
  }
  if ((x = el('[data-toggle]'))) {
    const c = $('#children-' + x.dataset.toggle);
    const open = c.style.display !== 'none';
    c.style.display = open ? 'none' : ''; x.classList.toggle('expanded', !open); return;
  }
  if ((x = el('[data-mark]'))) {
    const k = x.dataset.mark, v = x.dataset.val;
    S.review.tasks = { ...(S.review.tasks || {}) };
    if (S.review.tasks[k] === v) delete S.review.tasks[k]; else S.review.tasks[k] = v;
    renderTree(); queueSave(); return;
  }
  if ((x = el('[data-review]'))) {
    const f = x.dataset.review, v = x.dataset.val;
    S.review[f] = S.review[f] === v ? null : v;
    if (f === 'agree' && S.review.agree !== 'no') S.review.correct_verdict = '';
    renderInfo(); queueSave(); return;
  }
  if ((x = el('[data-use-suggestion]'))) {
    const k = x.dataset.useSuggestion;
    S.review.rewrites = { ...(S.review.rewrites || {}), [k]: x.dataset.text };
    S.review.tasks = { ...(S.review.tasks || {}), [k]: 'wrong' };  // replacing it means the original was wrong
    renderTree(); queueSave(); return;
  }
  if ((x = el('[data-queue-remove]'))) {
    try { await api('/api/queue/' + x.dataset.queueRemove, { method: 'DELETE' }); } catch (err) { alert(err.message === 'running' ? 'A running job cannot be stopped.' : err.message); }
    pollQueue(true); return;
  }
  if ((x = el('[data-queue-retry]'))) {
    x.disabled = true;
    const r = await postJSON(`/api/queue/${x.dataset.queueRetry}/retry`, {});
    if (!r.ok) toast('This video is already in the queue');
    pollQueue(true); return;
  }
  if ((x = el('[data-clear-rewrite]'))) {
    const r = { ...(S.review.rewrites || {}) }; delete r[x.dataset.clearRewrite];
    S.review.rewrites = r; renderTree(); queueSave(); return;
  }
  if (!(x = el('[data-act]'))) return;
  const act = x.dataset.act;
  if (act === 'sel-page') { filtered().slice((S.page - 1) * PER_PAGE, S.page * PER_PAGE).forEach((v) => S.selected.add(v.video_id)); renderGrid(); }
  if (act === 'sel-clear') { S.selected.clear(); S.selectedOnly = false; renderGrid(); }
  if (act === 'sel-random' || act === 'sel-sample') {
    const ids = await api('/api/sample?n=20' + (act === 'sel-sample' ? '&seed=42' : ''));
    S.selected = new Set(ids); S.selectedOnly = true; S.page = 1; renderGrid();
  }
  if (act === 'validate-sel') { const ids = toValidate(); if (ids.length) { x.disabled = true; enqueue(ids, S.force); } }
  if (act === 'validate-one') {
    x.disabled = true;
    S.detail.queue = 'queued';  // shown immediately; the poll refreshes it to "Validating" when a worker picks it up
    $('#info').querySelector('[data-act="validate-one"]').outerHTML = '<button class="btn primary" disabled>In queue</button>';
    enqueue([currentVid], S.detail.final?.stage === 'full');
  }
  if (act === 'queue-clear') { await postJSON('/api/queue/clear', {}); pollQueue(true); }
  if (act === 'delete-media' || act === 'delete-media-keep') {
    const keep = act === 'delete-media-keep';
    if (!confirm(`Permanently delete this video's downloaded ${keep ? 'video and audio files' : 'video, audio and frames'} from this computer?\n\n`
      + 'Kept: the verdict, all results, the transcript and your review.')) return;
    x.disabled = true;
    const freed = await deleteMedia({ ids: [currentVid], keep_frames: keep });
    await reloadDetail(currentVid);
    const e2 = $('.storage-row .muted');
    if (e2) e2.textContent = `Deleted: freed ${mb(freed)}. Results kept.`;
  }
  if (act === 'storage-free' || act === 'storage-all') {
    const keep = act === 'storage-free';
    if (!confirm(`Permanently delete ALL downloaded ${keep ? 'videos and audio' : 'videos, audio and frames'} from this computer?\n\n`
      + 'Kept: every verdict, result, transcript and your reviews. A video is downloaded again if you re-validate it.')) return;
    x.disabled = true;
    const freed = await deleteMedia({ all: true, keep_frames: keep });
    renderGrid();
    alert(`Freed ${mb(freed)}.`);
  }
});

document.addEventListener('input', (e) => {
  const k = e.target.dataset?.rewrite;
  if (!k) return;
  S.review.rewrites = { ...(S.review.rewrites || {}), [k]: e.target.value };
  queueSave();
});

async function route() {
  const h = location.hash || '#/';
  const tab = h.startsWith('#/how') ? 'how' : h.startsWith('#/jobs') ? 'jobs' : 'dataset';
  document.querySelectorAll('.nav-links a').forEach((a) => a.classList.toggle('active', a.dataset.nav === tab));
  if (h.startsWith('#/video/')) { await renderVideo(decodeURIComponent(h.slice(8))); window.scrollTo(0, 0); }
  else if (h.startsWith('#/how')) { leaveVideo(); renderHow(); window.scrollTo(0, 0); }
  else if (h.startsWith('#/jobs')) { leaveVideo(); renderJobs(); window.scrollTo(0, 0); pollQueue(true); }
  else { leaveVideo(); renderDataset(); }
}

(async function init() {
  try { S.videos = await api('/api/videos'); } catch (e) { $('#page').innerHTML = `<p class="loading">Could not reach the dashboard server: ${esc(e.message)}</p>`; return; }
  window.addEventListener('hashchange', route);
  await route();
  try { sessionStorage.removeItem('job'); } catch { /* storage unavailable */ }  // used by the old one-off job panel
  await pollQueue(true);
  setInterval(pollQueue, 3000);  // one poll for the whole app: nav count, cards, video page, Jobs tab
})();
