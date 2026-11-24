const { chromium } = require('playwright');
(async () => {
  const dir = process.argv[2], times = process.argv.slice(3).map(Number);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.type() + ': ' + m.text()); });
  await p.goto('file://' + dir + '/index.html');
  await p.waitForFunction(() => window.__ready === true, null, { timeout: 30000 }).catch(e => errs.push('not ready: ' + e.message));
  console.log('total', await p.evaluate(() => window.__total));
  for (const t of times) {
    await p.evaluate(t => window.__seek(t), t);
    await p.screenshot({ path: `${dir}/../probe/f_${String(t).padStart(6, '0')}.jpg`, type: 'jpeg', quality: 80 });
  }
  console.log(errs.slice(0, 20).join('\n') || 'no errors');
  await b.close();
})();
