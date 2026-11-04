// Behaviour checks: section sheet, standalone header, ?embed=1, iframe, offline fallback.
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'allow' });
  const pg = await ctx.newPage(); const errs = []; pg.on('pageerror', e => errs.push(String(e)));
  await ctx.addInitScript(() => { try { localStorage.setItem('dtf.header', '1'); } catch (e) {} });
  await pg.goto(BASE + '/Recordbook/'); await pg.waitForTimeout(1200);
  await pg.evaluate(() => document.querySelector('dtf-nav').shadowRoot.querySelector('button[data-t=moves]').click());
  console.log('sheet items', await pg.evaluate(() => document.querySelector('dtf-nav').shadowRoot.querySelectorAll('.sheet a').length));
  await pg.screenshot({ path: 'tests/screens/sheet.png' });
  await pg.goto(BASE + '/Recordbook/?embed=1'); await pg.waitForTimeout(800);
  console.log('embed nav present (want false)', await pg.evaluate(() => !!document.querySelector('dtf-nav')));
  await pg.goto(BASE + '/'); await pg.waitForTimeout(2500);
  console.log('sw controlled', await pg.evaluate(() => !!navigator.serviceWorker.controller));
  await pg.goto(BASE + '/Rulebook/'); await pg.waitForTimeout(1500);
  await ctx.setOffline(true);
  await pg.goto(BASE + '/Rulebook/').catch(() => {}); console.log('offline visited ->', await pg.title());
  await pg.goto(BASE + '/Sleeper-Head-to-Head/').catch(() => {}); console.log('offline unvisited ->', await pg.title());
  console.log('errors', errs);
  await b.close();
})();
