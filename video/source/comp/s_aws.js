// Scenes 7-10: AWS architecture, PORTAL FORGE + live counter, BUSINESS, CLOSE
function node(parent, x, y, w, h, title, sub, kind) {
  const col = { aws: ['rgba(255,153,0,.55)', 'rgba(255,153,0,.07)'], el: ['rgba(244,241,234,.5)', 'rgba(244,241,234,.05)'], supa: ['rgba(62,207,142,.55)', 'rgba(62,207,142,.06)'], gw: ['rgba(255,181,71,.85)', 'rgba(255,181,71,.08)'], wa: ['rgba(37,211,102,.6)', 'rgba(37,211,102,.07)'], plain: ['rgba(255,255,255,.14)', 'rgba(255,255,255,.035)'] }[kind || 'plain'];
  const n = box(parent, x, y, w, h, 'abs', { borderRadius: '18px', border: `1.5px solid ${col[0]}`, background: col[1], padding: '14px 20px', display: 'flex', flexDirection: 'column', justifyContent: 'center' });
  n.innerHTML = `<div style="font-size:26px;font-weight:600;letter-spacing:-0.01em;white-space:nowrap">${title}</div>${sub ? `<div class="mono" style="font-size:17px;color:var(--mute);margin-top:4px;white-space:nowrap">${sub}</div>` : ''}`;
  return n;
}
const Wt = (txt, id) => i => wordTime(txt, i, T[id], E[id] - T[id]);

