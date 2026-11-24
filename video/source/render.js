// Renders comp/index.html frame by frame: seek, screenshot, pipe JPEGs into ffmpeg.
// usage: node render.js <worker> <workers> [firstFrame lastFrame]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
const FPS = 30;
const dir = path.join(__dirname, 'comp');
const out = path.join(__dirname, 'render');
const [k, n] = [Number(process.argv[2] || 0), Number(process.argv[3] || 1)];

(async () => {
  const b = await chromium.launch({ args: ['--disable-gpu-vsync', '--force-color-profile=srgb'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto('file://' + dir + '/index.html');
  await p.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
  const total = Math.round((await p.evaluate(() => window.__total)) * FPS);
  let a = Math.floor((total * k) / n), z = Math.floor((total * (k + 1)) / n);
  if (process.argv[4]) { a = Number(process.argv[4]); z = Number(process.argv[5]); }
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '15', '-tune', 'film', '-pix_fmt', 'yuv420p', '-g', '60', '-threads', '2',
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
    path.join(out, `seg_${String(k).padStart(2, '0')}.mp4`)], { stdio: ['pipe', 'inherit', 'inherit'] });
  const write = buf => new Promise(r => (ff.stdin.write(buf) ? r() : ff.stdin.once('drain', r)));
  await p.evaluate(() => window.__seek(0));
  const t0 = Date.now();
  for (let f = a; f < z; f++) {
    await p.evaluate(t => window.__seek(t), f / FPS);
    await write(await p.screenshot({ type: 'jpeg', quality: 95 }));
    if ((f - a) % 150 === 0) console.log(`[w${k}] ${f - a}/${z - a} frames, ${((Date.now() - t0) / Math.max(1, f - a)).toFixed(0)} ms/frame`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  console.log(`[w${k}] done ${z - a} frames in ${((Date.now() - t0) / 1000).toFixed(0)} s`, errs.length ? 'ERRORS: ' + errs.slice(0, 5).join(' | ') : '');
  await b.close();
})();
