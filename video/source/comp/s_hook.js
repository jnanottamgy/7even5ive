// Scenes 1-3: HOOK (75%), PROBLEM (five apps), REVEAL (logo)
function center(n) { gsap.set(n, { xPercent: -50, yPercent: -50 }); return n; }
function bellSlash(size = 26, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="vertical-align:-5px"><path d="M6 17 V11 a6 6 0 0 1 10.5 -4 M18 11 V17 H8.5 M10 20 a2 2 0 0 0 4 0" fill="none" stroke="${color}" stroke-width="1.9" stroke-linecap="round"/><path d="M4 4 L20 20" stroke="${color}" stroke-width="1.9" stroke-linecap="round"/></svg>`;
}

// =============================== 1. HOOK =================================
(function hook() {
  const S = scene('hook'), cam = S.cam;
  on('hook', 0);
  tl.fromTo(cam, { scale: 1 }, { scale: 1.07, duration: C.problem, ease: 'power1.inOut' }, 0);
  lights(0.2, [960, 470, 0.85], [1700, 980, 0.35], [200, 120, 0.25], 3);

  const grp = box(cam, 0, 0, 1920, 1080, 'abs');
  const rg = ring(grp, 960, 470, 470, 18, { glow: 16 });
  tl.fromTo(rg.w, { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 1.8, ease: 'power2.out' }, 0.25);

  // the 75% line on the ring (9 o'clock) and its label
  const notch = box(grp, 960 - 226 - 30, 468, 60, 4, 'abs', { background: 'var(--ink)', borderRadius: '2px', opacity: 0 });
  const nlab = box(grp, 960 - 226 - 330, 454, 280, 40, 'abs mono', { fontSize: '20px', color: 'var(--mute)', textAlign: 'right', letterSpacing: '.1em', whiteSpace: 'nowrap' }, 'THE LINE · 75%');
  inn(notch, T.L01 + 1.0, { y: 0, x: -10, d: 0.5 });
  inn(nlab, T.L01 + 1.15, { y: 0, x: -14, d: 0.5 });

  // odometer number
  const num = box(grp, 960, 452, 'auto', 'auto', 'abs', { display: 'flex', alignItems: 'flex-start', fontSize: '200px', fontWeight: 650, letterSpacing: '-0.05em', lineHeight: '1' });
  center(num);
  const d7 = el('span', num, 'w', null, '7');
  const col = el('span', num, '', { display: 'inline-block', height: '200px', overflow: 'hidden' });
  const stack = el('span', col, '', { display: 'flex', flexDirection: 'column' }, '<span>5</span><span>4</span><span>3</span>');
  const pct = el('span', num, 'w', { fontSize: '96px', marginTop: '22px', marginLeft: '8px', color: 'var(--mute)', fontWeight: 500 }, '%');
  tl.fromTo([d7, col, pct], { yPercent: 70, opacity: 0, filter: 'blur(14px)' }, { yPercent: 0, opacity: 1, filter: 'blur(0px)', duration: 0.8, stagger: 0.07, ease: 'power3.out' }, T.L01 - 0.05);
  const sub = box(grp, 960, 588, 'auto', 'auto', 'abs mono', { fontSize: '20px', letterSpacing: '.22em', color: 'var(--mute)' }, 'ATTENDANCE');
  center(sub);
  inn(sub, T.L01 + 0.6, { y: 10, d: 0.5 });
  arcTo(rg, 0.75, T.L01 - 0.1, 1.3, 'power3.out');

  // the slide below the line: 75 -> 74 -> 73, amber turns red
  const chip = box(grp, 960, 780, 'auto', 'auto', 'abs mono', { fontSize: '24px', letterSpacing: '.12em', color: 'var(--mute)', padding: '14px 26px', borderRadius: '14px', border: '1px solid rgba(244,241,234,.14)' }, 'MINIMUM TO SIT YOUR EXAMS');
  center(chip);
  inn(chip, T.L02 + 0.3, { y: 12, d: 0.6 });
  [0, 1].forEach(k => {
    const t = T.L03 + 0.6 + k * 0.55;
    tl.to(stack, { y: -200 * (k + 1), duration: 0.32, ease: 'power3.inOut' }, t);
    arcTo(rg, 0.75 - 0.01 * (k + 1), t, 0.32, 'power3.inOut');
  });
  const red = T.L03 + 1.72;
  arcColor(rg, '#FF8B7E', '#FF3B2F', red, 0.35);
  tl.to([d7, col], { color: 'var(--red)', duration: 0.35 }, red);
  tl.to(chip, { color: '#FF7A6E', borderColor: 'rgba(255,90,78,.55)', background: 'rgba(255,90,78,.08)', duration: 0.3 }, red);
  tl.set(chip, { textContent: '73% · BARRED FROM EXAMS' }, red + 0.06);
  [0.0, 0.05, 0.1, 0.15, 0.2].forEach((dt, i) => tl.set(grp, { x: [0, -9, 7, -4, 0][i], filter: i % 2 ? 'hue-rotate(40deg)' : 'none' }, red + dt));
  tl.set(grp, { filter: 'none' }, red + 0.26);

  // "And nobody warns you."
  tl.to(grp, { y: -120, scale: 0.78, opacity: 0.22, duration: 0.9, ease: 'power3.inOut' }, T.L04 - 0.35);
  const line = words(cam, 'And nobody warns you.', 'abs serif', { left: '960px', top: '720px', fontSize: '112px', whiteSpace: 'nowrap', letterSpacing: '-0.01em' });
  center(line);
  spoken(line, T.L04 - 0.05, D_(T.L04), { y: 30, blur: 14, d: 0.55 });
  const pill = box(cam, 960, 868, 'auto', 'auto', 'abs', { display: 'flex', alignItems: 'center', gap: '14px', padding: '16px 30px', borderRadius: '999px', background: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.1)', fontSize: '28px', color: 'var(--mute)' }, `${bellSlash(28, '#8D919B')}<span>No notifications</span>`);
  center(pill);
  inn(pill, E.L04 + 0.7, { y: 16, d: 0.7 });
  // anticipation before the drop: the frame leans into the current
  tl.to(cam, { x: -40, duration: 1.2, ease: 'power2.in' }, C.problem - 1.2);
})();
function D_(t) { for (const k in T) if (Math.abs(T[k] - t) < 1e-6) return E[k] - T[k]; return 1; }

// =============================== 2. PROBLEM ==============================
(function problem() {
  const S = scene('problem'), cam = S.cam;
  seamLeft('hook', 'problem', C.problem);
  lights(C.problem, [600, 300, 0.7], [1500, 850, 0.55], [1200, 150, 0.35], 1.2);
  tl.to(GRID, { opacity: 0.35, duration: 1.2 }, C.problem);

  const head = (card, title, right) => {
    const h = box(card, 0, 0, '100%', 64, 'abs', { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 26px', borderBottom: '1px solid rgba(255,255,255,.07)' });
    h.innerHTML = `<span style="font-size:24px;font-weight:600">${title}</span><span>${right || ''}</span>`;
    return h;
  };
  // portal
  const portal = box(cam, 110, 150, 500, 340, 'card');
  head(portal, 'Student Portal', `<span class="mono" style="font-size:17px;color:#FF8B7E;letter-spacing:.1em">${bellSlash(20, '#FF8B7E')} NO ALERTS</span>`);
  [['DBMS', 73, true], ['Operating Systems', 81], ['Computer Networks', 76], ['MCIOT', 79]].forEach(([s, v, bad], i) => {
    const r = box(portal, 26, 88 + i * 60, 448, 46, 'abs', { display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '24px' });
    r.innerHTML = `<span style="color:${bad ? 'var(--ink)' : 'var(--mute)'}">${s}</span><span style="display:flex;align-items:center;gap:14px"><i style="display:block;width:120px;height:6px;border-radius:3px;background:rgba(255,255,255,.08);position:relative"><b style="position:absolute;left:0;top:0;height:6px;border-radius:3px;width:${v * 1.2}px;background:${bad ? 'var(--red)' : 'rgba(244,241,234,.45)'}"></b></i><span class="mono" style="color:${bad ? 'var(--red)' : 'var(--mute)'}">${v}%</span></span>`;
  });
  // classroom: assignments in one more app to check
  const gm = box(cam, 670, 110, 560, 330, 'card');
  head(gm, 'Classroom', '<span class="mono" style="font-size:17px;color:var(--mute)">1 due</span>');
  box(gm, 26, 96, 500, 200, 'abs', { fontSize: '26px', lineHeight: 1.6 }, '<div style="font-weight:600">DBMS · Assignment 3</div><div style="color:var(--mute)">Due Fri, 11:59 PM</div><div class="mono" style="font-size:17px;color:var(--dim);margin-top:8px">NOT ON YOUR CALENDAR</div>');
  // class group chat
  const ch = box(cam, 1290, 150, 520, 650, 'card', { overflow: 'hidden' });
  head(ch, 'CSE 3B · Class group', '<span class="mono memec" style="font-size:18px;color:var(--mute)">12 unread</span>');
  const memec = ch.querySelector('.memec');
  const chClip = box(ch, 0, 64, 520, 586, 'abs', { overflow: 'hidden' });
  const feed = box(chClip, 0, 0, 520, 2400, 'abs');
  const msgs = ['bro what is the DBMS deadline', 'LOL', 'ok', 'anyone has OS notes??', 'haha', 'STICKER', 'who took my charger', 'ok', 'LOL', 'STICKER', 'canteen?', 'haha', 'bro', 'STICKER', 'ok ok', 'LOL', 'STICKER', 'lmao', 'ok'];
  let y = 18;
  msgs.forEach((m, i) => {
    const mine = i % 3 === 1;
    if (m === 'STICKER') {
      const st = box(feed, mine ? 300 : 30, y, 150, 120, 'abs', { borderRadius: '26px', background: ['#3A2F5B', '#2F4A3A', '#5B3A2F'][i % 3], display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '40px', fontWeight: 700, color: 'rgba(255,255,255,.75)' }, ['LOL', 'XD', 'bruh'][i % 3]);
      y += 136;
    } else {
      const b = box(feed, mine ? 'auto' : 26, y, 'auto', 'auto', 'abs', { right: mine ? '26px' : 'auto', maxWidth: '380px', padding: '12px 18px', borderRadius: '18px', background: mine ? 'rgba(91,228,155,.14)' : 'rgba(255,255,255,.07)', fontSize: '22px', color: 'var(--ink)' }, m);
      y += 66;
    }
  });
  // the teacher's notes, three weeks ago, never downloaded
  const vn = box(feed, 26, y + 4, 420, 'auto', 'abs', { borderRadius: '18px', background: 'rgba(255,255,255,.07)', padding: '10px 16px 12px' });
  vn.innerHTML = '<div style="font-size:16px;font-weight:600;color:#9FE6C0;margin-bottom:6px">Prof. Rao · DBMS</div><div style="display:flex;align-items:center;gap:12px"><i style="display:flex;align-items:center;justify-content:center;flex:none;width:44px;height:52px;border-radius:8px;background:rgba(255,90,78,.16);color:#FF8B7E;font:600 12px JB;font-style:normal">PDF</i><div><div class="vnn" style="font-size:21px;font-weight:500">DBMS_Unit3_notes.pdf</div><div class="mono" style="font-size:13px;color:var(--mute);margin-top:3px">2.4 MB · 3 WEEKS AGO</div></div><svg class="dl" width="34" height="34" viewBox="0 0 24 24" style="margin-left:auto;flex:none"><circle cx="12" cy="12" r="10" fill="none" stroke="#8D919B" stroke-width="1.6"/><path d="M12 7 V15 M8.5 11.5 L12 15 L15.5 11.5" fill="none" stroke="#8D919B" stroke-width="1.6" stroke-linecap="round"/></svg></div>';
  const vnl = box(feed, 30, y + 116, 460, 30, 'abs mono', { fontSize: '16px', color: '#FF8B7E', letterSpacing: '.08em' }, 'NOT DOWNLOADED');
  const feedEnd = y + 160;
  // college mail: placement drives land where nobody looks
  const cr = box(cam, 330, 560, 620, 300, 'card');
  head(cr, 'College mail', '<span class="mono" style="font-size:17px;color:#FF8B7E">1,284 unread</span>');
  box(cr, 26, 96, 560, 170, 'abs', { fontSize: '26px', lineHeight: 1.6 }, '<div style="font-weight:600">T&amp;P Cell · Campus drive</div><div style="color:var(--mute)">Registration closes 6 PM</div><div class="mono" style="font-size:17px;color:var(--dim);margin-top:6px">UNREAD · YESTERDAY</div>');
  const cards = [portal, gm, ch, cr];
  tl.fromTo(cards, { x: 420, opacity: 0, filter: 'blur(16px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.75, stagger: 0.07, ease: 'power4.out' }, C.problem);

  // camera visits each problem, the rest falls back
  const focus = (t, cx, cy, s, keep) => {
    tl.to(cam, { scale: s, x: -s * (cx - 960), y: -s * (cy - 540), duration: 1.0, ease: 'power3.inOut' }, t);
    cards.forEach(c => tl.to(c, { opacity: keep.includes(c) ? 1 : 0.22, duration: 0.6 }, t));
  };
  focus(T.L05 - 0.25, 360, 320, 1.5, [portal]);
  tl.fromTo(portal.querySelectorAll('.mono')[0], { opacity: 0.2 }, { opacity: 1, duration: 0.3, repeat: 3, yoyo: true, ease: 'none' }, T.L05 + 1.6);
  focus(T.L06 - 0.25, 1550, 475, 1.32, [ch]);
  const scrollD = T.L07 + 0.4 - (T.L06 + 0.1);
  tl.to(feed, { y: -(feedEnd - 586), duration: scrollD, ease: 'power2.inOut' }, T.L06 + 0.1);
  count(memec, 12, 642, T.L06 + 0.1, scrollD, v => Math.round(v) + ' unread');
  const L07t = "Teachers send notes there too. You forget to download them, and they're lost.";
  const w07 = i => wordTime(L07t, i, T.L07, E.L07 - T.L07);
  focus(T.L07 + 0.1, 1550, 640, 1.6, [ch]);
  tl.fromTo(vnl, { opacity: 0 }, { opacity: 1, duration: 0.3 }, w07(6));
  tl.to(vn, { opacity: 0.45, duration: 0.4 }, w07(11));
  tl.set(vnl, { innerHTML: 'THIS MEDIA IS NO LONGER AVAILABLE' }, w07(11));
  tl.to(vn.querySelector('.vnn'), { textDecoration: 'line-through', duration: 0.01 }, w07(11));
  // ---------- the night before an exam: you message friends, nobody replies (L07a, L07b) ----------
  const L07b = 'You message your friends for the notes, the syllabus, the timetable, the circulars. The ones who have them are busy studying. Nobody replies.';
  const L07d = 'And placement mails go to a college inbox nobody checks. The drive registration closed at six.';
  const wb = i => wordTime(L07b, i, T.L07b, E.L07b - T.L07b);
  const wd = i => wordTime(L07d, i, T.L07d, E.L07d - T.L07d);
  const zt = T.L07a - 0.45;
  tl.to(cam, { scale: 3.2, x: -3.2 * (1550 - 960), y: -3.2 * (640 - 540), opacity: 0, filter: 'blur(16px)', duration: 0.45, ease: 'power4.in' }, zt);
  const hunt = box(S.seam, 0, 0, 1920, 1080, 'abs');
  tl.set(hunt, { opacity: 0 }, 0);
  tl.fromTo(hunt, { opacity: 0, scale: 0.72, filter: 'blur(14px)' }, { opacity: 1, scale: 1, filter: 'blur(0px)', duration: 0.6, ease: 'power4.out', immediateRender: false }, zt + 0.45);
  const h1 = words(hunt, 'The night before', 'abs serif', { left: '120px', top: '300px', fontSize: '100px', whiteSpace: 'nowrap' });
  const h2 = words(hunt, 'an exam.', 'abs serif', { left: '120px', top: '416px', fontSize: '100px', whiteSpace: 'nowrap', color: 'var(--amber)' });
  spoken(h1, T.L07a + 0.1, 1.0, { y: 30, d: 0.5 });
  spoken(h2, T.L07a + 0.7, 0.7, { y: 30, d: 0.5 });
  const clock = box(hunt, 126, 560, 640, 40, 'abs mono', { fontSize: '22px', color: 'var(--mute)', letterSpacing: '.14em' }, '11:48 PM · EXAM AT 9:30 AM');
  inn(clock, T.L07a + 1.3, { y: 10, d: 0.5 });
  tl.to([h1, h2, clock], { y: -60, opacity: 0, filter: 'blur(10px)', duration: 0.4, ease: 'power3.in' }, T.L07b - 0.3);
  // the chat list: everyone you asked
  const chat = box(hunt, 880, 70, 920, 890, 'card', { overflow: 'hidden', background: 'rgba(12,14,18,.94)' });
  const chH = box(chat, 0, 0, 920, 96, 'abs', { display: 'flex', alignItems: 'center', gap: '18px', padding: '0 28px', borderBottom: '1px solid rgba(255,255,255,.07)', background: 'rgba(255,255,255,.03)' });
  chH.innerHTML = '<div style="font-size:30px;font-weight:650">Chats</div><span class="mono rep" style="margin-left:auto;font-size:18px;padding:7px 14px;border-radius:999px;background:rgba(255,255,255,.06);color:var(--mute)">0 replies</span>';
  const NC = { Rahul: '#3B4A63', Priya: '#4A3B63', Arjun: '#5B4A2F', Sneha: '#2F4F3F', Kiran: '#4F2F3A' };
  const ticks = '<svg width="24" height="16" viewBox="0 0 24 16" style="flex:none"><path d="M1 8.5 L5 12.5 L12 3.5 M9 11 L10.5 12.5 L17.5 3.5" fill="none" stroke="#6FB7FF" stroke-width="1.8" stroke-linecap="round"/></svg>';
  const DM = [['Rahul', 'bro send the DBMS unit 3 notes pls', '11:41 PM', 3], ['Priya', 'do you have the syllabus?', '11:42 PM', 6], ['Arjun', 'IA-2 timetable??', '11:44 PM', 8], ['Sneha', 'the lab circular pls', '11:45 PM', 10], ['Kiran', 'anyone has the notes?', '11:47 PM', 12]];
  const dmEls = DM.map(([who, txt, tm, wi], i) => {
    const r = box(chat, 0, 96 + i * 132, 920, 132, 'abs', { display: 'flex', alignItems: 'center', gap: '22px', padding: '0 28px', borderBottom: '1px solid rgba(255,255,255,.05)' });
    r.innerHTML = `<i style="display:flex;align-items:center;justify-content:center;flex:none;width:72px;height:72px;border-radius:50%;background:${NC[who]};font-style:normal;font-size:30px;font-weight:600;color:rgba(244,241,234,.8)">${who[0]}</i><div style="flex:1;min-width:0"><div style="display:flex;justify-content:space-between"><b style="font-size:27px;font-weight:600">${who}</b><span class="mono" style="font-size:16px;color:var(--dim)">${tm}</span></div><div style="display:flex;align-items:center;gap:10px;margin-top:6px;font-size:23px;color:var(--mute)">${ticks}<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${txt}</span></div><div class="mono st" style="font-size:15px;color:var(--dim);margin-top:6px;letter-spacing:.06em">DELIVERED</div></div>`;
    inn(r, wb(wi) - 0.1, { x: 40, y: 0, d: 0.4, ease: 'power4.out' });
    tl.set(r.querySelector('.st'), { innerHTML: 'SEEN · ONLINE · STUDYING', color: '#7BE3A0' }, wb(17) + i * 0.12);
    tl.set(r.querySelector('.st'), { innerHTML: 'SEEN · NO REPLY', color: '#FF8B7E' }, wb(21) + i * 0.08);
    return r;
  });
  // what you actually needed, tallied on the left
  const NEED = [['Notes', 6], ['Syllabus', 8], ['Timetable', 10], ['Circulars', 12]];
  const needEls = NEED.map(([t, wi], i) => {
    const f = box(hunt, 120, 280 + i * 100, 700, 80, 'abs', { display: 'flex', alignItems: 'center', gap: '22px', fontSize: '46px', fontWeight: 600, letterSpacing: '-0.02em' }, `<span class="ic" style="display:flex;flex:none;width:54px;height:54px;border-radius:50%;border:2px solid rgba(255,255,255,.25);align-items:center;justify-content:center"></span>${t}<span class="mono nr" style="margin-left:6px;font-size:18px;letter-spacing:.1em;color:var(--dim)">WAITING…</span>`);
    inn(f, wb(wi), { x: -30, y: 0, d: 0.45, ease: 'power4.out' });
    tl.set(f.querySelector('.ic'), { innerHTML: cross(26), borderColor: '#FF5A4E' }, wb(21) + i * 0.1);
    tl.set(f.querySelector('.nr'), { innerHTML: 'NO REPLY', color: '#FF8B7E' }, wb(21) + i * 0.1);
    return f;
  });

  // ---------- the placement mail nobody opened (L07d) ----------
  tl.to(hunt, { x: -300, filter: 'blur(18px)', opacity: 0, duration: 0.36, ease: 'power4.in' }, T.L07d - 0.45);
  const ml = box(S.seam, 0, 0, 1920, 1080, 'abs');
  tl.set(ml, { opacity: 0 }, 0);
  tl.fromTo(ml, { x: 380, opacity: 1, filter: 'blur(18px)' }, { x: 0, filter: 'blur(0px)', duration: 0.56, ease: 'power4.out', immediateRender: false }, T.L07d - 0.09);
  const m1 = words(ml, 'Placement mail', 'abs serif', { left: '120px', top: '300px', fontSize: '96px', whiteSpace: 'nowrap' });
  const m2 = words(ml, 'nobody opens.', 'abs serif', { left: '120px', top: '412px', fontSize: '96px', whiteSpace: 'nowrap', color: 'var(--amber)' });
  spoken(m1, wd(1) - 0.1, 0.9, { y: 30, d: 0.5 });
  spoken(m2, wd(7), 0.9, { y: 30, d: 0.5 });
  const mid = box(ml, 126, 548, 700, 40, 'abs mono', { fontSize: '21px', color: 'var(--mute)', letterSpacing: '.12em' }, '21CS045@COLLEGE.EDU.IN');
  inn(mid, wd(6), { y: 10, d: 0.5 });
  const ib = box(ml, 880, 70, 920, 890, 'card', { overflow: 'hidden', background: 'rgba(12,14,18,.94)' });
  const ibH = box(ib, 0, 0, 920, 96, 'abs', { display: 'flex', alignItems: 'center', gap: '18px', padding: '0 28px', borderBottom: '1px solid rgba(255,255,255,.07)', background: 'rgba(255,255,255,.03)' });
  ibH.innerHTML = '<svg width="40" height="40" viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="14" rx="2.5" fill="none" stroke="#F4F1EA" stroke-width="1.6"/><path d="M3.5 6.5 L12 13 L20.5 6.5" fill="none" stroke="#F4F1EA" stroke-width="1.6"/></svg><div style="font-size:28px;font-weight:600">College mail · Inbox</div><span class="mono iu" style="margin-left:auto;font-size:18px;padding:7px 14px;border-radius:999px;background:rgba(255,90,78,.14);color:#FF8B7E">1,284 unread</span>';
  const ibody = box(ib, 0, 96, 920, 794, 'abs', { overflow: 'hidden' });
  const NEWN = 8, RH = 90;
  const ilist = box(ibody, 0, -NEWN * RH, 920, 2400, 'abs');
  const mailRow = (y, who, subj, time, hot) => {
    const r = box(ilist, 20, y, 880, RH - 10, 'abs', { display: 'flex', alignItems: 'center', gap: '18px', padding: '0 18px', borderRadius: '12px', background: hot ? 'rgba(255,181,71,.10)' : 'none', border: hot ? '1px solid rgba(255,181,71,.5)' : '1px solid transparent', fontSize: '23px' });
    r.innerHTML = `<b style="flex:none;width:190px;font-weight:600;color:${hot ? 'var(--amber)' : 'var(--ink)'}">${who}</b><span style="color:${hot ? 'var(--ink)' : 'var(--mute)'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${subj}</span><span class="mono" style="margin-left:auto;flex:none;font-size:15px;color:var(--dim)">${time}</span>`;
    return r;
  };
  [['Library', 'Book due back Friday', '7:10 PM'], ['Exam Cell', 'Revised seating plan', '6:58 PM'], ['Fest Committee', 'Volunteers meet at 5', '6:41 PM'], ['Webinar', 'Free AI webinar this Sunday', '6:30 PM'], ['Hostel Office', 'Water supply timings', '6:12 PM'], ['Newsletter', 'Campus digest · Week 47', '6:05 PM'], ['Sports Club', 'Cricket trials', '6:02 PM'], ['IT Services', 'Password expiry notice', '6:01 PM']]
    .forEach(([a, b, c], i) => mailRow(i * RH, a, b, c));
  [['Library', 'Overdue book reminder', '9:02 AM'], ['Student Welfare', 'Fest volunteers needed', '8:47 AM'], ['T&amp;P Cell', 'Campus drive · Registration closes today 6 PM', '8:15 AM', 1], ['Webinar', 'Resume workshop recording', 'Yesterday'], ['Fee Section', 'Last date for fee payment', 'Mon'], ['Newsletter', 'Campus digest · Week 46', 'Mon'], ['Sports Club', 'Inter-department cricket', 'Sun'], ['IT Services', 'Wi-Fi maintenance', 'Sun'], ['Library', 'New arrivals', 'Sat']]
    .forEach(([a, b, c, hot], i) => mailRow(NEWN * RH + i * RH, a, b, c, hot));
  tl.to(ilist, { y: NEWN * RH, duration: wd(12) - wd(5), ease: 'power1.inOut' }, wd(5));
  count(ibH.querySelector('.iu'), 1284, 1292, wd(5), wd(12) - wd(5), v => v.toLocaleString('en-IN') + ' unread');
  const t601 = box(ml, 126, 640, 600, 120, 'abs', { fontSize: '96px', fontWeight: 650, letterSpacing: '-0.04em', color: 'var(--red)' }, '6:01 PM');
  inn(t601, wd(13) - 0.15, { y: 20, d: 0.4, ease: 'power4.out' });
  const closed = box(ml, 990, 330, 700, 300, 'card', { background: 'rgba(16,17,22,.98)', borderColor: 'rgba(255,90,78,.55)', padding: '0', overflow: 'hidden', zIndex: 8 });
  closed.innerHTML = '<div style="height:10px;background:var(--red)"></div><div style="padding:30px 36px"><div style="font-size:32px;font-weight:650">Campus Drive 2026 · Registration</div><div style="font-size:26px;color:rgba(244,241,234,.8);margin-top:18px;line-height:1.4">This form is no longer accepting responses.</div><div class="mono" style="font-size:17px;color:#FF8B7E;letter-spacing:.12em;margin-top:22px">CLOSED AT 6:00 PM</div></div>';
  inn(closed, wd(13) + 0.1, { y: 0, scale: 1.12, d: 0.4, ease: 'power4.out' });
  // pull back: the mail shrinks into its card in the montage (arrival)
  tl.to(ml, { scale: 0.32, x: 640 - 960, y: 710 - 540, opacity: 0, filter: 'blur(6px)', duration: 0.6, ease: 'power3.inOut' }, T.L08 - 0.5);
  tl.to(cam, { opacity: 1, filter: 'blur(0px)', duration: 0.35 }, T.L08 - 0.45);

  // pull back: try to connect them, every link breaks
  focus(T.L08 - 0.45, 960, 520, 0.96, cards);
  const sv = svgLayer(cam);
  const centers = [[360, 320], [950, 275], [1550, 475], [640, 710]];
  const links = [];
  for (let i = 0; i < 4; i++) {
    const a = centers[i], b = centers[(i + 1) % 4];
    const pp = pathEl(sv, `M${a[0]} ${a[1]} L${b[0]} ${b[1]}`, { stroke: 'rgba(255,181,71,.7)', w: 3 });
    links.push(pp);
    drawPath(pp, T.L08 + 0.05 + i * 0.07, 0.45);
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const x = box(cam, mx - 22, my - 22, 44, 44, 'abs', { borderRadius: '50%', background: '#1a0d0c', border: '2px solid var(--red)', display: 'flex', alignItems: 'center', justifyContent: 'center' }, cross(24));
    inn(x, T.L08 + 0.85 + i * 0.05, { y: 0, scale: 0.4, d: 0.35, ease: 'back.out(1.7)' });
    tl.to(pp.p, { attr: { stroke: 'rgba(255,90,78,.6)' }, duration: 0.2 }, T.L08 + 0.85 + i * 0.05);
  }
  const big = box(cam, 960, 540, 'auto', 'auto', 'abs', { textAlign: 'center', fontWeight: 650, fontSize: '128px', letterSpacing: '-0.045em', lineHeight: 1.02, textShadow: '0 20px 60px rgba(0,0,0,.8)' }, '<div class="w">4 apps.</div><div class="w"><span style="color:var(--red)">0</span> connection.</div>');
  center(big);
  cards.forEach(c => tl.to(c, { opacity: 0.16, duration: 0.5 }, T.L08 + 0.25));
  tl.to(sv, { opacity: 0.35, duration: 0.5 }, T.L08 + 0.25);
  tl.fromTo(big.children, { yPercent: 60, opacity: 0, filter: 'blur(14px)' }, { yPercent: 0, opacity: 1, filter: 'blur(0px)', duration: 0.6, stagger: 0.55, ease: 'power3.out' }, T.L08 + 0.1);
})();

