// Core: master timeline, element helpers, scene + seam system, shared components.
gsap.registerPlugin(MotionPathPlugin);
const D = window.TLD, T = D.T, E = D.E, C = D.cuts, FPS = D.fps;
const tl = gsap.timeline({ paused: true });
const WORLD = document.getElementById('world');
const SC = {};
let _uid = 0;

function el(tag, parent, cls, css, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (css) Object.assign(e.style, css);
  if (html !== undefined) e.innerHTML = html;
  if (parent) parent.appendChild(e);
  return e;
}
function div(parent, cls, css, html) { return el('div', parent, cls, css, html); }
function px(v) { return typeof v === 'number' ? v + 'px' : v; }
function box(parent, x, y, w, h, cls, css, html) {
  return div(parent, cls || 'abs', Object.assign({ left: px(x), top: px(y), width: px(w), height: px(h) }, css || {}), html);
}

// ---------- scenes & seams ----------
function scene(name) {
  const root = div(WORLD, 'scene');
  const seam = div(root, 'seam');
  const cam = div(seam, 'cam');
  SC[name] = { root, seam, cam };
  return SC[name];
}
function on(name, t) { tl.set(SC[name].root, { visibility: 'visible' }, t); }
function off(name, t) { tl.set(SC[name].root, { visibility: 'hidden' }, t); }
// The current flows LEFT. Mirrored power4 eases, cut mid-motion, zero overlap.
function seamLeft(a, b, cut) {
  tl.to(SC[a].seam, { x: -300, filter: 'blur(18px)', duration: 0.36, ease: 'power4.in' }, cut - 0.36);
  off(a, cut); on(b, cut);
  tl.fromTo(SC[b].seam, { x: 380, filter: 'blur(18px)' }, { x: 0, filter: 'blur(0px)', duration: 0.56, ease: 'power4.out' }, cut);
}
// Arrival: both sides shrink (scale sign negative on both).
function seamArrive(a, b, cut) {
  tl.to(SC[a].seam, { scale: 0.62, filter: 'blur(14px)', duration: 0.4, ease: 'power4.in' }, cut - 0.4);
  off(a, cut); on(b, cut);
  tl.fromTo(SC[b].seam, { scale: 1.5, filter: 'blur(16px)' }, { scale: 1, filter: 'blur(0px)', duration: 0.7, ease: 'power4.out' }, cut);
}
// Conclusion rises.
function seamUp(a, b, cut) {
  tl.to(SC[a].seam, { y: -240, filter: 'blur(16px)', duration: 0.38, ease: 'power4.in' }, cut - 0.38);
  off(a, cut); on(b, cut);
  tl.fromTo(SC[b].seam, { y: 320, filter: 'blur(16px)' }, { y: 0, filter: 'blur(0px)', duration: 0.62, ease: 'power4.out' }, cut);
}

