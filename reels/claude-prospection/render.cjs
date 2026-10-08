// Renders broll.html frame by frame to transparent PNGs (top half + caption band).
// usage: node render.cjs <broll.html> <outDir> <durationSec> [fps=30] [workers=3] [onlyTimes=comma list]
const { chromium } = require('playwright');
const path = require('path');
const [html, outDir, dur, fps = '30', workers = '3', only] = process.argv.slice(2);
const FPS = +fps, N = Math.round(+dur * FPS), W = +workers;
const CLIP = { x: 0, y: 0, width: 1080, height: 1100 };
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
  const times = only ? only.split(',').map(Number) : null;
  const jobs = times ? times.map((t, i) => [i, t]) : [...Array(N)].map((_, i) => [i, i / FPS]);
  let done = 0;
  await Promise.all([...Array(W)].map(async (_, w) => {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
    await page.goto('file://' + path.resolve(html));
    await page.evaluate(() => document.fonts.ready);
    for (let j = w; j < jobs.length; j += W) {
      const [i, t] = jobs[j];
      await page.evaluate(t => window.render(t), t);
      const name = times ? `still_${String(t).replace('.', '_')}.png` : `f_${String(i).padStart(5, '0')}.png`;
      await page.screenshot({ path: path.join(outDir, name), omitBackground: true, clip: CLIP });
      if (++done % 150 === 0) console.log(`${done}/${jobs.length}`);
    }
  }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