// =============================== 2b. THE TRACK ===========================
(function track() {
  const S = scene('track'), cam = S.cam;
  seamLeft('problem', 'track', C.track);
  lights(C.track, [960, 500, 0.55], [1600, 900, 0.25], [300, 180, 0.25], 0.8);
  const L08b = 'Track one. Make M C P Matter. Less magic, more utility.';
  const w = i => wordTime(L08b, i, T.L08b, E.L08b - T.L08b);
  const k1 = box(cam, 960, 330, 'auto', 'auto', 'abs mono', { fontSize: '24px', letterSpacing: '.22em', color: 'var(--mute)', whiteSpace: 'nowrap' }, 'WHACKIEST 2026 · TRACK 1');
  center(k1);
  inn(k1, T.L08b - 0.1, { y: 14, d: 0.45 });
  const k2 = words(cam, 'Make MCP Matter', 'abs', { left: '960px', top: '470px', fontSize: '150px', fontWeight: 700, letterSpacing: '-0.045em', whiteSpace: 'nowrap' });
  center(k2);
  spoken(k2, w(2) - 0.05, 0.9, { y: 30, d: 0.5 });
  const k3 = words(cam, 'Less magic, more utility.', 'abs serif', { left: '960px', top: '612px', fontSize: '86px', whiteSpace: 'nowrap', color: 'var(--amber)' });
  center(k3);
  spoken(k3, w(6) - 0.05, E.L08b - w(6), { y: 24, d: 0.5 });
  const k4 = box(cam, 960, 724, 'auto', 'auto', 'abs', { fontSize: '27px', color: 'rgba(244,241,234,.72)', whiteSpace: 'nowrap' }, 'MCP-powered agents a regular person uses every day: useful, reliable, controlled.');
  center(k4);
  inn(k4, w(6) + 0.4, { y: 12, d: 0.5 });
  // everything collapses into one point (arrival of the brand)
  tl.to(S.seam, { scale: 0.02, filter: 'blur(6px)', duration: 0.5, ease: 'power4.in' }, C.reveal - 0.5);
  tl.to(GRID, { opacity: 0, duration: 0.5 }, C.reveal - 0.5);
  off('track', C.reveal);
})();

