/* =========================================================================
   VIGÍA-ENFERMERÍA — terminal app logic
   Vanilla JS. No framework.
   ========================================================================= */

const SOURCE_LABEL = {
  'boe':                 'BOE',
  'bocm':                'BOCM',
  'boam':                'BOAM',
  'comunidad_madrid':    'COMUNIDAD',
  'ayuntamiento_madrid': 'AYTO MADRID',
  'canal_isabel_ii':     'CANAL II',
  'codem':               'CODEM',
  'datos_madrid':        'DATOS MAD',
  'metro_madrid':        'METRO',
  'administracion_gob':  'ADMIN GOB',
};
const CAT_LABEL = {
  'oposicion':    'OPOSICIÓN',
  'bolsa':        'BOLSA',
  'traslado':     'TRASLADO',
  'nombramiento': 'NOMBRAMTO',
  'oep':          'OEP',
  'otro':         'OTRO',
};
const CAT_COLOR = {
  'oposicion':    '#39ff14',
  'bolsa':        '#ffb000',
  'traslado':     '#6cb4ff',
  'nombramiento': '#c46cff',
  'oep':          '#ff6c8a',
  'otro':         '#888888',
};

let DATA = { items: [], sources: [], meta: {} };

/* ---- bootstrap ------------------------------------------------------- */
async function loadData() {
  const items   = await fetch('data/items.json').then(r => r.json());
  const sources = await fetch('data/sources_status.json').then(r => r.json());
  const meta    = await fetch('data/meta.json').then(r => r.json());
  DATA = { items, sources, meta };
}

document.addEventListener('DOMContentLoaded', async () => {
  try {
    await loadData();
  } catch (err) {
    console.error('failed to load data', err);
    return;
  }
  renderStatusBar();
  renderHero();
  renderCounters();
  renderFeed();
  renderHistorical();
  renderIntel();
  renderSources();
  renderWatchlist();
  renderSubscribe();
  renderHowItWorks();
  renderFooter();
  initTweaks();
});