// ---------- motion helpers ----------
function inn(x, t, o = {}) {
  const from = { opacity: 0, y: o.y ?? 24, x: o.x ?? 0, filter: `blur(${o.blur ?? 10}px)` };
  if (o.scale !== undefined) from.scale = o.scale;
  const to = { opacity: o.op ?? 1, y: 0, x: 0, filter: 'blur(0px)', duration: o.d ?? 0.6, ease: o.ease || 'power3.out' };
  if (o.scale !== undefined) to.scale = 1;
  tl.fromTo(x, from, to, t);
}
function out(x, t, o = {}) {
  tl.to(x, { opacity: 0, y: o.y ?? 0, x: o.x ?? 0, filter: `blur(${o.blur ?? 8}px)`, duration: o.d ?? 0.35, ease: 'power2.in' }, t);
}
function dimTo(x, t, op, d = 0.5) { tl.to(x, { opacity: op, duration: d, ease: 'power2.inOut' }, t); }
function words(parent, text, cls, css) {
  const c = div(parent, cls, css);
  const parts = text.split(' ');
  parts.forEach((w, i) => {
    el('span', c, 'w', null, w);
    if (i < parts.length - 1) c.appendChild(document.createTextNode(' '));
  });
  return c;
}
function waterfall(c, t, o = {}) {
  const ws = c.querySelectorAll('.w');
  tl.fromTo(ws, { yPercent: o.y ?? 60, opacity: 0, filter: `blur(${o.blur ?? 12}px)` },
    { yPercent: 0, opacity: 1, filter: 'blur(0px)', duration: o.d ?? 0.7, stagger: o.s ?? 0.055, ease: 'power3.out' }, t);
}
// reveal words as they are spoken (char-length weighted across the line's duration)
function spoken(c, t0, dur, o = {}) {
  const ws = [...c.querySelectorAll('.w')];
  const lens = ws.map(w => w.textContent.length + 2);
  const tot = lens.reduce((a, b) => a + b, 0);
  let acc = 0;
  ws.forEach((w, i) => {
    const tt = t0 + (dur * 0.92) * acc / tot;
    acc += lens[i];
    tl.fromTo(w, { opacity: 0, y: o.y ?? 22, filter: `blur(${o.blur ?? 10}px)` },
      { opacity: 1, y: 0, filter: 'blur(0px)', duration: o.d ?? 0.42, ease: 'power3.out' }, tt);
  });
}
function wordTime(text, idx, t0, dur) {      // when word idx of a spoken line lands
  const ws = text.split(' ');
  const lens = ws.map(w => w.length + 2);
  const tot = lens.reduce((a, b) => a + b, 0);
  let acc = 0;
  for (let i = 0; i < idx; i++) acc += lens[i];
  return t0 + dur * 0.92 * acc / tot;
}
function typeText(node, text, t, cps = 38) {   // typewriter, deterministic
  const n = text.length;
  const st = { k: 0 };
  node.textContent = '';
  tl.to(st, {
    k: n, duration: n / cps, ease: 'none',
    onUpdate: () => { node.textContent = text.slice(0, Math.round(st.k)); }
  }, t);
  tl.set(node, { textContent: '' }, 0);
}
function count(node, from, to, t, d, fmt) {
  const st = { v: from };
  fmt = fmt || (v => Math.round(v));
  node.textContent = fmt(from);
  tl.to(st, { v: to, duration: d, ease: 'power2.out', onUpdate: () => { node.textContent = fmt(st.v); } }, t);
}

