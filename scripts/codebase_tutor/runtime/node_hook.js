'use strict';
// Codebase Tutor runtime tracer for Node (CommonJS). Loaded with NODE_OPTIONS=--require <this file>.
// Wraps functions exported by repository modules (not node_modules) in transparent Proxies and records
// call / return / throw events. Internal calls that do not go through module exports are not observed.
const Module = require('module');
const path = require('path');
const fs = require('fs');
const ROOT = fs.realpathSync(process.env.CT_TRACE_ROOT || process.cwd());
const OUT = process.env.CT_TRACE_OUT;
const MAX = Number(process.env.CT_TRACE_MAX || 200000);
const events = [];
let dropped = 0;
let depth = 0;
const t0 = process.hrtime.bigint();
const wrapped = new WeakMap();
const SEP = path.sep;

function inRepo(f) {
  return typeof f === 'string' && f.startsWith(ROOT + SEP) && !f.includes(SEP + 'node_modules' + SEP) &&
    !f.includes(SEP + '.codebase-tutor' + SEP);
}
function rec(type, file, name, extra) {
  if (events.length >= MAX) { dropped++; return; }
  events.push([type, file, name, Number((process.hrtime.bigint() - t0) / 1000n), depth, extra || null]);
}
function wrap(fn, file, name) {
  if (typeof fn !== 'function') return fn;
  if (wrapped.has(fn)) return wrapped.get(fn);
  const p = new Proxy(fn, {
    apply(target, thisArg, args) {
      rec('c', file, name); depth++;
      try {
        const r = Reflect.apply(target, thisArg, args);
        depth--; rec('r', file, name);
        return r;
      } catch (e) {
        depth--; rec('x', file, name, String(e && e.message).slice(0, 200));
        throw e;
      }
    },
    construct(target, args, newTarget) {
      rec('c', file, 'new ' + name); depth++;
      try {
        const r = Reflect.construct(target, args, newTarget === p ? target : newTarget);
        depth--; rec('r', file, 'new ' + name);
        return r;
      } catch (e) {
        depth--; rec('x', file, 'new ' + name, String(e && e.message).slice(0, 200));
        throw e;
      }
    }
  });
  wrapped.set(fn, p); wrapped.set(p, p);
  return p;
}
const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  const exp = origLoad.apply(this, arguments);
  let file;
  try { file = Module._resolveFilename(request, parent, isMain); } catch (e) { return exp; }
  if (!inRepo(file)) return exp;
  const rel = path.relative(ROOT, file).split(SEP).join('/');
  try {
    if (typeof exp === 'function') {
      const w = wrap(exp, rel, exp.name || 'default');
      if (require.cache[file] && require.cache[file].exports === exp) require.cache[file].exports = w;
      for (const k of Object.keys(exp)) {
        const d = Object.getOwnPropertyDescriptor(exp, k);
        if (d && 'value' in d && typeof d.value === 'function' && d.writable && d.configurable) exp[k] = wrap(d.value, rel, k);
      }
      return w;
    }
    if (exp && typeof exp === 'object' && !Object.isFrozen(exp)) {
      for (const k of Object.keys(exp)) {
        const d = Object.getOwnPropertyDescriptor(exp, k);
        if (d && 'value' in d && typeof d.value === 'function' && d.writable) exp[k] = wrap(d.value, rel, k);
      }
    }
  } catch (e) { /* never break the program under trace */ }
  return exp;
};
process.on('exit', () => {
  if (!OUT) return;
  try {
    fs.writeFileSync(OUT.replace(/\.json$/, '.' + process.pid + '.json'),
      JSON.stringify({ lang: 'node', pid: process.pid, argv: process.argv.slice(0, 4), events, dropped }));
  } catch (e) { /* ignore */ }
});
