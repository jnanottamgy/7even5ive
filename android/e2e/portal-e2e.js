// Plays the Android WebView against the real servers: the same runner.js, and the start script
// read straight out of PortalEngine.kt, so the check runs the app's own JavaScript.
//   node android/e2e/portal-e2e.js      (core :8000, PortMax API :8002, mock portal :8765)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const kt = fs.readFileSync(path.join(__dirname, '../app/src/main/java/com/sevenfive/app/portal/PortalEngine.kt'), 'utf8');
const raw = kt.match(/return """\n([\s\S]*?)"""\.trimIndent\(\)/)[1];
const indent = Math.min(...raw.split('\n').filter(l => l.trim()).map(l => l.match(/^ */)[0].length));
const T = raw.split('\n').map(l => l.slice(indent)).join('\n').split('${PortalBridge.NAME}').join('SevenFiveBridge');
const H = { Authorization: 'Bearer demo-student-token' };
const HOST = process.env.HOST || '127.0.0.1';
const PORTAL = `http://${HOST}:8765`, PM = `http://${HOST}:8002`, CORE = `http://${HOST}:8000`;
const script = (settings, keepAlive, nonce) =>
  T.split('$settingsJson').join(settings).split('$call').join(keepAlive ? 'keepAlive' : 'run').split('$nonce').join(nonce);

(async () => {
  const settings = await (await fetch(`${PM}/v1/connectors/mockcollege`, { headers: H })).text();
  const markers = JSON.stringify(JSON.parse(settings).markers);
  const runner = await (await fetch(`${PM}/v1/runner.js`)).text();
  const before = (await (await fetch(`${CORE}/api/cards`, { headers: H })).json()).attendance.fetched_at;

  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  // The @JavascriptInterface stand-in: records what the page posts back.
  await page.exposeFunction('__post', (kind, nonce, a, b) => { page.__result = { kind, nonce, a, b }; });
  await page.addInitScript(() => {
    window.SevenFiveBridge = {
      pages: (n, j) => window.__post('pages', n, j),
      error: (n, c, d) => window.__post('error', n, c, d),
    };
  });
  const loggedIn = async () => { await page.evaluate(runner + '\n;true;'); return page.evaluate(`PortMaxRunner.isLoggedIn(${markers})`); };
  const runOnce = async (keepAlive, nonce) => {
    page.__result = null;
    await page.evaluate(runner + '\n;true;');  // as PortalEngine.inject() does
    const started = await page.evaluate(script(settings, keepAlive, nonce));
    for (let i = 0; i < 100 && !page.__result; i++) await page.waitForTimeout(100);
    return { started, ...page.__result };
  };
  const upload = async (pagesJson) => {
    const r = await fetch(`${PM}/v1/pages`, { method: 'POST', headers: { ...H, 'content-type': 'application/json' },
      body: JSON.stringify({ college: 'mockcollege', pages: JSON.parse(pagesJson) }) });
    return [r.status, await r.json()];
  };

  await page.goto(`${PORTAL}/index.php`);
  console.log('1 login page, isLoggedIn =', await loggedIn());

  // The student types this themselves in the app; here the test plays the student.
  await page.fill('input[name=username]', '1MC24CS042');
  await page.selectOption('select[name=dd]', '14');
  await page.selectOption('select[name=mm]', '08');
  await page.selectOption('select[name=yyyy]', '2005');
  await page.fill('input[name=captcha]', 'PM42X');
  await Promise.all([page.waitForLoadState('load'), page.click('button[type=submit]')]);
  await page.fill('input[name=parent_digits]', '2345');
  await Promise.all([page.waitForURL(/dashboard/), page.click('button[type=submit]')]);
  const loggedInAfter = await loggedIn();
  console.log('2 after login, isLoggedIn =', loggedInAfter);

  const full = await runOnce(false, 'nonce-1');
  const pages = full.kind === 'pages' ? JSON.parse(full.a) : [];
  console.log('3 run:', full.started, full.kind, 'nonce', full.nonce, 'pages', pages.length, [...new Set(pages.map(p => p.step))].join(','));
  console.log('4 upload:', ...(await upload(full.a)));
  const after = (await (await fetch(`${CORE}/api/cards`, { headers: H })).json()).attendance;
  console.log('5 cards fetched_at', before, '->', after.fetched_at, 'subjects', after.subjects.length);

  // ForegroundSync path: start from the login page (session untouched), keep-alive from there.
  await page.goto(`${PORTAL}/index.php`);
  const keep = await runOnce(true, 'nonce-2');
  console.log('6 keep-alive from login page:', keep.kind, keep.kind === 'pages' ? JSON.parse(keep.a).map(p => p.step) : keep.a);
  console.log('7 upload:', (await upload(keep.a))[0]);

  // Session gone: the runner must say session_expired, not crash.
  await ctx.clearCookies();
  await page.goto(`${PORTAL}/index.php`);
  const dead = await runOnce(false, 'nonce-3');
  console.log('8 after cookies cleared:', dead.kind, dead.a, '|', dead.b);
  await browser.close();
  const ok = loggedInAfter && full.kind === 'pages' && keep.kind === 'pages' && dead.a === 'session_expired';
  console.log(ok ? 'PASS' : 'FAIL');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error('FAILED', e); process.exit(1); });
