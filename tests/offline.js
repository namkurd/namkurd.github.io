// Service worker: visited pages load offline, unvisited show /offline.html.
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext(); const pg = await ctx.newPage(); let bad = 0;
  const eq = (n, g, w) => { const ok = g === w; if (!ok) bad++; console.log(ok ? 'PASS' : 'FAIL', n, '->', g); };
  await pg.goto(BASE + '/'); await pg.waitForTimeout(2500);
  await pg.goto(BASE + '/Rulebook/'); await pg.waitForTimeout(1500);
  eq('sw controls', await pg.evaluate(() => !!navigator.serviceWorker.controller), true);
  eq('cache names', (await pg.evaluate(() => caches.keys())).sort().join(','), 'dtf-data-v11,dtf-pages-v11,dtf-shell-v11');
  await ctx.setOffline(true);
  await pg.goto(BASE + '/Rulebook/').catch(() => {}); eq('offline visited', await pg.title(), 'DTF Club Rulebook');
  await pg.goto(BASE + '/Sleeper-Head-to-Head/').catch(() => {}); eq('offline unvisited', await pg.title(), 'Offline');
  await b.close(); process.exit(bad ? 1 : 0);
})();
