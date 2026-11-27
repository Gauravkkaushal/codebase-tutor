/* Codebase Tutor visualisations: animated system map and flow stage (SVG, no dependencies). */
window.CTViz = (function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const reduceMotion = (() => { try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } })();
  const LAYERS = ['client', 'entry', 'routing', 'middleware', 'handlers', 'services', 'data', 'library', 'storage'];

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs || {}) if (attrs[k] !== undefined && attrs[k] !== null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function css(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  function moduleOf(path) {
    const parts = String(path || '').split('/');
    if (parts.length <= 1) return '(root)';
    return parts.slice(0, Math.min(2, parts.length - 1)).join('/');
  }
  const KIND_VAR = { database: '--k-db', cache: '--k-cache', session: '--k-session', files: '--k-files', external: '--k-ext',
    queue: '--k-queue', auth: '--k-auth', email: '--k-email', cloud: '--k-cloud', views: '--k-views', library: '--k-lib' };
  const LAYER_VAR = { client: '--l-client', entry: '--l-entry', routing: '--l-routing', middleware: '--l-middleware',
    handlers: '--l-handlers', services: '--l-services', data: '--l-data', library: '--l-library', storage: '--l-storage' };

  // ---- icons (drawn in a 24x24 box centred at cx, cy, scaled by s)
  function icon(kind, g, cx, cy, s, color) {
    const G = el('g', { transform: `translate(${cx - 12 * s},${cy - 12 * s}) scale(${s})`, fill: 'none', stroke: color, 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, g);
    const p = (d) => el('path', { d }, G);
    switch (kind) {
      case 'database': p('M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z'); p('M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6'); p('M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3'); break;
      case 'cache': p('M5 5h14v4H5z'); p('M5 10h14v4H5z'); p('M5 15h14v4H5z'); p('M13 3l-3 6h4l-3 6'); break;
      case 'session': el('circle', { cx: 8, cy: 12, r: 4 }, G); p('M12 12h9'); p('M18 12v3'); p('M21 12v2'); break;
      case 'files': p('M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'); break;
      case 'external': case 'cloud': p('M7 18h10a4 4 0 0 0 .5-8 6 6 0 0 0-11.4 1.6A3.3 3.3 0 0 0 7 18z'); break;
      case 'queue': p('M4 6h16'); p('M4 12h16'); p('M4 18h16'); el('circle', { cx: 8, cy: 6, r: 1 }, G); el('circle', { cx: 13, cy: 12, r: 1 }, G); el('circle', { cx: 17, cy: 18, r: 1 }, G); break;
      case 'auth': p('M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z'); p('M9 12l2 2 4-4'); break;
      case 'email': p('M3 6h18v12H3z'); p('M3 7l9 6 9-6'); break;
      case 'views': p('M6 3h9l4 4v14H6z'); p('M9 11h7'); p('M9 15h7'); break;
      case 'client': p('M3 5h18v14H3z'); p('M3 9h18'); el('circle', { cx: 6, cy: 7, r: 0.6 }, G); el('circle', { cx: 8.5, cy: 7, r: 0.6 }, G); break;
      default: p('M9 7l-5 5 5 5'); p('M15 7l5 5-5 5');
    }
    return G;
  }

  function edgePath(a, b, w, h) {
    const sx = a.x + w / 2, sy = a.y, tx = b.x - w / 2, ty = b.y;
    if (b.x > a.x + 1) {
      const dx = Math.max(40, (tx - sx) / 2);
      return `M${sx},${sy} C${sx + dx},${sy} ${tx - dx},${ty} ${tx},${ty}`;
    }
    if (Math.abs(b.x - a.x) <= 1) { // same column: arc on the right side
      const x = a.x + w / 2, bend = 46 + Math.abs(ty - sy) * 0.15;
      return `M${x},${sy} C${x + bend},${sy} ${x + bend},${ty} ${x},${ty}`;
    }
    const sx2 = a.x - w / 2, tx2 = b.x + w / 2, dy = -40 - Math.abs(sx2 - tx2) * 0.08;
    return `M${sx2},${sy} C${sx2 - 50},${sy + dy} ${tx2 + 50},${ty + dy} ${tx2},${ty}`;
  }

  // ===================================================================== System map
  function SystemMap(container, data, opts) {
    opts = opts || {};
    const t = opts.t || ((k) => k);
    const compact = !!opts.compact;
    const nodes = data.nodes.slice();
    const edges = data.edges.slice();
    const present = LAYERS.filter((l) => nodes.some((n) => n.layer === l));
    const nodeW = compact ? 120 : 176, nodeH = compact ? 30 : 58, gapY = compact ? 14 : 22, colW = compact ? 146 : 206;
    const top = compact ? 18 : 58, maxPer = compact ? 5 : 6;
    const byLayer = {}, sub = {};
    present.forEach((l) => { byLayer[l] = nodes.filter((n) => n.layer === l); sub[l] = Math.max(1, Math.ceil(byLayer[l].length / maxPer)); });
    const rowsOf = (l) => Math.ceil(byLayer[l].length / sub[l]);
    const maxRows = Math.max(1, ...present.map(rowsOf));
    const totalCols = present.reduce((a, l) => a + sub[l], 0) || 1;
    const W = 40 + totalCols * colW, H = top + maxRows * (nodeH + gapY) + 30;
    const pos = {}, bands = [];
    let cx0 = 20;
    present.forEach((l) => {
      const list = byLayer[l], k = sub[l], per = rowsOf(l);
      bands.push({ l, x: cx0, w: k * colW });
      for (let c = 0; c < k; c++) {
        const part = list.slice(c * per, (c + 1) * per);
        const colH = part.length * (nodeH + gapY) - gapY;
        const y0 = top + (maxRows * (nodeH + gapY) - gapY - colH) / 2 + (k > 1 && c % 2 ? (nodeH + gapY) / 2 * (part.length < per ? 1 : 0) : 0);
        part.forEach((n, i) => { pos[n.id] = { x: cx0 + c * colW + colW / 2, y: y0 + i * (nodeH + gapY) + nodeH / 2, layer: l }; });
      }
      cx0 += k * colW;
    });
    container.innerHTML = '';
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'sysmap' + (compact ? ' compact' : ''), role: 'img', 'aria-label': t('df_title') }, container);
    if (compact) svg.style.maxHeight = '320px';
    const defs = el('defs', {}, svg);
    const glow = el('filter', { id: 'ct-glow' + (compact ? 'c' : ''), x: '-50%', y: '-50%', width: '200%', height: '200%' }, defs);
    el('feGaussianBlur', { stdDeviation: compact ? 2 : 3, result: 'b' }, glow);
    const fm = el('feMerge', {}, glow); el('feMergeNode', { in: 'b' }, fm); el('feMergeNode', { in: 'SourceGraphic' }, fm);
    if (!compact) bands.forEach((b) => {
      el('rect', { x: b.x + 6, y: 8, width: b.w - 12, height: H - 16, rx: 12, class: 'sm-col' }, svg);
      const tx = el('text', { x: b.x + b.w / 2, y: 32, 'text-anchor': 'middle', class: 'sm-colh' }, svg);
      tx.textContent = t('df_layer_' + b.l);
    });
    const gEdges = el('g', {}, svg), gPackets = el('g', {}, svg), gNodes = el('g', {}, svg), gComet = el('g', {}, svg);
    const edgeEls = [];
    edges.forEach((e) => {
      const a = pos[e.source], b = pos[e.target];
      if (!a || !b) return;
      const d = edgePath(a, b, nodeW, nodeH);
      const w = Math.min(4.5, 1 + Math.log2(1 + (e.weight || 1)) * 0.6);
      const path = el('path', { d, class: 'sm-edge k-' + e.kind, 'stroke-width': w }, gEdges);
      const tip = el('title', {}, path); tip.textContent = `${e.source} → ${e.target}: ${e.label || ''}`;
      edgeEls.push({ e, path, len: 0 });
    });
    const nodeEls = {};
    nodes.forEach((n) => {
      const p = pos[n.id]; if (!p) return;
      const g = el('g', { class: 'sm-node n-' + n.kind + ' l-' + n.layer, transform: `translate(${p.x - nodeW / 2},${p.y - nodeH / 2})`, tabindex: 0, role: 'button', 'aria-label': n.label }, gNodes);
      const color = n.kind === 'storage' ? css(KIND_VAR[n.storage_kind] || '--k-lib', '#888') : css(LAYER_VAR[n.layer] || '--accent', '#2557c7');
      el('rect', { width: nodeW, height: nodeH, rx: compact ? 8 : 12, class: 'sm-box' }, g);
      el('rect', { width: 4, height: nodeH - (compact ? 10 : 16), x: 0, y: compact ? 5 : 8, rx: 2, fill: color }, g);
      const iconKind = n.kind === 'storage' ? n.storage_kind : n.kind === 'client' ? 'client' : 'module';
      icon(iconKind, g, compact ? 17 : 22, nodeH / 2, compact ? 0.62 : 0.85, color);
      const label = el('text', { x: compact ? 31 : 42, y: compact ? nodeH / 2 + 4 : 24, class: 'sm-label' }, g);
      const maxc = compact ? 13 : 19;
      label.textContent = n.label.length > maxc ? '…' + n.label.slice(-(maxc - 1)) : n.label;
      if (!compact) {
        const sub = el('text', { x: 42, y: 42, class: 'sm-sub' }, g);
        sub.textContent = n.kind === 'storage' ? (n.packages || []).slice(0, 2).join(', ') :
          n.kind === 'client' ? t('df_client_sub') : `${n.files} ${t('files').toLowerCase()} · ${(n.lines || 0).toLocaleString()} ${t('lines').toLowerCase()}`;
      }
      const tt = el('title', {}, g); tt.textContent = n.label;
      nodeEls[n.id] = g;
      const pick = () => { select(n.id); if (opts.onSelect) opts.onSelect(n, edges.filter((e) => e.source === n.id || e.target === n.id)); };
      g.addEventListener('click', pick);
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); } });
      g.addEventListener('mouseenter', () => { if (!selected) focus(n.id); });
      g.addEventListener('mouseleave', () => { if (!selected) focus(null); });
    });
    edgeEls.forEach((x) => { x.len = x.path.getTotalLength(); });

    // packets
    const packets = [];
    edgeEls.forEach((x, i) => {
      const n = x.e.kind === 'call' ? 1 : Math.min(3, 1 + Math.floor(Math.log2(1 + (x.e.weight || 1)) / 2));
      for (let k = 0; k < n; k++) {
        const c = el('circle', { r: compact ? 2.4 : 3.4, class: 'sm-packet k-' + x.e.kind }, gPackets);
        packets.push({ x, c, phase: (k / n) + (i * 0.137) % 1, speed: (x.e.kind === 'call' ? 0.00010 : 0.00016) * (compact ? 1.2 : 1) });
      }
    });
    let raf = null, running = !reduceMotion && opts.animate !== false, selected = null, focused = null;
    function frame(now) {
      for (const p of packets) {
        if (p.hidden) continue;
        let u = (now * p.speed + p.phase) % 1;
        if (p.x.e.kind === 'data') { u = u < 0.5 ? u * 2 : (1 - u) * 2; p.c.classList.toggle('ret', (now * p.speed + p.phase) % 1 >= 0.5); }
        const pt = p.x.path.getPointAtLength(u * p.x.len);
        p.c.setAttribute('cx', pt.x); p.c.setAttribute('cy', pt.y);
      }
      raf = running ? requestAnimationFrame(frame) : null;
    }
    function play() { if (!running) { running = true; raf = requestAnimationFrame(frame); } }
    function pause() { running = false; if (raf) cancelAnimationFrame(raf); raf = null; }
    if (running) raf = requestAnimationFrame(frame); else frame(1500);
    function focus(id) {
      focused = id;
      const conn = new Set();
      edgeEls.forEach((x) => {
        const on = !id || x.e.source === id || x.e.target === id;
        x.path.classList.toggle('dim', !on); x.path.classList.toggle('hot', !!id && on);
        if (on && id) { conn.add(x.e.source); conn.add(x.e.target); }
      });
      packets.forEach((p) => { const on = !id || p.x.e.source === id || p.x.e.target === id; p.hidden = !on; p.c.style.display = on ? '' : 'none'; });
      Object.entries(nodeEls).forEach(([nid, g]) => g.classList.toggle('dim', !!id && !conn.has(nid) && nid !== id));
    }
    function select(id) { selected = id; focus(id); Object.entries(nodeEls).forEach(([nid, g]) => g.classList.toggle('sel', nid === id)); }
    // comet replay along a sequence of node ids
    let cometTimer = null, replayTimeout = null, replayGen = 0;
    function replay(seq, onStep, onDone) {
      stopReplay();
      const gen = replayGen;
      gComet.innerHTML = '';
      const comet = el('circle', { r: compact ? 5 : 8, class: 'sm-comet', filter: `url(#ct-glow${compact ? 'c' : ''})` }, gComet);
      const trail = el('path', { class: 'sm-trail', d: '' }, gComet);
      let i = 0, trailD = '';
      const hop = () => {
        if (gen !== replayGen) return;
        if (i >= seq.length - 1) { if (onDone) onDone(); cometTimer = null; return; }
        const a = pos[seq[i]], b = pos[seq[i + 1]];
        const ex = edgeEls.find((x) => x.e.source === seq[i] && x.e.target === seq[i + 1]) || edgeEls.find((x) => x.e.source === seq[i + 1] && x.e.target === seq[i]);
        const reverse = ex && ex.e.source === seq[i + 1];
        const pathEl = ex ? ex.path : el('path', { d: `M${a.x},${a.y} L${b.x},${b.y}`, class: 'sm-ghost' }, gComet);
        const len = pathEl.getTotalLength(); const dur = reduceMotion ? 1 : 650; const t0 = performance.now();
        if (nodeEls[seq[i + 1]]) nodeEls[seq[i + 1]].classList.add('pulse');
        if (onStep) onStep(i + 1);
        const step = (now) => {
          if (gen !== replayGen) return;
          const u = Math.min(1, (now - t0) / dur);
          const pt = pathEl.getPointAtLength((reverse ? 1 - u : u) * len);
          comet.setAttribute('cx', pt.x); comet.setAttribute('cy', pt.y);
          if (u < 1) { cometTimer = requestAnimationFrame(step); return; }
          trailD += (trailD ? ' ' : '') + pathEl.getAttribute('d').replace(/^M/, 'M');
          trail.setAttribute('d', trailD);
          replayTimeout = setTimeout(() => {
            replayTimeout = null;
            if (gen !== replayGen) return;
            if (nodeEls[seq[i + 1]]) nodeEls[seq[i + 1]].classList.remove('pulse');
            i++; hop();
          }, reduceMotion ? 0 : 160);
        };
        cometTimer = requestAnimationFrame(step);
      };
      if (pos[seq[0]]) { comet.setAttribute('cx', pos[seq[0]].x); comet.setAttribute('cy', pos[seq[0]].y); }
      hop();
    }
    function stopReplay() {
      replayGen++;
      if (cometTimer) cancelAnimationFrame(cometTimer);
      cometTimer = null;
      if (replayTimeout) clearTimeout(replayTimeout);
      replayTimeout = null;
      Object.values(nodeEls).forEach((g) => g.classList.remove('pulse'));
    }
    return {
      play, pause, isRunning: () => running, focus, select, replay, stopReplay, has: (id) => !!pos[id],
      destroy() { pause(); stopReplay(); }
    };
  }

  // ===================================================================== Flow stage
  function participantsFor(flow, opts) {
    const symFile = (opts && opts.symFile) || (() => null);
    const list = [], idx = {};
    const add = (id, p) => { if (!(id in idx)) { idx[id] = list.length; list.push(Object.assign({ id }, p)); } };
    const steps = flow.steps || [];
    const front = steps.find((s) => s.kind === 'client-call');
    const hasClient = !!front || (steps.length && (steps[0].kind === 'route' || steps[0].kind === 'mount'));
    const clientId = front ? front.file : '@client';
    if (front) add(front.file, { label: front.file.split('/').pop(), sub: front.file, kind: 'client', front: true });
    else if (hasClient) add('@client', { label: 'HTTP client', kind: 'client' });
    const seq = steps.map((s) => {
      if (s.kind === 'external-call' && (s.storage || s.module)) {
        const id = '@' + (s.storage || s.module);
        add(id, { label: s.storage || s.module, kind: 'storage', storage_kind: s.storage_kind || 'library', pkg: s.module });
        return id;
      }
      if (s.kind === 'client-call') return clientId;
      if (s.kind === 'route' || s.kind === 'mount') return clientId;
      if (s.kind === 'respond' && hasClient) return clientId;
      if (s.kind === 'call' && s.target_id != null) {
        const tf = symFile(s.target_id);
        if (tf && tf !== s.file) {
          add(s.file, { label: s.file.split('/').pop(), sub: s.file, kind: 'file' });
          add(tf, { label: tf.split('/').pop(), sub: tf, kind: 'file' });
          return tf;
        }
      }
      add(s.file, { label: s.file.split('/').pop(), sub: s.file, kind: 'file' });
      return s.file;
    });
    return { list, seq };
  }

  function FlowStage(svg, flow, opts) {
    opts = opts || {};
    const { list, seq } = participantsFor(flow, opts);
    const symName = opts.symName || (() => null);
    const files = list.filter((p) => p.kind === 'file'), stores = list.filter((p) => p.kind === 'storage');
    const client = list.find((p) => p.kind === 'client');
    const W = 760, boxW = 150, boxH = 54;
    const perRow = Math.max(1, Math.min(4, files.length));
    const rows = Math.ceil(files.length / perRow) || 1;
    const left = client ? (client.front ? 175 : 150) : 30;
    const H = 60 + rows * 86 + (stores.length ? 96 : 0);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.innerHTML = '';
    const defs = el('defs', {}, svg);
    const glow = el('filter', { id: 'st-glow', x: '-50%', y: '-50%', width: '200%', height: '200%' }, defs);
    el('feGaussianBlur', { stdDeviation: 3.5, result: 'b' }, glow);
    const fm = el('feMerge', {}, glow); el('feMergeNode', { in: 'b' }, fm); el('feMergeNode', { in: 'SourceGraphic' }, fm);
    const pos = {};
    if (client) pos[client.id] = { x: client.front ? 85 : 70, y: 72 + ((rows - 1) * 86) / 2 };
    const span = W - left - 30;
    files.forEach((p, i) => {
      const r = Math.floor(i / perRow), c = i % perRow;
      const n = Math.min(perRow, files.length - r * perRow);
      pos[p.id] = { x: left + (span / n) * (c + 0.5), y: 72 + r * 86 };
    });
    stores.forEach((p, i) => { pos[p.id] = { x: 30 + ((W - 60) / stores.length) * (i + 0.5), y: H - 46 }; });
    const gTrail = el('g', {}, svg), gNodes = el('g', {}, svg), gTop = el('g', {}, svg);
    const els = {};
    list.forEach((p) => {
      const q = pos[p.id]; if (!q) return;
      const isStore = p.kind === 'storage', isClient = p.kind === 'client';
      const w = isClient && !p.front ? 110 : boxW;
      const g = el('g', { class: 'st-node' + (isStore ? ' st-store' : ''), transform: `translate(${q.x - w / 2},${q.y - boxH / 2})` }, gNodes);
      const color = isStore ? css(KIND_VAR[p.storage_kind] || '--k-lib', '#888') : isClient ? css('--l-client', '#888') : css('--accent', '#2557c7');
      el('rect', { width: w, height: boxH, rx: 12, class: 'st-box' }, g);
      icon(isStore ? p.storage_kind : isClient ? 'client' : 'module', g, 20, boxH / 2, 0.8, color);
      const tl = el('text', { x: 38, y: 23, class: 'sm-label' }, g);
      tl.textContent = p.label.length > 16 ? p.label.slice(0, 15) + '…' : p.label;
      const sub = el('text', { x: 38, y: 40, class: 'sm-sub st-fn' }, g);
      sub.textContent = isStore ? (p.pkg || '') : p.front ? 'frontend' : '';
      const tt = el('title', {}, g); tt.textContent = p.sub || p.label;
      els[p.id] = { g, sub, w };
    });
    const packet = el('circle', { r: 8, class: 'st-packet', filter: 'url(#st-glow)' }, gTop);
    const badge = el('text', { class: 'st-badge', 'text-anchor': 'middle' }, gTop);
    let cur = -1, anim = null;
    function curve(a, b) {
      const mx = (a.x + b.x) / 2, my = Math.min(a.y, b.y) - 36 - Math.abs(a.x - b.x) * 0.06;
      return `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`;
    }
    function show(i) {
      if (anim) cancelAnimationFrame(anim);
      const step = flow.steps[i]; if (!step) return;
      const id = seq[i], q0 = pos[id]; if (!q0) return;
      const q = { x: q0.x, y: q0.y - boxH / 2 - 6 };
      // trail of visited hops up to i
      gTrail.innerHTML = '';
      let prevId = null;
      for (let k = 0; k <= i; k++) {
        const sid = seq[k];
        if (prevId && sid !== prevId && pos[prevId] && pos[sid]) {
          const st = flow.steps[k];
          el('path', { d: curve(pos[prevId], pos[sid]), class: 'st-trail' + (st.outcome === 'failure' ? ' bad' : '') + (k === i ? ' now' : '') }, gTrail);
        }
        prevId = sid;
      }
      Object.entries(els).forEach(([pid, x]) => { x.g.classList.toggle('cur', pid === id); x.g.classList.remove('flash-success', 'flash-failure'); });
      const callee = step.kind === 'call' && step.target_id != null && id !== step.file ? symName(step.target_id) : null;
      if (step.kind === 'client-call' && step.symbol && els[id]) els[id].sub.textContent = String(step.symbol).slice(0, 20);
      else if ((callee || step.symbol) && els[id] && !String(id).startsWith('@') && step.kind !== 'route' && step.kind !== 'mount' && step.kind !== 'respond') {
        const fn = callee || String(step.symbol).replace(/^handler:/, '').replace(/@\d+(#\d+)?$/, '');
        els[id].sub.textContent = fn.length > 20 ? fn.slice(0, 19) + '…' : fn;
      }
      const from = cur >= 0 && pos[seq[cur]] ? { x: pos[seq[cur]].x, y: pos[seq[cur]].y - boxH / 2 - 6 } : q;
      const outcome = step.outcome || 'neutral';
      packet.setAttribute('class', 'st-packet o-' + outcome + (step.verification === 'unresolved' ? ' unres' : ''));
      const glyph = { call: '→', if: '◆', else: '◇', return: '↩', throw: '⚡', raise: '⚡', respond: '⇦', 'next-error': '⚡', next: '⇢', catch: '⚑', 'external-call': '⇣', 'client-call': '⇢', enter: '▸', route: '⇢', mount: '⇢', dispatch: '⇢' }[step.kind] || '•';
      badge.textContent = glyph;
      const pathD = from.x === q.x && from.y === q.y ? `M${q.x},${q.y} L${q.x},${q.y}` : curve(from, q);
      const tmp = el('path', { d: pathD, fill: 'none', stroke: 'none' }, gTop);
      const len = tmp.getTotalLength(); const dur = reduceMotion || len < 1 ? 1 : 420; const t0 = performance.now();
      const tick = (now) => {
        const u = Math.min(1, (now - t0) / dur), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
        const pt = tmp.getPointAtLength(e * len);
        packet.setAttribute('cx', pt.x); packet.setAttribute('cy', pt.y);
        badge.setAttribute('x', pt.x); badge.setAttribute('y', pt.y - 14);
        if (u < 1) anim = requestAnimationFrame(tick);
        else { tmp.remove(); if (outcome !== 'neutral' && els[id]) { els[id].g.classList.remove('flash-success', 'flash-failure'); void els[id].g.getBoundingClientRect(); els[id].g.classList.add('flash-' + outcome); } }
      };
      anim = requestAnimationFrame(tick);
      cur = i;
    }
    return { show, participants: list, destroy() { if (anim) cancelAnimationFrame(anim); } };
  }

  // ===================================================================== count-up
  function countUp(root) {
    root.querySelectorAll('[data-count]').forEach((n) => {
      const target = +n.dataset.count; if (!isFinite(target)) return;
      if (reduceMotion || target < 10) { n.textContent = target.toLocaleString(); return; }
      const t0 = performance.now(), dur = 900;
      const tick = (now) => { const u = Math.min(1, (now - t0) / dur); n.textContent = Math.round(target * (1 - Math.pow(1 - u, 3))).toLocaleString(); if (u < 1) requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    });
  }

  function iconMarkup(kind, size) {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('width', size || 22); svg.setAttribute('height', size || 22);
    svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('class', 'ico');
    icon(kind, svg, 12, 12, 1, 'currentColor');
    return svg.outerHTML;
  }
  function kindColorVar(kind) { return KIND_VAR[kind] || '--k-lib'; }

  return { SystemMap, FlowStage, participantsFor, moduleOf, countUp, iconMarkup, kindColorVar, reduceMotion };
})();