/* ---- helpers --------------------------------------------------------- */
const $  = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
const fmtDate = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toISOString().slice(0, 10);
};
const fmtTime = (iso) => {
  const d = new Date(iso);
  return d.toISOString().slice(11, 19) + 'Z';
};
const ago = (iso) => {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 60) return m + 'm';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h';
  return Math.floor(h / 24) + 'd';
};
const escapeHTML = (s) => String(s ?? '').replace(/[&<>"']/g, c => (
  {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
));

/* Mini-renderer de Markdown inline para el summary del enricher. Cubre los
   estilos que produce Claude Haiku en respuestas cortas: **bold**, *italic*,
   `code` y saltos de línea. Anti-XSS: escapamos HTML antes de aplicar las
   reglas, así cualquier marcado del LLM queda reducido a texto. */
function renderInlineMarkdown(s) {
  let out = escapeHTML(s);
  // Bold antes que italic para que **foo** no sea comido por *foo*.
  out = out.replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/__([^_\n]+?)__/g,     '<strong>$1</strong>');
  out = out.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, '$1<em>$2</em>');
  out = out.replace(/`([^`\n]+?)`/g, '<code>$1</code>');
  out = out.replace(/\n{2,}/g, '<br><br>').replace(/\n/g, '<br>');
  return out;
}

/* ---- count-up animation --------------------------------------------- */
function countUp(el, target, dur=1400) {
  const start = performance.now();
  const from = 0;
  const step = (t) => {
    const k = Math.min(1, (t - start) / dur);
    const eased = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(from + (target - from) * eased).toLocaleString('en-US');
    if (k < 1) requestAnimationFrame(step);
    else el.textContent = target.toLocaleString('en-US');
  };
  requestAnimationFrame(step);
}

/* ---- 1. Status bar --------------------------------------------------- */
function renderStatusBar() {
  const m = DATA.meta;
  const lastRunAgo = ago(m.last_run_at);
  const next = new Date(m.next_run_at);
  const dayShort = next.toLocaleDateString('es-ES', {
    weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'UTC',
  }).replace('.', '').toUpperCase();
  const nextStr = `${dayShort} ${next.toISOString().slice(11, 16)} UTC`;
  $('#statusbar').innerHTML = `
    <span class="item"><span class="dot"></span><span class="val">SYSTEM ONLINE</span></span>
    <span class="sep">│</span>
    <span class="item"><span class="label">LAST RUN</span><span class="val">T-${lastRunAgo}</span></span>
    <span class="sep">│</span>
    <span class="item"><span class="label">NEXT RUN</span><span class="val">${nextStr}</span></span>
    <span class="sep">│</span>
    <span class="item"><span class="label">SOURCES</span><span class="val ${m.sources_online === m.sources_total ? '' : 'amber'}">${m.sources_online}/${m.sources_total} OK</span></span>
    <span class="sep">│</span>
    <span class="item right"><span class="label">UTC</span><span class="val" id="utc-clock">${new Date().toISOString().slice(11,19)}</span></span>
  `;
  setInterval(() => {
    const e = $('#utc-clock');
    if (e) e.textContent = new Date().toISOString().slice(11, 19);
  }, 1000);
}

/* ---- 1b. Hero -------------------------------------------------------- */
function renderHero() {
  const ascii = $('#ascii-logo'); if (ascii) ascii.textContent = '';
  if (!$('#hero-meta')) return;
  $('#hero-meta').innerHTML = `
    <span class="glyph">[▮]</span>
    <span>NODE</span><span class="v">vigía-01</span>
    <span class="sep">/</span>
    <span>BUILD</span><span class="v">${DATA.meta.version}</span>
    <span class="sep">/</span>
    <span>HEAD</span><span class="v">${DATA.meta.commit}</span>
    <span class="right"><span class="dot"></span>SYSTEM ONLINE</span>
  `;
  $('#hero-title').innerHTML = `<span class="bracket">/</span>&nbsp;vigía-enfermería&nbsp;<span class="cursor">▮</span>`;
  $('#hero-tagline').innerHTML = `
    <span class="prefix">$ ./vigía --whoami</span><br>
    Automated surveillance of Spanish public-sector job postings for
    <b style="color:var(--phos)">Occupational Health Nursing</b>. Polls 8 official
    bulletins daily, hashes findings, enriches with Claude Haiku, dispatches
    to Telegram. Built with paranoia. Public log.
  `;
}

/* ---- 1c. Counters ---------------------------------------------------- */
function renderCounters() {
  const m = DATA.meta;
  const cs = [
    { id: 'C-01', label: 'DAYS WATCHING',  val: m.days_watching,  delta: 'CONTINUOUS UPTIME SINCE ' + ((m.first_seen_at || new Date().toISOString()).slice(0, 10)) },
    { id: 'C-02', label: 'ITEMS LOGGED',   val: m.total_items,    delta: '+' + m.total_today + ' DETECTED LAST 24H' },
    { id: 'C-03', label: 'SOURCES ONLINE', val: m.sources_online, delta: m.sources_total - m.sources_online + ' SKIPPED — SEE TARGETS', deltaAmber: true, suffix: '/' + m.sources_total },
  ];
  $('#counters').innerHTML = cs.map(c => `
    <div class="counter flickerable">
      <div class="label"><span>${c.label}</span><span class="id">${c.id}</span></div>
      <div class="val"><span data-counter="${c.val}">0</span>${c.suffix||''}</div>
      <div class="delta ${c.deltaAmber?'amber':''}">› ${c.delta}</div>
    </div>
  `).join('');
  $$('[data-counter]').forEach(el => countUp(el, +el.dataset.counter));
}

/* ---- 2. Daily feed --------------------------------------------------- */
function isToday(iso) {
  // For demo purposes: items first_seen_at on the meta.last_run_at date
  const ref = DATA.meta.last_run_at.slice(0, 10);
  return (iso || '').slice(0, 10) === ref;
}
function renderFeed() {
  const today = DATA.items
    .filter(it => isToday(it.first_seen_at))
    .sort((a,b) => b.first_seen_at.localeCompare(a.first_seen_at));
  const root = $('#feed');
  if (today.length === 0) {
    root.innerHTML = `
      <div class="feed-empty">
        <div class="glyph">[ ◌ ]</div>
        <div class="msg">NO ANOMALIES DETECTED — STANDING BY</div>
        <div class="sub">Next probe scheduled for ${fmtTime(DATA.meta.next_run_at)}</div>
      </div>`;
    $('#feed-meta').textContent = 'NO HITS · STANDING BY';
    return;
  }
  $('#feed-meta').textContent = today.length + ' HITS · ' + fmtDate(DATA.meta.last_run_at);
  root.innerHTML = today.map((it, i) => cardHTML(it, i)).join('');
  $$('#feed .card').forEach(c => {
    c.querySelector('.head').addEventListener('click', () => c.classList.toggle('open'));
    c.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', e => {
      e.stopPropagation();
      navigator.clipboard?.writeText(b.dataset.copy);
      b.classList.add('copied');
      const orig = b.textContent;
      b.textContent = '✓ COPIED';
      setTimeout(() => { b.classList.remove('copied'); b.textContent = orig; }, 1200);
    }));
    c.querySelectorAll('a').forEach(a => a.addEventListener('click', e => e.stopPropagation()));
  });
  // open the first one by default
  $('#feed .card')?.classList.add('open');
}
function cardHTML(it, i) {
  return `
    <div class="card" data-id="${it.id_hash}">
      <div class="head">
        <div class="ts">[${fmtDate(it.first_seen_at)}] <span class="age">T-${ago(it.first_seen_at)}</span></div>
        <div><span class="badge src ${it.source}">${SOURCE_LABEL[it.source] || it.source.toUpperCase()}</span></div>
        <div class="title">${escapeHTML(it.titulo)}</div>
        <div style="display:flex;gap:8px;align-items:center;">
          <span class="badge cat">${CAT_LABEL[it.categoria] || it.categoria}</span>
          <span class="chev">▶</span>
        </div>
      </div>
      <div class="body">
        <div class="meta-grid">
          <div>ID_HASH       <b>${it.id_hash}</b></div>
          <div>PUB DATE      <b>${fmtDate(it.fecha)}</b></div>
          <div>FIRST SEEN    <b>${fmtDate(it.first_seen_at)} ${fmtTime(it.first_seen_at)}</b></div>
          <div>SOURCE        <b>${SOURCE_LABEL[it.source]}</b></div>
          <div>CATEGORY      <b>${CAT_LABEL[it.categoria]}</b></div>
          <div>DETECTION LAG <b>${detectionLag(it)} </b></div>
        </div>
        <div class="summary-block">
          <span class="lbl">› AI SUMMARY (claude-haiku-4.5)</span>
          ${renderInlineMarkdown(it.summary)}
        </div>
        <div class="actions">
          <a href="${it.url}" target="_blank" rel="noopener" class="btn-term">OPEN SOURCE →</a>
          <button class="btn-term ghost" data-copy="${it.url}">COPY PERMALINK</button>
          <button class="btn-term ghost" data-copy="${it.id_hash}">COPY HASH</button>
        </div>
      </div>
    </div>`;
}
function detectionLag(it) {
  const a = new Date(it.fecha).getTime();
  const b = new Date(it.first_seen_at).getTime();
  const days = Math.max(0, Math.round((b - a) / 86400000));
  return days === 0 ? 'SAME DAY' : days + 'd';
}

/* ---- 3. Historical DB ----------------------------------------------- */
const filterState = {
  source:'',
  category:'',
  from:'',
  to:'',
  q:'',
  sortKey:'first_seen_at',
  sortDir:'desc',
  expanded: null,
};

function renderHistorical() {
  // build filter UI
  const sources = Array.from(new Set(DATA.items.map(i => i.source))).sort();
  const cats    = Array.from(new Set(DATA.items.map(i => i.categoria))).sort();
  $('#cmdbar').innerHTML = `
    <span class="prompt">&gt;</span>
    <span class="prompt">FILTER</span>
    <span class="seg"><label>source:</label><select id="f-source">
      <option value="">[*]</option>
      ${sources.map(s => `<option value="${s}">${s}</option>`).join('')}
    </select></span>
    <span class="seg"><label>category:</label><select id="f-cat">
      <option value="">[*]</option>
      ${cats.map(c => `<option value="${c}">${c}</option>`).join('')}
    </select></span>
    <span class="seg"><label>date:</label><input id="f-from" type="date" style="width:130px"> .. <input id="f-to" type="date" style="width:130px"></span>
    <span class="seg"><label>q:</label><input id="f-q" class="q" type="text" placeholder='"texto..."'></span>
    <span class="clear" id="f-clear">[× clear]</span>
  `;
  ['#f-source','#f-cat','#f-from','#f-to','#f-q'].forEach(sel => {
    const el = $(sel);
    el.addEventListener('input', () => { syncFilter(); drawTable(); });
    el.addEventListener('change', () => { syncFilter(); drawTable(); });
  });
  $('#f-clear').addEventListener('click', () => {
    filterState.source = ''; filterState.category=''; filterState.from=''; filterState.to=''; filterState.q='';
    $('#f-source').value=''; $('#f-cat').value=''; $('#f-from').value=''; $('#f-to').value=''; $('#f-q').value='';
    drawTable();
  });

  // table head
  const cols = [
    {k:'first_seen_at', label:'DETECTED', cls:'col-date'},
    {k:'fecha',         label:'PUBLISHED', cls:'col-date'},
    {k:'source',        label:'SOURCE', cls:'col-src'},
    {k:'categoria',     label:'CATEGORY', cls:'col-cat'},
    {k:'titulo',        label:'TITLE', cls:'col-title'},
    {k:null,            label:'', cls:'col-arrow'},
  ];
  $('#hist-thead').innerHTML = cols.map(c => `
    <th class="${c.cls}" ${c.k?`data-sort="${c.k}"`:''}>
      ${c.label}${c.k ? `<span class="sort">▾</span>` : ''}
    </th>
  `).join('');
  $$('#hist-thead th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.sort;
      if (filterState.sortKey === k) filterState.sortDir = filterState.sortDir === 'asc' ? 'desc' : 'asc';
      else { filterState.sortKey = k; filterState.sortDir = 'desc'; }
      drawTable();
    });
  });

  drawTable();
}
function syncFilter() {
  filterState.source   = $('#f-source').value;
  filterState.category = $('#f-cat').value;
  filterState.from     = $('#f-from').value;
  filterState.to       = $('#f-to').value;
  filterState.q        = $('#f-q').value.toLowerCase().trim();
}
function applyFilters(items) {
  return items.filter(it => {
    if (filterState.source && it.source !== filterState.source) return false;
    if (filterState.category && it.categoria !== filterState.category) return false;
    if (filterState.from && it.first_seen_at.slice(0,10) < filterState.from) return false;
    if (filterState.to && it.first_seen_at.slice(0,10) > filterState.to) return false;
    if (filterState.q) {
      const hay = (it.titulo + ' ' + it.summary + ' ' + it.source + ' ' + it.categoria).toLowerCase();
      if (!hay.includes(filterState.q)) return false;
    }
    return true;
  });
}
function drawTable() {
  let rows = applyFilters(DATA.items.slice());
  const k = filterState.sortKey, dir = filterState.sortDir === 'asc' ? 1 : -1;
  rows.sort((a,b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * dir);

  $$('#hist-thead th[data-sort]').forEach(th => {
    th.removeAttribute('aria-sort');
    th.querySelector('.sort').textContent = '▾';
  });
  const active = $(`#hist-thead th[data-sort="${k}"]`);
  if (active) {
    active.setAttribute('aria-sort', filterState.sortDir);
    active.querySelector('.sort').textContent = filterState.sortDir === 'asc' ? '▴' : '▾';
  }

  const tbody = $('#hist-tbody');
  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="padding:24px; text-align:center; color:var(--fg-dim); letter-spacing:.18em;">› NO MATCHING RECORDS</td></tr>`;
  } else {
    tbody.innerHTML = rows.map(it => `
      <tr data-id="${it.id_hash}">
        <td class="col-date">${fmtDate(it.first_seen_at)}</td>
        <td class="col-date">${fmtDate(it.fecha)}</td>
        <td class="col-src"><span class="badge src ${it.source}">${SOURCE_LABEL[it.source]}</span></td>
        <td class="col-cat"><span class="badge cat">${CAT_LABEL[it.categoria]}</span></td>
        <td class="col-title">${escapeHTML(it.titulo)}</td>
        <td class="col-arrow">→</td>
      </tr>
    `).join('');
    $$('#hist-tbody tr').forEach(tr => {
      tr.addEventListener('click', () => toggleExpanded(tr.dataset.id));
    });
    if (filterState.expanded) injectExpanded(filterState.expanded);
  }

  $('#hist-count').innerHTML = `MATCHED <b>${rows.length}</b> / ${DATA.items.length} RECORDS`;
}
function toggleExpanded(id) {
  if (filterState.expanded === id) {
    filterState.expanded = null;
    $$('.expanded-row').forEach(r => r.remove());
    $$('#hist-tbody tr').forEach(t => t.classList.remove('expanded'));
    return;
  }
  filterState.expanded = id;
  $$('.expanded-row').forEach(r => r.remove());
  $$('#hist-tbody tr').forEach(t => t.classList.remove('expanded'));
  injectExpanded(id);
}
function injectExpanded(id) {
  const it = DATA.items.find(x => x.id_hash === id);
  if (!it) return;
  const tr = $(`#hist-tbody tr[data-id="${id}"]`);
  if (!tr) return;
  tr.classList.add('expanded');
  const e = document.createElement('tr');
  e.className = 'expanded-row';
  e.innerHTML = `
    <td colspan="6">
      <div class="e-title">› ${escapeHTML(it.titulo)}</div>
      <div class="e-summary"><b style="color:var(--phos-dim);font-weight:500;">AI SUMMARY:</b> ${renderInlineMarkdown(it.summary)}</div>
      <div class="e-actions">
        <a href="${it.url}" target="_blank" rel="noopener" class="btn-term">OPEN SOURCE →</a>
        <button class="btn-term ghost" data-copy="${it.url}">COPY PERMALINK</button>
        <span style="color:var(--fg-dim);font-size:11px;letter-spacing:.14em;margin-left:auto;align-self:center;">HASH ${it.id_hash} · LAG ${detectionLag(it)}</span>
      </div>
    </td>`;
  tr.after(e);
  e.querySelector('[data-copy]')?.addEventListener('click', (ev) => {
    ev.stopPropagation();
    const b = ev.currentTarget;
    navigator.clipboard?.writeText(b.dataset.copy);
    b.textContent = '✓ COPIED';
    setTimeout(() => b.textContent = 'COPY PERMALINK', 1200);
  });
}

