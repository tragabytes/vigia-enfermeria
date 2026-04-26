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

/* Etiquetas legibles para los enums del enricher v2. Si llega un valor
   desconocido (versión más nueva del backend que el frontend), caemos al
   string crudo en MAYÚSCULAS para no romper nada. */
const PROCESS_TYPE_LABEL = {
  'oposicion':          'OPOSICIÓN',
  'bolsa':              'BOLSA',
  'concurso_traslados': 'CONCURSO TRASLADOS',
  'interinaje':         'INTERINAJE',
  'temporal':           'TEMPORAL',
  'otro':               'OTRO',
};
const FASE_LABEL = {
  'convocatoria':           'CONVOCATORIA',
  'admitidos_provisional':  'ADMITIDOS PROV.',
  'admitidos_definitivo':   'ADMITIDOS DEF.',
  'examen':                 'EXAMEN',
  'calificacion':           'CALIFICACIÓN',
  'propuesta_nombramiento': 'PROPUESTA NOMBR.',
  'otro':                   'ACTUALIZACIÓN',
};

let DATA = { items: [], sources: [], meta: {}, targets: [], changelog: [] };

/* ---- bootstrap ------------------------------------------------------- */
async function loadData() {
  const items   = await fetch('data/items.json').then(r => r.json());
  const meta    = await fetch('data/meta.json').then(r => r.json());
  // sources_status.json puede faltar transitoriamente (el backend ahora
  // se abstiene de escribirlo cuando no hay probe ni snapshot previo,
  // para no degradar la sección con "unknown/null"). Fallback a [] y
  // renderSources() pinta un placeholder.
  const sources = await fetch('data/sources_status.json')
    .then(r => r.ok ? r.json() : [])
    .catch(() => []);
  // targets.json y changelog.json son opcionales (versión vieja del backend
  // no los genera). Fallback a [] para no romper el render.
  const targets = await fetch('data/targets.json')
    .then(r => r.ok ? r.json() : [])
    .catch(() => []);
  const changelog = await fetch('data/changelog.json')
    .then(r => r.ok ? r.json() : [])
    .catch(() => []);
  DATA = { items, sources, meta, targets, changelog };
}

document.addEventListener('DOMContentLoaded', async () => {
  // En móvil ocultamos las secciones (excepto hero) ANTES del fetch para
  // que no haya un flash entre render y observe. El observer las irá
  // dejando visibles a medida que el usuario haga scroll.
  prepGlitchMobile();

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
  initScrollEffects();
  initCollapsibleSections();
  bindTerminalModal();
});

/* ---- Mobile pre-paint --------------------------------------------------
   Marcamos secciones como .pre-glitch antes del fetch. El CSS de
   .pre-glitch solo aplica en ≤900px, así que en desktop esto es un
   no-op visual. */
function prepGlitchMobile() {
  if (!window.matchMedia('(max-width: 900px)').matches) return;
  document.querySelectorAll('.shell > section:not(.hero)').forEach(s => {
    s.classList.add('pre-glitch');
  });
}

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

/* Helpers para los campos del enricher v2 ----------------------------- */

/* Días hasta el deadline (>=0 si en futuro, <0 si ya cerró). null si no hay. */
function daysUntil(iso) {
  if (!iso) return null;
  const dl = new Date(iso + 'T00:00:00Z');
  if (isNaN(dl)) return null;
  const today = new Date();
  const todayUTC = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.round((dl.getTime() - todayUTC) / 86400000);
}

/* Texto legible "en N días", "HOY", "mañana", "cerrado hace N días". */
function deadlineText(iso) {
  const d = daysUntil(iso);
  if (d === null) return null;
  if (d < 0)  return `cerrado hace ${-d} días`;
  if (d === 0) return 'HOY';
  if (d === 1) return 'mañana';
  return `en ${d} días`;
}

/* Badge de urgencia: 'urgent' si <=7 días, 'open' si futuro, 'closed' si pasado. */
function deadlineState(iso) {
  const d = daysUntil(iso);
  if (d === null) return null;
  if (d < 0) return 'closed';
  if (d <= 7) return 'urgent';
  return 'open';
}

/* Formatea un importe en euros con el estilo del notifier (30€ o 30,50€). */
function fmtEur(amount) {
  if (amount === null || amount === undefined) return null;
  if (Math.abs(amount - Math.round(amount)) < 0.005) {
    return `${Math.round(amount)}€`;
  }
  return `${amount.toFixed(2).replace('.', ',')}€`;
}