// =============================== 7. AWS ==================================
(function aws() {
  const S = scene('aws'), cam = S.cam;
  seamArrive('safety', 'aws', C.aws);
  lights(C.aws, [1180, 420, 0.55], [500, 900, 0.4], [1700, 150, 0.3], 1.2);
  tl.to(GRID, { opacity: 0.28, duration: 1 }, C.aws);
  const t0 = C.aws + 0.05;
  const title = box(cam, 110, 70, 1200, 80, 'abs', { fontSize: '64px', fontWeight: 600, letterSpacing: '-0.03em', whiteSpace: 'nowrap' }, 'Serverless, on <span style="color:var(--aws)">AWS</span>');
  inn(title, T.L34 + 0.3, { y: 20, d: 0.6 });
  // columns: sources | SQS | λ workers | AgentCore Gateway | tools ; bottom row: Bedrock | Supabase | phone
  const A1 = node(cam, 110, 204, 270, 76, 'WhatsApp', 'forwards · Cloud API', 'wa');
  const A5 = node(cam, 110, 290, 270, 76, 'College mail', 'Gmail push · read-only');
  const A2 = node(cam, 110, 376, 270, 76, 'Share sheet', 'S3 → Scribe', 'aws');
  const A4 = node(cam, 110, 462, 270, 76, 'Google Classroom', 'assignments · API');
  const A3 = node(cam, 110, 582, 270, 76, 'EventBridge', '07:00 · daily', 'aws');
  const B1 = node(cam, 440, 329, 200, 84, 'SQS', '+ dead-letter queue', 'aws');
  const EL = node(cam, 720, 196, 260, 80, 'ElevenLabs Agents', 'voice · MCP client', 'el');
  const LY = [334, 414, 494, 574, 654];
  const lam = ['understand', 'library', 'approve', 'briefing', 'notify'].map((n, i) => node(cam, 720, LY[i] - 34, 260, 68, `λ ${n}`, null, 'aws'));
  const G = node(cam, 1040, 190, 300, 520, '', '', 'gw');
  G.innerHTML = `<div class="mono" style="font-size:16px;color:var(--aws);letter-spacing:.14em;text-align:center">AMAZON BEDROCK</div><div style="font-size:34px;font-weight:650;text-align:center;line-height:1.1;margin-top:6px">AgentCore<br>Gateway</div>`;
  G.style.justifyContent = 'flex-start';
  G.style.paddingTop = '30px';
  const gRows = ['Cedar policy', 'Interceptor λ', 'Identity vault'].map((n, i) => box(G, 24, 170 + i * 104, 250, 84, 'abs', { borderRadius: '16px', background: 'rgba(0,0,0,.35)', border: '1px solid rgba(255,255,255,.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px', fontWeight: 600 }, n));
  const TY = [236, 328, 420, 512, 604];
  const tools = ['WhatsApp Cloud API', 'Gmail API · read-only', 'Google Calendar API', 'College portal', 'Agent tools λ'].map((n, i) => node(cam, 1410, TY[i] - 38, 400, 76, n, null, i === 0 ? 'wa' : 'plain'));
  const SB = node(cam, 500, 770, 640, 200, '', '', 'supa');
  SB.style.justifyContent = 'flex-start';
  SB.innerHTML = `<div style="display:flex;align-items:center;gap:14px"><span style="font-size:28px;font-weight:650">Supabase</span><span class="mono" style="font-size:16px;color:var(--supa);letter-spacing:.12em">POSTGRES · MUMBAI</span></div>`;
  const sbT = ['Row-level security', 'Realtime', 'Auth'].map((n, i) => box(SB, 20 + i * 205, 80, 190, 96, 'abs', { borderRadius: '14px', background: 'rgba(0,0,0,.3)', border: '1px solid rgba(62,207,142,.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '22px', fontWeight: 600 }, n));
  const BR = node(cam, 110, 790, 330, 110, 'Amazon Bedrock', 'Claude Haiku · India', 'aws');
  const PH = node(cam, 1500, 780, 310, 180, 'Your phone', 'WhatsApp + web app', 'plain');
  PH.style.justifyContent = 'flex-start';
  const all = [A1, A5, A2, A4, A3, B1, EL, ...lam, G, ...tools, SB, BR, PH];
  tl.fromTo([A1, A5, A2, A4, A3], { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.6, stagger: 0.06, ease: 'power4.out' }, t0 + 0.2);
  tl.fromTo([B1, ...lam], { y: 30, opacity: 0 }, { y: 0, opacity: 0.45, duration: 0.6, stagger: 0.06, ease: 'power4.out' }, t0 + 0.45);
  tl.fromTo(EL, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power4.out' }, t0 + 0.45);
  tl.fromTo(G, { scale: 0.9, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.7, ease: 'power4.out' }, t0 + 0.7);
  tl.fromTo([...tools, SB, BR, PH], { x: 60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.6, stagger: 0.06, ease: 'power4.out' }, t0 + 0.9);

  // connectors: right angles with rounded corners; shared buses are drawn once, nothing crosses a box
  const sv = svgLayer(cam);
  const rp = (pts, r = 12) => {
    let d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
      const l1 = Math.hypot(x1 - x0, y1 - y0), l2 = Math.hypot(x2 - x1, y2 - y1), rr = Math.min(r, l1 / 2, l2 / 2);
      d += ` L ${x1 - (x1 - x0) / l1 * rr} ${y1 - (y1 - y0) / l1 * rr} Q ${x1} ${y1} ${x1 + (x2 - x1) / l2 * rr} ${y1 + (y2 - y1) / l2 * rr}`;
    }
    return d + ` L ${pts[pts.length - 1][0]} ${pts[pts.length - 1][1]}`;
  };
  const P = (pts, o) => pathEl(sv, rp(pts), Object.assign({ stroke: 'rgba(244,241,234,.24)', w: 2 }, o || {}));
  const M = pts => pathEl(sv, rp(pts), { stroke: 'none' });        // invisible route a packet can ride
  const pA1B = P([[380, 242], [410, 242], [410, 371], [440, 371]]);
  const pA5B = P([[380, 328], [410, 328]]);
  const pA2B = P([[380, 414], [410, 414], [410, 371], [440, 371]]);
  const pA4B = P([[380, 500], [410, 500], [410, 371], [440, 371]]);
  const pBbus = P([[640, 371], [690, 371]]);
  const pLin = P([[690, LY[0]], [690, LY[4]]]);
  const pLst = LY.map(y => P([[690, y], [720, y]]));
  const pA3C = P([[380, 620], [690, 620]]);
  const pLout = [236, ...LY].map(y => P([[980, y], [1010, y]]));
  const pGin = P([[1010, 236], [1010, LY[4]]]);
  const pGin2 = P([[1010, 450], [1040, 450]]);
  const pGt = P([[1340, 450], [1375, 450]]);
  const pTbus = P([[1375, TY[0]], [1375, TY[4]]]);
  const pTst = TY.map(y => P([[1375, y], [1410, y]]));
  const pCS = P([[850, 688], [850, 770]]);
  const pCB = P([[850, 730], [275, 730], [275, 790]]);
  const pSP = P([[1140, 870], [1500, 870]]);
  const pWP = P([[1810, TY[0]], [1855, TY[0]], [1855, 870], [1810, 870]], { stroke: 'rgba(37,211,102,.35)' });
  [pA1B, pA5B, pA2B, pA4B, pBbus, pLin, ...pLst, pA3C, ...pLout, pGin, pGin2, pGt, pTbus, ...pTst, pCS, pCB, pSP, pWP].forEach((p, i) => drawPath(p, t0 + 1.0 + i * 0.025, 0.7));
  const mBC = M([[640, 371], [690, 371], [690, LY[0]], [720, LY[0]]]);
  const mA3C = M([[380, 620], [690, 620], [690, LY[3]], [720, LY[3]]]);

  // L35 — Lambdas wake only when needed; SQS retry-safe; EventBridge at 7
  const L35 = 'Lambda workers wake only when needed. S Q S makes every event retry-safe. Event Bridge wakes us at seven.';
  const w35 = Wt(L35, 'L35');
  const wake = (n, t) => { tl.to(n, { opacity: 1, boxShadow: '0 0 40px rgba(255,153,0,.45)', duration: 0.25 }, t); tl.to(n, { opacity: 0.55, boxShadow: '0 0 0 rgba(0,0,0,0)', duration: 0.8 }, t + 1.2); };
  packet(sv, pA1B, w35(2) - 0.5, 0.45, '#5BE49B');
  packet(sv, mBC, w35(2), 0.45);
  wake(lam[0], w35(2) + 0.45);
  [1, 2, 3, 4].forEach((k, j) => wake(lam[k], w35(3) + j * 0.3));
  tl.to(B1, { opacity: 1, boxShadow: '0 0 40px rgba(255,153,0,.45)', duration: 0.3 }, w35(6));
  const retry = box(cam, 600, 277, 50, 50, 'abs', {}, '<svg width="50" height="50" viewBox="0 0 24 24"><path d="M19 12 a7 7 0 1 1 -2.05 -4.95 M19 4 V8 H15" fill="none" stroke="#FF9900" stroke-width="2" stroke-linecap="round"/></svg>');
  inn(retry, w35(9), { y: 0, scale: 0.5, d: 0.35, ease: 'back.out(1.8)' });
  tl.to(retry, { rotation: 360, duration: 1.0, ease: 'power2.inOut' }, w35(11));
  packet(sv, pA2B, w35(10), 0.45, '#F4F1EA');
  tl.to(B1, { boxShadow: '0 0 0 rgba(0,0,0,0)', duration: 0.6 }, w35(13));
  tl.to(A3, { boxShadow: '0 0 40px rgba(255,153,0,.5)', duration: 0.3 }, w35(13));
  tl.set(A3.querySelector('.mono'), { innerHTML: '07:00 · wake up' }, w35(17));
  packet(sv, mA3C, w35(15), 0.7);
  wake(lam[3], w35(15) + 0.7);
  tl.to(A3, { boxShadow: '0 0 0 rgba(0,0,0,0)', duration: 0.6 }, E.L35);

  // L36 — Identity keeps keys encrypted
  const L36 = 'Agent Core Identity keeps your keys encrypted, never in our code.';
  const w36 = Wt(L36, 'L36');
  const focus = (t, cx, cy, s) => tl.to(cam, { scale: s, x: -s * (cx - 960), y: -s * (cy - 540), duration: 1.0, ease: 'power3.inOut' }, t);
  focus(T.L36 - 0.35, 1190, 520, 1.45);
  tl.to([SB, BR, PH], { opacity: 0.06, duration: 0.5 }, T.L36 - 0.35);
  tl.to([SB, BR, PH], { opacity: 1, duration: 0.5 }, T.L37 - 0.4);
  tl.to(gRows[2], { borderColor: 'rgba(255,181,71,.9)', background: 'rgba(255,181,71,.16)', duration: 0.3 }, w36(2));
  const key = box(G, 30, 486, 240, 26, 'abs mono', { fontSize: '15px', color: 'var(--amber)', letterSpacing: '.08em', textAlign: 'center' }, 'KMS-ENCRYPTED KEYS');
  inn(key, w36(6) - 0.1, { y: 8, d: 0.4 });
  const nic = box(cam, 1360, 668, 'auto', 'auto', 'chip', { fontSize: '22px' }, `<svg width="26" height="26" viewBox="0 0 24 24"><circle cx="8" cy="12" r="4" fill="none" stroke="#F4F1EA" stroke-width="2"/><path d="M12 12 H21 M18 12 V15" stroke="#F4F1EA" stroke-width="2"/><path d="M3 3 L21 21" stroke="#FF5A4E" stroke-width="2.2"/></svg> never in our code`);
  inn(nic, w36(7) - 0.1, { x: 30, y: 0, d: 0.45, ease: 'power4.out' });

  // L37 — Supabase RLS + Realtime
  const L37 = 'Supa base stores your data with row-level security, so you only ever see your own rows, and pushes each new card to your phone in real time.';
  const w37 = Wt(L37, 'L37');
  tl.to(nic, { opacity: 0, duration: 0.3 }, T.L37 - 0.4);
  focus(T.L37 - 0.4, 1080, 840, 1.38);
  tl.to(sbT[0], { borderColor: 'rgba(62,207,142,.9)', background: 'rgba(62,207,142,.15)', duration: 0.3 }, w37(5));
  const rls = box(cam, 470, 560, 640, 190, 'abs', { borderRadius: '16px', background: 'rgba(9,12,11,.96)', border: '1px solid rgba(62,207,142,.4)', padding: '14px 18px', fontSize: '21px' });
  const rows = [['you', 'DBMS Assignment 3', 'Fri 11:59 PM', true], ['you', 'OS lab record', 'Mon 9:00 AM', true], ['ananya', '██████ ██ ████', '███ ████', false], ['ramesh', '████ ███████', '██ ████', false]];
  rls.innerHTML = rows.map(([u, a, b, mine]) => `<div style="display:flex;gap:18px;align-items:center;height:40px;${mine ? '' : 'opacity:.45;filter:blur(2.4px)'}"><span class="mono" style="width:110px;font-size:17px;color:${mine ? 'var(--supa)' : 'var(--mute)'}">${u}</span><span style="flex:1">${a}</span><span class="mono" style="font-size:17px;color:var(--mute)">${b}</span></div>`).join('');
  const locks = box(cam, 1050, 660, 60, 80, 'abs', { color: 'var(--mute)' }, `${lockIcon(30, '#8D919B')}<br>${lockIcon(30, '#8D919B')}`);
  inn(rls, w37(2) - 0.1, { y: 30, d: 0.55, ease: 'power4.out' });
  inn(locks, w37(9), { y: 0, d: 0.4 });
  tl.to(sbT[1], { borderColor: 'rgba(62,207,142,.9)', background: 'rgba(62,207,142,.15)', duration: 0.3 }, w37(17));
  tl.to(pSP.p, { attr: { stroke: 'rgba(62,207,142,.8)' }, duration: 0.3 }, w37(17));
  packet(sv, pSP, w37(18), 0.7, '#3ECF8E');
  tl.to(PH, { borderColor: 'rgba(62,207,142,.9)', boxShadow: '0 0 50px rgba(62,207,142,.35)', duration: 0.3 }, w37(18) + 0.7);
  const pc = box(PH, 20, 96, 270, 66, 'abs', { borderRadius: '12px', background: 'rgba(255,181,71,.12)', border: '1px solid rgba(255,181,71,.4)', fontSize: '17px', padding: '8px 12px', lineHeight: 1.3 }, '<b>New deadline</b><br><span style="color:var(--mute)">DBMS · Assignment 3</span>');
  inn(pc, w37(18) + 0.75, { y: -16, d: 0.45, ease: 'back.out(1.6)' });

  // L38 — nothing runs when idle
  const L38 = "When nobody's using it, nothing runs. So it costs nothing to keep alive.";
  const w38 = Wt(L38, 'L38');
  focus(T.L38 - 0.3, 960, 540, 1);
  tl.to([rls, locks], { opacity: 0, duration: 0.4 }, T.L38 - 0.3);
  tl.to(all.concat([sv, title]), { opacity: 0.16, duration: 0.8, ease: 'power2.inOut' }, w38(4) - 0.1);
  const zero = box(cam, 960, 500, 'auto', 'auto', 'abs', { fontSize: '230px', fontWeight: 700, letterSpacing: '-0.05em', lineHeight: 1, whiteSpace: 'nowrap' }, '₹0');
  center(zero);
  const zl = box(cam, 960, 660, 'auto', 'auto', 'abs serif', { fontSize: '72px', whiteSpace: 'nowrap' }, 'while nobody’s using it.');
  center(zl);
  tl.fromTo(zero, { opacity: 0, scale: 1.25, filter: 'blur(18px)' }, { opacity: 1, scale: 1, filter: 'blur(0px)', duration: 0.6, ease: 'power4.out' }, w38(8) - 0.1);
  inn(zl, w38(9), { y: 20, d: 0.5 });
})();

// =============================== 8. FORGE ================================
(function forge() {
  const S = scene('forge'), cam = S.cam;
  seamLeft('aws', 'forge', C.forge);
  lights(C.forge, [700, 400, 0.5], [1500, 850, 0.4], [1500, 150, 0.25], 1);
  tl.to(GRID, { opacity: 0.18, duration: 1 }, C.forge);
  const L39 = 'Every college portal is different, and none has an A P I.';
  const w39 = Wt(L39, 'L39');
  const looks = [['#2E4A7A', 'Student Information System'], ['#6B2737', 'Campus ERP · Login'], ['#2F5A44', 'Academic Portal v2.1']];
  const mocks = looks.map(([c, n], i) => {
    const m = box(cam, 240 + i * 360, 250 + i * 70, 640, 420, 'abs', { borderRadius: '14px', background: '#E9E6DF', overflow: 'hidden', boxShadow: '0 30px 80px rgba(0,0,0,.55)', color: '#222' });
    gsap.set(m, { rotation: [-3, 1.5, -1][i] });
    m.innerHTML = `<div style="height:60px;background:${c};color:#fff;display:flex;align-items:center;padding:0 22px;font-family:Times,serif;font-size:26px">${n}</div>
      <div style="padding:18px 22px;font-family:Arial,sans-serif;font-size:18px">${Array.from({ length: 6 }, (_, r) => `<div style="display:flex;gap:10px;margin-bottom:8px">${Array.from({ length: 4 }, (_, k) => `<span style="flex:1;height:30px;background:${(r + k) % 3 ? '#d6d2c8' : '#c9c4b8'};border:1px solid #bbb"></span>`).join('')}</div>`).join('')}</div>`;
    const st = box(m, 330, 300, 270, 80, 'abs', { display: 'flex', alignItems: 'center', justifyContent: 'center', border: '4px solid #D7261E', color: '#D7261E', fontSize: '40px', fontWeight: 800, letterSpacing: '.06em', borderRadius: '10px', background: 'rgba(255,255,255,.75)' }, 'NO API');
    gsap.set(st, { rotation: -8 });
    tl.fromTo(m, { x: 500, opacity: 0, filter: 'blur(14px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.6, ease: 'power4.out' }, w39(i) - 0.15);
    tl.fromTo(st, { scale: 1.8, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.22, ease: 'power4.in' }, w39(9) + i * 0.15);
    return m;
  });
  // Portal Forge pipeline
  const L40 = 'Portal Forge learns a portal once, writes an Open A P I spec, and the gateway turns it into tools.';
  const w40 = Wt(L40, 'L40');
  mocks.forEach((m, i) => tl.to(m, { x: -260 - i * 330, y: 140 - i * 70, scale: 0.36, opacity: 0.7, duration: 0.7, ease: 'power3.inOut' }, T.L40 - 0.4));
  const ttl = box(cam, 110, 90, 900, 80, 'abs', { fontSize: '64px', fontWeight: 600, letterSpacing: '-0.03em', whiteSpace: 'nowrap' }, 'Portal Forge');
  inn(ttl, T.L40, { y: 20, d: 0.6 });
  const col = (x, w, h, lab) => { const c = box(cam, x, 260, w, h, 'card', { background: 'rgba(10,11,15,.9)', padding: '26px' }); c.innerHTML = `<div class="mono" style="font-size:18px;color:var(--mute);letter-spacing:.14em">${lab}</div>`; return c; };
  const c1 = col(480, 440, 520, '1 · WATCH IT ONCE');
  const c2 = col(960, 470, 520, '2 · OPENAPI SPEC');
  const c3 = col(1470, 350, 520, '3 · GATEWAY TOOLS');
  tl.fromTo([c1, c2, c3], { x: 120, opacity: 0, filter: 'blur(12px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.55, stagger: 0.1, ease: 'power4.out' }, w40(2) - 0.2);
  const net = ['GET /student/attendance', 'GET /student/timetable', 'GET /student/marks', 'POST /login (skipped)'];
  net.forEach((n, i) => {
    const r = box(c1, 26, 80 + i * 62, 388, 48, 'abs mono', { fontSize: '19px', display: 'flex', alignItems: 'center', gap: '10px', color: i === 3 ? 'var(--dim)' : 'var(--ink)' }, `<span style="color:${i === 3 ? 'var(--dim)' : 'var(--green)'}">${i === 3 ? '302' : '200'}</span>${n}`);
    inn(r, w40(2) + i * 0.35, { x: -20, y: 0, d: 0.35 });
  });
  const yml = ['openapi: 3.1.0', 'paths:', '  /student/attendance:', '    get: { operationId:', '      get_attendance }', '  /student/timetable:', '    get: { operationId:', '      get_timetable }'];
  yml.forEach((l, i) => {
    const r = box(c2, 26, 76 + i * 46, 430, 40, 'abs code', { fontSize: '21px', whiteSpace: 'pre', color: i < 2 ? 'var(--amber)' : 'rgba(244,241,234,.85)' }, l);
    inn(r, w40(6) + i * 0.18, { x: -14, y: 0, d: 0.3 });
  });
  const tls = ['get_attendance', 'get_timetable', 'get_marks'];
  tls.forEach((n, i) => {
    const r = box(c3, 26, 90 + i * 110, 298, 88, 'abs', { borderRadius: '16px', border: '1px solid rgba(91,228,155,.45)', background: 'rgba(91,228,155,.07)', padding: '12px 16px' }, `<div class="mono" style="font-size:15px;color:var(--mute)">Portal___</div><div class="mono" style="font-size:22px">${n}</div>`);
    inn(r, w40(15) + i * 0.35, { y: 20, scale: 0.9, d: 0.45, ease: 'back.out(1.6)' });
  });
  const ro = box(c3, 26, 430, 300, 60, 'abs mono', { fontSize: '16px', color: 'var(--green)', letterSpacing: '.08em', lineHeight: 1.5 }, `${check(18)} REPLAY-VERIFIED<br>${check(18)} READ-ONLY`);
  inn(ro, w40(18), { y: 10, d: 0.4 });
  const credit = box(cam, 480, 810, 1300, 30, 'abs mono', { fontSize: '17px', color: 'var(--dim)', letterSpacing: '.12em' }, 'BUILT ON THE OPEN-SOURCE REVERSE-API-ENGINEER · ONE SPEC PER COLLEGE');
  inn(credit, w40(16), { y: 8, d: 0.4 });

})();

// =============================== 10. CLOSE ===============================
(function close() {
  const S = scene('close'), cam = S.cam;
  seamUp('forge', 'close', C.close);
  lights(C.close, [960, 470, 1], [1650, 950, 0.4], [250, 150, 0.35], 1.2);
  tl.to(GRID, { opacity: 0, duration: 0.6 }, C.close);
  const rg = ring(cam, 612, 450, 210, 30, { glow: 14, glowOp: 0.65, trackOp: 0 });
  arcTo(rg, 0.75, C.close + 0.15, 0.9, 'power3.out');
  const wm = wordmark(cam, 750, 372, 168);
  tl.fromTo(wm.children, { y: 80, opacity: 0, filter: 'blur(14px)' }, { y: 0, opacity: 1, filter: 'blur(0px)', duration: 0.7, stagger: 0.04, ease: 'power4.out' }, C.close + 0.2);
  const L44 = 'Seven Five. Your semester, on autopilot.';
  const w44 = Wt(L44, 'L44');
  const t1 = words(cam, 'Your semester, on autopilot.', 'abs serif', { left: '960px', top: '640px', fontSize: '76px', whiteSpace: 'nowrap' });
  center(t1);
  spoken(t1, w44(2) - 0.05, E.L44 - w44(2), { y: 24, d: 0.5 });
  const t2 = words(cam, 'You keep the steering wheel.', 'abs serif', { left: '960px', top: '740px', fontSize: '76px', whiteSpace: 'nowrap', color: 'var(--amber)' });
  center(t2);
  spoken(t2, T.L45 - 0.05, E.L45 - T.L45, { y: 24, d: 0.5 });
  const cr = box(cam, 960, 900, 'auto', 'auto', 'abs', { textAlign: 'center', whiteSpace: 'nowrap' });
  center(cr);
  cr.innerHTML = `<div class="mono" style="font-size:19px;letter-spacing:.18em;color:var(--mute)">WHACKIEST 2026 · TRACK 1 · MAKE MCP MATTER</div>
    <div style="font-size:24px;margin-top:14px;color:rgba(244,241,234,.8)">Powered by <span style="color:var(--aws);font-weight:600">AWS</span> + <span style="font-weight:600">ElevenLabs</span> &nbsp;·&nbsp; Jnanottam GY · Kartik · Mohammed Zaid</div>`;
  inn(cr, C.endcard, { y: 14, d: 0.6 });
  tl.fromTo(document.getElementById('black'), { opacity: 0 }, { opacity: 1, duration: 1.1, ease: 'power2.in' }, D.total - 1.2);
})();
