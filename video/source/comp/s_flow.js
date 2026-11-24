// Scenes 4-5: FLOW (one message, end to end) and VOICE (ElevenLabs)
function hl(parent, text) { return `<span class="hl" style="position:relative;display:inline-block">${text}<i style="position:absolute;left:0;right:0;bottom:-6px;height:5px;border-radius:3px;background:var(--amber);transform-origin:0 50%;transform:scaleX(0)"></i></span>`; }
function layer(parent) { return box(parent, 0, 0, '100%', '100%', 'abs'); }

// =============================== 4. FLOW =================================
(function flow() {
  const S = scene('flow'), cam = S.cam;
  seamLeft('reveal', 'flow', C.flow);
  lights(C.flow, [520, 420, 0.65], [1500, 820, 0.45], [1150, 120, 0.25], 1.2);
  tl.to(GRID, { opacity: 0.22, duration: 1 }, C.flow);

  // --- the message ---
  const L12 = 'D B M S assignment three. Due Friday, eleven fifty-nine P M.';
  const L13 = 'Forward it to Seven Five on WhatsApp, in one tap. Or let your class rep forward it once, for the whole section.';
  const L15 = "It finds the subject, the due date and the task, and checks it isn't a duplicate.";
  const L16 = "Only when the rules aren't sure does Claude step in, on Amazon Bedrock, and its answer is checked against your real subjects.";
  const w12 = i => wordTime(L12, i, T.L12, E.L12 - T.L12);
  const w13 = i => wordTime(L13, i, T.L13, E.L13 - T.L13);
  const w16 = i => wordTime(L16, i, T.L16, E.L16 - T.L16);

  const msgWrap = box(cam, 250, 300, 940, 260, 'abs');
  const bub = box(msgWrap, 0, 0, 940, 'auto', 'abs', { padding: '30px 40px 34px', borderRadius: '30px', background: 'rgba(255,255,255,.065)', border: '1px solid rgba(255,255,255,.1)' });
  bub.innerHTML = `<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px"><i style="display:block;width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#3E8E6A,#1F4F3A)"></i><b style="font-size:26px;color:var(--green);font-weight:600">Ramesh (CR)</b><span style="font-size:24px;color:var(--mute)">· CSE 3B class group</span><span class="mono" style="margin-left:auto;font-size:20px;color:var(--dim)">9:14 PM</span></div>
  <div style="font-size:48px;line-height:1.3;font-weight:500;letter-spacing:-0.01em">${hl(0, 'DBMS')} ${hl(0, 'Assignment 3')} due ${hl(0, 'Friday 11:59 PM.')} Submit on Classroom.</div>`;
  inn(bub, T.L11 - 0.2, { y: 40, d: 0.7 });
  // tracking brackets lock on
  const br = box(msgWrap, -26, -26, 992, 300, 'abs');
  [[0, 0, 'tl'], [1, 0, 'tr'], [0, 1, 'bl'], [1, 1, 'br']].forEach(([x, y]) => {
    const b = box(br, x ? 'auto' : 0, y ? 'auto' : 0, 46, 46, 'abs', { right: x ? '0' : 'auto', bottom: y ? '0' : 'auto', borderColor: 'var(--amber)', borderStyle: 'solid', borderWidth: `${y ? 0 : 4}px ${x ? 4 : 0}px ${y ? 4 : 0}px ${x ? 0 : 4}px`, borderRadius: '6px' });
  });
  const trk = box(msgWrap, -24, -78, 600, 40, 'abs mono', { fontSize: '20px', color: 'var(--amber)', letterSpacing: '.14em' }, '● TRACKING · ONE MESSAGE');
  tl.fromTo(br, { scale: 1.3, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.7, ease: 'power3.out' }, T.L11 + 0.15);
  inn(trk, T.L11 + 0.35, { y: 0, x: -20, d: 0.5 });
  tl.fromTo(cam, { scale: 1 }, { scale: 1.06, duration: E.L12 - C.flow, ease: 'power1.inOut' }, C.flow);
  const hls = bub.querySelectorAll('.hl');
  [0, 4, 7].forEach((wi, k) => {
    const t = w12(wi);
    tl.to(hls[k].querySelector('i'), { scaleX: 1, duration: 0.45, ease: 'power3.out' }, t);
    tl.to(hls[k], { color: 'var(--amber)', duration: 0.3 }, t);
  });

  // --- forward it on WhatsApp, or the class rep forwards once for everyone ---
  tl.to(msgWrap, { x: -40, y: -120, scale: 0.84, duration: 0.8, ease: 'power3.inOut' }, T.L13 - 0.2);
  tl.to(cam, { scale: 1, duration: 0.8, ease: 'power3.inOut' }, T.L13 - 0.2);
  const sheet = box(cam, 250, 600, 860, 250, 'abs', { borderRadius: '30px', background: 'rgba(22,24,30,.92)', border: '1px solid rgba(255,255,255,.1)' });
  box(sheet, 34, 26, 400, 30, 'abs mono', { fontSize: '19px', color: 'var(--mute)', letterSpacing: '.14em' }, 'FORWARD TO');
  const apps = [['Amma', '#3B4A63'], ['Rahul', '#4A3B63'], ['Hostel 4B', '#2F4F3F'], ['7even5ive', 'ring']];
  let app75;
  apps.forEach(([n, c], i) => {
    const a = box(sheet, 40 + i * 205, 74, 160, 150, 'abs', { textAlign: 'center' });
    const ic = box(a, 36, 0, 88, 88, 'abs', { borderRadius: c === 'ring' ? '24px' : '50%', background: c === 'ring' ? '#0d0e12' : c, border: c === 'ring' ? '2px solid var(--amber)' : '1px solid rgba(255,255,255,.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '34px', fontWeight: 600, color: 'rgba(244,241,234,.75)' }, c === 'ring' ? '' : n[0]);
    if (c === 'ring') { const rr = ring(ic, 43, 43, 56, 8, { glow: 3, trackOp: 0 }); rr.arcs.forEach(x => x.setAttribute('stroke-dashoffset', rr.C * 0.25)); app75 = a; }
    box(a, 0, 100, 160, 34, 'abs', { fontSize: '22px', color: c === 'ring' ? 'var(--amber)' : 'var(--mute)', fontWeight: c === 'ring' ? 600 : 400 }, n);
  });
  tl.fromTo(sheet, { y: 260, opacity: 0, filter: 'blur(10px)' }, { y: 0, opacity: 1, filter: 'blur(0px)', duration: 0.7, ease: 'power4.out' }, T.L13 + 0.3);
  const cur = cursor(cam, 1400, 1150, 96);
  tap(cur, 250 + 40 + 615 + 80, 600 + 74 + 44, w13(8), cam);
  tl.to(app75, { scale: 0.9, duration: 0.08 }, w13(8));
  tl.to(app75, { scale: 1, duration: 0.3, ease: 'back.out(1.7)' }, w13(8) + 0.08);
  tl.to(cur, { left: 1500 + 'px', top: 1200 + 'px', duration: 0.6, ease: 'power3.in' }, w13(8) + 0.5);
  // the email path
  const mail = box(cam, 1310, 330, 470, 'auto', 'abs', { padding: '26px 30px', borderRadius: '26px', background: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.1)' });
  mail.innerHTML = `<div style="display:flex;align-items:center;gap:16px"><svg width="44" height="44" viewBox="0 0 24 24" style="flex:none"><path d="M3 10 V14 H6.5 L13.5 18.5 V5.5 L6.5 10 Z" fill="none" stroke="#F4F1EA" stroke-width="1.6" stroke-linejoin="round"/><path d="M16.5 9.5 Q18.3 12 16.5 14.5 M19 7.5 Q22.2 12 19 16.5" fill="none" stroke="#F4F1EA" stroke-width="1.6" stroke-linecap="round"/></svg><div><div style="font-size:28px;font-weight:600">or your class rep, once</div><div class="mono" style="font-size:18px;color:var(--mute);margin-top:4px">ONE FORWARD → WHOLE SECTION</div></div></div>`;
  inn(mail, w13(10) - 0.1, { x: 60, y: 0, d: 0.6, ease: 'power4.out' });
  const bolt = box(mail, 400, 20, 48, 48, 'abs', {}, '<svg width="48" height="48" viewBox="0 0 24 24"><path d="M13 2 L5 13.5 H11 L10 22 L19 9.5 H13 Z" fill="#FFB547"/></svg>');
  tl.fromTo(bolt, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.4, ease: 'back.out(2)' }, w13(17));
  const sv = svgLayer(cam);
  const p1 = pathEl(sv, 'M 1545 470 C 1545 620, 1450 700, 1300 730', { stroke: 'rgba(255,181,71,.45)', w: 2.5, dash: '6 8' });
  drawPath(p1, w13(17), 0.6);
  packet(sv, p1, w13(19), 0.7);

  // --- the rules engine ---
  const t14 = T.L14 - 0.35;
  tl.to([msgWrap, sheet, mail, sv], { x: '-=520', opacity: 0, filter: 'blur(12px)', duration: 0.42, ease: 'power4.in' }, t14);
  const eng = box(cam, 220, 96, 1480, 800, 'card', { background: 'rgba(255,255,255,.03)' });
  tl.fromTo(eng, { x: 620, opacity: 0, filter: 'blur(16px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.62, ease: 'power4.out' }, t14 + 0.42);
  box(eng, 50, 40, 600, 34, 'abs mono', { fontSize: '20px', color: 'var(--mute)', letterSpacing: '.16em' }, 'STEP 1 · RULES ENGINE');
  const noai = box(eng, 1120, 28, 310, 52, 'abs mono', { display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '999px', border: '1px solid rgba(91,228,155,.55)', color: 'var(--green)', fontSize: '20px', letterSpacing: '.12em' }, 'NO AI USED');
  const pc = words(eng, 'Plain code. No AI.', 'abs serif', { left: '50px', top: '84px', fontSize: '84px', whiteSpace: 'nowrap' });
  spoken(pc, T.L14, E.L14 - T.L14, { y: 30, d: 0.5 });
  inn(noai, E.L14 - 0.3, { y: 0, scale: 0.8, d: 0.5, ease: 'back.out(1.7)' });
  const src = box(eng, 50, 212, 1380, 60, 'abs mono', { fontSize: '27px', color: 'rgba(244,241,234,.7)', padding: '10px 18px', borderRadius: '12px', background: 'rgba(0,0,0,.3)' }, '"DBMS Assignment 3 due Friday 11:59 PM. Submit on Classroom."');
  inn(src, T.L14 + 0.5, { y: 14, d: 0.5 });
  const fields = [['SUBJECT', 'DBMS', 'matched to your subject list'], ['DUE', 'Fri · 11:59 PM', 'date parser, anchored to the sent time'], ['TASK', 'Assignment 3', 'pattern rules'], ['DUPLICATE?', 'None', 'content hash + subject, title, date']];
  fields.forEach(([k, v, how], i) => {
    const r = box(eng, 50, 296 + i * 80, 1380, 68, 'abs', { display: 'flex', alignItems: 'center', gap: '26px', padding: '0 24px', borderRadius: '14px', background: 'rgba(255,255,255,.035)', border: '1px solid rgba(255,255,255,.07)' });
    r.innerHTML = `<span class="mono" style="width:210px;font-size:20px;color:var(--mute);letter-spacing:.12em">${k}</span><b style="font-size:36px;font-weight:600;width:360px">${v}</b>${check(32)}<span class="mono" style="margin-left:auto;font-size:19px;color:var(--dim)">${how}</span>`;
    inn(r, T.L15 + 0.3 + i * 0.95, { x: -40, y: 0, d: 0.5, ease: 'power4.out' });
  });
  // confidence → model only if unsure
  const gx = 50, gy = 630, gw = 900;
  const clab = box(eng, gx, gy, 300, 30, 'abs mono', { fontSize: '19px', color: 'var(--mute)', letterSpacing: '.14em' }, 'CONFIDENCE');
  const track = box(eng, gx, gy + 40, gw, 14, 'abs', { borderRadius: '7px', background: 'rgba(255,255,255,.07)' });
  const zone = box(eng, gx + gw * 0.6, gy + 40, gw * 0.3, 14, 'abs', { background: 'rgba(255,153,0,.22)', borderRadius: '2px' });
  const fill = box(track, 0, 0, gw, 14, 'abs', { borderRadius: '7px', background: 'linear-gradient(90deg,#3d8f6a,#5BE49B)', transformOrigin: '0 50%' });
  const ticks = [[0.6, '0.6'], [0.9, '0.9']].map(([f, l]) => box(eng, gx + gw * f - 20, gy + 64, 40, 26, 'abs mono', { fontSize: '17px', color: 'var(--mute)', textAlign: 'center' }, l));
  const cval = box(eng, gx + gw + 30, gy + 22, 300, 50, 'abs mono', { fontSize: '40px', color: 'var(--green)', fontWeight: 500 }, '0.00');
  tl.fromTo([clab, track, zone, ...ticks], { opacity: 0 }, { opacity: 1, duration: 0.4, immediateRender: true }, T.L16 - 0.1);
  tl.fromTo(fill, { scaleX: 0 }, { scaleX: 0.94, duration: 1.1, ease: 'power3.out' }, T.L16 + 0.1);
  count(cval, 0, 0.94, T.L16 + 0.1, 1.1, v => v.toFixed(2));
  tl.fromTo(cval, { opacity: 0 }, { opacity: 1, duration: 0.3 }, T.L16 + 0.1);
  const keep = box(eng, gx + gw + 30, gy + 80, 480, 30, 'abs mono', { fontSize: '19px', color: 'var(--green)', letterSpacing: '.08em' }, '≥ 0.9 → SAVED, NO AI NEEDED');
  inn(keep, T.L16 + 1.2, { y: 8, d: 0.4 });
  const branch = box(eng, gx, gy + 100, 1380, 46, 'abs', { display: 'flex', alignItems: 'center', gap: '16px', fontSize: '24px', color: 'var(--mute)' });
  branch.innerHTML = `<span class="mono" style="font-size:19px;color:var(--aws);letter-spacing:.08em">IF 0.6 – 0.9 →</span><span style="color:var(--ink);font-weight:600">Claude Haiku</span><span>on</span><span style="padding:4px 14px;border-radius:10px;border:1px solid rgba(255,153,0,.6);background:rgba(255,153,0,.1);color:var(--ink);font-weight:500"><span class="mono" style="font-size:15px;color:var(--aws);letter-spacing:.12em;margin-right:8px">AWS</span>Amazon Bedrock</span><span class="chk2" style="margin-left:18px">→ checked against your real subjects ${check(26)}</span>`;
  inn(branch, w16(7) - 0.15, { x: 30, y: 0, d: 0.55, ease: 'power4.out' });
  tl.fromTo(branch.querySelector('.chk2'), { opacity: 0 }, { opacity: 1, duration: 0.4 }, w16(15));

  // --- the phone ---
  const t17 = T.L17 - 0.35;
  tl.to(eng, { x: -640, opacity: 0, filter: 'blur(14px)', duration: 0.42, ease: 'power4.in' }, t17);
  const ph = phone(cam, 1110, 110, 420, 860);
  tl.fromTo(ph.p, { x: 700, filter: 'blur(14px)' }, { x: 0, filter: 'blur(0px)', duration: 0.65, ease: 'power4.out' }, t17 + 0.42);
  appHeader(ph.scr, 420);
  box(ph.scr, 30, 140, 340, 30, 'abs mono', { fontSize: '17px', color: 'var(--mute)', letterSpacing: '.14em' }, 'INBOX');
  const old = box(ph.scr, 22, 470, 354, 110, 'abs', { borderRadius: '22px', background: 'rgba(255,255,255,.035)', padding: '20px 22px', fontSize: '21px', color: 'var(--mute)' }, '<div class="mono" style="font-size:15px;letter-spacing:.12em">DEADLINE</div><div style="color:rgba(244,241,234,.6);font-weight:600;margin-top:6px">OS · Lab record</div><div>Mon, 9:00 AM</div>');
  const crd = box(ph.scr, 22, 182, 354, 270, 'abs', { borderRadius: '24px', background: 'rgba(255,255,255,.07)', border: '1px solid rgba(255,181,71,.35)', padding: '22px 22px', boxShadow: '0 20px 50px rgba(0,0,0,.4)' });
  crd.innerHTML = `<div class="mono" style="font-size:15px;color:var(--amber);letter-spacing:.14em">NEW DEADLINE</div>
   <div style="font-size:29px;font-weight:650;margin-top:8px;letter-spacing:-0.01em">DBMS · Assignment 3</div>
   <div style="font-size:22px;color:var(--mute);margin-top:2px">Fri, 11:59 PM</div>
   <div class="mono" style="font-size:15px;color:var(--dim);margin-top:10px">"…due Friday 11:59 PM" · class group</div>
   <div style="display:flex;gap:10px;margin-top:18px"><span class="btn addb" style="height:50px;padding:0 16px;background:var(--amber);color:#1a1205;font-size:19px;white-space:nowrap">Add to Calendar</span><span class="btn" style="height:50px;padding:0 14px;border:1px solid rgba(255,255,255,.2);font-size:19px;color:var(--mute);white-space:nowrap">Not now</span></div>`;
  tl.fromTo(old, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t17 + 0.5);
  tl.fromTo(crd, { y: -160, opacity: 0, scale: 0.94 }, { y: 0, opacity: 1, scale: 1, duration: 0.7, ease: 'back.out(1.4)' }, T.L17 + 0.35);
  tl.to(old, { y: 0, duration: 0.01 }, T.L17 + 0.35);
  const left = words(cam, 'Seconds later.', 'abs serif', { left: '250px', top: '380px', fontSize: '104px', whiteSpace: 'nowrap' });
  spoken(left, T.L17, 1.0, { y: 30, d: 0.5 });
  const rt = box(cam, 256, 520, 700, 40, 'abs mono', { fontSize: '21px', color: 'var(--mute)', letterSpacing: '.12em' }, 'SUPABASE REALTIME → YOUR PHONE');
  inn(rt, T.L17 + 0.8, { y: 10, d: 0.5 });
  // one tap
  const addb = crd.querySelector('.addb');
  const cur2 = cursor(cam, 1700, 1150, 96);
  const ax = 1110 + 11 + 22 + 22 + 88, ay = 110 + 11 + 182 + 22 + 190;
  tap(cur2, ax, ay, T.L18 + 0.75, cam);
  tl.to(addb, { scale: 0.92, duration: 0.08 }, T.L18 + 0.75);
  tl.to(addb, { scale: 1, background: '#5BE49B', duration: 0.3, ease: 'back.out(1.7)' }, T.L18 + 0.83);
  tl.set(addb, { innerHTML: 'Added ✓' }, T.L18 + 0.85);
  tl.to(cur2, { left: '1750px', top: '1180px', duration: 0.6, ease: 'power3.in' }, T.L18 + 1.4);
  const calrow = box(ph.scr, 22, 470, 354, 92, 'abs', { borderRadius: '20px', background: 'rgba(91,228,155,.1)', border: '1px solid rgba(91,228,155,.4)', display: 'flex', alignItems: 'center', gap: '16px', padding: '0 20px' });
  calrow.innerHTML = `<div style="text-align:center"><div class="mono" style="font-size:15px;color:var(--green)">FRI</div><div style="font-size:30px;font-weight:650">29</div></div><div><div style="font-size:22px;font-weight:600">DBMS Assignment 3</div><div class="mono" style="font-size:16px;color:var(--mute)">11:59 PM · Google Calendar</div></div>`;
  tl.to(old, { y: 120, opacity: 0.4, duration: 0.5, ease: 'power3.inOut' }, T.L18 + 1.15);
  inn(calrow, T.L18 + 1.2, { y: -30, d: 0.55, ease: 'power4.out' });
  const toast = box(ph.scr, 60, 760, 280, 54, 'abs mono', { borderRadius: '999px', background: 'rgba(244,241,234,.92)', color: '#111', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '18px', fontSize: '18px' }, 'LOGGED <b style="color:#C2410C">UNDO</b>');
  inn(toast, T.L18 + 2.0, { y: 30, d: 0.5, ease: 'power4.out' });

  // ---------- the library: every file filed by subject (L18a, L18b) ----------
  const L18a = 'Files work the same way. Every P D F you forward is filed by subject: notes, question papers, circulars.';
  const L18b = 'Ask for the unit three notes, and you get the file. Not two hundred results.';
  const L18c = 'It reads your college email too, and keeps only what a student needs: placements, internships, and exam notices.';
  const wa = i => wordTime(L18a, i, T.L18a, E.L18a - T.L18a);
  const wbb = i => wordTime(L18b, i, T.L18b, E.L18b - T.L18b);
  const wcc = i => wordTime(L18c, i, T.L18c, E.L18c - T.L18c);
  tl.to([ph.p, left, rt], { x: '-=420', opacity: 0, filter: 'blur(14px)', duration: 0.42, ease: 'power4.in' }, T.L18a - 0.45);
  const LB = box(cam, 0, 0, 1920, 1080, 'abs');
  tl.set(LB, { opacity: 0 }, 0);
  tl.fromTo(LB, { x: 420, opacity: 1, filter: 'blur(14px)' }, { x: 0, filter: 'blur(0px)', duration: 0.56, ease: 'power4.out', immediateRender: false }, T.L18a - 0.03);
  // left: the 7even5ive chat on WhatsApp
  const wc = box(LB, 120, 96, 780, 868, 'card', { overflow: 'hidden', background: 'rgba(12,14,18,.94)' });
  const wcH = box(wc, 0, 0, 780, 96, 'abs', { display: 'flex', alignItems: 'center', gap: '18px', padding: '0 28px', borderBottom: '1px solid rgba(255,255,255,.07)', background: 'rgba(255,255,255,.03)' });
  wcH.innerHTML = '<div class="av" style="position:relative;flex:none;width:54px;height:54px;border-radius:50%;background:#0d0e12;border:1.5px solid rgba(255,181,71,.6)"></div><div><div style="font-size:28px;font-weight:600">7even5ive</div><div class="mono" style="font-size:16px;color:#7BE3A0;margin-top:2px">YOUR LIBRARY, ON WHATSAPP</div></div>';
  const avr = ring(wcH.querySelector('.av'), 27, 27, 34, 6, { glow: 2, trackOp: 0 }); avr.arcs.forEach(a => a.setAttribute('stroke-dashoffset', avr.C * 0.25));
  const wbody = box(wc, 0, 96, 780, 772, 'abs', { overflow: 'hidden' });
  const pdfB = (name, meta) => `<div style="display:flex;align-items:center;gap:14px"><i style="display:flex;align-items:center;justify-content:center;flex:none;width:46px;height:56px;border-radius:8px;background:rgba(255,90,78,.16);color:#FF8B7E;font:600 13px JB;font-style:normal">PDF</i><div><div style="font-size:23px;font-weight:500">${name}</div><div class="mono" style="font-size:14px;color:var(--mute);margin-top:3px">${meta}</div></div></div>`;
  const cb = (y, mine, html) => box(wbody, mine ? 'auto' : 28, y, 'auto', 'auto', 'abs', { right: mine ? '28px' : 'auto', maxWidth: '560px', padding: '10px 16px 12px', borderRadius: '18px', background: mine ? 'rgba(37,211,102,.16)' : 'rgba(255,255,255,.07)', fontSize: '23px', lineHeight: 1.35, whiteSpace: 'nowrap' }, html);
  const fwd = '<div class="mono" style="font-size:13px;color:var(--mute);letter-spacing:.08em;margin-bottom:6px">↪ FORWARDED</div>';
  const o1 = cb(18, true, fwd + pdfB('DBMS_U3_notes.pdf', '3.2 MB · PDF'));
  const o2 = cb(140, true, fwd + pdfB('OS_PYQ_2025.pdf', '1.4 MB · PDF'));
  const o3 = cb(262, true, fwd + pdfB('Lab_circular.pdf', '220 KB · PDF'));
  const r1 = cb(384, false, '<div class="mono" style="font-size:14px;color:var(--amber);letter-spacing:.1em;margin-bottom:6px">FILED 3 FILES</div>DBMS · Notes<br>OS · Question papers<br>Circulars');
  const o4 = cb(552, true, '<span class="q4"></span>');
  const r2 = cb(626, false, pdfB('DBMS_U3_notes.pdf', '24 PAGES · FROM RAHUL · 12 NOV'));
  [[o1, wa(5)], [o2, wa(8)], [o3, wa(10)], [r1, wa(12) + 0.15]].forEach(([b, t]) => inn(b, t - 0.1, { y: 24, d: 0.4 }));
  inn(o4, T.L18b + 0.05, { y: 20, d: 0.3 });
  typeText(o4.querySelector('.q4'), 'dbms unit 3 notes', T.L18b + 0.2, 16);
  inn(r2, wbb(8) - 0.1, { y: 24, d: 0.4, ease: 'back.out(1.4)' });
  const oneF = box(LB, 520, 900, 380, 40, 'abs mono', { fontSize: '17px', color: 'var(--green)', letterSpacing: '.1em', textAlign: 'right' }, '1 FILE · NOT 200 RESULTS');
  inn(oneF, wbb(11), { y: 10, d: 0.4 });
  // right: the library itself
  const lib = box(LB, 980, 96, 820, 868, 'card', { background: 'rgba(255,255,255,.035)' });
  box(lib, 36, 30, 400, 50, 'abs', { fontSize: '40px', fontWeight: 650, letterSpacing: '-0.02em' }, 'Library');
  box(lib, 40, 84, 600, 30, 'abs mono', { fontSize: '17px', color: 'var(--mute)', letterSpacing: '.14em' }, 'STORAGE · BY SUBJECT · S3');
  const SH = [['DBMS', [['Notes', 12], ['Question papers', 6], ['Circulars', 3]]], ['Operating Systems', [['Notes', 9], ['Question papers', 4]]], ['Computer Networks', [['Notes', 7], ['Question papers', 3]]], ['General', [['Circulars', 14], ['Timetables', 2]]], ['Opportunities', [['Placement drives', 2], ['Internships', 1], ['Exam cell', 5]]]];
  const chipEl = {};
  SH.forEach(([sub, chips], i) => {
    const y = 140 + i * 134;
    box(lib, 40, y, 740, 34, 'abs', { fontSize: '25px', fontWeight: 600, color: sub === 'Opportunities' ? 'var(--amber)' : 'var(--ink)' }, sub);
    let x = 40;
    chips.forEach(([n, c]) => {
      const w = 34 + n.length * 12.5 + 40;
      const ch = box(lib, x, y + 46, w, 50, 'abs', { display: 'flex', alignItems: 'center', gap: '10px', padding: '0 16px', borderRadius: '12px', background: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.1)', fontSize: '19px', whiteSpace: 'nowrap' }, `<span>${n}</span><b class="mono cnt" style="font-weight:500;color:var(--mute)">${c}</b>`);
      chipEl[sub + '/' + n] = { el: ch, c, x: 980 + x + w / 2, y: 96 + y + 46 + 25 };
      x += w + 12;
    });
  });
  tl.fromTo(lib, { x: 60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.6, ease: 'power4.out' }, T.L18a + 0.2);
  // files fly from the chat into their shelves; each count ticks on arrival
  const land = (key, t) => {
    const k = chipEl[key], cnt = k.el.querySelector('.cnt');
    tl.to(k.el, { borderColor: 'rgba(255,181,71,.9)', background: 'rgba(255,181,71,.14)', duration: 0.15 }, t);
    tl.to(k.el, { borderColor: 'rgba(255,255,255,.1)', background: 'rgba(255,255,255,.05)', duration: 0.8 }, t + 0.6);
    tl.set(cnt, { textContent: String(k.c + 1), color: '#FFB547' }, t);
  };
  const fly = (fromX, fromY, key, t0, label) => {
    const k = chipEl[key];
    const f = box(LB, fromX - 23, fromY - 28, 46, 56, 'abs', { display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '8px', background: label ? 'rgba(255,181,71,.25)' : 'rgba(255,90,78,.3)', color: label ? '#FFD08A' : '#FFB3AB', font: '600 13px JB', zIndex: 9, boxShadow: '0 8px 24px rgba(0,0,0,.5)' }, label || 'PDF');
    tl.set(f, { opacity: 0 }, 0);
    tl.set(f, { opacity: 1 }, t0);
    tl.to(f, { x: k.x - fromX, y: k.y - fromY, scale: 0.7, duration: 0.7, ease: 'power3.inOut' }, t0);
    tl.set(f, { opacity: 0 }, t0 + 0.7);
    land(key, t0 + 0.7);
  };
  fly(690, 96 + 96 + 18 + 62, 'DBMS/Notes', wa(15) - 0.7);
  fly(690, 96 + 96 + 140 + 62, 'Operating Systems/Question papers', wa(16) - 0.6);
  fly(690, 96 + 96 + 262 + 62, 'General/Circulars', wa(18) - 0.6);
  tl.to(chipEl['DBMS/Notes'].el, { borderColor: 'rgba(91,228,155,.9)', background: 'rgba(91,228,155,.14)', duration: 0.2 }, wbb(8) - 0.3);
  tl.to(chipEl['DBMS/Notes'].el, { borderColor: 'rgba(255,255,255,.1)', background: 'rgba(255,255,255,.05)', duration: 0.8 }, wbb(8) + 1.2);

  // ---------- college mail, read-only, filtered to what a student needs (L18c) ----------
  tl.to(wc, { x: -300, opacity: 0, filter: 'blur(16px)', duration: 0.4, ease: 'power4.in' }, T.L18c - 0.45);
  tl.to(oneF, { opacity: 0, duration: 0.2 }, T.L18c - 0.45);
  const ib = box(LB, 120, 96, 780, 868, 'card', { overflow: 'hidden', background: 'rgba(12,14,18,.94)' });
  tl.set(ib, { opacity: 0 }, 0);
  tl.fromTo(ib, { x: 380, opacity: 1, filter: 'blur(16px)' }, { x: 0, filter: 'blur(0px)', duration: 0.56, ease: 'power4.out', immediateRender: false }, T.L18c - 0.05);
  const ibH = box(ib, 0, 0, 780, 96, 'abs', { display: 'flex', alignItems: 'center', gap: '16px', padding: '0 28px', borderBottom: '1px solid rgba(255,255,255,.07)', background: 'rgba(255,255,255,.03)' });
  ibH.innerHTML = '<svg width="38" height="38" viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="14" rx="2.5" fill="none" stroke="#F4F1EA" stroke-width="1.6"/><path d="M3.5 6.5 L12 13 L20.5 6.5" fill="none" stroke="#F4F1EA" stroke-width="1.6"/></svg><div><div style="font-size:28px;font-weight:600">College mail</div><div class="mono" style="font-size:15px;color:var(--mute);margin-top:2px">GMAIL API · READ-ONLY · RULES FIRST</div></div>';
  const MR = [['Newsletter', 'Campus digest · Week 48'], ['T&amp;P Cell', 'Campus drive · register by 6 PM', 'Opportunities/Placement drives', 13], ['Webinar', 'Free crypto trading webinar'], ['Internship Cell', 'Summer internship · apply by Fri', 'Opportunities/Internships', 14], ['Library', 'New arrivals this week'], ['Exam Cell', 'Hall tickets released', 'Opportunities/Exam cell', 16], ['Fest Committee', 'Volunteers needed'], ['Promotions', '50% off on laptops'], ['IT Services', 'Password expiry notice']];
  const mrows = MR.map(([who, subj, key, wi], i) => {
    const r = box(ib, 20, 112 + i * 82, 740, 72, 'abs', { display: 'flex', alignItems: 'center', gap: '16px', padding: '0 16px', borderRadius: '12px', border: '1px solid transparent', fontSize: '21px' });
    r.innerHTML = `<b style="flex:none;width:180px;font-weight:600">${who}</b><span class="sj" style="color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${subj}</span>`;
    return { r, key, wi };
  });
  const scan = box(ib, 0, 100, 780, 3, 'abs', { background: 'linear-gradient(90deg,rgba(255,181,71,0),#FFB547,rgba(255,181,71,0))', boxShadow: '0 0 18px #FFB547' });
  tl.set(scan, { opacity: 0 }, 0);
  tl.set(scan, { opacity: 1 }, wcc(6));
  tl.to(scan, { y: 740, duration: 1.0, ease: 'power1.inOut' }, wcc(6));
  tl.set(scan, { opacity: 0 }, wcc(6) + 1.0);
  mrows.forEach(({ r, key, wi }, i) => {
    if (!key) {
      tl.to(r, { opacity: 0.22, duration: 0.3 }, wcc(7) + i * 0.06);
      tl.to(r.querySelector('.sj'), { textDecoration: 'line-through', duration: 0.01 }, wcc(7) + i * 0.06);
    } else {
      tl.to(r, { borderColor: 'rgba(255,181,71,.8)', background: 'rgba(255,181,71,.10)', duration: 0.25 }, wcc(wi) - 0.15);
      fly(700, 96 + 112 + i * 82 + 36, key, wcc(wi) + 0.1, 'MAIL');
    }
  });
  const newOp = box(lib, 40, 140 + 4 * 134 + 112, 740, 60, 'abs', { display: 'flex', alignItems: 'center', gap: '14px', padding: '0 18px', borderRadius: '12px', background: 'rgba(255,181,71,.10)', border: '1px solid rgba(255,181,71,.55)', fontSize: '21px' }, '<span class="mono" style="font-size:14px;color:var(--amber);letter-spacing:.12em">NEW</span><b style="font-weight:600">Campus drive</b><span style="color:var(--mute)">· form closes today 6 PM</span>');
  inn(newOp, wcc(13) + 0.9, { y: 14, d: 0.45, ease: 'back.out(1.4)' });
})();

// =============================== 5. VOICE ================================
(function voice() {
  const S = scene('voice'), cam = S.cam;
  seamLeft('flow', 'voice', C.voice);
  lights(C.voice, [560, 520, 0.7], [1500, 300, 0.4], [1300, 950, 0.3], 1.2);
  tl.to(GRID, { opacity: 0.12, duration: 1 }, C.voice);
  const ph = phone(cam, 300, 110, 420, 860);
  const sA = layer(ph.scr), sB = layer(ph.scr), sC = layer(ph.scr);
  appHeader(sA, 420);
  // A: the urgent card
  const warn = box(sA, 22, 170, 354, 300, 'abs', { borderRadius: '26px', background: 'rgba(255,90,78,.09)', border: '1px solid rgba(255,90,78,.45)', padding: '24px' });
  const wr = ring(warn, 64, 70, 84, 12, { c1: '#FF8B7E', c2: '#FF3B2F', glow: 4, trackOp: 0.08 });
  wr.arcs.forEach(a => a.setAttribute('stroke-dashoffset', wr.C * 0.27));
  box(warn, 22, 50, 84, 40, 'abs', { textAlign: 'center', fontSize: '22px', fontWeight: 700, color: '#FF8B7E' }, '73%');
  box(warn, 130, 34, 210, 90, 'abs', { fontSize: '26px', fontWeight: 650, lineHeight: 1.2 }, 'DBMS attendance');
  box(warn, 24, 140, 310, 140, 'abs', { fontSize: '25px', lineHeight: 1.35, color: 'rgba(244,241,234,.85)' }, 'Attend the next 3 classes to get back to 75%.<div class="mono" style="font-size:16px;color:#FF8B7E;margin-top:12px;letter-spacing:.1em">0 BUNKS LEFT</div>');
  tl.fromTo(warn, { y: -140, opacity: 0, scale: 0.94 }, { y: 0, opacity: 1, scale: 1, duration: 0.7, ease: 'back.out(1.4)' }, T.L19 + 0.5);
  // right side headline
  const r1 = words(cam, 'When it\'s urgent,', 'abs serif', { left: '860px', top: '330px', fontSize: '110px', whiteSpace: 'nowrap' });
  spoken(r1, T.L19 + 0.4, 1.2, { y: 30, d: 0.5 });
  const r2 = words(cam, 'it calls you.', 'abs serif', { left: '860px', top: '460px', fontSize: '110px', whiteSpace: 'nowrap', color: 'var(--amber)' });
  spoken(r2, T.L20, E.L20 - T.L20 + 0.2, { y: 30, d: 0.5 });
  // B: incoming call
  tl.set(sB, { opacity: 0 }, 0);
  tl.to(sB, { opacity: 1, duration: 0.3 }, T.L20 + 0.1);
  tl.to(sA, { opacity: 0, duration: 0.3 }, T.L20 + 0.1);
  box(sB, 0, 0, '100%', '100%', 'abs', { background: 'radial-gradient(circle at 50% 38%,#2a1d0c 0%,#0b0c10 62%)' });
  box(sB, 0, 120, 398, 40, 'abs', { textAlign: 'center', fontSize: '22px', color: 'var(--mute)' }, 'Incoming call');
  box(sB, 0, 156, 398, 50, 'abs', { textAlign: 'center', fontSize: '38px', fontWeight: 650, letterSpacing: '-0.02em' }, '7even5ive');
  const ctime = box(sB, 0, 206, 398, 30, 'abs mono', { textAlign: 'center', fontSize: '18px', color: 'var(--mute)' }, 'voice agent');
  const orb = box(sB, 199 - 110, 300, 220, 220, 'abs', { borderRadius: '50%', background: 'radial-gradient(circle at 40% 35%,#FFF3DC 0%,#FFC56B 30%,#FF8A1F 62%,rgba(255,138,31,0) 72%)', boxShadow: '0 0 80px 20px rgba(255,160,60,.35)' });
  orb.classList.add('orb');
  // ringing (an action, not idle): orb pulses with each ring until answered
  [0, 0.55, 1.1, 1.65].forEach(dt => {
    tl.to(orb, { scale: 1.12, duration: 0.18, ease: 'power2.out' }, T.L20 + 0.4 + dt);
    tl.to(orb, { scale: 1, duration: 0.3, ease: 'power2.in' }, T.L20 + 0.58 + dt);
  });
  const dec = box(sB, 70, 650, 84, 84, 'abs', { borderRadius: '50%', background: '#E5483D', display: 'flex', alignItems: 'center', justifyContent: 'center' }, cross(34, '#fff'));
  const acc = box(sB, 244, 650, 84, 84, 'abs', { borderRadius: '50%', background: '#3CC47C', display: 'flex', alignItems: 'center', justifyContent: 'center' }, check(36, '#fff'));
  tl.to(acc, { scale: 0.86, duration: 0.08 }, T.D01 - 0.35);
  tl.to(acc, { scale: 1, duration: 0.25 }, T.D01 - 0.27);
  tl.to([dec, acc], { opacity: 0, y: 30, duration: 0.35, ease: 'power2.in' }, T.D01 - 0.2);
  tl.set(ctime, { textContent: '00:00' }, T.D01 - 0.3);
  const callStart = T.D01 - 0.3;
  const cst = { s: 0 };
  tl.to(cst, { s: 12, duration: 12, ease: 'none', onUpdate: () => { ctime.textContent = '00:' + String(Math.floor(cst.s)).padStart(2, '0'); } }, callStart);
  const end = box(sB, 70, 650, 258, 84, 'abs', { borderRadius: '999px', background: 'rgba(229,72,61,.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '22px', fontWeight: 600 }, 'End call');
  inn(end, T.D01, { y: 20, d: 0.4 });
  // transcript on the right, big and readable
  tl.to([r1, r2], { opacity: 0, y: -40, filter: 'blur(10px)', duration: 0.4, ease: 'power2.in' }, T.D01 - 0.5);
  const tr = box(cam, 860, 250, 960, 600, 'abs');
  const lineA = box(tr, 0, -30, 960, 'auto', 'abs', { fontSize: '40px', lineHeight: 1.3, fontWeight: 500 }, '<div class="mono" style="font-size:19px;color:var(--amber);letter-spacing:.14em;margin-bottom:10px">7EVEN5IVE · VOICE AGENT</div>"DBMS is at 73%. Attend the next three classes, and you\'re back at 75. Want a reminder before each one?"');
  const lineB = box(tr, 0, 240, 960, 'auto', 'abs', { fontSize: '46px', lineHeight: 1.3, fontWeight: 500, textAlign: 'right' }, '<div class="mono" style="font-size:19px;color:var(--mute);letter-spacing:.14em;margin-bottom:10px">YOU</div>"Yes."');
  const lineC = box(tr, 0, 410, 960, 'auto', 'abs', { fontSize: '40px', lineHeight: 1.3, fontWeight: 500 }, '<div class="mono" style="font-size:19px;color:var(--amber);letter-spacing:.14em;margin-bottom:10px">7EVEN5IVE · VOICE AGENT</div>"Done. And the campus drive form closes at six. The link is in your library."');
  inn(lineA, T.D01, { y: 30, d: 0.5 });
  inn(lineB, T.D02 - 0.05, { y: 30, d: 0.4 });
  inn(lineC, T.D03 - 0.05, { y: 30, d: 0.45 });
  const blk = box(sB, 40, 560, 318, 70, 'abs', { borderRadius: '18px', background: 'rgba(91,228,155,.12)', border: '1px solid rgba(91,228,155,.45)', display: 'flex', alignItems: 'center', gap: '12px', padding: '0 18px', fontSize: '20px', fontWeight: 600 }, `${check(24)}<span>Reminders on · next 3 DBMS</span>`);
  inn(blk, E.D03 - 0.2, { y: 20, d: 0.5, ease: 'back.out(1.5)' });
  // C: after the call, the morning briefing lock screen (L23)
  tl.set(sC, { opacity: 0 }, 0);

  // --- ElevenLabs Agents = just another MCP client ---
  const L21 = 'That voice runs on Eleven Labs Agents, connected to our M C P tools like any other A I, and held to the same rules.';
  const w21 = i => wordTime(L21, i, T.L21, E.L21 - T.L21);
  tl.to(tr, { x: -200, opacity: 0, filter: 'blur(12px)', duration: 0.4, ease: 'power4.in' }, T.L21 - 0.3);
  const dg = box(cam, 860, 230, 960, 620, 'abs');
  const ech = elevenChip(dg, 0, 40, 'ElevenLabs Agents');
  ech.style.fontSize = '34px';
  inn(ech, w21(3) - 0.1, { x: 60, y: 0, d: 0.55, ease: 'power4.out' });
  const dsv = svgLayer(dg, 960, 620);
  const pa = pathEl(dsv, 'M 200 150 L 200 300', { stroke: 'rgba(244,241,234,.35)', w: 2.5, dash: '6 8' });
  drawPath(pa, w21(9) - 0.1, 0.5);
  const mcpl = box(dg, 224, 200, 300, 40, 'abs mono', { fontSize: '20px', color: 'var(--mute)', letterSpacing: '.12em' }, 'MCP');
  inn(mcpl, w21(10), { y: 0, d: 0.4 });
  const gwc = box(dg, 0, 300, 'auto', 'auto', 'chip', { fontSize: '34px', borderColor: 'rgba(255,181,71,.7)', background: 'rgba(255,181,71,.08)' }, `<span class="mono" style="font-size:16px;color:var(--aws);letter-spacing:.12em">AWS</span>AgentCore Gateway`);
  inn(gwc, w21(10) + 0.2, { x: 60, y: 0, d: 0.55, ease: 'power4.out' });
  packet(dsv, pa, w21(12), 0.6);
  const same = box(dg, 0, 410, 900, 60, 'abs serif', { fontSize: '64px' }, 'Same tools. Same rules.');
  inn(same, w21(20) - 0.1, { y: 24, d: 0.55 });
  const mcp2 = box(dg, 0, 490, 900, 40, 'abs mono', { fontSize: '20px', color: 'var(--mute)', letterSpacing: '.1em' }, 'THE VOICE AGENT IS JUST ANOTHER MCP CLIENT');
  inn(mcp2, w21(20) + 0.3, { y: 10, d: 0.5 });
  tl.to(sB, { opacity: 0.0, duration: 0.4 }, E.D03 + 1.0);
  tl.to(sA, { opacity: 1, duration: 0.4 }, E.D03 + 1.0);
  tl.to(warn, { opacity: 0, duration: 0.3 }, E.D03 + 1.0);
  const cal2 = box(sA, 22, 170, 354, 92, 'abs', { borderRadius: '20px', background: 'rgba(91,228,155,.1)', border: '1px solid rgba(91,228,155,.4)', display: 'flex', alignItems: 'center', gap: '16px', padding: '0 20px' }, `<div style="text-align:center"><div class="mono" style="font-size:15px;color:var(--green)">NEXT</div><div style="font-size:30px;font-weight:650">3</div></div><div><div style="font-size:22px;font-weight:600">DBMS class reminders</div><div class="mono" style="font-size:16px;color:var(--mute)">15 min before · by voice</div></div>`);
  inn(cal2, E.D03 + 1.1, { y: -20, d: 0.5 });
  const opp = box(sA, 22, 276, 354, 92, 'abs', { borderRadius: '20px', background: 'rgba(255,181,71,.1)', border: '1px solid rgba(255,181,71,.45)', display: 'flex', alignItems: 'center', gap: '16px', padding: '0 20px' }, `<div style="text-align:center"><div class="mono" style="font-size:15px;color:var(--amber)">TODAY</div><div style="font-size:24px;font-weight:650">6 PM</div></div><div><div style="font-size:22px;font-weight:600">Campus drive form</div><div class="mono" style="font-size:16px;color:var(--mute)">link in your library</div></div>`);
  inn(opp, E.D03 + 1.3, { y: -20, d: 0.5 });

  // --- Scribe: voice notes become text ---
  const L22 = 'Voice notes from your class group? Eleven Labs Scribe turns them into text, in Kannada, Hindi or English.';
  const w22 = i => wordTime(L22, i, T.L22, E.L22 - T.L22);
  tl.to(dg, { x: -200, opacity: 0, filter: 'blur(12px)', duration: 0.4, ease: 'power4.in' }, T.L22 - 0.3);
  const sc = box(cam, 860, 220, 980, 640, 'abs');
  const vn = box(sc, 0, 30, 470, 96, 'abs', { borderRadius: '24px', background: 'rgba(255,255,255,.07)', display: 'flex', alignItems: 'center', gap: '10px', padding: '0 26px' });
  vn.innerHTML = '<svg width="34" height="34" viewBox="0 0 24 24"><path d="M7 4 L20 12 L7 20 Z" fill="#F4F1EA"/></svg>' + Array.from({ length: 22 }, (_, i) => `<i class="vb" style="display:block;width:6px;border-radius:3px;background:#F4F1EA;height:${10 + ((i * 41) % 36)}px"></i>`).join('') + '<span class="mono" style="font-size:20px;color:var(--mute);margin-left:8px">0:14</span>';
  inn(vn, T.L22 + 0.1, { x: 60, y: 0, d: 0.55, ease: 'power4.out' });
  const vbs = vn.querySelectorAll('.vb');
  tl.fromTo(vbs, { opacity: 0.35 }, { opacity: 1, duration: 0.12, stagger: 0.05, ease: 'none' }, T.L22 + 0.6);
  const ech2 = elevenChip(sc, 520, 42, 'ElevenLabs Scribe');
  inn(ech2, w22(6) - 0.1, { x: 40, y: 0, d: 0.5, ease: 'power4.out' });
  const out1 = box(sc, 0, 170, 980, 'auto', 'abs', { fontSize: '50px', fontWeight: 500, lineHeight: 1.25 });
  const outT = el('span', out1, '');
  const caret = el('span', out1, '', { color: 'var(--amber)', opacity: 0 }, '▍');
  const scribeTxt = '"DBMS lab moved to Thursday, 2 PM."';
  typeText(outT, scribeTxt, w22(8), 30);
  tl.set(caret, { opacity: 1 }, w22(8) - 0.05);
  tl.set(caret, { opacity: 0 }, w22(8) + scribeTxt.length / 30 + 0.5);
  const langs = [['ಕನ್ನಡ', 'NK', 14], ['हिन्दी', 'ND', 15], ['English', 'IT', 17]];
  langs.forEach(([n, f, wi], i) => {
    const lc = box(sc, i * 240, 330, 220, 86, 'abs', { borderRadius: '20px', border: '1px solid rgba(255,255,255,.14)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: `'${f}'`, fontSize: '36px', color: 'var(--mute)' }, n);
    inn(lc, w22(wi) - 0.15, { y: 20, d: 0.4 });
    tl.to(lc, { color: '#F4F1EA', borderColor: 'rgba(255,181,71,.6)', background: 'rgba(255,181,71,.08)', duration: 0.3 }, w22(wi) - 0.05);
  });
  box(sc, 0, 450, 900, 40, 'abs mono', { fontSize: '20px', color: 'var(--mute)', letterSpacing: '.1em', opacity: 0 }, '');

  // --- morning briefing ---
  tl.to(sc, { x: -200, opacity: 0, filter: 'blur(12px)', duration: 0.4, ease: 'power4.in' }, T.L23 - 0.3);
  tl.to(sA, { opacity: 0, duration: 0.3 }, T.L23 + 0.1);
  tl.to(sC, { opacity: 1, duration: 0.35 }, T.L23 + 0.1);
  box(sC, 0, 0, '100%', '100%', 'abs', { background: 'linear-gradient(180deg,#1b1408,#0b0c10 70%)' });
  box(sC, 0, 120, 398, 40, 'abs', { textAlign: 'center', fontSize: '22px', color: 'var(--mute)' }, 'Friday, 28 November');
  box(sC, 0, 150, 398, 130, 'abs', { textAlign: 'center', fontSize: '120px', fontWeight: 600, letterSpacing: '-0.04em' }, '7:00');
  const brief = box(sC, 22, 330, 354, 262, 'abs', { borderRadius: '26px', background: 'rgba(255,255,255,.09)', padding: '22px' });
  brief.innerHTML = `<div style="display:flex;align-items:center;gap:12px"><div style="width:30px;height:30px;position:relative" class="bi"></div><b style="font-size:22px">Morning briefing</b><span class="mono" style="margin-left:auto;font-size:15px;color:var(--mute)">now</span></div>
   <div style="font-size:21px;color:rgba(244,241,234,.8);margin-top:12px;line-height:1.4">2 classes · DBMS at 73%<br><span style="color:var(--amber)">Campus drive form closes 6 PM</span></div>
   <div style="display:flex;align-items:center;gap:14px;margin-top:18px"><span style="width:52px;height:52px;border-radius:50%;background:var(--amber);display:flex;align-items:center;justify-content:center"><svg width="22" height="22" viewBox="0 0 24 24"><path d="M7 4 L20 12 L7 20 Z" fill="#1a1205"/></svg></span><i style="flex:1;height:6px;border-radius:3px;background:rgba(255,255,255,.12);position:relative;display:block"><b class="prog" style="position:absolute;left:0;top:0;height:6px;border-radius:3px;background:var(--amber);width:100%;transform-origin:0 50%;transform:scaleX(0)"></b></i><span class="mono" style="font-size:16px;color:var(--mute)">0:42</span></div>`;
  const bi = ring(brief.querySelector('.bi'), 15, 15, 30, 5, { glow: 2, trackOp: 0 }); bi.arcs.forEach(a => a.setAttribute('stroke-dashoffset', bi.C * 0.25));
  inn(brief, T.L23 + 0.35, { y: -30, d: 0.55, ease: 'back.out(1.4)' });
  tl.fromTo(brief.querySelector('.prog'), { scaleX: 0 }, { scaleX: 0.35, duration: C.safety - T.L23 - 0.6, ease: 'none' }, T.L23 + 0.8);
  const mb = words(cam, 'A briefing you can listen to.', 'abs serif', { left: '860px', top: '380px', fontSize: '92px', whiteSpace: 'nowrap' });
  spoken(mb, T.L23 + 0.1, E.L23 - T.L23, { y: 30, d: 0.5 });
  const tts = elevenChip(cam, 866, 540, 'ElevenLabs text-to-speech');
  inn(tts, T.L23 + 1.0, { x: 40, y: 0, d: 0.5, ease: 'power4.out' });
  window.ORB = orb;
})();