/* HTML de los chips meta v2 (process_type, plazas, deadline, tasa, fase).
   Devuelve string vacío si el item no tiene ninguno de estos campos. */
function chipsHTML(it) {
  const chips = [];
  if (it.process_type) {
    const lbl = PROCESS_TYPE_LABEL[it.process_type] || it.process_type.toUpperCase();
    chips.push(`<span class="chip chip-pt">${escapeHTML(lbl)}</span>`);
  }
  if (it.plazas) {
    chips.push(`<span class="chip chip-plz">${escapeHTML(String(it.plazas))} PLAZAS</span>`);
  }
  if (it.deadline_inscripcion) {
    const state = deadlineState(it.deadline_inscripcion);
    const txt = deadlineText(it.deadline_inscripcion);
    chips.push(
      `<span class="chip chip-dl chip-dl-${state}" title="Cierre ${it.deadline_inscripcion}">⏰ ${escapeHTML(txt)}</span>`
    );
  }
  if (it.tasas_eur !== null && it.tasas_eur !== undefined) {
    chips.push(`<span class="chip chip-eur">${escapeHTML(fmtEur(it.tasas_eur))}</span>`);
  }
  if (it.fase && it.fase !== 'convocatoria' && it.fase !== 'otro') {
    const lbl = FASE_LABEL[it.fase] || it.fase.toUpperCase();
    chips.push(`<span class="chip chip-fase">⛓ ${escapeHTML(lbl)}</span>`);
  }
  if (it.is_relevant === false) {
    chips.push(`<span class="chip chip-discard">DISCARDED</span>`);
  }
  return chips.length ? `<div class="chips">${chips.join('')}</div>` : '';
}

/* Mini-renderer de Markdown inline para el summary del enricher. Cubre los
   estilos que produce Claude en respuestas cortas: **bold**, *italic*,
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

/* ---- Terminal modal ------------------------------------------------- */

/* Abre el <dialog> con los items pasados, reutilizando cardHTML() para
   que la representación sea idéntica al daily feed. Acepta un title +
   meta corto para el header del modal. */
function openTerminalModal({ title, meta = '', items }) {
  const dlg = $('#term-modal');
  if (!dlg) return;
  $('#term-modal-title').textContent = title;
  $('#term-modal-meta').textContent = meta;

  const body = $('#term-modal-body');
  if (!items || items.length === 0) {
    body.innerHTML = `<div class="term-modal-empty">› NO MATCHING RECORDS</div>`;
  } else {
    // Más recientes primero — coherente con el daily feed.
    const ordered = items.slice().sort((a, b) =>
      (b.first_seen_at || '').localeCompare(a.first_seen_at || '')
    );
    body.innerHTML = ordered.map((it, i) => cardHTML(it, i)).join('');
    // Misma interactividad que en el feed: head abre/cierra el body, los
    // botones de copy paran propagación. La primera card empieza abierta.
    $$('.card', body).forEach((c, idx) => {
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
      if (idx === 0) c.classList.add('open');
    });
  }

  if (!dlg.open) dlg.showModal();
  body.scrollTop = 0;
}

/* Click en el botón × o en el backdrop cierran el modal. ESC ya viene
   gratis con <dialog>. Lo registramos una sola vez al cargar la página. */
