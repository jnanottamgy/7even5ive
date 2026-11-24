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
  // department notices: every circular arrives as a forwarded PDF
  const gm = box(cam, 670, 92, 560, 400, 'card');
  head(gm, 'CSE Dept · Notices', '<span class="mono gmc" style="font-size:18px;padding:6px 14px;border-radius:999px;background:rgba(37,211,102,.14);color:#7BE3A0">212 unread</span>');
  const gcount = gm.querySelector('.gmc');
  const clip = box(gm, 0, 64, 560, 336, 'abs', { overflow: 'hidden' });
  const list = box(clip, 0, -280, 560, 900, 'abs');
  const pdf = '<i style="display:flex;align-items:center;justify-content:center;flex:none;width:34px;height:40px;border-radius:6px;background:rgba(255,90,78,.16);color:#FF8B7E;font:600 11px JB;font-style:normal">PDF</i>';
  const rows = ['IA-2_timetable.pdf', 'Fee_payment_notice.pdf', 'Lab_record_format.pdf', 'Holiday_list.pdf', 'Hackathon_registration.pdf', 'Bus_route_change.pdf', 'Exam_form_last_date.pdf', 'DBMS_Assignment_3.pdf', 'Seminar_attendance.pdf', 'Sports_day_circular.pdf'];
  rows.forEach((f, i) => {
    const hot = i === 7;
    const r = box(list, 18, i * 56 + 8, 524, 48, 'abs', { display: 'flex', gap: '14px', alignItems: 'center', fontSize: '21px', padding: '0 12px', borderRadius: '10px', background: hot ? 'rgba(255,181,71,.10)' : 'none', border: hot ? '1px solid rgba(255,181,71,.45)' : '1px solid transparent' });
    r.innerHTML = `<span class="mono" style="flex:none;width:70px;font-size:14px;letter-spacing:.06em;color:var(--dim)">↪ FWD</span>${pdf}<span style="color:${hot ? 'var(--amber)' : 'var(--mute)'};font-weight:${hot ? 600 : 400};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${f}</span>${hot ? '<span class="mono" style="margin-left:auto;flex:none;font-size:15px;color:var(--amber)">due Fri</span>' : ''}`;
  });
  // class group chat
  const ch = box(cam, 1290, 150, 520, 650, 'card', { overflow: 'hidden' });
  head(ch, 'CSE 3B · Class group', '<span class="mono memec" style="font-size:18px;color:var(--mute)">0 memes</span>');
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
  // the buried voice note at the bottom of the feed
  const vn = box(feed, 26, y + 4, 360, 74, 'abs', { borderRadius: '18px', background: 'rgba(255,255,255,.07)', display: 'flex', alignItems: 'center', gap: '14px', padding: '0 18px' });
  vn.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M7 4 L20 12 L7 20 Z" fill="#8D919B"/></svg>' +
    Array.from({ length: 18 }, (_, i) => `<i style="display:block;width:5px;border-radius:3px;background:#8D919B;height:${8 + ((i * 37) % 26)}px"></i>`).join('') +
    '<span class="mono" style="font-size:18px;color:var(--mute);margin-left:6px">0:14</span>';
  const vnl = box(feed, 400, y + 26, 120, 30, 'abs mono', { fontSize: '16px', color: '#FF8B7E', letterSpacing: '.08em' }, 'UNPLAYED');
  const feedEnd = y + 80;
  // college mail: placement drives land where nobody looks
  const cr = box(cam, 230, 570, 470, 250, 'card');
  head(cr, 'College mail', '<span class="mono" style="font-size:17px;color:#FF8B7E">1,284 unread</span>');
  box(cr, 26, 90, 420, 140, 'abs', { fontSize: '24px', lineHeight: 1.6 }, '<div style="font-weight:600">T&amp;P Cell · Campus drive</div><div style="color:var(--mute)">Registration closes 6 PM</div><div class="mono" style="font-size:17px;color:var(--dim);margin-top:6px">UNREAD · YESTERDAY</div>');
  // instagram: club deadlines live in stories that disappear
  const ig = box(cam, 780, 560, 450, 330, 'card');
  head(ig, 'Instagram', '<span class="mono" style="font-size:17px;color:var(--mute)">story · 3h left</span>');
  const story = box(ig, 26, 82, 150, 228, 'abs', { borderRadius: '16px', overflow: 'hidden', background: 'linear-gradient(160deg,#4b2a86,#a83279 55%,#e2683c)' });
  story.innerHTML = `<i style="position:absolute;left:10px;right:10px;top:8px;height:3px;border-radius:2px;background:rgba(255,255,255,.35)"><b style="display:block;width:78%;height:3px;border-radius:2px;background:#fff"></b></i>
    <div style="position:absolute;left:10px;top:20px;display:flex;align-items:center;gap:6px"><i style="display:block;width:22px;height:22px;border-radius:50%;border:2px solid #fff;background:#151515"></i><span style="font-size:13px;font-weight:600">techclub</span></div>
    <div style="position:absolute;left:12px;right:10px;top:76px;font-weight:700;font-size:21px;line-height:1.08;letter-spacing:-0.01em">HACKATHON<br>REG CLOSES<br>TONIGHT</div>
    <div class="mono" style="position:absolute;left:12px;bottom:14px;font-size:13px">11:59 PM</div>`;
  box(ig, 198, 92, 230, 210, 'abs', { fontSize: '22px', lineHeight: 1.45 }, '<div style="font-weight:600">@techclub</div><div style="color:var(--mute)">Hackathon registrations close tonight</div><div class="mono" style="font-size:16px;color:#FF8B7E;margin-top:12px;letter-spacing:.06em">GONE IN 3 HOURS</div>');

  const cards = [portal, gm, ch, cr, ig];
  tl.fromTo(cards, { x: 420, opacity: 0, filter: 'blur(16px)' }, { x: 0, opacity: 1, filter: 'blur(0px)', duration: 0.75, stagger: 0.07, ease: 'power4.out' }, C.problem);

  // camera visits each problem, the rest falls back
  const focus = (t, cx, cy, s, keep) => {
    tl.to(cam, { scale: s, x: -s * (cx - 960), y: -s * (cy - 540), duration: 1.0, ease: 'power3.inOut' }, t);
    cards.forEach(c => tl.to(c, { opacity: keep.includes(c) ? 1 : 0.22, duration: 0.6 }, t));
  };
  focus(T.L05 - 0.25, 360, 320, 1.5, [portal]);
  tl.fromTo(portal.querySelectorAll('.mono')[0], { opacity: 0.2 }, { opacity: 1, duration: 0.3, repeat: 3, yoyo: true, ease: 'none' }, T.L05 + 1.6);
  focus(T.L06 - 0.25, 950, 300, 1.45, [gm]);
  tl.to(list, { y: 280, duration: 1.4, ease: 'power2.inOut' }, T.L06 + 0.3);
  count(gcount, 212, 219, T.L06 + 0.3, 1.4, v => Math.round(v) + ' unread');
  focus(T.L07 - 0.2, 1550, 475, 1.32, [ch]);
  tl.to(feed, { y: -(feedEnd - 560), duration: 4.0, ease: 'power2.in' }, T.L07 + 0.2);
  count(memec, 0, 40, T.L07 + 0.2, 4.0, v => Math.round(v) + ' memes');
  tl.fromTo(vnl, { opacity: 0 }, { opacity: 1, duration: 0.3 }, T.L07 + 4.0);
  // ---------- zoom through the class group: the night-before-exam hunt (L07a-c) ----------
  const L07b = 'Someone asks for the unit three notes. Someone sends unit two. The drive link needs access, and the file you need is buried under six hundred messages.';
  const L07c = 'Search for notes, and you get two hundred results. Not one of them is the file.';
  const L07d = 'And placement mails go to a college inbox nobody checks. The drive registration closed at six.';
  const wb = i => wordTime(L07b, i, T.L07b, E.L07b - T.L07b);
  const wc = i => wordTime(L07c, i, T.L07c, E.L07c - T.L07c);
  const wd = i => wordTime(L07d, i, T.L07d, E.L07d - T.L07d);
  const zt = T.L07a - 0.45;
  tl.to(cam, { scale: 3.2, x: -3.2 * (1550 - 960), y: -3.2 * (475 - 540), opacity: 0, filter: 'blur(16px)', duration: 0.45, ease: 'power4.in' }, zt);
  const hunt = box(S.seam, 0, 0, 1920, 1080, 'abs');
  tl.set(hunt, { opacity: 0 }, 0);
  tl.fromTo(hunt, { opacity: 0, scale: 0.72, filter: 'blur(14px)' }, { opacity: 1, scale: 1, filter: 'blur(0px)', duration: 0.6, ease: 'power4.out', immediateRender: false }, zt + 0.45);
  const h1 = words(hunt, 'The night before', 'abs serif', { left: '120px', top: '300px', fontSize: '100px', whiteSpace: 'nowrap' });
  const h2 = words(hunt, 'an exam.', 'abs serif', { left: '120px', top: '416px', fontSize: '100px', whiteSpace: 'nowrap', color: 'var(--amber)' });
  spoken(h1, T.L07a + 0.15, 1.3, { y: 30, d: 0.5 });
  spoken(h2, T.L07a + 0.95, 0.8, { y: 30, d: 0.5 });
  const clock = box(hunt, 126, 560, 640, 40, 'abs mono', { fontSize: '22px', color: 'var(--mute)', letterSpacing: '.14em' }, '11:48 PM · EXAM AT 9:30 AM');
  inn(clock, T.L07a + 1.7, { y: 10, d: 0.5 });
  tl.to([h1, h2, clock], { y: -60, opacity: 0, filter: 'blur(10px)', duration: 0.4, ease: 'power3.in' }, T.L07b - 0.3);
  // the chat
  const chat = box(hunt, 880, 70, 920, 890, 'card', { overflow: 'hidden', background: 'rgba(12,14,18,.94)' });
  const chH = box(chat, 0, 0, 920, 96, 'abs', { display: 'flex', alignItems: 'center', gap: '18px', padding: '0 28px', borderBottom: '1px solid rgba(255,255,255,.07)', background: 'rgba(255,255,255,.03)' });
  chH.innerHTML = `<i style="display:block;flex:none;width:54px;height:54px;border-radius:50%;background:linear-gradient(135deg,#2F6B52,#1C3B2E)"></i><div><div style="font-size:28px;font-weight:600">CSE 3B · Class group</div><div class="mono sub" style="font-size:16px;color:var(--mute);margin-top:2px">64 PARTICIPANTS</div></div><span class="mono unr" style="margin-left:auto;font-size:18px;padding:7px 14px;border-radius:999px;background:rgba(37,211,102,.16);color:#7BE3A0">42 unread</span>`;
  const unr = chH.querySelector('.unr');
  const sub = chH.querySelector('.sub');
  tl.set(sub, { innerHTML: 'RAHUL IS TYPING…', color: '#7BE3A0' }, T.L07a + 1.2);
  tl.set(sub, { innerHTML: '64 PARTICIPANTS', color: '#8D919B' }, wb(1) - 0.1);
  const body = box(chat, 0, 96, 920, 794, 'abs', { overflow: 'hidden' });
  const feedH = box(body, 0, 0, 920, 5200, 'abs');
  const NC = { Rahul: '#7FB8FF', Priya: '#F7A8D0', Arjun: '#FFC46B', Sneha: '#9FE6C0', Kiran: '#C9A7FF', Meera: '#FF9F8A' };
  const msg = (y, who, html, o) => {
    const mine = who === 'you';
    const b = box(feedH, mine ? 'auto' : 28, y, 'auto', 'auto', 'abs', Object.assign({ right: mine ? '28px' : 'auto', maxWidth: '640px', padding: '10px 18px 12px', borderRadius: '18px', background: mine ? 'rgba(37,211,102,.16)' : 'rgba(255,255,255,.07)', fontSize: '26px', lineHeight: 1.3, whiteSpace: 'nowrap' }, o || {}));
    b.innerHTML = (mine ? '' : `<div style="font-size:18px;font-weight:600;color:${NC[who] || 'var(--mute)'};margin-bottom:3px">${who}</div>`) + html;
    return b;
  };
  const pdfB = (name, meta) => `<div style="display:flex;align-items:center;gap:14px;padding:4px 2px"><i style="display:flex;align-items:center;justify-content:center;flex:none;width:50px;height:60px;border-radius:8px;background:rgba(255,90,78,.16);color:#FF8B7E;font:600 14px JB;font-style:normal">PDF</i><div><div style="font-size:24px;font-weight:500">${name}</div><div class="mono" style="font-size:15px;color:var(--mute);margin-top:4px">${meta}</div></div></div>`;
  const slash = '<svg width="22" height="22" viewBox="0 0 24 24" style="vertical-align:-4px;margin-right:8px"><circle cx="12" cy="12" r="9" fill="none" stroke="#8D919B" stroke-width="2"/><path d="M5.5 18.5 L18.5 5.5" stroke="#8D919B" stroke-width="2"/></svg>';
  const M = [
    [24, 'Rahul', 'anyone has DBMS unit 3 notes??', 1],
    [122, 'Priya', '+1, send PYQs also', 5],
    [220, 'Arjun', pdfB('Unit2_notes.pdf', '2.1 MB · PDF'), 8],
    [348, 'Priya', "bro that's unit 2", 10],
    [446, 'Sneha', 'check the drive link from last week', 12],
    [544, 'Sneha', '<div style="border-radius:12px;background:rgba(0,0,0,.28);padding:10px 16px"><div class="mono" style="font-size:18px;color:#8FB8FF">drive.google.com/drive/folders/1xQ…</div><div style="font-size:20px;color:var(--mute);margin-top:4px">DBMS notes folder</div><div class="mono acc" style="margin-top:10px;font-size:17px;color:#FF8B7E;letter-spacing:.06em;opacity:0">YOU NEED ACCESS · REQUEST SENT</div></div>', 13],
    [714, 'Rahul', `<span style="font-style:italic;color:var(--mute)">${slash}This message was deleted</span>`, 17],
    [812, 'you', 'can someone resend pls', 19],
  ];
  const mels = M.map(([y, who, html, wi]) => { const b = msg(y, who, html); inn(b, wb(wi) - 0.1, { y: 26, d: 0.4, ease: 'power3.out' }); return b; });
  tl.to(mels[5].querySelector('.acc'), { opacity: 1, duration: 0.3 }, wb(15));
  tl.to(feedH, { y: -120, duration: 0.5, ease: 'power3.out' }, wb(19) - 0.1);
  // ...then six hundred more bury it
  const filler = ['lol', 'ok', 'STICKER', 'same', 'anyone??', 'bro', 'who has the lab manual', 'ok ok', 'STICKER', 'notes??', 'haha', 'see you tmrw', 'STICKER', 'lol', 'is it open book?', 'ok', 'bruh', 'STICKER', 'canteen?', 'notes pls', 'lmao', 'ok', 'STICKER', 'same here', 'who took my charger', 'lol', 'STICKER', 'ok'];
  let fy = 930;
  filler.forEach((m, i) => {
    const who = ['Kiran', 'Meera', 'Arjun', 'Rahul', 'Sneha', 'Priya'][i % 6];
    if (m === 'STICKER') { box(feedH, i % 2 ? 560 : 28, fy, 150, 120, 'abs', { borderRadius: '24px', background: ['#3A2F5B', '#2F4A3A', '#5B3A2F'][i % 3], display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '38px', fontWeight: 700, color: 'rgba(255,255,255,.75)' }, ['LOL', 'XD', 'bruh'][i % 3]); fy += 136; }
    else { msg(fy, who, m); fy += 98; }
  });
  const buryA = wb(21), buryZ = E.L07b + 0.2;
  tl.to(feedH, { y: -(fy - 760), duration: buryZ - buryA, ease: 'power2.in' }, buryA);
  tl.to(body, { filter: 'blur(1.5px)', duration: 0.3 }, buryA + 0.6);
  tl.to(body, { filter: 'blur(0px)', duration: 0.3 }, buryZ - 0.2);
  count(unr, 42, 642, buryA, buryZ - buryA, v => Math.round(v) + ' unread');
  const upChip = box(chat, 220, 112, 480, 46, 'abs mono', { display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '999px', background: 'rgb(42,32,14)', border: '1px solid rgba(255,181,71,.6)', boxShadow: '0 8px 24px rgba(0,0,0,.5)', color: 'var(--amber)', fontSize: '17px', letterSpacing: '.06em', zIndex: 5 }, '↑ DBMS_U3_notes.pdf · 600 MESSAGES UP');
  inn(upChip, wb(18), { y: -14, d: 0.45 });
  // the failures, tallied on the left
  const fails = [['Wrong unit', 10], ['Link needs access', 15], ['Buried, 600 messages up', 22]];
  const failEls = fails.map(([t, wi], i) => {
    const f = box(hunt, 120, 300 + i * 96, 700, 80, 'abs', { display: 'flex', alignItems: 'center', gap: '22px', fontSize: '42px', fontWeight: 600, letterSpacing: '-0.02em' }, `<span style="display:flex;flex:none;width:52px;height:52px;border-radius:50%;border:2px solid var(--red);align-items:center;justify-content:center">${cross(26)}</span>${t}`);
    inn(f, wb(wi), { x: -30, y: 0, d: 0.45, ease: 'power4.out' });
    return f;
  });
  // search: two hundred results, no file (L07c)
  const sb = box(chat, 0, 0, 920, 96, 'abs', { display: 'flex', alignItems: 'center', gap: '16px', padding: '0 28px', background: 'rgb(16,18,23)', borderBottom: '2px solid rgba(255,181,71,.6)', zIndex: 6 });
  sb.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="#F4F1EA" stroke-width="2"/><path d="M15.5 15.5 L21 21" stroke="#F4F1EA" stroke-width="2" stroke-linecap="round"/></svg><span class="q" style="font-size:30px;font-weight:500"></span><span style="color:var(--amber);font-size:30px">▍</span><span class="mono rc" style="margin-left:auto;font-size:18px;color:var(--mute)"></span>';
  inn(sb, T.L07c - 0.25, { y: -20, d: 0.4 });
  typeText(sb.querySelector('.q'), 'notes', wc(1), 9);
  const res = box(chat, 0, 96, 920, 794, 'abs', { background: 'rgb(12,14,18)', zIndex: 5, padding: '10px 0' });
  tl.set(res, { opacity: 0 }, 0); tl.to(res, { opacity: 1, duration: 0.3 }, wc(3));
  tl.to(upChip, { opacity: 0, duration: 0.2 }, wc(3));
  const R = [['Rahul', 'anyone has DBMS unit 3 <b>notes</b>??', '12 Nov'], ['Priya', '<b>notes</b> pls', '12 Nov'], ['Kiran', 'whose <b>notes</b> are these', '9 Nov'], ['Sneha', 'the <b>notes</b> are in the drive', '5 Nov'], ['Meera', 'send <b>notes</b> also', '3 Nov'], ['Arjun', '<b>NOTES</b>??', '1 Nov'], ['Rahul', 'did anyone get the <b>notes</b>', '28 Oct']];
  const rows2 = R.map(([who, t, d], i) => {
    const r = box(res, 28, 14 + i * 104, 864, 92, 'abs', { borderRadius: '14px', background: 'rgba(255,255,255,.035)', padding: '12px 20px', fontSize: '24px' });
    r.innerHTML = `<div style="display:flex;justify-content:space-between"><span style="font-size:18px;font-weight:600;color:${NC[who]}">${who}</span><span class="mono" style="font-size:15px;color:var(--dim)">${d}</span></div><div style="margin-top:4px;color:rgba(244,241,234,.8)">${t.replace(/<b>/g, '<b style="color:var(--amber)">')}</div>`;
    inn(r, wc(4) + i * 0.09, { y: 18, d: 0.35 });
    return r;
  });
  count(sb.querySelector('.rc'), 0, 214, wc(4), wc(8) - wc(4), v => Math.round(v) + ' results');
  const zero = box(hunt, 120, 300 + 3 * 96, 700, 80, 'abs', { display: 'flex', alignItems: 'center', gap: '22px', fontSize: '42px', fontWeight: 600, letterSpacing: '-0.02em', color: 'var(--red)' }, `<span style="display:flex;flex:none;width:52px;height:52px;border-radius:50%;border:2px solid var(--red);align-items:center;justify-content:center">${cross(26)}</span>214 results, 0 files`);
  inn(zero, wc(9), { x: -30, y: 0, d: 0.45, ease: 'power4.out' });
  tl.to(rows2, { opacity: 0.3, duration: 0.4 }, wc(9) + 0.1);

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
  tl.to(ml, { scale: 0.24, x: 465 - 960, y: 695 - 540, opacity: 0, filter: 'blur(6px)', duration: 0.6, ease: 'power3.inOut' }, T.L08 - 0.5);
  tl.to(cam, { opacity: 1, filter: 'blur(0px)', duration: 0.35 }, T.L08 - 0.45);

  // pull back: try to connect them, every link breaks
  focus(T.L08 - 0.45, 960, 520, 0.96, cards);
  const sv = svgLayer(cam);
  const centers = [[360, 320], [950, 292], [1550, 475], [1005, 725], [465, 695]];
  const links = [];
  for (let i = 0; i < 5; i++) {
    const a = centers[i], b = centers[(i + 1) % 5];
    const pp = pathEl(sv, `M${a[0]} ${a[1]} L${b[0]} ${b[1]}`, { stroke: 'rgba(255,181,71,.7)', w: 3 });
    links.push(pp);
    drawPath(pp, T.L08 + 0.05 + i * 0.07, 0.45);
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const x = box(cam, mx - 22, my - 22, 44, 44, 'abs', { borderRadius: '50%', background: '#1a0d0c', border: '2px solid var(--red)', display: 'flex', alignItems: 'center', justifyContent: 'center' }, cross(24));
    inn(x, T.L08 + 0.85 + i * 0.05, { y: 0, scale: 0.4, d: 0.35, ease: 'back.out(1.7)' });
    tl.to(pp.p, { attr: { stroke: 'rgba(255,90,78,.6)' }, duration: 0.2 }, T.L08 + 0.85 + i * 0.05);
  }
  const big = box(cam, 960, 540, 'auto', 'auto', 'abs', { textAlign: 'center', fontWeight: 650, fontSize: '128px', letterSpacing: '-0.045em', lineHeight: 1.02, textShadow: '0 20px 60px rgba(0,0,0,.8)' }, '<div class="w">5 apps.</div><div class="w"><span style="color:var(--red)">0</span> connection.</div>');
  center(big);
  cards.forEach(c => tl.to(c, { opacity: 0.16, duration: 0.5 }, T.L08 + 0.25));
  tl.to(sv, { opacity: 0.35, duration: 0.5 }, T.L08 + 0.25);
  tl.fromTo(big.children, { yPercent: 60, opacity: 0, filter: 'blur(14px)' }, { yPercent: 0, opacity: 1, filter: 'blur(0px)', duration: 0.6, stagger: 0.55, ease: 'power3.out' }, T.L08 + 0.1);
  // everything collapses into one point (arrival of the brand)
  tl.to(S.seam, { scale: 0.02, filter: 'blur(6px)', duration: 0.5, ease: 'power4.in' }, C.reveal - 0.5);
  tl.to(GRID, { opacity: 0, duration: 0.5 }, C.reveal - 0.5);
  off('problem', C.reveal);
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

  // what it does, as it is said
  const L10 = 'An agent that watches your college life, turns it into deadlines, warnings and plans, and asks before it ever touches anyone else.';
  const wt = i => wordTime(L10, i, T.L10, E.L10 - T.L10);
  const l1 = words(cam, 'Watches your college life.', 'abs serif', { left: '960px', top: '668px', fontSize: '58px', whiteSpace: 'nowrap', color: 'rgba(244,241,234,.92)' });
  center(l1);
  waterfall(l1, wt(3) - 0.1, { d: 0.6, s: 0.05 });
  const pills = ['deadlines', 'warnings', 'plans'];
  const pw = [250, 250, 190];
  let px0 = 960 - (pw.reduce((a, b) => a + b, 0) + 40) / 2;
  const pillEls = pills.map((p, i) => {
    const e = box(cam, px0, 742, pw[i], 66, 'abs', { borderRadius: '999px', border: '1px solid rgba(255,181,71,.5)', background: 'rgba(255,181,71,.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '30px', fontWeight: 600, color: 'var(--amber)' }, p);
    px0 += pw[i] + 20;
    return e;
  });
  [10, 11, 13].forEach((wi, i) => inn(pillEls[i], wt(wi) - 0.05, { y: 20, scale: 0.85, d: 0.5, ease: 'back.out(1.6)' }));
  const l2 = words(cam, 'Asks before it touches anyone else.', 'abs serif', { left: '960px', top: '880px', fontSize: '58px', whiteSpace: 'nowrap', color: 'rgba(244,241,234,.92)' });
  center(l2);
  waterfall(l2, wt(15) - 0.1, { d: 0.6, s: 0.05 });
})();
