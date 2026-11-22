/* Codebase Tutor interactive report. Vanilla JS; data from data.js (window.CT_DATA). Works from file://. */
(function () {
  'use strict';
  const D = window.CT_DATA;
  if (!D) { document.getElementById('main').textContent = 'data.js missing — regenerate with `ct report`.'; return; }
  const store = {
    get(k) { try { return window.localStorage.getItem('ct:' + k); } catch (e) { return null; } },
    set(k, v) { try { window.localStorage.setItem('ct:' + k, v); } catch (e) { /* ignore */ } }
  };
  let lang = store.get('lang') || D.meta.default_lang || 'en';
  if (!D.i18n[lang]) lang = 'en';

  // ------------------------------------------------------------------ helpers
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function t(key, vars) {
    let s = (D.i18n[lang] && D.i18n[lang][key]) || (D.i18n.en && D.i18n.en[key]) || key;
    if (vars) for (const k in vars) s = s.split('{' + k + '}').join(vars[k]);
    return s;
  }
  function loc(obj) {
    if (obj == null) return '';
    if (typeof obj === 'string' || Array.isArray(obj)) return obj;
    return obj[lang] || obj.en || Object.values(obj)[0] || '';
  }
  const hasLang = (obj) => obj && typeof obj === 'object' && !Array.isArray(obj) && obj[lang] != null;
  function badge(level, label) {
    const key = 'v_' + level;
    const text = label || (D.i18n.en[key] ? t(key) : level);
    return `<span class="badge b-${esc(level)}" title="${esc(D.i18n.en[key + '_desc'] ? t(key + '_desc') : '')}">${esc(text)}</span>`;
  }
  const codeHref = (file, s, e) => '#/code/' + encodeURIComponent(file) + (s ? ':' + s + (e && e !== s ? '-' + e : '') : '');
  const ref = (file, s, e) => file ? `<a class="ref" href="${codeHref(file, s, e)}">${esc(file)}${s ? ':' + s + (e && e !== s ? '-' + e : '') : ''}</a>` : '';
  const fmtDate = (ts) => { try { return new Date(ts * 1000).toLocaleString(); } catch (e) { return String(ts); } };
  const fileLang = (p) => /\.py$/.test(p) ? 'py' : /\.(m?[jt]sx?|cjs|mts|cts)$/.test(p) ? 'js' : 'txt';
  const symById = new Map(D.symbols.map((s) => [s[0], s]));
  const symsByFile = new Map();
  D.symbols.forEach((s) => { if (!symsByFile.has(s[4])) symsByFile.set(s[4], []); symsByFile.get(s[4]).push(s); });

  // ------------------------------------------------------------------ syntax highlighting (lightweight)
  const KW = {
    js: new Set('async await break case catch class const continue debugger default delete do else export extends finally for from function if import in instanceof let new of return static super switch this throw try typeof var void while with yield interface type enum implements private public protected readonly null undefined true false'.split(' ')),
    py: new Set('and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield None True False self cls'.split(' '))
  };
  const RX = {
    js: /(\/\/.*$|\/\*.*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b\d+(?:\.\d+)?\b|[A-Za-z_$][\w$]*(?=\s*\()|[A-Za-z_$][\w$]*)/g,
    py: /(#.*$|"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|[A-Za-z_][\w]*(?=\s*\()|[A-Za-z_][\w]*)/g
  };
  function hl(line, lg) {
    if (lg === 'txt' || line.length > 2000) return esc(line);
    const rx = RX[lg]; const kw = KW[lg];
    let out = ''; let last = 0; let m;
    rx.lastIndex = 0;
    while ((m = rx.exec(line))) {
      out += esc(line.slice(last, m.index));
      const tok = m[0]; let cls = null;
      const c0 = tok[0];
      if ((lg === 'js' && (tok.startsWith('//') || tok.startsWith('/*'))) || (lg === 'py' && c0 === '#')) cls = 'com';
      else if (c0 === '"' || c0 === "'" || c0 === '`') cls = 'str';
      else if (/^\d/.test(tok)) cls = 'num';
      else if (kw.has(tok)) cls = 'kw';
      else if (line.slice(m.index + tok.length).match(/^\s*\(/)) cls = 'fn';
      out += cls ? `<span class="tk-${cls}">${esc(tok)}</span>` : esc(tok);
      last = m.index + tok.length;
    }
    return out + esc(line.slice(last));
  }
  function codeBlock(file, start, end, opts) {
    opts = opts || {};
    const src = D.sources[file];
    if (!src) return `<div class="empty small">${esc(t('not_embedded'))} ${ref(file, start, end)}</div>`;
    const lg = fileLang(file);
    const s = Math.max(1, (start || 1) - (opts.context || 0));
    const e = Math.min(src.length, (end || src.length) + (opts.context || 0));
    const hlset = new Set(opts.highlight || []);
    let html = '';
    for (let n = s; n <= e; n++) {
      const cls = ['ln'];
      if (hlset.has(n)) cls.push('hl');
      if (opts.cur === n) cls.push('cur');
      if (opts.dimOutside && (n < start || n > end)) cls.push('dim');
      html += `<div class="${cls.join(' ')}" data-n="${n}"><span class="no">${n}</span><span class="tx">${hl(src[n - 1] || '', lg)}</span></div>`;
    }
    return `<div class="code"${opts.id ? ` id="${opts.id}"` : ''}>${html}</div>`;
  }
  function parseRange(spec) {
    const s = String(spec || ''); const [a, b] = s.split('-');
    return [parseInt(a, 10), parseInt(b || a, 10)];
  }
  function hlList(spec) {
    const out = [];
    String(spec || '').split(',').forEach((p) => { if (p.trim()) { const [a, b] = parseRange(p.trim()); for (let i = a; i <= b; i++) out.push(i); } });
    return out;
  }
  function evidenceBlock(ev) {
    const [s, e] = parseRange(ev.lines);
    const st = ev.current_status || 'valid';
    const stBadge = st === 'valid' ? '' : `<span class="badge b-${esc(st)}">${esc(t('ev_' + st))}</span>` + (ev.relocated_lines ? ` <span class="small">${esc(t('relocated_to'))} ${ref(ev.file, ...parseRange(ev.relocated_lines))}</span>` : '');
    return `<div class="evidence"><div class="evh">${ref(ev.file, s, e)}${ev.symbol ? ` · <code>${esc(ev.symbol)}</code>` : ''} ${ev.status ? badge(ev.status) : ''} ${stBadge}</div>` +
      codeBlock(ev.file, s, e, { highlight: hlList(ev.highlight), context: 1, dimOutside: true }) + '</div>';
  }
  function md(text) {
    if (!text) return '';
    if (Array.isArray(text)) text = text.map((x) => '- ' + x).join('\n');
    const blocks = []; let s = String(text);
    s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lg, code) => { blocks.push(`<pre><code>${esc(code)}</code></pre>`); return `\u0000${blocks.length - 1}\u0000`; });
    s = esc(s);
    s = s.replace(/`([^`]+)`/g, (_, c) => {
      const m = c.match(/^([\w.@/-]+\.[A-Za-z0-9]{1,6}):(\d+)(?:-(\d+))?$/);
      return m ? `<a class="ref" href="${codeHref(m[1], +m[2], m[3] ? +m[3] : null)}">${c}</a>` : `<code>${c}</code>`;
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/(^|\W)_([^_]+)_(?=\W|$)/g, '$1<em>$2</em>');
    s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    const lines = s.split('\n'); let html = ''; let inList = false;
    for (const ln of lines) {
      const h = ln.match(/^(#{1,4})\s+(.*)$/);
      const li = ln.match(/^\s*[-*]\s+(.*)$/) || ln.match(/^\s*\d+\.\s+(.*)$/);
      if (li) { if (!inList) { html += '<ul>'; inList = true; } html += `<li>${li[1]}</li>`; continue; }
      if (inList) { html += '</ul>'; inList = false; }
      if (h) html += `<h4>${h[2]}</h4>`;
      else if (ln.trim()) html += `<p>${ln}</p>`;
    }
    if (inList) html += '</ul>';
    return `<div class="md">${html.replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[+i])}</div>`;
  }
  function empty(msgKey, cmd) {
    return `<div class="empty">${esc(t(msgKey))}${cmd ? ` <code>${esc(cmd)}</code>` : ''}</div>`;
  }

  // ------------------------------------------------------------------ chrome
  const TABS = ['overview', 'architecture', 'dataflow', 'flows', 'code', 'learn', 'contribute', 'changes', 'simulation'];
  const state = { tab: 'overview', arg: '', flowIdx: 0, step: 0, playing: false, speed: 1, timer: null, archMode: 'modules', archModule: null, simTab: 'l1', learnLevel: 'all', playTo: null };
  const VZ = window.CTViz || null;
  const SM = D.system_map && D.system_map.nodes && D.system_map.nodes.length ? D.system_map : null;
  let live = [];        // running visualisations, destroyed on every render
  let flowStage = null; let dashTimer = null;
  const SYM_OPTS = { symFile: (id) => (symById.get(id) || [])[4] || null, symName: (id) => (symById.get(id) || [])[2] || null };
  function counts() {
    return {
      dataflow: SM ? SM.nodes.filter((n) => n.kind === 'storage').length : 0, flows: D.flows.length, learn: D.explanations.filter((e) => e.type !== 'flow-notes').length, contribute: D.contexts.length,
      changes: D.changes ? D.changes.files.length : 0, simulation: D.test_runs.length + D.runtime.length, code: Object.keys(D.sources).length
    };
  }
  function chrome() {
    document.documentElement.lang = lang === 'hinglish' ? 'hi-Latn' : lang;
    document.title = t('report_title') + ' — ' + D.meta.repo_name;
    $('#repo-title').textContent = D.meta.repo_name;
    $('#meta-line').innerHTML = `${esc(t('commit'))} <code>${esc((D.meta.commit || 'n/a').slice(0, 10))}</code>${D.meta.dirty ? ' · ' + esc(t('dirty_tree')) : ''} · ${esc(D.meta.branch || '')} · ${esc(t('generated'))} ${esc(fmtDate(D.meta.generated_at))}`;
    $('#legend-btn').textContent = t('legend_btn');
    const sel = $('#lang-select');
    sel.innerHTML = D.meta.languages.map((l) => `<option value="${l}"${l === lang ? ' selected' : ''}>${esc((D.i18n[l] || {}).lang_name || l)}</option>`).join('');
    const c = counts();
    $('#sidenav').innerHTML = TABS.map((k) => `<a href="#/${k}" data-tab="${k}" class="${state.tab === k ? 'active' : ''}">${esc(t('nav_' + k))}${c[k] ? `<span class="count">${c[k]}</span>` : ''}</a>`).join('') +
      `<div class="sep"></div><div class="hint">${esc(t('nav_hint'))}</div>`;
    $('#legend').innerHTML = `<strong>${esc(t('legend_title'))}</strong><p class="small muted">${esc(t('legend_intro'))}</p><dl>` +
      ['verified-source', 'structurally-inferred', 'test-verified', 'runtime-observed', 'partially-verified', 'not-verified'].map((l) => `<dt>${badge(l)}</dt><dd>${esc(t('v_' + l + '_desc'))}</dd>`).join('') +
      `</dl><p class="small muted">${esc(t('legend_ids'))}</p><button id="legend-close">${esc(t('close'))}</button>`;
    $('#legend-close').onclick = () => { $('#legend').hidden = true; };
  }
  $('#legend-btn').onclick = () => { const l = $('#legend'); l.hidden = !l.hidden; };
  $('#lang-select').onchange = (e) => { lang = e.target.value; store.set('lang', lang); route(); };

  // ------------------------------------------------------------------ views
  const V = {};
  V.overview = function () {
    const ov = D.overview; const p = ov.project || {};
    const cov = ov.coverage;
    const totalLines = ov.languages.reduce((a, l) => a + l.lines, 0);
    const routes = ov.routes.filter((r) => r.kind === 'route');
    const ovExp = D.explanations.find((e) => e.id === 'overview' || e.topic === 'architecture');
    const storages = SM ? SM.nodes.filter((n) => n.kind === 'storage') : [];
    let h = `<section class="hero"><div class="hero-grid" aria-hidden="true"></div><div class="hero-glow" aria-hidden="true"></div><div class="hero-in">` +
      `<div class="eyebrow">${esc(t('hero_eyebrow'))}</div><h1>${esc(p.name || D.meta.repo_name)}</h1>` +
      `<p class="sub">${p.description ? esc(p.description) + ' · ' + ref(p.file, p.line) : esc(t('no_description'))}</p>` +
      `<div class="chips hero-chips">${(ov.frameworks || []).slice(0, 5).map((f) => `<span class="chip">${esc(f.name)}</span>`).join('')}${storages.slice(0, 5).map((n) => `<span class="chip store-chip" style="--kc:var(${VZ ? VZ.kindColorVar(n.storage_kind) : '--accent'})">${VZ ? VZ.iconMarkup(n.storage_kind, 14) : ''}${esc(n.label)}</span>`).join('')}</div>` +
      `<div class="stats hero-stats">` + [
        [Object.values(cov.by_role || {}).reduce((a, b) => a + b, 0), t('files')], [totalLines, t('code_lines')],
        [ov.languages.length, t('languages')], [Object.values(ov.symbols || {}).reduce((a, b) => a + b, 0), t('symbols')],
        [routes.length, t('routes')], [ov.test_files, t('test_files')]
      ].map(([v, k], i) => `<div class="stat" style="--d:${i * 70}ms"><div class="v" data-count="${+v || 0}">${(+v || 0).toLocaleString()}</div><div class="k">${esc(k)}</div></div>`).join('') + `</div></div></section>`;
    if (SM && VZ) h += `<div class="card mini-map"><div class="row"><strong>${esc(t('df_title'))}</strong><span class="small muted">${esc(t('df_shown_of', { shown: SM.modules_shown, total: SM.modules_total }))}</span><span class="spacer"></span><a href="#/dataflow">${esc(t('df_open_full'))} →</a></div><div id="mini-map"></div></div>`;
    if (ovExp) h += `<div class="card">${renderExplanation(ovExp, true)}</div>`;
    else h += `<div class="card"><strong>${esc(t('summary'))}</strong>${md(t('auto_summary', {
      lang: ov.languages[0] ? ov.languages[0].lang : '—', share: ov.languages[0] ? Math.round(ov.languages[0].share * 100) : 0,
      fw: (ov.frameworks || []).map((f) => f.name).slice(0, 4).join(', ') || t('none_detected'),
      entries: ov.entry_points.length, routes: routes.length, tests: ov.test_files
    }))}<p class="small muted">${esc(t('auto_summary_note'))}</p></div>`;
    const cats = ['frameworks', 'databases', 'auth', 'security', 'external_services', 'queues', 'realtime', 'test_frameworks', 'build', 'lint', 'package_managers', 'ci', 'containers'];
    h += `<h2>${esc(t('stack'))}</h2><div class="grid cols-2">`;
    cats.forEach((c) => {
      const items = ov[c] || []; if (!items.length) return;
      h += `<div class="card"><div class="small muted">${esc(t('cat_' + c))}</div><div class="chips" style="margin-top:6px">` +
        items.map((it) => `<a class="chip" href="${codeHref(it.file, it.line)}" title="${esc(t('evidence'))}: ${esc(it.file)}${it.line ? ':' + it.line : ''}">${esc(it.name)}<span class="ev">${esc(it.file.split('/').pop())}${it.line ? ':' + it.line : ''}</span></a>`).join('') + `</div></div>`;
    });
    h += `</div>`;
    if (ov.monorepo) h += `<p><strong>${esc(t('monorepo'))}:</strong> ${esc(ov.monorepo.type)} — ${(ov.monorepo.packages || []).length} ${esc(t('packages'))}</p>`;
    h += `<div class="grid cols-2"><div><h2>${esc(t('structure'))}</h2><div class="card"><table><thead><tr><th>${esc(t('folder'))}</th><th class="num">${esc(t('files'))}</th><th class="num">${esc(t('lines'))}</th><th>${esc(t('layer_hint'))}</th></tr></thead><tbody>` +
      ov.structure.slice(0, 20).map((s) => `<tr><td class="mono">${esc(s.path)}</td><td class="num">${s.files}</td><td class="num">${s.lines.toLocaleString()}</td><td>${s.layer_hint ? `<span class="badge b-inferred">${esc(s.layer_hint)}</span>` : '—'}</td></tr>`).join('') +
      `</tbody></table><p class="small muted">${esc(t('layer_hint_note'))}</p></div></div>`;
    h += `<div><h2>${esc(t('entry_points'))}</h2><div class="card"><ul class="list">` + (ov.entry_points.length ? ov.entry_points.slice(0, 12).map((e) => `<li>${e.file ? ref(e.file) + '<br>' : ''}<span class="small">${esc(e.reason)}</span> · ${ref(e.evidence.file, e.evidence.line)}</li>`).join('') : `<li class="muted">${esc(t('none_found'))}</li>`) + `</ul></div>`;
    h += `<h2>${esc(t('hubs'))}</h2><div class="card"><ul class="list">` + ov.hubs.slice(0, 8).map((x) => `<li>${ref(x.file)} <span class="small muted">${esc(t('imported_by_n', { n: x.imported_by_files }))} · ${esc(t('incoming_calls_n', { n: x.incoming_calls }))}</span></li>`).join('') + `</ul></div></div></div>`;
    h += `<h2>${esc(t('learning_path'))}</h2><div class="card"><ol>` + ov.learning_path.map((s) => `<li>${s.kind === 'trace-route' ? `<a href="#/flows">${esc(s.target)}</a> · ${ref(s.file, s.line)}` : ref(s.target)} — <span class="muted">${esc(s.why)}</span></li>`).join('') + `</ol></div>`;
    if (routes.length) {
      h += `<h2>${esc(t('routes'))} (${routes.length})</h2><div class="card" style="max-height:340px;overflow:auto"><table><thead><tr><th>${esc(t('method'))}</th><th>${esc(t('path'))}</th><th>${esc(t('defined_at'))}</th><th>${esc(t('framework'))}</th></tr></thead><tbody>` +
        routes.slice(0, 200).map((r) => `<tr><td class="mono">${esc(r.method)}</td><td class="mono">${esc(r.full_path || r.path)}</td><td>${ref(r.file, r.line)}</td><td>${esc(r.framework)}</td></tr>`).join('') + `</tbody></table></div>`;
    }
    if (ov.env_var_names.length) h += `<h2>${esc(t('env_vars'))}</h2><p class="small muted">${esc(t('env_vars_note'))}</p><div class="chips">` + ov.env_var_names.slice(0, 60).map((e) => `<a class="chip mono" href="${codeHref(e.refs[0].file, e.refs[0].line)}">${esc(e.name)}</a>`).join('') + `</div>`;
    h += `<h2>${esc(t('coverage'))}</h2><div class="card"><table><thead><tr><th>${esc(t('language'))}</th><th class="num">${esc(t('files'))}</th><th class="num">${esc(t('lines'))}</th><th class="num">${esc(t('analyzed'))}</th><th class="num">${esc(t('partial'))}</th><th class="num">${esc(t('inventory_only'))}</th><th class="num">${esc(t('failed'))}</th></tr></thead><tbody>` +
      ov.languages.map((l) => `<tr><td>${esc(l.lang)}</td><td class="num">${l.files}</td><td class="num">${l.lines.toLocaleString()}</td><td class="num">${l.analyzed}</td><td class="num">${l.partial}</td><td class="num">${l.inventory_only}</td><td class="num">${l.failed}</td></tr>`).join('') +
      `</tbody></table><p class="small">${esc(t('calls_resolution', { total: cov.calls_total, unresolved: cov.calls_unresolved }))}</p>` +
      (cov.excluded_dir_count ? `<p class="small muted">${esc(t('excluded_dirs', { n: cov.excluded_dir_count }))}: ${Object.keys(cov.excluded_dirs).slice(0, 12).map((d) => `<code>${esc(d)}</code>`).join(', ')}</p>` : '') +
      `<p class="small muted">${esc(t('limitations_static'))}</p>` +
      (ov.cycle_count ? `<p class="small">${esc(t('cycles_found', { n: ov.cycle_count }))}: ${ov.cycles.slice(0, 3).map((c) => c.map((f) => ref(f)).join(' ↔ ')).join('<br>')}</p>` : '') + `</div>`;
    return h;
  };
  V.overview.after = function () {
    if (VZ) VZ.countUp($('.hero'));
    const mm = $('#mini-map');
    if (mm && SM && VZ) live.push(VZ.SystemMap(mm, SM, { t, compact: true, onSelect: () => { location.hash = '#/dataflow'; } }));
  };

  // ---- data flow / system map
  const BASIS = { 'entry point': 'df_basis_entry', 'defines routes': 'df_basis_routes', 'contains route handlers': 'df_basis_handlers', 'folder naming (inferred)': 'df_basis_folder' };
  function evRefs(list, n) {
    return (list || []).slice(0, n || 4).map((x) => `<li>${ref(x.file, x.line)} <span class="small muted">${esc(x.text || '')}</span></li>`).join('');
  }
  function flowToMapSeq(f) {
    const fileNode = new Map();
    SM.nodes.forEach((n) => (n.file_list || []).forEach((p) => fileNode.set(p, n.id)));
    const ids = new Set(SM.nodes.map((n) => n.id));
    const seq = []; const stepOf = [];
    const raw = VZ.participantsFor(f, SYM_OPTS).seq;
    raw.forEach((pid, i) => {
      const id = String(pid).startsWith('@') ? pid : (fileNode.get(pid) || null);
      if (id && ids.has(id) && seq[seq.length - 1] !== id) { seq.push(id); stepOf.push(i); }
    });
    if (ids.has('@client') && seq.length && seq[0] !== '@client' && SM.edges.some((e) => e.source === '@client' && e.target === seq[0])) { seq.unshift('@client'); stepOf.unshift(0); }
    return { seq, stepOf };
  }
  V.dataflow = function () {
    let h = `<h1>${esc(t('nav_dataflow'))}</h1><p class="sub">${esc(t('df_sub'))}</p>`;
    if (!SM) return h + empty('df_empty', 'ct scan');
    if (!VZ) return h + empty('graph_lib_missing');
    const stores = SM.nodes.filter((n) => n.kind === 'storage');
    const kinds = Array.from(new Set(stores.map((n) => n.storage_kind)));
    h += `<div class="player df-tools"><button id="df-pause">${VZ.reduceMotion ? '▶ ' + esc(t('df_resume')) : '❚❚ ' + esc(t('df_pause'))}</button>` +
      (D.flows.length ? `<label class="small">${esc(t('df_replay'))} <select id="df-flow"><option value="">${esc(t('df_replay_pick'))}</option>${D.flows.map((f, i) => `<option value="${i}">${esc(f.title)}</option>`).join('')}</select></label><button class="primary" id="df-replay">▶ ${esc(t('df_replay_btn'))}</button>` : `<span class="small muted">${esc(t('df_no_flows'))} <code>ct trace "GET /"</code></span>`) +
      `<span class="spacer"></span><span class="small muted">${esc(t('df_shown_of', { shown: SM.modules_shown, total: SM.modules_total }))}</span></div>` +
      `<div class="df-legend small"><span><i class="sw sw-request"></i>${esc(t('df_edge_request'))}</span><span><i class="sw sw-call"></i>${esc(t('df_edge_call'))}</span><span><i class="sw sw-data"></i>${esc(t('df_edge_data'))}</span>` +
      kinds.map((k) => `<span class="lk" style="--kc:var(${VZ.kindColorVar(k)})">${VZ.iconMarkup(k, 15)}${esc(t('df_kind_' + k))}</span>`).join('') + `</div>` +
      `<div class="dfgrid"><div class="card map-card"><div id="sysmap"></div><div id="df-cap" class="replay-cap" hidden></div></div>` +
      `<div class="card df-detail" id="df-detail"><p class="muted">${esc(t('df_detail_hint'))}</p></div></div>`;
    h += `<h2>${esc(t('df_storages'))}</h2>`;
    if (!stores.length) h += empty('df_no_storages');
    else h += `<div class="grid cols-3 storage-grid">` + stores.map((n, i) => {
      const inc = SM.edges.filter((e) => e.target === n.id);
      const ev = inc.flatMap((e) => e.evidence || []);
      return `<div class="card store-card" style="--kc:var(${VZ.kindColorVar(n.storage_kind)});--d:${i * 60}ms" data-node="${esc(n.id)}"><div class="row"><span class="store-ico">${VZ.iconMarkup(n.storage_kind, 26)}</span><div><strong>${esc(n.label)}</strong><div class="small muted">${esc(t('df_kind_' + n.storage_kind))}</div></div></div>` +
        `<div class="chips" style="margin:8px 0">${(n.packages || []).map((p) => `<code class="chip mono">${esc(p)}</code>`).join('')}</div>` +
        `<div class="small"><strong>${esc(t('df_used_by'))}:</strong> ${inc.map((e) => `<code>${esc(e.source)}</code>`).join(', ')}</div>` +
        (ev.length ? `<ul class="list small">${evRefs(ev, 3)}</ul>` : '') + `</div>`;
    }).join('') + `</div>`;
    h += `<p class="small muted">${esc(t('df_note'))}</p>`;
    return h;
  };
  function dfDetail(n, edges) {
    const el = $('#df-detail'); if (!el) return;
    const out = edges.filter((e) => e.source === n.id); const inn = edges.filter((e) => e.target === n.id);
    const label = (id) => { const x = SM.nodes.find((m) => m.id === id); return x ? x.label : id; };
    const list = (es, other) => es.map((e) => `<li><span class="sw sw-${esc(e.kind)}"></span><strong>${esc(label(e[other]))}</strong> <span class="small muted">${esc(e.label || '')}</span> ${badge(e.verification)}<ul class="list small ev-list">${evRefs(e.evidence, 3)}</ul></li>`).join('') || `<li class="muted">—</li>`;
    let h = `<div class="row"><span class="store-ico" style="--kc:var(${n.kind === 'storage' ? VZ.kindColorVar(n.storage_kind) : '--accent'})">${VZ.iconMarkup(n.kind === 'storage' ? n.storage_kind : n.kind === 'client' ? 'client' : 'module', 24)}</span><h3 class="mono" style="margin:0">${esc(n.label)}</h3></div>`;
    if (n.kind === 'module') {
      const basis = BASIS[n.layer_basis];
      h += `<p class="small">${esc(t('df_layer_' + n.layer))} · ${n.files} ${esc(t('files').toLowerCase())} · ${(n.lines || 0).toLocaleString()} ${esc(t('lines').toLowerCase())}</p>` +
        `<p class="small"><strong>${esc(t('df_layer_basis'))}:</strong> ${esc(basis ? t(basis) : n.layer_basis || '')} ${badge(n.layer_basis === 'folder naming (inferred)' ? 'structurally-inferred' : 'verified-source')}</p>`;
    } else if (n.kind === 'storage') {
      h += `<p class="small">${esc(t('df_kind_' + n.storage_kind))}</p><div class="chips">${(n.packages || []).map((p) => `<code class="chip mono">${esc(p)}</code>`).join('')}</div>`;
    } else h += `<p class="small muted">${esc(t('df_client_sub'))}</p>`;
    h += `<h3>${esc(t('df_talks_to'))} (${out.length})</h3><ul class="list">${list(out, 'target')}</ul><h3>${esc(t('df_called_by'))} (${inn.length})</h3><ul class="list">${list(inn, 'source')}</ul>`;
    if (n.file_list && n.file_list.length) h += `<h3>${esc(t('files'))}</h3><ul class="list small">${n.file_list.slice(0, 14).map((f) => `<li>${ref(f)}</li>`).join('')}</ul>`;
    el.innerHTML = h;
    el.classList.remove('pop'); void el.offsetWidth; el.classList.add('pop');
  }
  V.dataflow.after = function () {
    if (!SM || !VZ) return;
    const map = VZ.SystemMap($('#sysmap'), SM, { t, onSelect: dfDetail });
    live.push(map);
    const pb = $('#df-pause');
    pb.onclick = () => { if (map.isRunning()) { map.pause(); pb.innerHTML = '▶ ' + esc(t('df_resume')); } else { map.play(); pb.innerHTML = '❚❚ ' + esc(t('df_pause')); } };
    $$('.store-card').forEach((c) => { c.onclick = () => { const n = SM.nodes.find((x) => x.id === c.dataset.node); if (n) { map.select(n.id); dfDetail(n, SM.edges.filter((e) => e.source === n.id || e.target === n.id)); $('#sysmap').scrollIntoView({ behavior: VZ.reduceMotion ? 'auto' : 'smooth', block: 'center' }); } }; });
    const sel = $('#df-flow'); const btn = $('#df-replay');
    if (!sel) return;
    const run = () => {
      const f = D.flows[+sel.value]; const cap = $('#df-cap');
      if (!f) return;
      const { seq, stepOf } = flowToMapSeq(f);
      cap.hidden = false;
      if (seq.length < 2) { cap.innerHTML = `${esc(t('df_replay_none'))} <a href="#/flows" data-flow="${sel.value}">${esc(t('open_player'))}</a>`; return; }
      map.select(null);
      const say = (k) => { const s = f.steps[stepOf[k]]; cap.innerHTML = `<span class="badge b-${s.outcome === 'failure' ? 'failed' : s.outcome === 'success' ? 'passed' : 'inferred'}">${esc(t('step'))} ${s.n}</span> <strong>${esc(SM.nodes.find((n) => n.id === seq[k]).label)}</strong> — ${esc(s.text)} · ${ref(s.file, s.line)}`; };
      say(0);
      map.replay(seq, say, () => { cap.insertAdjacentHTML('beforeend', ` <span class="small muted">· ${esc(t('df_replay_done'))}</span> <a href="#/flows" data-flow="${sel.value}">${esc(t('open_player'))}</a>`); });
    };
    btn.onclick = run;
    $('#df-cap').addEventListener('click', (e) => { const a = e.target.closest('a[data-flow]'); if (a) { state.flowIdx = +a.dataset.flow; state.step = 0; } });
    const m = /^flow:(\d+)$/.exec(state.arg || '');
    if (m && D.flows[+m[1]]) { sel.value = m[1]; setTimeout(run, 350); }
  };

  // ---- architecture
  let cy = null;
  V.architecture = function () {
    const langs = Array.from(new Set(D.graph.file_nodes.map((n) => n.lang))).sort();
    const layers = Array.from(new Set(D.graph.file_nodes.map((n) => n.layer).filter(Boolean))).sort();
    return `<h1>${esc(t('nav_architecture'))}</h1><p class="sub">${esc(t('arch_sub'))}</p>
    <div class="split"><div class="pane"><div class="pane-h"><input type="search" id="arch-q" placeholder="${esc(t('search_symbols'))}"><div class="searchres" id="arch-res"></div></div>
    <div class="pane-b small"><label>${esc(t('view'))} <select id="arch-mode"><option value="modules">${esc(t('modules'))}</option><option value="files">${esc(t('files'))}</option></select></label><br><br>
    <label>${esc(t('language'))} <select id="arch-lang"><option value="">${esc(t('all'))}</option>${langs.map((l) => `<option>${esc(l)}</option>`).join('')}</select></label><br><br>
    <label>${esc(t('layer_hint'))} <select id="arch-layer"><option value="">${esc(t('all'))}</option>${layers.map((l) => `<option>${esc(l)}</option>`).join('')}</select></label>
    <p class="muted">${esc(t('arch_help'))}</p><p class="muted">${esc(t('layer_hint_note'))}</p></div></div>
    <div class="pane graph-pane"><div class="graph-tools"><button id="arch-fit">${esc(t('fit'))}</button><button id="arch-back" hidden>${esc(t('back_to_modules'))}</button></div><div id="cy"></div></div>
    <div class="pane"><div class="pane-h"><strong>${esc(t('details'))}</strong></div><div class="pane-b" id="arch-detail"><p class="muted">${esc(t('arch_select'))}</p></div></div></div>`;
  };
  V.architecture.after = function () {
    $('#arch-mode').value = state.archMode;
    $('#arch-mode').onchange = (e) => { state.archMode = e.target.value; state.archModule = null; drawGraph(); };
    $('#arch-lang').onchange = drawGraph; $('#arch-layer').onchange = drawGraph;
    $('#arch-fit').onclick = () => cy && cy.fit(undefined, 30);
    $('#arch-back').onclick = () => { state.archMode = 'modules'; state.archModule = null; $('#arch-mode').value = 'modules'; drawGraph(); };
    $('#arch-q').oninput = (e) => searchInto(e.target.value, $('#arch-res'));
    drawGraph();
  };
  function searchInto(q, el) {
    q = q.trim().toLowerCase();
    if (q.length < 2) { el.innerHTML = ''; return; }
    const syms = D.symbols.filter((s) => s[2].toLowerCase().includes(q)).slice(0, 40);
    const files = D.files.filter((f) => f.path.toLowerCase().includes(q)).slice(0, 15);
    el.innerHTML = syms.map((s) => `<a href="${codeHref(s[4], s[5], s[6])}"><span class="kind">${esc(s[3])}</span>${esc(s[2])} <span class="muted small">${esc(s[4])}:${s[5]}</span></a>`).join('') +
      files.map((f) => `<a href="${codeHref(f.path)}"><span class="kind">file</span>${esc(f.path)}</a>`).join('') || `<span class="muted small">${esc(t('no_results'))}</span>`;
  }
  function drawGraph() {
    if (typeof window.cytoscape !== 'function') { $('#cy').innerHTML = `<div class="empty">${esc(t('graph_lib_missing'))}</div>`; return; }
    const fl = $('#arch-lang').value; const ly = $('#arch-layer').value;
    const css = getComputedStyle(document.documentElement);
    const col = (v) => css.getPropertyValue(v).trim() || '#888';
    let nodes = []; let edges = [];
    const fileOk = (n) => (!fl || n.lang === fl) && (!ly || n.layer === ly);
    if (state.archMode === 'modules') {
      const okMods = new Set(D.graph.file_nodes.filter(fileOk).map((n) => n.module));
      nodes = D.graph.modules.nodes.filter((n) => okMods.has(n.id)).map((n) => ({ data: { id: n.id, label: n.id, size: 18 + Math.min(46, Math.sqrt(n.lines || 1)), kind: 'module', layer: n.layer || '' } }));
      const ids = new Set(nodes.map((n) => n.data.id));
      edges = D.graph.modules.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e, i) => ({ data: { id: 'e' + i, source: e.source, target: e.target, w: e.imports + e.calls, label: '' } }));
      $('#arch-back').hidden = true;
    } else {
      let fnodes = D.graph.file_nodes.filter(fileOk);
      if (state.archModule) {
        const inMod = new Set(fnodes.filter((n) => n.module === state.archModule).map((n) => n.id));
        const near = new Set(inMod);
        D.graph.file_edges.forEach((e) => { if (inMod.has(e.source)) near.add(e.target); if (inMod.has(e.target)) near.add(e.source); });
        fnodes = D.graph.file_nodes.filter((n) => near.has(n.id));
        $('#arch-back').hidden = false;
      }
      fnodes = fnodes.slice(0, 400);
      const ids = new Set(fnodes.map((n) => n.id));
      nodes = fnodes.map((n) => ({ data: { id: n.id, label: n.id.split('/').pop(), size: 14 + Math.min(30, Math.sqrt(n.lines || 1)), kind: 'file', layer: n.layer || '', dim: state.archModule && n.module !== state.archModule ? 1 : 0 } }));
      edges = D.graph.file_edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e, i) => ({ data: { id: 'f' + i, source: e.source, target: e.target, w: e.count } }));
    }
    const cycleFiles = new Set(D.graph.cycles.flat());
    if (cy) cy.destroy();
    cy = window.cytoscape({
      container: $('#cy'), elements: nodes.concat(edges),
      style: [
        { selector: 'node', style: { 'background-color': col('--accent'), label: 'data(label)', 'font-size': 10, color: col('--text'), 'text-valign': 'bottom', 'text-margin-y': 3, width: 'data(size)', height: 'data(size)', 'text-wrap': 'ellipsis', 'text-max-width': 120 } },
        { selector: 'node[dim = 1]', style: { opacity: 0.45 } },
        { selector: 'node:selected', style: { 'border-width': 3, 'border-color': col('--hl-border') } },
        { selector: 'edge', style: { width: 'mapData(w, 1, 30, 1, 5)', 'line-color': col('--border'), 'target-arrow-color': col('--muted'), 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', opacity: 0.85 } },
        { selector: 'edge.hot', style: { 'line-color': col('--accent'), 'target-arrow-color': col('--accent'), opacity: 1, 'line-style': 'dashed', 'line-dash-pattern': [7, 4] } },
        { selector: 'node.cycle', style: { 'background-color': col('--bad') } }
      ],
      layout: { name: nodes.length > 250 ? 'concentric' : 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 90, padding: 30 }
    });
    cy.nodes().forEach((n) => { if (cycleFiles.has(n.id())) n.addClass('cycle'); });
    cy.on('tap', 'node', (ev) => { const id = ev.target.id(); cy.edges().removeClass('hot'); ev.target.connectedEdges().addClass('hot'); showNode(id, ev.target.data('kind')); });
    if (dashTimer) clearInterval(dashTimer);
    if (!(VZ && VZ.reduceMotion)) { let off = 0; dashTimer = setInterval(() => { off = (off - 1) % 1000; const hot = cy && cy.edges('.hot'); if (hot && hot.length) hot.style('line-dash-offset', off); }, 40); }
    cy.on('dbltap', 'node[kind = "module"]', (ev) => { state.archMode = 'files'; state.archModule = ev.target.id(); $('#arch-mode').value = 'files'; drawGraph(); });
  }
  function showNode(id, kind) {
    const el = $('#arch-detail');
    if (kind === 'module') {
      const files = D.graph.file_nodes.filter((n) => n.module === id);
      const out = D.graph.modules.edges.filter((e) => e.source === id); const inn = D.graph.modules.edges.filter((e) => e.target === id);
      const exList = (es, dirKey) => es.map((e) => `<li><code>${esc(e[dirKey])}</code> <span class="small muted">${e.imports} ${esc(t('imports'))}, ${e.calls} ${esc(t('calls'))}</span>${(e.examples || []).map((x) => `<br>${ref(x.file, x.line)} → <span class="small">${esc(x.to)}</span>`).join('')}</li>`).join('');
      el.innerHTML = `<h3 class="mono">${esc(id)}</h3><button id="drill">${esc(t('show_files'))}</button><h3>${esc(t('outgoing'))} (${out.length})</h3><ul class="list small">${exList(out, 'target') || `<li class="muted">—</li>`}</ul>` +
        `<h3>${esc(t('incoming'))} (${inn.length})</h3><ul class="list small">${exList(inn, 'source') || `<li class="muted">—</li>`}</ul><h3>${esc(t('files'))} (${files.length})</h3><ul class="list small">${files.slice(0, 60).map((f) => `<li>${ref(f.id)} <span class="muted">${f.symbols} ${esc(t('symbols'))}</span></li>`).join('')}</ul>` +
        `<p class="small">${badge('verified-source', t('edges_from_imports'))}</p>`;
      $('#drill').onclick = () => { state.archMode = 'files'; state.archModule = id; $('#arch-mode').value = 'files'; drawGraph(); };
    } else {
      const imps = D.imports.filter((x) => x[0] === id); const by = D.imports.filter((x) => x[1] === id);
      const syms = (symsByFile.get(id) || []).filter((s) => s[3] !== 'variable');
      el.innerHTML = `<h3 class="mono">${esc(id)}</h3><p>${ref(id)}</p><h3>${esc(t('imports'))} (${imps.length})</h3><ul class="list small">${imps.map((x) => `<li>${ref(id, x[2])} → ${ref(x[1])}</li>`).join('') || '<li class="muted">—</li>'}</ul>` +
        `<h3>${esc(t('imported_by'))} (${by.length})</h3><ul class="list small">${by.map((x) => `<li>${ref(x[0], x[2])}</li>`).join('') || '<li class="muted">—</li>'}</ul>` +
        `<h3>${esc(t('symbols'))} (${syms.length})</h3><ul class="list small">${syms.slice(0, 80).map((s) => `<li><span class="kind">${esc(s[3])}</span><a href="${codeHref(s[4], s[5], s[6])}">${esc(s[2])}</a></li>`).join('')}</ul>`;
    }
  }

  // ---- flows
  function notesFor(flow) {
    const n = D.explanations.find((e) => e.type === 'flow-notes' && e.flow === flow.id);
    return n || null;
  }
  V.flows = function () {
    if (!D.flows.length) return `<h1>${esc(t('nav_flows'))}</h1>` + empty('no_flows', 'ct trace "POST /login"');
    const f = D.flows[state.flowIdx] || D.flows[0];
    const notes = notesFor(f);
    return `<h1>${esc(t('nav_flows'))}</h1><p class="sub">${esc(t('flows_sub'))}</p>
    <div class="row" style="margin-bottom:10px"><label>${esc(t('flow'))} <select id="flow-sel">${D.flows.map((x, i) => `<option value="${i}"${i === state.flowIdx ? ' selected' : ''}>${esc(x.title)} (${x.steps.length})</option>`).join('')}</select></label>
    ${badge(f.verification)} <span class="small muted">${esc(t('flow_static_note'))}</span>${f.stale_steps ? ` <span class="badge b-stale">${esc(t('stale_steps', { n: f.stale_steps }))}</span>` : ''}</div>
    ${notes ? `<div class="card" style="margin-bottom:10px"><strong>${esc(loc(notes.title))}</strong>${notes.summary ? md(loc(notes.summary)) : ''}${!hasLang(notes.title) ? `<p class="small muted">${esc(t('translation_missing'))}</p>` : ''}</div>` : ''}
    <div class="player" role="group" aria-label="${esc(t('playback'))}"><button id="p-restart" aria-label="${esc(t('restart'))}">⏮ ${esc(t('restart'))}</button><button id="p-prev" aria-label="${esc(t('prev'))}">◀ ${esc(t('prev'))}</button>
    <button class="primary" id="p-play">${state.playing ? '❚❚ ' + esc(t('pause')) : '▶ ' + esc(t('play'))}</button><button id="p-next" aria-label="${esc(t('next'))}">${esc(t('next'))} ▶</button>
    <label class="small">${esc(t('speed'))} <select id="p-speed">${[0.5, 1, 2, 4].map((s) => `<option value="${s}"${s === state.speed ? ' selected' : ''}>${s}×</option>`).join('')}</select></label>
    <span class="spacer"></span><span id="p-count" class="small muted"></span></div>
    <div class="flowgrid"><div class="card steps" id="steps"></div><div><div class="card stage-card"><div class="row small"><strong>${esc(t('stage_title'))}</strong><span class="spacer"></span>${SM ? `<a href="#/dataflow/flow:${state.flowIdx}">${esc(t('df_play_on_map'))} →</a>` : ''}</div><svg class="stage" id="stage" role="img" aria-label="${esc(t('stage_title'))}"></svg></div><div id="narr"></div><div id="step-code"></div></div></div>
    <h2>${esc(t('scenarios'))}</h2><div class="card" id="outcomes"></div>`;
  };
  V.flows.after = function () {
    if (!D.flows.length) return;
    const f = D.flows[state.flowIdx] || D.flows[0];
    $('#flow-sel').onchange = (e) => { stopPlay(); state.flowIdx = +e.target.value; state.step = 0; render(); };
    $('#p-restart').onclick = () => { state.step = 0; drawStep(); };
    $('#p-prev').onclick = () => { stopPlay(); state.step = Math.max(0, state.step - 1); drawStep(); };
    $('#p-next').onclick = () => { stopPlay(); state.step = Math.min(f.steps.length - 1, state.step + 1); drawStep(); };
    $('#p-play').onclick = () => { state.playing ? stopPlay() : startPlay(); };
    $('#p-speed').onchange = (e) => { state.speed = +e.target.value; if (state.playing) { stopPlay(); startPlay(); } };
    $('#steps').innerHTML = f.steps.map((s, i) => `<div class="step" data-i="${i}" style="padding-left:${8 + (s.depth || 0) * 14}px"><span class="n">${s.n}</span><span class="o-${s.outcome}">${s.outcome === 'failure' ? '✗' : s.outcome === 'success' ? '✓' : '·'}</span><span>${esc(s.text)}${s.verification !== 'verified-source' ? ' ' + badge(s.verification === 'unresolved' ? 'unresolved' : s.verification, s.verification === 'unresolved' ? t('unresolved') : null) : ''}${s.stale ? ` <span class="badge b-stale">${esc(t('ev_stale'))}</span>` : ''}<span class="meta2">${esc(s.file)}:${s.line}</span></span></div>`).join('');
    $$('#steps .step').forEach((el) => { el.onclick = () => { stopPlay(); state.step = +el.dataset.i; drawStep(); }; });
    $('#outcomes').innerHTML = (f.outcomes || []).length ? `<p class="small muted">${esc(t('scenarios_note'))}</p><ul class="list">` + f.outcomes.map((o) => `<li><span class="badge b-${o.outcome === 'failure' ? 'failed' : 'passed'}">${esc(t('outcome_' + o.outcome))}</span> <a href="#" data-step="${o.step - 1}">${esc(t('step'))} ${o.step}</a> · <code>${esc(o.text)}</code> · ${ref(o.file, o.line)}${o.nearest_guards.length ? `<br><span class="small muted">${esc(t('guards'))}: ${o.nearest_guards.map((g) => `<code>${esc(g.text)}</code>`).join(' → ')}</span>` : ''} <button class="mini" data-play-to="${o.step - 1}">▶ ${esc(t('play_to_here'))}</button></li>`).join('') + '</ul>' : `<p class="muted">${esc(t('no_outcomes'))}</p>`;
    $$('#outcomes a[data-step]').forEach((a) => { a.onclick = (e) => { e.preventDefault(); stopPlay(); state.step = +a.dataset.step; drawStep(); window.scrollTo({ top: 0, behavior: 'smooth' }); }; });
    $$('#outcomes button[data-play-to]').forEach((b) => { b.onclick = () => { stopPlay(); state.step = 0; state.playTo = +b.dataset.playTo; drawStep(); window.scrollTo({ top: 0, behavior: VZ && VZ.reduceMotion ? 'auto' : 'smooth' }); startPlay(); }; });
    flowStage = VZ ? VZ.FlowStage($('#stage'), f, SYM_OPTS) : null;
    drawStep();
  };
  function startPlay() {
    const f = D.flows[state.flowIdx]; state.playing = true;
    const btn = $('#p-play'); if (btn) btn.innerHTML = '❚❚ ' + esc(t('pause'));
    state.timer = setInterval(() => {
      const last = state.playTo != null ? state.playTo : f.steps.length - 1;
      if (state.step >= last) { stopPlay(); return; }
      state.step++; drawStep();
    }, 1400 / state.speed);
  }
  function stopPlay() {
    state.playing = false; state.playTo = null; if (state.timer) clearInterval(state.timer); state.timer = null;
    const btn = $('#p-play'); if (btn) btn.innerHTML = '▶ ' + esc(t('play'));
  }
  function drawStep() {
    const f = D.flows[state.flowIdx]; if (!f) return;
    const s = f.steps[state.step]; if (!s) return;
    $$('#steps .step').forEach((el) => el.classList.toggle('cur', +el.dataset.i === state.step));
    const cur = $(`#steps .step[data-i="${state.step}"]`); if (cur) cur.scrollIntoView({ block: 'nearest' });
    $('#p-count').textContent = t('step_of', { n: state.step + 1, total: f.steps.length });
    // narration
    const notes = notesFor(f);
    const note = notes && notes.step_notes && notes.step_notes[String(s.n)];
    $('#narr').innerHTML = `<div class="narration"><strong>${esc(t('kind_' + s.kind) !== 'kind_' + s.kind ? t('kind_' + s.kind) : s.kind)}</strong> — ${esc(s.text)} ${badge(s.verification === 'unresolved' ? 'unresolved' : s.verification, s.verification === 'unresolved' ? t('unresolved') : null)}${note ? md(loc(note)) : ''}</div>`;
    // code
    const src = D.sources[s.file];
    const end = s.kind === 'enter' ? Math.min(s.end_line || s.line, s.line + 40) : s.line;
    const start = Math.max(1, s.line - (s.kind === 'enter' ? 0 : 6));
    const stop = src ? Math.min(src.length, Math.max(end, s.line + 6)) : end;
    $('#step-code').innerHTML = `<div class="evh small muted" style="padding:6px 0">${ref(s.file, s.line, s.kind === 'enter' ? s.end_line : null)}${s.symbol ? ` · <code>${esc(s.symbol)}</code>` : ''}</div>` +
      codeBlock(s.file, start, stop, { highlight: [s.line], cur: s.line });
    if (flowStage) flowStage.show(state.step);
    const sc = $('#step-code'); if (sc) { sc.classList.remove('flash'); void sc.offsetWidth; sc.classList.add('flash'); }
  }
  // ---- code
  V.code = function () {
    const [file, s, e] = parseCodeArg(state.arg);
    return `<h1>${esc(t('nav_code'))}</h1><p class="sub">${esc(t('code_sub'))}</p>
    <div class="split"><div class="pane"><div class="pane-h"><input type="search" id="tree-q" placeholder="${esc(t('filter_files'))}"></div><div class="pane-b tree" id="tree"></div></div>
    <div class="pane" id="viewer">${file ? '' : `<div class="pane-b">${empty('pick_file')}</div>`}</div>
    <div class="pane"><div class="pane-h"><strong>${esc(t('in_this_file'))}</strong></div><div class="pane-b" id="file-side"></div></div></div>`;
  };
  function parseCodeArg(arg) {
    if (!arg) return [null];
    const m = decodeURIComponent(arg).match(/^(.*?)(?::(\d+)(?:-(\d+))?)?$/);
    return [m[1], m[2] ? +m[2] : null, m[3] ? +m[3] : (m[2] ? +m[2] : null)];
  }
  V.code.after = function () {
    const [file, s, e] = parseCodeArg(state.arg);
    const drawTree = (q) => {
      q = (q || '').toLowerCase();
      const files = D.files.filter((f) => f.role !== 'binary' && f.role !== 'secret' && (!q || f.path.toLowerCase().includes(q)));
      if (q) { $('#tree').innerHTML = files.slice(0, 400).map((f) => `<a href="${codeHref(f.path)}" class="${f.path === file ? 'active' : ''} ${f.embedded ? '' : 'off'}" title="${esc(f.path)}">${esc(f.path)}</a>`).join(''); return; }
      const root = {};
      files.forEach((f) => { const parts = f.path.split('/'); let n = root; parts.slice(0, -1).forEach((p) => { n[p] = n[p] || {}; n = n[p]; }); (n['\u0000'] = n['\u0000'] || []).push(f); });
      const walk = (n, prefix) => Object.keys(n).filter((k) => k !== '\u0000').sort().map((k) => {
        const p = prefix + k + '/'; const open = file && file.startsWith(p);
        return `<details${open ? ' open' : ''}><summary>${esc(k)}</summary><div class="indent">${walk(n[k], p)}</div></details>`;
      }).join('') + (n['\u0000'] || []).map((f) => `<a href="${codeHref(f.path)}" class="${f.path === file ? 'active' : ''} ${f.embedded ? '' : 'off'}" title="${esc(f.embedded ? f.path : t('not_embedded'))}">${esc(f.path.split('/').pop())}</a>`).join('');
      $('#tree').innerHTML = walk(root, '');
    };
    drawTree('');
    $('#tree-q').oninput = (ev) => drawTree(ev.target.value);
    if (!file) return;
    const meta = D.files.find((f) => f.path === file) || {};
    const hlR = []; if (s) for (let i = s; i <= (e || s); i++) hlR.push(i);
    $('#viewer').innerHTML = `<div class="pane-h row"><strong class="mono">${esc(file)}</strong><span class="kind">${esc(meta.lang || '')}</span><span class="kind">${esc(meta.role || '')}</span>${meta.layer ? `<span class="badge b-inferred">${esc(meta.layer)}</span>` : ''}<span class="spacer"></span><span class="small muted">${meta.lines || ''} ${esc(t('lines'))}</span></div>` + codeBlock(file, 1, null, { highlight: hlR, id: 'codeview' });
    if (s) { const el = $(`#codeview .ln[data-n="${s}"]`); if (el) el.scrollIntoView({ block: 'center' }); }
    const syms = (symsByFile.get(file) || []);
    const imps = D.imports.filter((x) => x[0] === file); const by = D.imports.filter((x) => x[1] === file);
    const callers = (sid) => D.symbol_edges.filter((x) => x[1] === sid); const callees = (sid) => D.symbol_edges.filter((x) => x[0] === sid);
    $('#file-side').innerHTML = `<h3>${esc(t('symbols'))} (${syms.length})</h3><ul class="list small">${syms.map((x) => `<li><span class="kind">${esc(x[3])}</span><a href="${codeHref(file, x[5], x[6])}">${esc(x[2])}</a> <span class="muted">${x[5]}–${x[6]}</span><br><span class="muted">${esc(t('callers'))}: ${callers(x[0]).length} · ${esc(t('callees'))}: ${callees(x[0]).length}</span> <a href="#" data-sym="${x[0]}">${esc(t('details'))}</a></li>`).join('') || '<li class="muted">—</li>'}</ul>
      <h3>${esc(t('imports'))}</h3><ul class="list small">${imps.map((x) => `<li>${ref(file, x[2])} → ${ref(x[1])}</li>`).join('') || '<li class="muted">—</li>'}</ul>
      <h3>${esc(t('imported_by'))}</h3><ul class="list small">${by.map((x) => `<li>${ref(x[0], x[2])}</li>`).join('') || '<li class="muted">—</li>'}</ul><div id="sym-detail"></div>`;
    $$('#file-side a[data-sym]').forEach((a) => { a.onclick = (ev) => {
      ev.preventDefault(); const sid = +a.dataset.sym; const sym = symById.get(sid);
      const row = (x, other) => { const o = symById.get(x[other]); return `<li>${o ? `<a href="${codeHref(o[4], o[5], o[6])}">${esc(o[2])}</a>` : '?'} · ${ref(x[3], x[4])} ${x[2] !== 'verified-source' ? badge(x[2]) : ''}</li>`; };
      $('#sym-detail').innerHTML = `<h3 class="mono">${esc(sym[2])}</h3><h3>${esc(t('callers'))}</h3><ul class="list small">${callers(sid).map((x) => row(x, 0)).join('') || '<li class="muted">—</li>'}</ul><h3>${esc(t('callees'))}</h3><ul class="list small">${callees(sid).map((x) => row(x, 1)).join('') || '<li class="muted">—</li>'}</ul><p class="small muted">${esc(t('resolved_edges_only'))}</p>`;
    }; });
  };

  // ---- learn
  function renderExplanation(e, compact) {
    let h = `<div class="row"><h2 style="margin:0">${esc(loc(e.title))}</h2>${e.level ? `<span class="kind">${esc(t('level_' + e.level))}</span>` : ''}${evSummaryBadge(e)}</div>`;
    if (!hasLang(e.title) && lang !== 'en') h += `<p class="small muted">${esc(t('translation_missing'))}</p>`;
    if (e.summary) h += md(loc(e.summary));
    (e.sections || []).forEach((sec) => {
      if (sec.heading) h += `<h3>${esc(loc(sec.heading))} ${sec.status ? badge(sec.status) : ''}</h3>`;
      h += md(loc(sec.body));
      (sec.evidence || []).forEach((ev) => { h += evidenceBlock(ev); });
    });
    if (compact) return h;
    if ((e.claims || []).length) h += `<h3>${esc(t('claims'))}</h3><ul class="list">` + e.claims.map((c) => `<li>${badge(c.status || 'verified-source')} ${esc(loc(c.text))}${(c.evidence || []).map((ev) => ' · ' + ref(ev.file, ...parseRange(ev.lines))).join('')}</li>`).join('') + '</ul>';
    if ((e.concepts || []).length) h += `<h3>${esc(t('concepts'))}</h3><dl>` + e.concepts.map((c) => `<dt><strong>${esc(c.term)}</strong></dt><dd>${md(loc(c.definition))}</dd>`).join('') + '</dl>';
    if ((e.checkpoints || []).length) {
      h += `<h3>${esc(t('checkpoints'))}</h3>` + e.checkpoints.map((c, i) => {
        const choices = c.choices ? loc(c.choices) : null;
        return `<div class="checkpoint" data-correct="${c.correct != null ? c.correct : ''}"><strong>${esc(t('checkpoint'))} ${i + 1}.</strong> ${esc(loc(c.question))}` +
          (Array.isArray(choices) ? choices.map((ch, k) => `<button class="choice" data-k="${k}">${esc(ch)}</button>`).join('') : `<div><button class="reveal">${esc(t('show_answer'))}</button></div>`) +
          `<div class="answer">${md(loc(c.answer))}${(c.evidence || []).map(evidenceBlock).join('')}</div></div>`;
      }).join('');
    }
    if (e.next_steps) h += `<h3>${esc(t('next_steps'))}</h3>${md(loc(e.next_steps))}`;
    return h;
  }
  function evSummaryBadge(e) {
    const s = e.evidence_summary || {}; const bad = (s.stale || 0) + (s.missing || 0) + (s['out-of-range'] || 0);
    if (bad) return `<span class="badge b-stale">${esc(t('stale_refs', { n: bad }))}</span>`;
    if (s.moved) return `<span class="badge b-moved">${esc(t('moved_refs', { n: s.moved }))}</span>`;
    return e.evidence_count ? `<span class="badge b-valid">${esc(t('refs_valid', { n: e.evidence_count }))}</span>` : '';
  }
  V.learn = function () {
    const ex = D.explanations.filter((e) => e.type !== 'flow-notes' && (state.learnLevel === 'all' || e.level === state.learnLevel));
    let h = `<h1>${esc(t('nav_learn'))}</h1><p class="sub">${esc(t('learn_sub'))}</p><div class="tabs">` +
      ['all', 'beginner', 'developer', 'deep-dive', 'contribution'].map((l) => `<button data-l="${l}" class="${state.learnLevel === l ? 'on' : ''}">${esc(l === 'all' ? t('all') : t('level_' + l))}</button>`).join('') + `</div>`;
    h += `<div class="card"><strong>${esc(t('learning_path'))}</strong><ol>` + D.overview.learning_path.map((s) => `<li>${s.kind === 'trace-route' ? `<a href="#/flows">${esc(s.target)}</a>` : ref(s.target)} — <span class="muted">${esc(s.why)}</span></li>`).join('') + `</ol></div>`;
    if (!ex.length) h += '<br>' + empty('no_explanations', 'ct explain add <file.json>');
    ex.forEach((e) => { h += `<div class="card" style="margin-top:14px" id="x-${esc(e.id)}">${renderExplanation(e, false)}</div>`; });
    return h;
  };
  V.learn.after = function () {
    $$('.tabs button[data-l]').forEach((b) => { b.onclick = () => { state.learnLevel = b.dataset.l; render(); }; });
    $$('.checkpoint .reveal').forEach((b) => { b.onclick = () => b.closest('.checkpoint').classList.toggle('open'); });
    $$('.checkpoint .choice').forEach((b) => { b.onclick = () => {
      const cp = b.closest('.checkpoint'); const right = cp.dataset.correct;
      if (right !== '') { b.classList.add(String(b.dataset.k) === right ? 'right' : 'wrong'); }
      cp.classList.add('open');
    }; });
  };

  // ---- contribute
  V.contribute = function () {
    let h = `<h1>${esc(t('nav_contribute'))}</h1><p class="sub">${esc(t('contribute_sub'))}</p>`;
    const plans = D.explanations.filter((e) => e.type === 'contribution-plan' || e.type === 'review');
    if (!D.contexts.length && !plans.length) return h + empty('no_contexts', 'ct context <symbol|file|"METHOD /path">');
    plans.forEach((p) => { h += `<div class="card" style="margin-bottom:12px">${renderExplanation(p, false)}</div>`; });
    D.contexts.forEach((c, ci) => {
      h += `<div class="card" style="margin-bottom:14px"><h2 style="margin-top:0">${esc(c.target)}${c.task ? ` — <span class="muted">${esc(c.task)}</span>` : ''}</h2>
      <table><thead><tr><th>${esc(t('area'))}</th><th>${esc(t('status'))}</th><th>${esc(t('basis'))}</th></tr></thead><tbody>` +
        c.coverage.map((r) => `<tr><td>${esc(r.area)}</td><td><span class="badge b-${/partial|Not fully|Needs/.test(r.status) ? 'inferred' : r.status === 'Found' ? 'valid' : 'skipped'}">${esc(r.status)}</span></td><td class="small">${esc(r.basis)}</td></tr>`).join('') +
        `</tbody></table><p class="small muted">${esc(t('context_note'))}</p><div class="grid cols-3">
        <div><h3>${esc(t('implementation'))}</h3><ul class="list small">${c.implementation.map((s) => `<li>${ref(s.file, s.start_line, s.end_line)}<br><code>${esc(s.qualname)}</code></li>`).join('')}</ul></div>
        <div><h3>${esc(t('callers'))}</h3><ul class="list small">${c.direct_callers.slice(0, 15).map((x) => `<li>${ref(x.file, x.line)} <code>${esc(x.caller || '(module)')}</code> ${x.resolution !== 'verified-source' ? badge(x.resolution) : ''}</li>`).join('') || '<li class="muted">—</li>'}</ul></div>
        <div><h3>${esc(t('tests'))}</h3><ul class="list small">${c.tests.slice(0, 10).map((x) => `<li>${ref(x.test_file)}<br><span class="muted">${esc(x.signals.slice(0, 2).join('; '))}</span></li>`).join('') || '<li class="muted">—</li>'}</ul></div></div>
        ${c.routes.length ? `<h3>${esc(t('routes_reaching'))}</h3><ul class="list small">${c.routes.slice(0, 10).map((r) => `<li><code>${esc(r.method)} ${esc(r.path)}</code> · ${ref(r.file, r.line)} · ${esc(t('distance'))} ${r.distance}</li>`).join('')}</ul>` : ''}
        ${c.branch_conditions.length ? `<h3>${esc(t('edge_cases'))}</h3><ul class="list small">${c.branch_conditions.slice(0, 15).map((b) => `<li>${ref(c.file, b.line)} <code>${esc(b.text)}</code></li>`).join('')}</ul>` : ''}
        <h3>${esc(t('readiness'))}</h3>${['ready_1', 'ready_2', 'ready_3', 'ready_4', 'ready_5', 'ready_6'].map((k, i) => `<label class="row small"><input type="checkbox" data-ck="${ci}-${i}"${store.get('ck:' + D.meta.repo_name + ':' + c.id + ':' + i) ? ' checked' : ''}> ${esc(t(k))}</label>`).join('')}</div>`;
    });
    return h;
  };
  V.contribute.after = function () {
    $$('input[data-ck]').forEach((cb) => { cb.onchange = () => { const [ci, i] = cb.dataset.ck.split('-'); store.set('ck:' + D.meta.repo_name + ':' + D.contexts[+ci].id + ':' + i, cb.checked ? '1' : ''); }; });
  };

  // ---- changes
  V.changes = function () {
    const c = D.changes;
    let h = `<h1>${esc(t('nav_changes'))}</h1>`;
    if (!c) return h + empty('no_changes', 'ct changes');
    const s = c.summary;
    h += `<p class="sub">${esc(t('changes_vs', { baseline: c.baseline.id || '', kind: c.baseline.kind }))} · ${esc(fmtDate(c.generated_at))} · ${esc(c.verification)}</p>`;
    h += `<div class="stats">` + [[s.files_added, t('files_added')], [s.files_modified, t('files_modified')], [s.files_deleted, t('files_deleted')], [s.symbols_modified, t('symbols_modified')], [s.impacted_symbols, t('impacted_symbols')], [c.risks.length, t('risks')]].map(([v, k]) => `<div class="stat"><div class="v">${v}</div><div class="k">${esc(k)}</div></div>`).join('') + `</div>`;
    if (c.risks.length) h += `<h2>${esc(t('risks'))}</h2><div class="card"><ul class="list">` + c.risks.map((r) => `<li><span class="badge b-${r.level}">${esc(t('risk_' + r.level))}</span> <strong>${esc(r.kind)}</strong> — ${esc(r.detail)} ${r.file ? ref(r.file, r.line) : ''}</li>`).join('') + `</ul></div>`;
    h += `<h2>${esc(t('code_and_behaviour'))}</h2>`;
    c.files.forEach((f, i) => {
      const sd = f.symbols || {};
      h += `<div class="card" style="margin-bottom:10px"><div class="row"><span class="badge b-${f.status === 'deleted' ? 'failed' : f.status === 'added' ? 'passed' : 'medium'}">${esc(t('fs_' + f.status))}</span><strong class="mono">${esc(f.path)}</strong><span class="small muted">+${f.lines_added || 0} / −${f.lines_removed || 0}</span>${f.note ? `<span class="small muted">${esc(f.note)}</span>` : ''}</div>`;
      (sd.symbols_modified || []).forEach((m) => {
        h += `<div style="margin-top:8px"><code>${esc(m.qualname)}</code> <span class="small muted">${m.old_lines.join('–')} → ${m.new_lines.join('–')}</span> ${m.signature_changed ? `<span class="badge b-high">${esc(t('signature_changed'))}</span>` : ''} ${f.status !== 'deleted' ? ref(f.path, m.new_lines[0], m.new_lines[1]) : ''}<ul class="small">` +
          Object.entries(m.behaviour_signals).map(([k, v]) => `<li>${esc(t('bs_' + k))}: ${(Array.isArray(v) ? v : [JSON.stringify(v)]).map((x) => `<code>${esc(x)}</code>`).join(', ')}</li>`).join('') +
          ((m.routes_reaching || []).length ? `<li>${esc(t('routes_reaching'))}: ${m.routes_reaching.slice(0, 5).map((r) => `<code>${esc(r.method)} ${esc(r.path)}</code>`).join(', ')}</li>` : '') + `</ul></div>`;
      });
      ['symbols_added', 'symbols_removed'].forEach((k) => { if ((sd[k] || []).length) h += `<p class="small">${esc(t(k))}: ${sd[k].map((x) => `<code>${esc(x.qualname)}</code>`).join(', ')}</p>`; });
      ['imports_added', 'imports_removed', 'routes_added', 'routes_removed', 'env_vars_added', 'env_vars_removed', 'exports_removed'].forEach((k) => { if ((sd[k] || []).length) h += `<p class="small">${esc(t(k))}: ${sd[k].map((x) => `<code>${esc(x)}</code>`).join(', ')}</p>`; });
      if ((f.diff || []).length) h += `<details${i < 3 ? ' open' : ''}><summary class="small">${esc(t('show_diff'))}</summary><div class="code diff">` + f.diff.map((ln) => `<div class="ln ${ln.startsWith('@@') ? 'hunk' : ln.startsWith('+') && !ln.startsWith('+++') ? 'add' : ln.startsWith('-') && !ln.startsWith('---') ? 'del' : ''}"><span class="tx">${esc(ln)}</span></div>`).join('') + (f.diff_truncated ? `<div class="ln"><span class="tx muted">… ${esc(t('truncated'))}</span></div>` : '') + `</div></details>`;
      h += `</div>`;
    });
    if ((c.dependency_changes || []).length) h += `<h2>${esc(t('dependency_changes'))}</h2><div class="card">` + c.dependency_changes.map((d) => `<p>${ref(d.file)}: +${Object.keys(d.added).join(', ') || '—'} / −${Object.keys(d.removed).join(', ') || '—'} / ~${Object.keys(d.changed).join(', ') || '—'}</p>`).join('') + `</div>`;
    h += `<h2>${esc(t('architecture_impact'))}</h2><div class="grid cols-2"><div class="card"><h3 style="margin-top:0">${esc(t('impacted_callers'))}</h3><table><thead><tr><th>${esc(t('distance'))}</th><th>${esc(t('symbol'))}</th><th>${esc(t('via'))}</th></tr></thead><tbody>` +
      c.impact.callers.slice(0, 60).map((x) => `<tr><td class="num">${x.distance}</td><td><code>${esc(x.qualname)}</code><br>${ref(x.file, x.line)}</td><td class="small"><code>${esc(x.because_of)}</code></td></tr>`).join('') + `</tbody></table><p class="small muted">${esc(c.impact.completeness.note)}</p><p class="small">${esc(t('modules'))}: ${(s.impacted_modules || []).map((m) => `<code>${esc(m)}</code>`).join(' ')}</p></div>` +
      `<div class="card"><h3 style="margin-top:0">${esc(t('tests_to_run'))}</h3><ul class="list small">${c.impact.tests_to_run.map((x) => `<li>${ref(x.test_file)} <span class="muted">(${esc(x.covers.join(', '))})</span></li>`).join('') || '<li class="muted">—</li>'}</ul>` +
      ((c.impact.possibly_broken_references || []).length ? `<h3>${esc(t('possibly_broken'))}</h3><ul class="list small">${c.impact.possibly_broken_references.map((b) => `<li>${ref(b.file, b.line)} <code>${esc(b.expr)}</code> → ${esc(b.removed)}</li>`).join('')}</ul>` : '') + `</div></div>`;
    return h;
  };

  // ---- simulation
  V.simulation = function () {
    let h = `<h1>${esc(t('nav_simulation'))}</h1><p class="sub">${esc(t('sim_sub'))}</p><div class="tabs">` +
      [['l1', t('sim_l1')], ['l2', t('sim_l2')], ['l3', t('sim_l3')]].map(([k, l]) => `<button data-s="${k}" class="${state.simTab === k ? 'on' : ''}">${esc(l)}</button>`).join('') + `</div>`;
    if (state.simTab === 'l1') {
      h += `<p>${badge('structurally-inferred')} ${esc(t('sim_l1_desc'))}</p>`;
      if (!D.flows.length) return h + empty('no_flows', 'ct trace <target>');
      D.flows.forEach((f, i) => {
        h += `<div class="card" style="margin-bottom:10px"><div class="row"><strong>${esc(f.title)}</strong>${badge(f.verification)}<span class="spacer"></span>${SM ? `<a href="#/dataflow/flow:${i}">${esc(t('df_play_on_map'))}</a> · ` : ''}<a href="#/flows" data-flow="${i}">${esc(t('open_player'))}</a></div><ul class="list small">` +
          (f.outcomes || []).map((o) => `<li><span class="badge b-${o.outcome === 'failure' ? 'failed' : 'passed'}">${esc(t('outcome_' + o.outcome))}</span> <code>${esc(o.text)}</code> · ${ref(o.file, o.line)}${o.nearest_guards.length ? ` — ${esc(t('when'))} ${o.nearest_guards.map((g) => `<code>${esc(g.text)}</code>`).join(' / ')}` : ''}</li>`).join('') + `</ul></div>`;
      });
    } else if (state.simTab === 'l2') {
      h += `<p>${badge('test-verified')} ${esc(t('sim_l2_desc'))}</p>`;
      if (!D.test_runs.length) return h + empty('no_test_runs', 'ct tests plan <target>  →  ct tests run --yes -- <command>');
      D.test_runs.slice().reverse().forEach((r) => {
        const c = r.counts || {};
        h += `<div class="card" style="margin-bottom:10px"><div class="row"><span class="badge b-${r.status === 'passed' ? 'passed' : 'failed'}">${esc(r.status)}</span><code>${esc(r.command)}</code><span class="spacer"></span><span class="small muted">${c.passed || 0} ${esc(t('passed'))} · ${c.failed || 0} ${esc(t('failed'))} · ${c.skipped || 0} ${esc(t('skipped'))} · ${r.duration_s}s · ${esc((r.git_commit || '').slice(0, 10))}${r.dirty ? ' ' + esc(t('dirty_tree')) : ''}</span></div>` +
          `<details><summary class="small">${esc(t('per_test'))} (${(r.tests || []).length})</summary><ul class="list small">` + (r.tests || []).map((x) => `<li><span class="badge b-${x.status}">${esc(t(x.status))}</span> ${esc(x.name)} ${x.file ? ref(x.file) : ''}${x.message ? `<br><span class="muted">${esc(x.message)}</span>` : ''}</li>`).join('') + `</ul></details><p class="small muted">${esc(r.verification || '')}</p></div>`;
      });
    } else {
      h += `<p>${badge('runtime-observed')} ${esc(t('sim_l3_desc'))}</p>`;
      if (!D.runtime.length) return h + empty('no_runtime', 'ct runtime --yes -- <command>');
      D.runtime.slice().reverse().forEach((r, ri) => {
        h += `<div class="card" style="margin-bottom:10px"><div class="row"><strong>${esc(r.command)}</strong><span class="spacer"></span><span class="small muted">${r.events_total} ${esc(t('events'))} · ${r.functions_observed} ${esc(t('functions'))} · ${esc(r.lang)}</span></div><p class="small muted">${esc(r.limitations)}</p>
        <div class="grid cols-2"><div><h3>${esc(t('top_functions'))}</h3><table><tbody>${(r.mapped_symbols || []).slice(0, 25).map((m) => `<tr><td><a href="${codeHref(m.file, m.line)}">${esc(m.qualname)}</a></td><td class="num">${m.calls}×</td><td>${m.throws ? `<span class="badge b-failed">${m.throws} ${esc(t('throws'))}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>
        <div><h3>${esc(t('event_sequence'))}</h3><div class="steps card" style="max-height:420px">${(r.sequence || []).slice(0, 600).map((e) => `<div class="step" style="padding-left:${8 + Math.min(10, e.depth || 0) * 12}px"><span class="n">${e.t === 'c' ? '→' : e.t === 'r' ? '←' : '✗'}</span><span></span><span>${e.symbol_id && symById.get(e.symbol_id) ? `<a href="${codeHref(e.file, symById.get(e.symbol_id)[5])}">${esc(e.name)}</a>` : esc(e.name)} <span class="meta2">${esc(e.file)} · ${e.us}µs${e.error ? ' · ' + esc(e.error) : ''}</span></span></div>`).join('')}</div></div></div></div>`;
      });
    }
    return h;
  };
  V.simulation.after = function () {
    $$('.tabs button[data-s]').forEach((b) => { b.onclick = () => { state.simTab = b.dataset.s; render(); }; });
    $$('a[data-flow]').forEach((a) => { a.onclick = () => { state.flowIdx = +a.dataset.flow; state.step = 0; }; });
  };

  // ------------------------------------------------------------------ routing
  function route() {
    const h = location.hash.replace(/^#\/?/, '');
    const [tab, ...rest] = h.split('/');
    state.tab = TABS.includes(tab) ? tab : 'overview';
    state.arg = rest.join('/');
    render();
  }
  function render() {
    if (state.tab !== 'flows') stopPlay();
    live.forEach((x) => { try { x.destroy(); } catch (e) { /* ignore */ } }); live = [];
    if (flowStage) { flowStage.destroy(); flowStage = null; }
    if (dashTimer) { clearInterval(dashTimer); dashTimer = null; }
    chrome();
    const main = $('#main');
    main.classList.remove('enter'); void main.offsetWidth; main.classList.add('enter');
    main.innerHTML = V[state.tab]();
    if (V[state.tab].after) V[state.tab].after();
    if (state.tab !== 'code') main.focus({ preventScroll: true });
  }
  document.addEventListener('keydown', (e) => {
    if (state.tab !== 'flows' || /input|select|textarea/i.test(document.activeElement.tagName)) return;
    if (e.key === ' ') { e.preventDefault(); state.playing ? stopPlay() : startPlay(); }
    else if (e.key === 'ArrowRight') { const n = $('#p-next'); if (n) n.click(); }
    else if (e.key === 'ArrowLeft') { const p = $('#p-prev'); if (p) p.click(); }
  });
  window.addEventListener('hashchange', route);
  
  route();
})();