function bindTerminalModal() {
  const dlg = $('#term-modal');
  if (!dlg) return;
  dlg.querySelector('.term-modal-close')?.addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => {
    // El click en el propio dialog (no en el frame interno) implica click
    // en el backdrop — porque el frame es .term-modal-frame, hijo directo.
    const rect = dlg.getBoundingClientRect();
    const inDialog =
      e.clientX >= rect.left && e.clientX <= rect.right &&
      e.clientY >= rect.top  && e.clientY <= rect.bottom;
    if (!inDialog) dlg.close();
  });
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

  // Alarma de urgentes: sale solo si hay targets urgentes (deadline ≤7 días).
  // Caso 1 urgente: muestra el nombre + countdown ("URGENT · CANAL II · CIERRA EN 2D").
  // Caso N urgentes: contador genérico ("N URGENTES").
  // Click → modal del urgente más próximo / scroll a sección 06 si hay varios.
  // Estética: pulso rojo en todo el pill (sin icono, sin shake).
  const urgentTargets = (DATA.targets || []).filter(t => t.urgent);
  let alarmHTML = '';
  if (urgentTargets.length === 1) {
    const t = urgentTargets[0];
    const txt = t.days_until <= 0 ? 'CIERRA HOY'
              : t.days_until === 1 ? 'CIERRA MAÑANA'
              : `CIERRA EN ${t.days_until}D`;
    alarmHTML = `
      <span class="item alarm" id="alarm-bell" data-target-id="${escapeHTML(t.id)}" title="Ver convocatoria urgente">
        <span class="val">URGENT · ${escapeHTML(t.name.toUpperCase())} · ${escapeHTML(txt)}</span>
      </span>`;
  } else if (urgentTargets.length > 1) {
    // Ordenamos por días restantes para usar el más urgente al hacer click.
    urgentTargets.sort((a, b) => (a.days_until ?? 99) - (b.days_until ?? 99));
    alarmHTML = `
      <span class="item alarm" id="alarm-bell" data-target-id="${escapeHTML(urgentTargets[0].id)}" title="Ir a la sección de watchlist">
        <span class="val">${urgentTargets.length} URGENTES</span>
      </span>`;
  }

  $('#statusbar').innerHTML = `
    <span class="item"><span class="dot"></span><span class="val">SYSTEM ONLINE</span></span>
    <span class="sep">│</span>
    <span class="item"><span class="label">LAST RUN</span><span class="val">T-${lastRunAgo}</span></span>
    <span class="sep">│</span>
    <span class="item"><span class="label">NEXT RUN</span><span class="val">${nextStr}</span></span>
    <span class="sep">│</span>
    <span class="item"><span class="label">SOURCES</span><span class="val ${m.sources_online === m.sources_total ? '' : 'amber'}">${m.sources_online}/${m.sources_total} OK</span></span>
    ${alarmHTML ? '<span class="sep">│</span>' + alarmHTML : ''}
    <span class="sep">│</span>
    <span class="item right"><span class="label">UTC</span><span class="val" id="utc-clock">${new Date().toISOString().slice(11,19)}</span></span>
  `;

  // Click en el bell:
  // - 1 urgente: abre el modal con los items de ese target.
  // - N urgentes: scroll a la sección 06 (watchlist) — los tiles urgentes
  //   están al principio (orden aplicado por renderWatchlist) y el usuario
  //   elige cuál inspeccionar.
  $('#alarm-bell')?.addEventListener('click', (e) => {
    if (urgentTargets.length === 1) {
      openTargetModal(urgentTargets[0].id);
    } else {
      const wl = $('#watchlist')?.closest('section');
      if (wl?.classList.contains('collapsed')) wl.classList.remove('collapsed');
      wl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  setInterval(() => {
    const e = $('#utc-clock');
    if (e) e.textContent = new Date().toISOString().slice(11, 19);
  }, 1000);
}

/* ---- 1b. Hero -------------------------------------------------------- */
function renderHero() {
  const ascii = $('#ascii-logo'); if (ascii) ascii.textContent = '';
  if (!$('#hero-meta')) return;
  // Hero meta: NODE / BUILD / HEAD. El indicador "SYSTEM ONLINE" vivía
  // aquí Y en la status bar — redundante. Lo dejamos solo arriba.
  $('#hero-meta').innerHTML = `
    <span class="glyph">[▮]</span>
    <span>NODE</span><span class="v">vigía-01</span>
    <span class="sep">/</span>
    <span>BUILD</span><span class="v">${DATA.meta.version}</span>
    <span class="sep">/</span>
    <span>HEAD</span><span class="v">${DATA.meta.commit}</span>
  `;
  // Título: arrancamos vacío y disparamos la animación de typing.
  $('#hero-title').innerHTML = `<span class="bracket">/</span>&nbsp;<span id="title-text"></span><span class="cursor">▮</span>`;
  typeTitle();

  $('#hero-tagline').innerHTML = `
    <span class="prefix">$ ./vigía --whoami</span><br>
    Automated surveillance of Spanish public-sector job postings for
    <b style="color:var(--phos)">Occupational Health Nursing</b>. Polls 8 official
    bulletins daily, hashes findings, enriches with Claude Sonnet 4.6 (tool use), dispatches
    to Telegram. Built with paranoia. Public log.
  `;
}

/* Typing del título con un typo intencional y corrección, tipo terminal.
   Secuencia: teclea "vigía-enfermenía", pausa breve, borra los 3 últimos
   caracteres ("nía") y corrige a "ría" para llegar a "vigía-enfermería". */
function typeTitle() {
  const target = 'vigía-enfermería';
  const wrong  = 'vigía-enfermenía';     // typo en la última sílaba: nía → ría
  const keep   = 'vigía-enferme';        // hasta donde retrocede el cursor
  const el = document.getElementById('title-text');
  if (!el) return;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const TYPE_MS = 75;
  const PAUSE_AFTER_TYPO = 380;
  const BACK_MS = 55;

  (async () => {
    for (let i = 1; i <= wrong.length; i++) {
      el.textContent = wrong.slice(0, i);
      await sleep(TYPE_MS);
    }
    await sleep(PAUSE_AFTER_TYPO);
    while (el.textContent.length > keep.length) {
      el.textContent = el.textContent.slice(0, -1);
      await sleep(BACK_MS);
    }
    await sleep(160);
    while (el.textContent.length < target.length) {
      el.textContent = target.slice(0, el.textContent.length + 1);
      await sleep(TYPE_MS);
    }
  })();
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
  // El countUp se dispara desde initScrollEffects: en desktop al instante
  // (los counters están en viewport al cargar), en móvil cuando el counter
  // entra en viewport. Por eso aquí solo dejamos el "0" inicial.
}

/* ---- 2. Daily feed --------------------------------------------------- */
function isToday(iso) {
  // For demo purposes: items first_seen_at on the meta.last_run_at date
  const ref = DATA.meta.last_run_at.slice(0, 10);
  return (iso || '').slice(0, 10) === ref;
}
function renderFeed() {
  // En el daily feed nunca mostramos los descartados (is_relevant=false):
  // son ruido confirmado por el enricher. Quien quiera auditarlos puede
  // activar el toggle "show discarded" en la sección Historical DB.
  const today = DATA.items
    .filter(it => isToday(it.first_seen_at))
    .filter(it => it.is_relevant !== false)
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
  const chips = chipsHTML(it);
  // Modelo del enricher (mostrado en el header del summary). Items v2
  // pasaron por Sonnet; legacy v1 por Haiku. Items sin enriquecer todavía
  // (enriched_version=null) llevan el placeholder neutro.
  let enrichedTag = '';
  if (it.enriched_version === 2) enrichedTag = 'claude-sonnet-4-6';
  else if (it.enriched_version === 1) enrichedTag = 'claude-haiku-4-5';
  else enrichedTag = 'pending enrichment';

  // Línea de acción inmediata + datos auxiliares (organismo, próxima acción)
  const auxLines = [];
  if (it.organismo) auxLines.push(`<div>ORGANISMO     <b>${escapeHTML(it.organismo)}</b></div>`);
  if (it.next_action) auxLines.push(`<div class="next-action">› ${escapeHTML(it.next_action)}</div>`);

  // Enlace a las bases si difiere del anuncio principal
  const basesBtn = (it.url_bases && it.url_bases !== it.url)
    ? `<a href="${it.url_bases}" target="_blank" rel="noopener" class="btn-term ghost">OPEN BASES →</a>`
    : '';

  return `
    <div class="card${it.is_relevant === false ? ' card-discarded' : ''}" data-id="${it.id_hash}">
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
        ${chips}
        <div class="meta-grid">
          <div>ID_HASH       <b>${it.id_hash}</b></div>
          <div>PUB DATE      <b>${fmtDate(it.fecha)}</b></div>
          <div>FIRST SEEN    <b>${fmtDate(it.first_seen_at)} ${fmtTime(it.first_seen_at)}</b></div>
          <div>SOURCE        <b>${SOURCE_LABEL[it.source]}</b></div>
          <div>CATEGORY      <b>${CAT_LABEL[it.categoria]}</b></div>
          <div>DETECTION LAG <b>${detectionLag(it)} </b></div>
          ${auxLines.join('')}
        </div>
        <div class="summary-block">
          <span class="lbl">› AI SUMMARY (${enrichedTag})</span>
          ${renderInlineMarkdown(it.summary)}
        </div>
        <div class="actions">
          <a href="${it.url}" target="_blank" rel="noopener" class="btn-term">OPEN SOURCE →</a>
          ${basesBtn}
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
  showDiscarded: false,        // toggle: incluir items con is_relevant=false
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
    <span class="seg toggle-seg"><label for="f-discarded">show discarded:</label><input id="f-discarded" type="checkbox"${filterState.showDiscarded ? ' checked' : ''}></span>
    <span class="clear" id="f-clear">[× clear]</span>
  `;
  ['#f-source','#f-cat','#f-from','#f-to','#f-q','#f-discarded'].forEach(sel => {
    const el = $(sel);
    el.addEventListener('input', () => { syncFilter(); drawTable(); });
    el.addEventListener('change', () => { syncFilter(); drawTable(); });
  });
  $('#f-clear').addEventListener('click', () => {
    filterState.source = ''; filterState.category=''; filterState.from=''; filterState.to=''; filterState.q='';
    filterState.showDiscarded = false;
    $('#f-source').value=''; $('#f-cat').value=''; $('#f-from').value=''; $('#f-to').value=''; $('#f-q').value='';
    $('#f-discarded').checked = false;
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
  filterState.showDiscarded = !!$('#f-discarded')?.checked;
}
function applyFilters(items) {
  return items.filter(it => {
    // Por defecto los items con is_relevant=false (falsos positivos
    // confirmados por el enricher) se ocultan. El toggle "show discarded"
    // los muestra para auditoría.
    if (!filterState.showDiscarded && it.is_relevant === false) return false;
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
  const chips = chipsHTML(it);
  // Aux: organismo y next action (si los tenemos por v2)
  const aux = [];
  if (it.organismo) aux.push(`<span class="e-aux"><b>ORG:</b> ${escapeHTML(it.organismo)}</span>`);
  if (it.next_action) aux.push(`<span class="e-aux"><b>NEXT:</b> ${escapeHTML(it.next_action)}</span>`);
  if (it.relevance_reason && it.is_relevant === false) {
    aux.push(`<span class="e-aux e-discarded"><b>WHY DISCARDED:</b> ${escapeHTML(it.relevance_reason)}</span>`);
  }
  const basesBtn = (it.url_bases && it.url_bases !== it.url)
    ? `<a href="${it.url_bases}" target="_blank" rel="noopener" class="btn-term ghost">OPEN BASES →</a>`
    : '';
  e.innerHTML = `
    <td colspan="6">
      <div class="e-title">› ${escapeHTML(it.titulo)}</div>
      ${chips}
      ${aux.length ? `<div class="e-aux-row">${aux.join('')}</div>` : ''}
      <div class="e-summary"><b style="color:var(--phos-dim);font-weight:500;">AI SUMMARY:</b> ${renderInlineMarkdown(it.summary)}</div>
      <div class="e-actions">
        <a href="${it.url}" target="_blank" rel="noopener" class="btn-term">OPEN SOURCE →</a>
        ${basesBtn}
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
  // Las bars arrancan con width=0 (CSS .bar-row .fill). El target se
  // aplica desde initScrollEffects (rAF inmediato en desktop, lazy en
  // móvil), y la transition CSS hace el resto.

  // 4b. donut by category
  const byCat = {};
  DATA.items.forEach(it => byCat[it.categoria] = (byCat[it.categoria]||0)+1);
  const totalCat = Object.values(byCat).reduce((a,b)=>a+b,0);
  const cats = Object.entries(byCat).sort((a,b)=>b[1]-a[1]);

  // SVG donut. En móvil arrancamos con dasharray="0 C" (segmentos
  // invisibles) para que el observer dispare el sweep al hacer scroll.
  // En desktop usamos el valor final: render estático, sin animación,
  // como antes.
  const isMobile = window.matchMedia('(max-width: 900px)').matches;
  const cx = 70, cy = 70, r = 55, sw = 18;
  const C = 2 * Math.PI * r;
  let offset = 0;
  const segs = cats.map(([cat, n]) => {
    const frac = n / totalCat;
    const len = frac * C;
    const initialDash = isMobile ? `0 ${C}` : `${len} ${C}`;
    const seg = `<circle class="donut-seg" cx="${cx}" cy="${cy}" r="${r}" fill="none"
        stroke="${CAT_COLOR[cat] || '#39ff14'}" stroke-width="${sw}"
        stroke-dasharray="${initialDash}"
        data-target-dasharray="${len} ${C}"
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
  if (!DATA.sources || DATA.sources.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="padding:24px;text-align:center;color:var(--fg-dim);letter-spacing:.18em;">
      › NO PROBE DATA — RUN <code>--probe</code> TO REFRESH
    </td></tr>`;
    return;
  }
  tbody.innerHTML = DATA.sources.map(s => {
    const hitsCell = s.total_hits > 0
      ? `<button type="button" class="hits-link" data-source="${s.name}" title="Filter Historical DB by ${SOURCE_LABEL[s.name] || s.name}">${s.total_hits}</button>`
      : s.total_hits;
    return `
    <tr data-name="${s.name}">
      <td class="col-name">${SOURCE_LABEL[s.name] || s.name.toUpperCase()}</td>
      <td class="col-url">${s.url}</td>
      <td class="col-probe">${fmtDate(s.last_probe_at)} ${fmtTime(s.last_probe_at)}</td>
      <td class="col-code">${s.code}</td>
      <td class="col-status"><span class="status-pill ${s.status}">${s.status.toUpperCase()}</span></td>
      <td class="col-hits">${hitsCell}</td>
      <td class="col-arrow">▾</td>
    </tr>`;
  }).join('');
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
  $$('#src-tbody .hits-link').forEach(b => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      openSourceModal(b.dataset.source);
    });
  });
}

/* Abre el modal con todos los items de una fuente concreta. Reemplaza el
   antiguo filter+scroll a la sección 03: el contexto se mantiene y el
   usuario puede volver al estado anterior cerrando con ESC. */
function openSourceModal(name) {
  const items = DATA.items.filter(it => it.source === name);
  const lbl = SOURCE_LABEL[name] || name.toUpperCase();
  openTerminalModal({
    title: `SOURCE · ${lbl}`,
    meta: `${items.length} ITEM${items.length === 1 ? '' : 'S'}`,
    items,
  });
}

/* ---- 6. Watchlist (organismos vigilados, calculados en backend) -----
   Orden: urgent (deadline ≤ 7 días) → active → cold. Dentro de cada
   bucket, los que tienen deadline más próximo arriba; en cold mantenemos
   orden original. Esto coloca lo accionable primero sin matar la lista. */
function renderWatchlist() {
  const targets = (DATA.targets || []).slice();
  const urgentN = targets.filter(t => t.urgent).length;
  const activeN = targets.filter(t => t.active && !t.urgent).length;
  const total = targets.length;
  const cold = total - urgentN - activeN;

  const meta = $('#watchlist-meta');
  if (meta) {
    const urgentChip = urgentN > 0 ? ` · ${urgentN} URGENT` : '';
    meta.textContent = `${total} ENTITIES · ${urgentN + activeN} ACTIVE${urgentChip} · ${cold} COLD`;
  }

  // Ranking determinista. Los urgentes con menor days_until al frente.
  targets.sort((a, b) => {
    const rank = (t) => t.urgent ? 0 : (t.active ? 1 : 2);
    const ra = rank(a), rb = rank(b);
    if (ra !== rb) return ra - rb;
    // Dentro del mismo rank: primero los que tienen deadline más cerca.
    const da = a.days_until ?? Infinity;
    const db = b.days_until ?? Infinity;
    if (da !== db) return da - db;
    return (a.id || '').localeCompare(b.id || '');
  });

  $('#watchlist').innerHTML = targets.map(t => {
    const cls = t.urgent ? 'urgent' : (t.active ? '' : 'cold');
    const stateLabel = t.urgent ? 'URGENT' : (t.active ? 'ACTIVE' : 'COLD');
    let countdown = '';
    if (t.days_until !== null && t.days_until !== undefined) {
      const txt = t.days_until <= 0 ? 'CIERRA HOY'
                : t.days_until === 1 ? 'CIERRA MAÑANA'
                : `CIERRA EN ${t.days_until} DÍAS`;
      countdown = `<div class="countdown">⏰ ${escapeHTML(txt)}</div>`;
    }
    const fase = (t.latest_phase && t.latest_phase !== 'convocatoria' && t.latest_phase !== 'otro')
      ? `<div class="phase">⛓ ${escapeHTML(FASE_LABEL[t.latest_phase] || t.latest_phase.toUpperCase())}</div>`
      : '';
    // HITS clickable solo si hay >0; mantiene mismo patrón que SOURCES.
    const hitsCell = t.hits > 0
      ? `<button type="button" class="hits-link" data-target-id="${escapeHTML(t.id)}" title="Ver items de ${escapeHTML(t.name)}"><b>${t.hits}</b></button>`
      : `<b>${t.hits}</b>`;
    return `
    <div class="target ${cls}" data-target-id="${escapeHTML(t.id)}">
      <div class="id">${escapeHTML(t.id)}</div>
      <div class="name">${escapeHTML(t.name)}</div>
      <div class="desc">${escapeHTML(t.desc)}</div>
      <div class="stat">HITS ${hitsCell} · ${stateLabel}</div>
      ${countdown}
      ${fase}
    </div>`;
  }).join('');

  $$('#watchlist .hits-link').forEach(b => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      openTargetModal(b.dataset.targetId);
    });
  });
}

/* Abre el modal con los items que matchean un organismo del watchlist.
   Usa `target.item_ids` (pre-computado en el backend) para evitar
   replicar la lógica de normalización + match. */
function openTargetModal(targetId) {
  const t = (DATA.targets || []).find(x => x.id === targetId);
  if (!t) return;
  const ids = new Set(t.item_ids || []);
  const items = DATA.items.filter(it => ids.has(it.id_hash));
  const meta = [
    `${items.length} ITEM${items.length === 1 ? '' : 'S'}`,
    t.urgent ? 'URGENT' : (t.active ? 'ACTIVE' : 'COLD'),
    t.days_until !== null && t.days_until !== undefined
      ? (t.days_until <= 0 ? 'CIERRA HOY'
         : t.days_until === 1 ? 'CIERRA MAÑANA'
         : `CIERRA EN ${t.days_until}D`)
      : null,
  ].filter(Boolean).join(' · ');
  openTerminalModal({
    title: `TARGET · ${t.name}`,
    meta,
    items,
  });
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
║  ░ chan: @vigia_enfermeria_lt_bot                   ║
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
      <div class="line"><span class="p">$</span>open https://t.me/vigia_enfermeria_lt_bot</div>
      <div class="line"><span class="p">$</span>send <span class="amber">/start</span> &nbsp;<span class="muted">// future: the bot will reply with a 6-digit pairing code</span></div>
      <div class="line"><span class="amber">!</span> <span class="muted">Self-service pairing not wired yet — see panel on the right for the manual flow.</span></div>
      <div class="submit-row">
        <button class="btn-term" id="sub-next" disabled style="opacity:0.45;cursor:not-allowed">[ COMING SOON ]</button>
        <a class="btn-term ghost" href="https://t.me/vigia_enfermeria_lt_bot" target="_blank" rel="noopener">OPEN TELEGRAM →</a>
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
<span class="dim">│</span>  │  CMA / AYTO  │    │  strong+weak │    │  sonnet-4.6  │
<span class="dim">│</span>  │  CANAL CODEM │    │  hash dedupe │    │  + tool use  │
<span class="dim">│</span>  │  DATOS BOAM  │    │  + classify  │    │  structured  │
<span class="dim">│</span>  └──────────────┘    └──────────────┘    └──────────────┘
<span class="dim">│</span>          │                                          │
<span class="dim">│</span>          ▼                                          ▼
<span class="dim">│</span>  ┌──────────────┐                          ┌──────────────┐
<span class="dim">│</span>  │  <span class="amb">SQLite</span>      │◀─────────────────────────│  <span class="fg">DISPATCH</span>    │
<span class="dim">│</span>  │  vigía.db    │  store hits + summaries  │  Telegram    │──▶ subscribers
<span class="dim">│</span>  │  rama state  │                          │  bot         │
<span class="dim">│</span>  └──────────────┘                          └──────────────┘
<span class="dim">│</span>          │
<span class="dim">│</span>          └──▶ <span class="fg">EXPORT</span> ──▶ data/*.json ──▶ git push gh-pages ──▶ <span class="amb">YOU ARE HERE</span>
<span class="dim">│</span>
<span class="dim">└────────────────────────────────────────────────────────────┘</span>`;
  $('#diagram').innerHTML = diag;

  const entries = DATA.changelog || [];
  const repoUrl = 'https://github.com/tragabytes/vigia-enfermeria';
  const entriesHTML = entries.length
    ? entries.map(e => {
        const scope = e.scope ? `<span class="muted">[${escapeHTML(e.scope)}]</span> ` : '';
        const link = `<a href="${repoUrl}/commit/${encodeURIComponent(e.commit)}" target="_blank" rel="noopener">${escapeHTML(e.commit)}</a>`;
        const body = e.body ? `<p>${escapeHTML(e.body)}</p>` : '';
        return `
          <div class="entry">
            <span class="stamp">${escapeHTML(e.date)} · ${link}</span>
            <div class="title">${scope}${escapeHTML(e.title)}</div>
            ${body}
          </div>`;
      }).join('')
    : '<p class="muted">No commits to show — fetch-depth limited or git unavailable in this run.</p>';

  $('#changelog').innerHTML = `<h4>// FIELD NOTES</h4>${entriesHTML}`;
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
    <span class="right">© ${new Date().getUTCFullYear()} · NO COOKIES · NO TRACKERS · STATIC HTML</span>
  `;
}

/* ---- Scroll-driven effects ----------------------------------------------
   En móvil (≤900px) las secciones nacen ocultas (.pre-glitch) y un
   IntersectionObserver les pone .glitch-in cuando entran al viewport.
   También diferimos el countUp de los counters y la animación de
   bars/donut hasta que cada bloque sea visible. En desktop (o con IO no
   soportado o reduced-motion) disparamos todo al instante: las
   transitions CSS existentes hacen el resto.
   ---------------------------------------------------------------------- */
function initScrollEffects() {
  const isMobile = window.matchMedia('(max-width: 900px)').matches;
  const supportsIO = 'IntersectionObserver' in window;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (!isMobile || !supportsIO || reduced) {
    // Fuera de la ruta lazy: limpiamos cualquier .pre-glitch que hayamos
    // dejado puesto en prepGlitchMobile y aplicamos estado final ya.
    document.querySelectorAll('.shell > section.pre-glitch').forEach(s => {
      s.classList.remove('pre-glitch');
    });
    fireAllAnimationsNow();
    return;
  }

  // ----- Mobile: glitch-in para secciones -------------------------------
  const sectionObs = new IntersectionObserver((entries, obs) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.classList.remove('pre-glitch');
      e.target.classList.add('glitch-in');
      obs.unobserve(e.target);
    });
  }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });
  document.querySelectorAll('.shell > section.pre-glitch').forEach(s => sectionObs.observe(s));

  // ----- Mobile: counters lazy -----------------------------------------
  const counterObs = new IntersectionObserver((entries, obs) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      countUp(e.target, +e.target.dataset.counter);
      obs.unobserve(e.target);
    });
  }, { threshold: 0.4 });
  document.querySelectorAll('[data-counter]').forEach(el => counterObs.observe(el));

  // ----- Mobile: charts lazy (bars + donut) ----------------------------
  const chartObs = new IntersectionObserver((entries, obs) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      animateChartPanel(e.target);
      obs.unobserve(e.target);
    });
  }, { threshold: 0.2 });
  document.querySelectorAll('.intel .panel').forEach(p => chartObs.observe(p));
}

function fireAllAnimationsNow() {
  document.querySelectorAll('[data-counter]').forEach(el => countUp(el, +el.dataset.counter));
  document.querySelectorAll('.intel .panel').forEach(animateChartPanel);
}

/* Aplica el estado final (target) a un panel de Intelligence. Envuelto en
   rAF para garantizar que el browser pinta el estado inicial (width=0,
   dasharray="0 C") antes de la mutación, así la transition CSS dispara
   en lugar de saltarse. */
function animateChartPanel(panel) {
  requestAnimationFrame(() => {
    panel.querySelectorAll('.bar-row .fill[data-w]').forEach(f => {
      f.style.width = f.dataset.w + '%';
    });
    panel.querySelectorAll('circle[data-target-dasharray]').forEach(c => {
      c.setAttribute('stroke-dasharray', c.dataset.targetDasharray);
    });
  });
}

/* ---- Collapsible sections (móvil) -----------------------------------
   Cada section-title se vuelve clickable y pliega/despliega el resto
   de la sección. El handler se añade siempre, pero el CSS asociado
   (.collapsed, cursor:pointer, chevron ▾) sólo aplica en ≤900px, así
   que en desktop clickar es un no-op visual. */
function initCollapsibleSections() {
  document.querySelectorAll('.shell > section .section-title').forEach(t => {
    t.addEventListener('click', (e) => {
      // No interferir con clicks sobre links/inputs internos.
      if (e.target.closest('a, button, input, select')) return;
      t.parentElement.classList.toggle('collapsed');
    });
  });
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