// =============================== 3. REVEAL ===============================
(function reveal() {
  const S = scene('reveal'), cam = S.cam;
  on('reveal', C.reveal);
  const I = C.reveal_impact;
  lights(C.reveal, [960, 540, 0.0], [1600, 900, 0.0], [300, 200, 0.0], 0.6);
  const dot = box(cam, 960 - 9, 540 - 9, 18, 18, 'abs', { borderRadius: '50%', background: 'var(--amber)', boxShadow: '0 0 30px 8px rgba(255,181,71,.55)' });
  tl.fromTo(dot, { scale: 2.4 }, { scale: 1, duration: 0.5, ease: 'power4.out' }, C.reveal);
  tl.to(dot, { boxShadow: '0 0 90px 34px rgba(255,181,71,.55)', duration: I - C.reveal - 0.05, ease: 'power2.in' }, C.reveal + 0.3);
  tl.set(dot, { opacity: 0 }, I);

  // impact: the point becomes the 75% ring — the number you feared becomes the brand
  const RING = 300;
  const holder = box(cam, 0, 0, 1920, 1080, 'abs');
  const rg = ring(holder, 960, 540, RING, 40, { glow: 22, glowOp: 0.7, trackOp: 0.0 });
  tl.set(rg.w, { opacity: 0 }, 0);
  tl.set(rg.w, { opacity: 1 }, I);
  arcTo(rg, 0.75, I, 0.55, 'power4.out');
  const FL = document.getElementById('flash');
  tl.fromTo(FL, { opacity: 0 }, { opacity: 0.9, duration: 0.06, ease: 'none' }, I);
  tl.to(FL, { opacity: 0, duration: 0.9, ease: 'power2.out' }, I + 0.06);
  tl.fromTo(cam, { scale: 1.07 }, { scale: 1, duration: 1.0, ease: 'power3.out' }, I);
  lights(I, [960, 540, 1], [1650, 950, 0.45], [250, 150, 0.4], 0.8);
  // light streaks
  const sv = svgLayer(cam);
  for (let k = 0; k < 18; k++) {
    const a = (k / 18) * Math.PI * 2 + 0.17;
    const r0 = 170, r1 = 520 + (k % 3) * 120;
    const pp = pathEl(sv, `M${960 + Math.cos(a) * r0} ${540 + Math.sin(a) * r0} L${960 + Math.cos(a) * r1} ${540 + Math.sin(a) * r1}`, { stroke: 'rgba(255,214,150,.75)', w: 2 });
    pp.p.style.strokeDasharray = `${pp.L * 0.25} ${pp.L}`;
    tl.fromTo(pp.p, { strokeDashoffset: pp.L * 0.25, opacity: 1 }, { strokeDashoffset: -pp.L * 0.8, opacity: 0, duration: 0.9, ease: 'power3.out' }, I);
  }
  // lockup: ring travels left, wordmark arrives from the right (the current)
  const LX = 610, LY = 470;
  tl.to(rg.w, { x: LX - 960, y: LY - 540, scale: 0.66, duration: 0.9, ease: 'power3.inOut' }, I + 0.75);
  const wm = wordmark(cam, 745, LY - 80, 168);
  tl.fromTo(wm.children, { x: 120, opacity: 0, filter: 'blur(14px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.8, stagger: 0.045, ease: 'power4.out' }, I + 0.95);
  // light sweep over the wordmark on "Meet 7even5ive"
  const sweep = box(cam, 745, LY - 80, 900, 180, 'abs', { fontWeight: 650, fontSize: '168px', letterSpacing: '-0.045em', lineHeight: 1, whiteSpace: 'nowrap', color: 'transparent', backgroundImage: 'linear-gradient(100deg,rgba(255,255,255,0) 40%,rgba(255,255,255,.95) 50%,rgba(255,255,255,0) 60%)', backgroundSize: '300% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', backgroundPosition: '100% 0' }, '7even5ive');
  tl.fromTo(sweep, { backgroundPosition: '100% 0' }, { backgroundPosition: '0% 0', duration: 1.1, ease: 'power2.inOut' }, T.L09 + 0.1);

  // what it is, as it is said
  const L10 = 'An M C P server that centralises your college life, and organises the chaos into academic data you can actually use.';
  const wt = i => wordTime(L10, i, T.L10, E.L10 - T.L10);
  const l1 = words(cam, 'Centralises your college life.', 'abs serif', { left: '960px', top: '668px', fontSize: '58px', whiteSpace: 'nowrap', color: 'rgba(244,241,234,.92)' });
  center(l1);
  waterfall(l1, wt(6) - 0.1, { d: 0.6, s: 0.05 });
  const l2 = words(cam, 'Organises the chaos into academic data.', 'abs serif', { left: '960px', top: '758px', fontSize: '58px', whiteSpace: 'nowrap', color: 'rgba(244,241,234,.92)' });
  center(l2);
  waterfall(l2, wt(11) - 0.1, { d: 0.6, s: 0.05 });
  const pills = ['deadlines', 'notes', 'attendance', 'mail'];
  const pw = [230, 160, 240, 140];
  let px0 = 960 - (pw.reduce((a, b) => a + b, 0) + 60) / 2;
  const pillEls = pills.map((p, i) => {
    const e = box(cam, px0, 838, pw[i], 62, 'abs', { borderRadius: '999px', border: '1px solid rgba(255,181,71,.5)', background: 'rgba(255,181,71,.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '28px', fontWeight: 500 }, p);
    px0 += pw[i] + 20;
    return e;
  });
  pillEls.forEach((e, i) => inn(e, wt(15) + i * 0.14, { y: 20, scale: 0.85, d: 0.5, ease: 'back.out(1.6)' }));

  // ---------- the MCP connector: your college life inside any AI you use (L10b) ----------
  const L10b = "And because it's an M C P server, plug it into Claude Code, Codex, Cursor, or any A I you already use, and ask about your semester.";
  const wk = i => wordTime(L10b, i, T.L10b, E.L10b - T.L10b);
  tl.to([rg.w, wm, sweep, l1, l2, ...pillEls], { y: '-=70', opacity: 0, filter: 'blur(12px)', duration: 0.4, ease: 'power4.in' }, T.L10b - 0.45);
  const mc = box(cam, 0, 0, 1920, 1080, 'abs');
  tl.set(mc, { opacity: 0 }, 0);
  tl.fromTo(mc, { opacity: 1, y: 90, filter: 'blur(14px)' }, { y: 0, filter: 'blur(0px)', duration: 0.6, ease: 'power4.out', immediateRender: false }, T.L10b - 0.05);
  const node = box(mc, 960 - 230, 150, 460, 120, 'abs', { display: 'flex', alignItems: 'center', gap: '22px', padding: '0 30px', borderRadius: '24px', border: '2px solid rgba(255,181,71,.85)', background: 'rgba(255,181,71,.08)', boxShadow: '0 0 60px rgba(255,160,60,.25)' });
  node.innerHTML = '<div class="nm" style="position:relative;flex:none;width:64px;height:64px"></div><div><div style="font-size:40px;font-weight:650;letter-spacing:-0.02em">7even5ive</div><div class="mono" style="font-size:17px;color:var(--amber);letter-spacing:.14em;margin-top:2px">MCP SERVER</div></div>';
  const nr = ring(node.querySelector('.nm'), 32, 32, 64, 9, { glow: 3, trackOp: 0 }); nr.arcs.forEach(a => a.setAttribute('stroke-dashoffset', nr.C * 0.25));
  const CL = [['Claude Code', 11], ['Codex', 13], ['Cursor', 14], ['Claude', 16], ['ChatGPT', 16], ['Any MCP client', 17]];
  const cw = [250, 160, 160, 160, 180, 260], gap = 26;
  let cx = 960 - (cw.reduce((a, b) => a + b, 0) + gap * (cw.length - 1)) / 2;
  const msv = svgLayer(mc);
  const bus = pathEl(msv, 'M 960 270 L 960 360', { stroke: 'rgba(244,241,234,.3)', w: 2 });
  drawPath(bus, wk(10), 0.3);
  const xs = [];
  CL.forEach(([n, wi], i) => {
    const c = box(mc, cx, 420, cw[i], 70, 'abs', { display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '16px', border: '1px solid rgba(244,241,234,.28)', background: 'rgba(255,255,255,.05)', fontSize: '25px', fontWeight: 600, whiteSpace: 'nowrap' }, n);
    xs.push(cx + cw[i] / 2);
    inn(c, wk(wi) - 0.1 + (i === 4 ? 0.12 : 0), { y: 24, d: 0.45, ease: 'back.out(1.5)' });
    cx += cw[i] + gap;
  });
  const hb = pathEl(msv, `M ${xs[0]} 360 L ${xs[xs.length - 1]} 360`, { stroke: 'rgba(244,241,234,.3)', w: 2 });
  drawPath(hb, wk(10) + 0.2, 0.5);
  xs.forEach((x, i) => drawPath(pathEl(msv, `M ${x} 360 L ${x} 420`, { stroke: 'rgba(244,241,234,.3)', w: 2 }), wk(CL[i][1]) - 0.15, 0.25));
  // ask about your semester, from your own AI
  const q = box(mc, 960 - 470, 560, 940, 'auto', 'card', { padding: '26px 32px', background: 'rgba(10,11,15,.96)' });
  q.innerHTML = '<div class="mono" style="font-size:16px;color:var(--mute);letter-spacing:.14em">IN YOUR AI · VIA THE 7EVEN5IVE MCP SERVER</div><div style="font-size:30px;margin-top:14px"><span style="color:var(--amber)">›</span> <span class="qq"></span></div><div class="ans" style="margin-top:16px;font-size:26px;line-height:1.55;color:rgba(244,241,234,.88);opacity:0">DBMS Assignment 3 · <b>Fri 11:59 PM</b><br>Campus drive form · <b>today 6 PM</b><br>DBMS attendance · <b style="color:#FF8B7E">73%</b>, attend the next 3</div>';
  inn(q, wk(21), { y: 24, d: 0.45 });
  typeText(q.querySelector('.qq'), "what's due this week?", wk(22), 22);
  tl.to(q.querySelector('.ans'), { opacity: 1, duration: 0.4 }, wk(26) + 0.25);
})();
