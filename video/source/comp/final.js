// Captions, beat-synced light flashes, grain, voice-reactive orb, and the render API.
(function finalize() {
  // captions (skipped where the same words are already on screen)
  const SKIP = new Set(['L01', 'L04', 'L08', 'L08b', 'L09', 'L19', 'L20', 'L23', 'L24', 'L33', 'L44', 'L45']);
  const CAP = document.getElementById('cap');
  D.captions.forEach(c => {
    if (SKIP.has(c.id)) return;
    const n = div(CAP, 'abs', { left: '0', right: '0', bottom: '0', padding: '0 260px', opacity: 0 }, c.text);
    tl.fromTo(n, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.22, ease: 'power2.out', immediateRender: false }, c.t - 0.05);
    tl.to(n, { opacity: 0, duration: 0.2, ease: 'power2.in' }, c.e + 0.12);
  });

  // "flashing lights": a warm pulse on every downbeat while the montage and the AWS build are running
  const pulse = div(document.getElementById('fx'), 'abs', { inset: '0', background: 'radial-gradient(circle at 50% 45%,rgba(255,190,110,.10),rgba(0,0,0,0) 60%)', opacity: 0 });
  const windows = [[C.problem, C.reveal - 0.6], [C.aws + 1.0, T.L36]];
  D.downbeats.forEach(b => {
    if (windows.some(([a, z]) => b >= a && b <= z)) {
      tl.fromTo(pulse, { opacity: 1 }, { opacity: 0, duration: 0.55, ease: 'power2.out', immediateRender: false }, b);
    }
  });

  // voice-reactive halo around the call orb
  const orb = window.ORB;
  const halo = box(orb.parentNode, parseFloat(orb.style.left) - 30, parseFloat(orb.style.top) - 30, 280, 280, 'abs', { borderRadius: '50%', border: '2px solid rgba(255,200,130,.6)', opacity: 0 });
  const halo2 = box(orb.parentNode, parseFloat(orb.style.left) - 60, parseFloat(orb.style.top) - 60, 340, 340, 'abs', { borderRadius: '50%', border: '1px solid rgba(255,200,130,.35)', opacity: 0 });
  const callA = T.D01 - 0.3, callZ = E.D03 + 0.6;

  const grain = document.getElementById('grain');
  const total = tl.duration();
  window.__total = D.total;
  window.__seek = function (t) {
    tl.seek(Math.min(t, total), false);
    const f = Math.round(t * FPS);
    grain.style.transform = `translate(${((f * 73) % 128) - 64}px,${((f * 151) % 128) - 64}px)`;
    if (t >= callA && t <= callZ) {
      const a = (D.env.agent[f] || 0);
      halo.style.opacity = String(0.15 + 0.85 * a);
      halo.style.transform = `scale(${1 + 0.18 * a})`;
      halo2.style.opacity = String(0.6 * a);
      halo2.style.transform = `scale(${1 + 0.32 * a})`;
      orb.style.filter = `brightness(${1 + 0.35 * a})`;
    } else {
      halo.style.opacity = '0'; halo2.style.opacity = '0'; orb.style.filter = 'none';
    }
  };
  const faces = ['400 40px IT', '500 40px IT', '600 40px IT', '700 40px IT', 'italic 400 40px IS', '400 40px IS', '400 40px JB', '500 40px JB'];
  Promise.all([
    ...faces.map(f => document.fonts.load(f, 'AaZz09%₹→·')),
    document.fonts.load('40px NK', 'ಕನ್ನಡ'),
    document.fonts.load('40px ND', 'हिन्दी'),
  ]).then(() => document.fonts.ready).then(() => { window.__seek(0); window.__ready = true; });
})();
