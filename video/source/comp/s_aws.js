// Scenes 7-10: AWS architecture, PORTAL FORGE + live counter, BUSINESS, CLOSE
function node(parent, x, y, w, h, title, sub, kind) {
  const col = { aws: ['rgba(255,153,0,.55)', 'rgba(255,153,0,.07)'], el: ['rgba(244,241,234,.5)', 'rgba(244,241,234,.05)'], supa: ['rgba(62,207,142,.55)', 'rgba(62,207,142,.06)'], gw: ['rgba(255,181,71,.85)', 'rgba(255,181,71,.08)'], plain: ['rgba(255,255,255,.14)', 'rgba(255,255,255,.035)'] }[kind || 'plain'];
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
  const A1 = node(cam, 110, 230, 270, 96, 'Gmail push', 'Google Pub/Sub');
  const A2 = node(cam, 110, 350, 270, 96, 'Share sheet', 'S3 → Scribe', 'aws');
  const A3 = node(cam, 110, 470, 270, 96, 'EventBridge', '07:00 · daily', 'aws');
  const B1 = node(cam, 440, 290, 230, 96, 'SQS', '+ dead-letter queue', 'aws');
  const lam = ['cascade', 'planner', 'approve', 'briefing', 'notify'].map((n, i) => node(cam, 720, 200 + i * 86, 260, 74, `λ ${n}`, null, 'aws'));
  const G = node(cam, 1040, 190, 300, 520, '', '', 'gw');
  G.innerHTML = `<div class="mono" style="font-size:16px;color:var(--aws);letter-spacing:.14em;text-align:center">AMAZON BEDROCK</div><div style="font-size:34px;font-weight:650;text-align:center;line-height:1.1;margin-top:6px">AgentCore<br>Gateway</div>`;
  G.style.justifyContent = 'flex-start';
  G.style.paddingTop = '30px';
  const gRows = ['Cedar policy', 'Interceptor λ', 'Identity vault'].map((n, i) => box(G, 24, 170 + i * 104, 250, 84, 'abs', { borderRadius: '16px', background: 'rgba(0,0,0,.35)', border: '1px solid rgba(255,255,255,.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px', fontWeight: 600 }, n));
  const tools = ['Gmail API', 'Google Calendar API', 'College portal', 'Agent tools λ'].map((n, i) => node(cam, 1410, 210 + i * 104, 400, 80, n));
  const EL = node(cam, 110, 620, 330, 96, 'ElevenLabs Agents', 'voice agent · MCP client', 'el');
  const SB = node(cam, 470, 770, 640, 200, '', '', 'supa');
  SB.style.justifyContent = 'flex-start';
  SB.innerHTML = `<div style="display:flex;align-items:center;gap:14px"><span style="font-size:28px;font-weight:650">Supabase</span><span class="mono" style="font-size:16px;color:var(--supa);letter-spacing:.12em">POSTGRES · MUMBAI</span></div>`;
  const sbT = ['Row-level security', 'Realtime', 'Auth'].map((n, i) => box(SB, 20 + i * 205, 80, 190, 96, 'abs', { borderRadius: '14px', background: 'rgba(0,0,0,.3)', border: '1px solid rgba(62,207,142,.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '22px', fontWeight: 600, textAlign: 'center' }, n));
  const BR = node(cam, 1150, 800, 330, 110, 'Amazon Bedrock', 'Claude Haiku · India', 'aws');
  const PH = node(cam, 1540, 770, 270, 200, 'Your phone', 'web app · push', 'plain');
  const all = [A1, A2, A3, B1, ...lam, G, ...tools, EL, SB, BR, PH];
  tl.fromTo([A1, A2, A3, EL], { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.6, stagger: 0.06, ease: 'power4.out' }, t0 + 0.2);
  tl.fromTo([B1, ...lam], { y: 30, opacity: 0 }, { y: 0, opacity: 0.45, duration: 0.6, stagger: 0.06, ease: 'power4.out' }, t0 + 0.45);
  tl.fromTo(G, { scale: 0.9, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.7, ease: 'power4.out' }, t0 + 0.7);
  tl.fromTo([...tools, SB, BR, PH], { x: 60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.6, stagger: 0.06, ease: 'power4.out' }, t0 + 0.9);
  const sv = svgLayer(cam);
  const P = (d, o) => pathEl(sv, d, Object.assign({ stroke: 'rgba(244,241,234,.2)', w: 2 }, o || {}));
  const pA1B = P('M 380 278 C 410 278, 410 338, 440 338');
  const pA2B = P('M 380 398 C 410 398, 410 338, 440 338');
  const pBC = P('M 670 338 C 695 338, 690 237, 720 237');
  const pA3C = P('M 380 518 C 560 518, 560 495, 720 495');
  const pCG = lam.map((l, i) => P(`M 980 ${237 + i * 86} C 1010 ${237 + i * 86}, 1010 450, 1040 450`));
  const pGT = tools.map((t, i) => P(`M 1340 450 C 1375 450, 1375 ${250 + i * 104}, 1410 ${250 + i * 104}`));
  const pEL = P('M 440 668 C 760 668, 900 640, 1040 640');
  const pCB = P('M 980 237 C 1100 140, 1560 400, 1315 800', { dash: '5 8' });
  const pCS = P('M 850 618 L 850 770');
  const pSP = P('M 1110 880 C 1300 880, 1400 870, 1540 870');
  [pA1B, pA2B, pBC, pA3C, ...pCG, ...pGT, pEL, pCB, pCS, pSP].forEach((p, i) => drawPath(p, t0 + 1.0 + i * 0.03, 0.7));

  // L35 — Lambdas wake only when needed; SQS retry-safe; EventBridge at 7
  const L35 = 'Lambda workers wake only when needed. S Q S makes every event retry-safe. Event Bridge wakes us at seven.';
  const w35 = Wt(L35, 'L35');
  const wake = (n, t) => { tl.to(n, { opacity: 1, boxShadow: '0 0 40px rgba(255,153,0,.45)', duration: 0.25 }, t); tl.to(n, { opacity: 0.55, boxShadow: '0 0 0 rgba(0,0,0,0)', duration: 0.8 }, t + 1.2); };
  packet(sv, pA1B, w35(2) - 0.5, 0.45);
  packet(sv, pBC, w35(2), 0.45);
  wake(lam[0], w35(2) + 0.45);
  [1, 2, 3, 4].forEach((k, j) => wake(lam[k], w35(3) + j * 0.3));
  tl.to(B1, { opacity: 1, boxShadow: '0 0 40px rgba(255,153,0,.45)', duration: 0.3 }, w35(6));
  const retry = box(cam, 610, 250, 50, 50, 'abs', {}, '<svg width="50" height="50" viewBox="0 0 24 24"><path d="M19 12 a7 7 0 1 1 -2.05 -4.95 M19 4 V8 H15" fill="none" stroke="#FF9900" stroke-width="2" stroke-linecap="round"/></svg>');
  inn(retry, w35(9), { y: 0, scale: 0.5, d: 0.35, ease: 'back.out(1.8)' });
  tl.to(retry, { rotation: 360, duration: 1.0, ease: 'power2.inOut' }, w35(11));
  packet(sv, pA2B, w35(10), 0.45, '#F4F1EA');
  tl.to(B1, { boxShadow: '0 0 0 rgba(0,0,0,0)', duration: 0.6 }, w35(13));
  tl.to(A3, { boxShadow: '0 0 40px rgba(255,153,0,.5)', duration: 0.3 }, w35(13));
  tl.set(A3.querySelector('.mono'), { innerHTML: '07:00 · wake up' }, w35(17));
  packet(sv, pA3C, w35(15), 0.7);
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
  const nic = box(cam, 1360, 640, 'auto', 'auto', 'chip', { fontSize: '22px' }, `<svg width="26" height="26" viewBox="0 0 24 24"><circle cx="8" cy="12" r="4" fill="none" stroke="#F4F1EA" stroke-width="2"/><path d="M12 12 H21 M18 12 V15" stroke="#F4F1EA" stroke-width="2"/><path d="M3 3 L21 21" stroke="#FF5A4E" stroke-width="2.2"/></svg> never in our code`);
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
  const pc = box(PH, 20, 112, 230, 66, 'abs', { borderRadius: '12px', background: 'rgba(255,181,71,.12)', border: '1px solid rgba(255,181,71,.4)', fontSize: '17px', padding: '8px 12px', lineHeight: 1.3 }, '<b>New deadline</b><br><span style="color:var(--mute)">DBMS · Assignment 3</span>');
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

  // the live counter
  const L41 = 'And on stage, a live counter shows how much ran on rules, how much needed A I, and what it cost per student. Measured, never estimated.';
  const w41 = Wt(L41, 'L41');
  tl.to([ttl, c1, c2, c3, credit, ...mocks], { x: '-=380', opacity: 0, filter: 'blur(14px)', duration: 0.42, ease: 'power4.in' }, T.L41 - 0.4);
  const dash = box(cam, 360, 200, 1200, 560, 'card', { background: 'rgba(12,13,17,.95)', padding: '36px 44px' });
  tl.fromTo(dash, { x: 420, opacity: 0, filter: 'blur(14px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.56, ease: 'power4.out' }, T.L41);
  dash.innerHTML = `<div style="display:flex;align-items:center;gap:16px"><span style="width:14px;height:14px;border-radius:50%;background:var(--red);box-shadow:0 0 14px var(--red)"></span><span class="mono" style="font-size:20px;letter-spacing:.16em">LIVE COUNTER</span><span class="mono" style="margin-left:auto;font-size:16px;color:var(--dim);letter-spacing:.12em">PREVIEW · REAL NUMBERS ARE MEASURED ON STAGE</span></div>`;
  const bars = [['Handled by rules', 0.78, 'var(--green)', 11], ['Needed AI', 0.17, 'var(--aws)', 16], ['Asked you', 0.05, 'var(--amber)', 16]];
  bars.forEach(([n, f, c, wi], i) => {
    const r = box(dash, 44, 110 + i * 100, 1110, 80, 'abs');
    r.innerHTML = `<div style="font-size:28px;font-weight:600;margin-bottom:14px">${n}</div><div style="height:14px;border-radius:7px;background:rgba(255,255,255,.07);position:relative"><b class="bf" style="position:absolute;left:0;top:0;height:14px;border-radius:7px;width:100%;background:${c};transform-origin:0 50%;transform:scaleX(0)"></b></div>`;
    inn(r, w41(wi) - 0.3, { y: 14, d: 0.4 });
    tl.to(r.querySelector('.bf'), { scaleX: f, duration: 1.0, ease: 'power3.out' }, w41(wi));
  });
  const cost = box(dash, 44, 420, 1110, 80, 'abs', { display: 'flex', alignItems: 'center', gap: '20px' }, '<span style="font-size:28px;font-weight:600">Cost per student</span><span class="mono" style="font-size:40px;color:var(--amber)">₹ · · ·</span><span class="mono" style="font-size:16px;color:var(--mute);letter-spacing:.12em">FROM REAL TOKEN + VOICE USAGE</span>');
  inn(cost, w41(20) - 0.2, { y: 14, d: 0.4 });
  const mne = words(cam, 'Measured, never estimated.', 'abs serif', { left: '960px', top: '860px', fontSize: '84px', whiteSpace: 'nowrap' });
  center(mne);
  spoken(mne, w41(23), E.L41 - w41(23), { y: 24, d: 0.5 });
})();

// =============================== 9. BUSINESS =============================
(function business() {
  const S = scene('business'), cam = S.cam;
  seamLeft('forge', 'business', C.business);
  lights(C.business, [960, 420, 0.5], [300, 900, 0.3], [1700, 200, 0.3], 1);
  tl.to(GRID, { opacity: 0.12, duration: 0.8 }, C.business);
  const L42 = 'Free for students. Plus, for voice and planning. Pro, to bring your own A I, safely. And colleges get an official feed.';
  const w42 = Wt(L42, 'L42');
  const hd = box(cam, 110, 170, 900, 40, 'abs mono', { fontSize: '21px', color: 'var(--mute)', letterSpacing: '.16em' }, 'HOW IT SUSTAINS ITSELF');
  inn(hd, T.L42 - 0.2, { y: 8, d: 0.4 });
  const tiers = [['Free', 'FOR STUDENTS', 'Deadlines, warnings, approvals', 0], ['Plus', '₹79–99 / MONTH', 'Voice calls, briefings, week planner', 3], ['Pro', 'BRING YOUR OWN AI', 'Use Claude or ChatGPT, safely, through our gateway', 8], ['Colleges', 'OFFICIAL FEED', 'Read-only data, anonymised attendance risk', 17]];
  const cards = tiers.map(([n, p, d, wi], i) => {
    const c = box(cam, 110 + i * 430, 250, 410, 420, 'card', { padding: '40px 36px', background: i === 1 ? 'rgba(255,181,71,.06)' : 'rgba(255,255,255,.035)', borderColor: i === 1 ? 'rgba(255,181,71,.45)' : 'rgba(255,255,255,.09)' });
    c.innerHTML = `<div style="font-size:64px;font-weight:650;letter-spacing:-0.03em">${n}</div><div class="mono" style="font-size:19px;color:var(--amber);letter-spacing:.12em;margin-top:10px">${p}</div><div style="font-size:28px;color:rgba(244,241,234,.78);margin-top:28px;line-height:1.35">${d}</div>`;
    tl.fromTo(c, { x: 260, opacity: 0, filter: 'blur(12px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.6, ease: 'power4.out' }, w42(wi) - 0.15);
    return c;
  });
  const L43 = 'We never sell your data.';
  tl.to(cards.concat(hd), { opacity: 0.13, duration: 0.45 }, T.L43 - 0.25);
  const never = box(cam, 960, 470, 'auto', 'auto', 'abs', { display: 'flex', alignItems: 'center', gap: '30px', fontSize: '110px', fontWeight: 700, letterSpacing: '-0.04em', whiteSpace: 'nowrap', textShadow: '0 20px 60px rgba(0,0,0,.8)' }, `${lockIcon(100, '#FFB547')}<span>We never sell your data.</span>`);
  center(never);
  tl.fromTo(never, { opacity: 0, scale: 1.15, filter: 'blur(18px)' }, { opacity: 1, scale: 1, filter: 'blur(0px)', duration: 0.55, ease: 'power4.out' }, T.L43 - 0.08);
})();

// =============================== 10. CLOSE ===============================
(function close() {
  const S = scene('close'), cam = S.cam;
  seamUp('business', 'close', C.close);
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