// ---------- shared components ----------
function ring(parent, x, y, size, stroke, o = {}) {
  const id = 'rg' + (++_uid);
  const r = (size - stroke) / 2, c = size / 2, Cc = 2 * Math.PI * r;
  const w = box(parent, x - size / 2, y - size / 2, size, size, 'abs');
  w.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="overflow:visible">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${o.c1 || '#FFD08A'}"/><stop offset="1" stop-color="${o.c2 || '#FF8A1F'}"/></linearGradient>
      <filter id="${id}f" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${o.glow ?? 10}"/></filter></defs>
    <circle class="track" cx="${c}" cy="${c}" r="${r}" fill="none" stroke="rgba(244,241,234,${o.trackOp ?? 0.07})" stroke-width="${stroke}"/>
    <circle class="arcglow" cx="${c}" cy="${c}" r="${r}" fill="none" stroke="url(#${id})" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${Cc}" stroke-dashoffset="${Cc}" transform="rotate(-90 ${c} ${c})" filter="url(#${id}f)" opacity="${o.glowOp ?? 0.55}"/>
    <circle class="arc" cx="${c}" cy="${c}" r="${r}" fill="none" stroke="url(#${id})" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${Cc}" stroke-dashoffset="${Cc}" transform="rotate(-90 ${c} ${c})"/>
  </svg>`;
  const arcs = w.querySelectorAll('.arc,.arcglow');
  return { w, arcs, C: Cc, r, c, stops: w.querySelectorAll('stop'), track: w.querySelector('.track') };
}
function arcTo(rg, frac, t, d = 1, ease = 'power3.out') {
  tl.to(rg.arcs, { attr: { 'stroke-dashoffset': rg.C * (1 - frac) }, duration: d, ease }, t);
}
function arcColor(rg, c1, c2, t, d = 0.4) {
  tl.to(rg.stops[0], { attr: { 'stop-color': c1 }, duration: d }, t);
  tl.to(rg.stops[1], { attr: { 'stop-color': c2 }, duration: d }, t);
}
// the 7even5ive wordmark: 7 and 5 in amber
function wordmark(parent, x, y, size, o = {}) {
  const w = box(parent, x, y, 'auto', 'auto', 'abs', { fontWeight: 650, fontSize: px(size), letterSpacing: '-0.045em', lineHeight: 1, whiteSpace: 'nowrap' });
  const chars = '7even5ive'.split('');
  chars.forEach((ch, i) => {
    const s = el('span', w, 'w', null, ch);
    if (ch === '7' || ch === '5') {
      s.style.color = 'var(--amber)';
    }
  });
  return w;
}
// the logo mark: a ring at exactly 75%
function logoMark(parent, x, y, size) {
  const rg = ring(parent, x, y, size, Math.max(6, size * 0.13), { glow: size * 0.06, glowOp: 0.6, trackOp: 0.0 });
  return rg;
}
function phone(parent, x, y, w = 410, h = 840) {
  const p = box(parent, x, y, w, h, 'phone');
  const scr = div(p, 'scr');
  div(p, 'notch');
  const status = box(scr, 0, 0, w - 22, 60, 'abs', { display: 'flex', justifyContent: 'space-between', padding: '20px 40px 0', fontSize: '19px', fontWeight: 600, color: 'rgba(244,241,234,.85)' });
  status.innerHTML = '<span>9:41</span><span style="letter-spacing:2px">••• ▮</span>';
  return { p, scr };
}
function appHeader(scr, w, title) {
  const h = box(scr, 0, 60, w - 22, 70, 'abs', { display: 'flex', alignItems: 'center', gap: '14px', padding: '0 30px' });
  const m = div(h, 'abs', { position: 'relative', width: '34px', height: '34px' });
  const rg = ring(m, 17, 17, 34, 5, { glow: 2, glowOp: 0.4, trackOp: 0.0 });
  rg.arcs.forEach(a => a.setAttribute('stroke-dashoffset', rg.C * 0.25));
  const t = el('span', h, '', { fontSize: '26px', fontWeight: 650, letterSpacing: '-0.03em' });
  t.innerHTML = title || '7even5ive';
  return h;
}
function cursor(parent, x, y, size = 92) {
  const c = box(parent, x, y, size, size, 'abs', { zIndex: 50 });
  c.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 32 32"><path d="M6 3 L6 25 L11.5 20 L15 28.5 L18.6 27 L15.2 18.8 L22.5 18.8 Z" fill="#F4F1EA" stroke="#07080B" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
  return c;
}
function ripple(parent, x, y, t, color = 'rgba(255,181,71,.55)') {
  const r = box(parent, x - 30, y - 30, 60, 60, 'abs', { borderRadius: '50%', border: `3px solid ${color}`, zIndex: 49 });
  tl.fromTo(r, { scale: 0.2, opacity: 0 }, { scale: 2.6, opacity: 0, duration: 0.7, ease: 'power2.out', keyframes: { opacity: [0, 1, 0] } }, t);
  return r;
}
function tap(cur, tx, ty, t, layer) {   // cursor travels in, presses, ripple ignites on the same frame
  tl.to(cur, { left: px(tx - 8), top: px(ty - 4), duration: 0.6, ease: 'power3.inOut' }, t - 0.6);
  tl.to(cur, { scale: 0.84, duration: 0.08, ease: 'power2.in' }, t);
  tl.to(cur, { scale: 1, duration: 0.25, ease: 'back.out(1.6)' }, t + 0.08);
  ripple(layer || cur.parentNode, tx, ty, t);
}
function check(size = 26, color = 'var(--green)') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="vertical-align:-4px"><path d="M4 12.5 L9.5 18 L20 6.5" fill="none" stroke="${color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
function cross(size = 26, color = 'var(--red)') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="vertical-align:-4px"><path d="M6 6 L18 18 M18 6 L6 18" fill="none" stroke="${color}" stroke-width="2.6" stroke-linecap="round"/></svg>`;
}
function lockIcon(size = 28, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="vertical-align:-4px"><rect x="5" y="10.5" width="14" height="10" rx="2.4" fill="none" stroke="${color}" stroke-width="2"/><path d="M8 10.5 V7.5 a4 4 0 0 1 8 0 V10.5" fill="none" stroke="${color}" stroke-width="2"/></svg>`;
}
function awsChip(parent, x, y, text, sub) {
  const c = box(parent, x, y, 'auto', 'auto', 'chip', { borderColor: 'rgba(255,153,0,.55)', background: 'rgba(255,153,0,.08)' });
  c.innerHTML = `<span class="mono" style="font-size:15px;color:var(--aws);letter-spacing:.12em">AWS</span><span>${text}</span>${sub ? `<span class="mono" style="font-size:18px;color:var(--mute)">${sub}</span>` : ''}`;
  return c;
}
function elevenChip(parent, x, y, text) {
  const c = box(parent, x, y, 'auto', 'auto', 'chip', { borderColor: 'rgba(244,241,234,.5)', background: 'rgba(244,241,234,.06)' });
  c.innerHTML = `<span style="display:inline-flex;gap:4px;margin-right:2px"><i style="display:block;width:5px;height:22px;background:var(--ink);border-radius:2px"></i><i style="display:block;width:5px;height:22px;background:var(--ink);border-radius:2px"></i></span><span>${text}</span>`;
  return c;
}
// a path with a travelling packet
function svgLayer(parent, w = 1920, h = 1080) {
  const s = box(parent, 0, 0, w, h, 'abs');
  s.innerHTML = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="overflow:visible"></svg>`;
  return s.firstChild;
}
function pathEl(svg, d, o = {}) {
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', d);
  p.setAttribute('fill', 'none');
  p.setAttribute('stroke', o.stroke || 'rgba(244,241,234,.22)');
  p.setAttribute('stroke-width', o.w || 2);
  if (o.dash) p.setAttribute('stroke-dasharray', o.dash);
  p.setAttribute('stroke-linecap', 'round');
  svg.appendChild(p);
  const L = p.getTotalLength();
  return { p, L };
}
function drawPath(pp, t, d = 0.8) {
  pp.p.style.strokeDasharray = pp.L;
  tl.fromTo(pp.p, { strokeDashoffset: pp.L }, { strokeDashoffset: 0, duration: d, ease: 'power2.inOut' }, t);
}
function packet(svg, pp, t, d = 0.9, color = '#FFB547', r = 7) {
  const g = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
  g.setAttribute('r', r);
  g.setAttribute('fill', color);
  g.style.filter = `drop-shadow(0 0 8px ${color})`;
  svg.appendChild(g);
  tl.set(g, { opacity: 0 }, 0);
  tl.set(g, { opacity: 1 }, t);
  tl.to(g, { motionPath: { path: pp.p, align: pp.p, alignOrigin: [0.5, 0.5] }, duration: d, ease: 'power1.inOut' }, t);
  tl.set(g, { opacity: 0 }, t + d);
  return g;
}
// background glow positions (the "lights") — moved per scene with intent
const G1 = document.getElementById('g1'), G2 = document.getElementById('g2'), G3 = document.getElementById('g3');
const GRID = document.getElementById('grid');
function lights(t, a, b, c, d = 1.4) {
  tl.to(G1, { x: a[0], y: a[1], opacity: a[2] ?? 1, duration: d, ease: 'power2.inOut' }, t);
  tl.to(G2, { x: b[0], y: b[1], opacity: b[2] ?? 1, duration: d, ease: 'power2.inOut' }, t);
  tl.to(G3, { x: c[0], y: c[1], opacity: c[2] ?? 1, duration: d, ease: 'power2.inOut' }, t);
}
tl.set(G1, { x: 960, y: 520, opacity: 0 }, 0);
tl.set(G2, { x: 1700, y: 1000, opacity: 0 }, 0);
tl.set(G3, { x: 200, y: 100, opacity: 0 }, 0);
