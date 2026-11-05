// Dark only: with the OS set to LIGHT, every page must still render dark (page background luminance low).
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
const PAGES = ['/', '/install/', '/SleeperLiveRumbles/rumbles.html', '/sleepersheet/', '/SleeperTradeNodes/', '/FAB-Management/', '/FAB-Management/lineup.html', '/Recordbook/', '/Sleeper-Head-to-Head/', '/SleeperAuction/', '/Rulebook/'];
const lum = c => { const m = c.match(/[\d.]+/g).map(Number); if (m.length > 3 && m[3] === 0) return null; return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; };
(async () => {
  const b = await chromium.launch(); let bad = 0;
  for (const path of PAGES) {
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light' }); const pg = await ctx.newPage();
    await pg.goto(BASE + path, { waitUntil: 'load' }).catch(() => {}); await pg.waitForTimeout(1500);
    const r = await pg.evaluate(() => { const g = e => getComputedStyle(e).backgroundColor; return { body: g(document.body), html: g(document.documentElement), card: (document.querySelector('table, .card, .tile, .rule, main, .panel') ? g(document.querySelector('table, .card, .tile, .rule, main, .panel')) : null), scheme: getComputedStyle(document.documentElement).colorScheme }; });
    const l = [r.body, r.html].map(lum).filter(x => x !== null);
    const ok = l.length && Math.min(...l) < 0.25;
    if (!ok) bad++; console.log(ok ? 'PASS' : 'FAIL', path, JSON.stringify(r));
    await ctx.close();
  }
  await b.close(); process.exit(bad ? 1 : 0);
})();