/* ---- 4. Intelligence ------------------------------------------------- */
function renderIntel() {
  // 4a. bar chart by source
  const bySrc = {};
  DATA.items.forEach(it => bySrc[it.source] = (bySrc[it.source]||0) + 1);
  // include the empty source (boam)
  DATA.sources.forEach(s => { if (!(s.name in bySrc)) bySrc[s.name] = 0; });
  const max = Math.max(1, ...Object.values(bySrc));
  const sortedSrc = Object.entries(bySrc).sort((a,b) => b[1]-a[1]);
  $('#bars').innerHTML = sortedSrc.map(([k,v]) => `
    <div class="bar-row">
      <div class="name">${SOURCE_LABEL[k] || k}</div>
      <div class="track"><div class="fill" data-w="${(v/max)*100}"></div></div>
      <div class="num">${v}</div>
    </div>
  `).join('');
  requestAnimationFrame(() => {
    $$('#bars .fill').forEach(f => f.style.width = f.dataset.w + '%');
  });

  // 4b. donut by category
  const byCat = {};
  DATA.items.forEach(it => byCat[it.categoria] = (byCat[it.categoria]||0)+1);
  const totalCat = Object.values(byCat).reduce((a,b)=>a+b,0);
  const cats = Object.entries(byCat).sort((a,b)=>b[1]-a[1]);

  // SVG donut
  const cx = 70, cy = 70, r = 55, sw = 18;
  const C = 2 * Math.PI * r;
  let offset = 0;
  const segs = cats.map(([cat, n]) => {
    const frac = n / totalCat;
    const len = frac * C;
    const seg = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none"
        stroke="${CAT_COLOR[cat] || '#39ff14'}" stroke-width="${sw}"
        stroke-dasharray="${len} ${C}"
        stroke-dashoffset="${-offset}"
        transform="rotate(-90 ${cx} ${cy})"
        style="filter: drop-shadow(0 0 3px ${CAT_COLOR[cat] || '#39ff14'}88)" />`;
    offset += len;
    return seg;
  }).join('');

  $('#donut').innerHTML = `
    <div class="donut-wrap">
      <svg viewBox="0 0 140 140" width="160" height="160">
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#0d3d0a" stroke-width="${sw}" />
        ${segs}
        <text x="${cx}" y="${cy-4}" text-anchor="middle" fill="#39ff14" font-family="Major Mono Display" font-size="22">${totalCat}</text>
        <text x="${cx}" y="${cy+12}" text-anchor="middle" fill="#6f7a64" font-family="JetBrains Mono" font-size="8" letter-spacing="2">RECORDS</text>
      </svg>
      <div class="donut-legend">
        ${cats.map(([cat,n]) => `
          <div class="li">
            <span class="sw" style="background:${CAT_COLOR[cat]}"></span>
            <span class="lname">${CAT_LABEL[cat]}</span>
            <span class="lcount">${n}</span>
            <span class="lpct">${(n/totalCat*100).toFixed(1)}%</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;

}

/* ---- 5. Sources status ---------------------------------------------- */
function renderSources() {
  const tbody = $('#src-tbody');
  tbody.innerHTML = DATA.sources.map(s => `
    <tr data-name="${s.name}">
      <td class="col-name">${SOURCE_LABEL[s.name] || s.name.toUpperCase()}</td>
      <td class="col-url">${s.url}</td>
      <td class="col-probe">${fmtDate(s.last_probe_at)} ${fmtTime(s.last_probe_at)}</td>
      <td class="col-code">${s.code}</td>
      <td class="col-status"><span class="status-pill ${s.status}">${s.status.toUpperCase()}</span></td>
      <td class="col-hits">${s.total_hits}</td>
      <td class="col-arrow">▾</td>
    </tr>
  `).join('');
  $$('#src-tbody tr').forEach(tr => {
    tr.addEventListener('click', () => {
      const next = tr.nextElementSibling;
      if (next?.classList.contains('src-detail-row')) { next.remove(); return; }
      $$('.src-detail-row').forEach(r => r.remove());
      const s = DATA.sources.find(x => x.name === tr.dataset.name);
      const det = document.createElement('tr');
      det.className = 'src-detail-row';
      det.innerHTML = `<td colspan="7"><div class="src-detail">${escapeHTML(s.detail)}</div></td>`;
      tr.after(det);
    });
  });
}

/* ---- 6. Watchlist (HEALTH_ORGS) ------------------------------------- */
const WATCHLIST = [
  { id:'T-01', name:'SERMAS',                          desc:'Servicio Madrileño de Salud (incluye 11 hospitales públicos)', hits:178, hot:true },
  { id:'T-02', name:'H. La Paz',                       desc:'Hospital Universitario La Paz — Servicio de Prevención',       hits: 14, hot:true },
  { id:'T-03', name:'H. 12 de Octubre',                desc:'Hospital Universitario 12 de Octubre — Salud Laboral',         hits: 11, hot:true },
  { id:'T-04', name:'H. Gregorio Marañón',             desc:'Hospital Universitario Gregorio Marañón — Prevención',         hits:  9, hot:true },
  { id:'T-05', name:'H. Ramón y Cajal',                desc:'Hospital Universitario Ramón y Cajal — Salud Laboral',         hits:  6, hot:true },
  { id:'T-06', name:'SUMMA 112',                       desc:'Servicio de Urgencia Médica de Madrid',                        hits: 12, hot:true },
  { id:'T-07', name:'FNMT-RCM',                        desc:'Fábrica Nacional de Moneda y Timbre — Servicio Médico',        hits:  5, hot:true },
  { id:'T-08', name:'EMT Madrid',                      desc:'Empresa Municipal de Transportes — Salud Laboral',             hits:  4, hot:true },
  { id:'T-09', name:'Metro de Madrid',                 desc:'Metro de Madrid S.A. — Servicio de Prevención propio',         hits:  3, hot:true },
  { id:'T-10', name:'Canal de Isabel II',              desc:'Canal de Isabel II — SP Mancomunado',                          hits:  6, hot:true },
  { id:'T-11', name:'Ayto. Madrid',                    desc:'Ayuntamiento de Madrid — IMD, Bomberos, Policía Municipal',    hits: 18, hot:true },
  { id:'T-12', name:'Las Rozas',                       desc:'Ayto. de Las Rozas — Corredor A-6',                            hits:  2, hot:false },
  { id:'T-13', name:'Majadahonda',                     desc:'Ayto. de Majadahonda — Corredor A-6',                          hits:  2, hot:false },
  { id:'T-14', name:'Pozuelo de Alarcón',              desc:'Ayto. de Pozuelo de Alarcón — Corredor A-6',                   hits:  1, hot:false },
  { id:'T-15', name:'Boadilla del Monte',              desc:'Ayto. de Boadilla del Monte — Corredor A-6',                   hits:  1, hot:false },
  { id:'T-16', name:'Villaviciosa de Odón',            desc:'Ayto. de Villaviciosa de Odón — Corredor A-6',                 hits:  1, hot:false },
  { id:'T-17', name:'Alcorcón',                        desc:'Ayto. de Alcorcón — Corredor A-5',                             hits:  2, hot:false },
  { id:'T-18', name:'Móstoles',                        desc:'Ayto. de Móstoles — Corredor A-5',                             hits:  3, hot:false },
  { id:'T-19', name:'Fuenlabrada',                     desc:'Ayto. de Fuenlabrada — Corredor A-5',                          hits:  2, hot:false },
  { id:'T-20', name:'Cuerpo Militar Sanidad',          desc:'Ministerio de Defensa — Esp. Enfermería del Trabajo',          hits:  4, hot:true },
  { id:'T-21', name:'INSS',                            desc:'Instituto Nacional de la Seguridad Social',                    hits:  3, hot:false },
  { id:'T-22', name:'AGE — Política Territorial',      desc:'Delegaciones de Gobierno — concurso de traslados',             hits:  2, hot:false },
];
function renderWatchlist() {
  $('#watchlist').innerHTML = WATCHLIST.map(t => `
    <div class="target ${t.hot ? '' : 'cold'}">
      <div class="id">${t.id}</div>
      <div class="name">${t.name}</div>
      <div class="desc">${t.desc}</div>
      <div class="stat">HITS <b>${t.hits}</b> · ${t.hot ? 'ACTIVE' : 'COLD'}</div>
    </div>
  `).join('');
}

/* ---- 7. Subscribe terminal ------------------------------------------ */
const subState = { step: 1, code: '', email: '', error: '', success: false };
function renderSubscribe() {
  drawSub();
  $('#tty').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); subSubmit(); }
  });
}
function drawSub() {
  const lines = [];
  const frame = `╔══════════════════════════════════════════════════╗
║  ░ ALERT CHANNEL — REQUEST ACCESS                ║
║  ░ chan: @vigia_enfermeria_bot                   ║
╚══════════════════════════════════════════════════╝`;
  let body = '';
  const stepper = `
    <div class="stepper">
      <span class="s ${subState.step===1?'active':subState.step>1?'done':''}">[01] /start</span>
      <span class="s ${subState.step===2?'active':subState.step>2?'done':''}">[02] PAIR</span>
      <span class="s ${subState.step===3?'active':subState.step>3?'done':''}">[03] CONFIRM</span>
      <span class="s ${subState.step===4?'active':''}">[04] OK</span>
    </div>`;
  if (subState.step === 1) {
    body = `
      <div class="line"><span class="p">$</span>open https://t.me/vigia_enfermeria_bot</div>
      <div class="line"><span class="p">$</span>send <span class="amber">/start</span> &nbsp;<span class="muted">// the bot replies with a 6-digit pairing code</span></div>
      <div class="line"><span class="muted">› Once you have the code, click [I HAVE A CODE] below.</span></div>
      <div class="submit-row">
        <button class="btn-term" id="sub-next">[ I HAVE A CODE → ]</button>
        <a class="btn-term ghost" href="https://t.me/vigia_enfermeria_bot" target="_blank" rel="noopener">OPEN TELEGRAM →</a>
      </div>`;
  } else if (subState.step === 2) {
    body = `
      <div class="line"><span class="p">&gt;</span>ENTER PAIRING CODE <span class="muted">(6 digits)</span></div>
      <div class="input-row">
        <span class="p">code:</span>
        <input id="sub-code" type="text" maxlength="6" inputmode="numeric" autocomplete="off" placeholder="______" value="${subState.code}">
      </div>
      <div class="line"><span class="p">&gt;</span>EMAIL <span class="muted">(optional, for recovery)</span></div>
      <div class="input-row">
        <span class="p">email:</span>
        <input id="sub-email" type="email" autocomplete="off" placeholder="user@domain" value="${subState.email}">
      </div>
      ${subState.error ? `<div class="line"><span class="err">! ${escapeHTML(subState.error)}</span></div>` : ''}
      <div class="submit-row">
        <button class="btn-term" id="sub-submit">[ TRANSMIT → ]</button>
        <button class="btn-term ghost" id="sub-back">[ ← BACK ]</button>
      </div>
      <div class="line cursor"><span class="muted">awaiting input</span></div>`;
  } else if (subState.step === 3) {
    body = `
      <div class="line"><span class="p">&gt;</span>HANDSHAKE...</div>
      <div class="line"><span class="muted">[████████████░░░░░░░░] 60%</span></div>
      <div class="line"><span class="muted">› POST /api/subscribe → cf-worker</span></div>
      <div class="line"><span class="muted">› verify code · pair tg_chat_id · install hooks</span></div>`;
    setTimeout(() => { subState.step = 4; subState.success = true; drawSub(); }, 1400);
  } else {
    body = `
      <div class="line"><span class="ok">[ ✓ ] PAIRING SUCCESSFUL</span></div>
      <div class="line"><span class="muted">› chat_id 84219**** linked to channel</span></div>
      <div class="line"><span class="muted">› next dispatch: ${fmtTime(DATA.meta.next_run_at)} (UTC)</span></div>
      <div class="line"><span class="ok">› welcome aboard.</span></div>
      <div class="submit-row">
        <button class="btn-term ghost" id="sub-reset">[ ENROLL ANOTHER ]</button>
      </div>`;
  }
  $('#tty').innerHTML = `
    <div class="ascii-frame">${frame}</div>
    ${stepper}
    ${body}
  `;
  $('#sub-next')?.addEventListener('click', () => { subState.step = 2; drawSub(); });
  $('#sub-back')?.addEventListener('click', () => { subState.step = 1; drawSub(); });
  $('#sub-submit')?.addEventListener('click', subSubmit);
  $('#sub-reset')?.addEventListener('click', () => {
    subState.step = 1; subState.code=''; subState.email=''; subState.error=''; subState.success=false;
    drawSub();
  });
  $('#sub-code')?.focus();
  $('#sub-code')?.addEventListener('input', e => subState.code = e.target.value);
  $('#sub-email')?.addEventListener('input', e => subState.email = e.target.value);
}
function subSubmit() {
  if (subState.step !== 2) return;
  if (!/^\d{6}$/.test(subState.code)) {
    subState.error = 'INVALID CODE — expected 6 digits.';
    drawSub();
    return;
  }
  if (subState.email && !/^.+@.+\..+$/.test(subState.email)) {
    subState.error = 'INVALID EMAIL FORMAT.';
    drawSub();
    return;
  }
  subState.error = '';
  subState.step = 3;
  drawSub();
  // Note: real impl would POST to https://api.vigia-enfermeria.workers.dev/api/subscribe
}

/* ---- 8. How it works diagram + changelog ---------------------------- */
function renderHowItWorks() {
  const diag = String.raw`<span class="dim">┌─[ 00:00 UTC · cron tick ]──────────────────────────────────┐</span>
<span class="dim">│</span>
<span class="dim">│</span>  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
<span class="dim">│</span>  │  <span class="fg">8 SOURCES</span>   │───▶│  <span class="fg">EXTRACTOR</span>   │───▶│  <span class="fg">ENRICHER</span>    │
<span class="dim">│</span>  │  BOE / BOCM  │    │  regex       │    │  claude-     │
<span class="dim">│</span>  │  CMA / AYTO  │    │  strong+weak │    │  haiku-4.5   │
<span class="dim">│</span>  │  CANAL CODEM │    │  hash dedupe │    │  summary +   │
<span class="dim">│</span>  │  DATOS BOAM  │    │              │    │  category    │
<span class="dim">│</span>  └──────────────┘    └──────────────┘    └──────────────┘
<span class="dim">│</span>          │                                          │
<span class="dim">│</span>          ▼                                          ▼
<span class="dim">│</span>  ┌──────────────┐                          ┌──────────────┐
<span class="dim">│</span>  │  <span class="amb">SQLite</span>      │◀─────────────────────────│  <span class="fg">DISPATCH</span>    │
<span class="dim">│</span>  │  vigía.db    │  store hits + summaries  │  Telegram    │──▶ subscribers
<span class="dim">│</span>  │  WAL mode    │                          │  bot         │
<span class="dim">│</span>  └──────────────┘                          └──────────────┘
<span class="dim">│</span>          │
<span class="dim">│</span>          └──▶ <span class="fg">EXPORT</span> ──▶ data/*.json ──▶ git push gh-pages ──▶ <span class="amb">YOU ARE HERE</span>
<span class="dim">│</span>
<span class="dim">└────────────────────────────────────────────────────────────┘</span>`;
  $('#diagram').innerHTML = diag;

  $('#changelog').innerHTML = `
    <h4>// FIELD NOTES</h4>
    <div class="entry">
      <span class="stamp">2026-04-25 · v0.7.3</span>
      <div class="title">BOE 400 → fixed Accept header</div>
      <p>BOE diario API silently 400s without <code>Accept: application/json</code>. Took 2 days to spot — the response body said "OK" with an empty XML.</p>
    </div>
    <div class="entry">
      <span class="stamp">2026-04-19 · v0.7.2</span>
      <div class="title">BOAM geo-block confirmed</div>
      <p>403 from every Azure-region runner. Confirmed via cf-worker proxy too. Switched coverage to BOE 2B + datos.madrid.es; weekly manual fallback scheduled.</p>
    </div>
    <div class="entry">
      <span class="stamp">2026-03-04 · v0.7.0</span>
      <div class="title">Strong+weak match scoring</div>
      <p>Added a two-pass extractor — strong on <code>"enfermería del trabajo"</code>, weak on <code>"salud laboral|prevención|enfermer*"</code> with title-bigram filter. False positive rate dropped 12% → 1.8%.</p>
    </div>
    <div class="entry">
      <span class="stamp">2026-02-11 · v0.6.4</span>
      <div class="title">Haiku migration</div>
      <p>Moved enrichment from sonnet-3.5 to haiku-4.5. Same summary quality, 8× cheaper. Median enrich latency 1.4s.</p>
    </div>
  `;
}

/* ---- 9. Footer ------------------------------------------------------- */
function renderFooter() {
  $('#footer').innerHTML = `
    <span>BUILT WITH PARANOIA · MAINTAINED BY <a href="https://github.com/tragabytes" target="_blank">@tragabytes</a></span>
    <span class="sep">│</span>
    <span><a href="https://github.com/tragabytes/vigia-enfermeria" target="_blank">github.com/tragabytes/vigia-enfermeria →</a></span>
    <span class="sep">│</span>
    <span>VERSION <span class="commit">${DATA.meta.version}</span></span>
    <span class="sep">│</span>
    <span>HEAD <span class="commit">${DATA.meta.commit}</span></span>
    <span class="right">© 2022—2026 · NO COOKIES · NO TRACKERS · STATIC HTML</span>
  `;
}

/* ---- Tweaks panel --------------------------------------------------- */
function initTweaks() {
  // protocol: register listener BEFORE announcing availability
  let panel = $('#tweaks');
  window.addEventListener('message', (ev) => {
    const t = ev.data?.type;
    if (t === '__activate_edit_mode') panel.classList.add('open');
    if (t === '__deactivate_edit_mode') panel.classList.remove('open');
  });
  try { window.parent.postMessage({type:'__edit_mode_available'}, '*'); } catch {}

  panel.querySelector('.x').addEventListener('click', () => {
    panel.classList.remove('open');
    try { window.parent.postMessage({type:'__edit_mode_dismissed'}, '*'); } catch {}
  });

  // Hydrate from defaults
  const d = window.TWEAK_DEFAULTS;
  setScanlines(d.scanlines);
  setFlicker(d.flicker);
  setDensity(d.density);
  setTypingSound(d.typingSound);

  // Bind toggles
  bindToggle('#tw-scan',   d.scanlines,   v => { setScanlines(v); persist({scanlines:v}); });
  bindToggle('#tw-flick',  d.flicker,     v => { setFlicker(v);   persist({flicker:v}); });
  bindToggle('#tw-density',d.density==='high', v => { const m = v?'high':'normal'; setDensity(m); persist({density:m}); });
  bindToggle('#tw-sound',  d.typingSound, v => { setTypingSound(v); persist({typingSound:v}); });
}
function bindToggle(sel, initial, onChange) {
  const el = $(sel);
  if (!el) return;
  if (initial) el.classList.add('on');
  el.addEventListener('click', () => {
    el.classList.toggle('on');
    onChange(el.classList.contains('on'));
  });
}
function setScanlines(on)   { document.body.dataset.scanlines = on ? 'on' : 'off'; }
function setFlicker(on)     { document.body.dataset.flicker   = on ? 'on' : 'off'; }
function setDensity(mode)   { document.body.dataset.density   = mode; }
function setTypingSound(on) {
  if (!on) { document.removeEventListener('keydown', tickSound); return; }
  document.addEventListener('keydown', tickSound);
}
let audioCtx = null;
function tickSound() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.frequency.value = 1200 + Math.random()*400;
    o.type = 'square';
    g.gain.value = 0.02;
    o.connect(g).connect(audioCtx.destination);
    o.start();
    setTimeout(() => { o.stop(); }, 22);
  } catch {}
}
function persist(edits) {
  try { window.parent.postMessage({type:'__edit_mode_set_keys', edits}, '*'); } catch {}
}
