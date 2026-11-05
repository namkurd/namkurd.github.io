// Visual states for review: node tests/shots.js  -> tests/screens/
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
(async () => {
  const b = await chromium.launch();
  const mk = async (vp, sa, scheme) => {
    const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 2, colorScheme: scheme || 'dark' });
    if (sa) await ctx.addInitScript(() => { const mm = window.matchMedia.bind(window); window.matchMedia = q => /display-mode/.test(q) ? { matches: true, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} } : mm(q); });
    return ctx.newPage();
  };
  let p = await mk({ width: 390, height: 844 }, false);
  await p.goto(BASE + '/SleeperLiveRumbles/rumbles.html'); await p.waitForTimeout(1500); await p.screenshot({ path: 'tests/screens/v2-phone-rumbles.png' });
  await p.goto(BASE + '/SleeperTradeNodes/'); await p.waitForTimeout(1200);
  await p.evaluate(() => document.querySelector('dtf-nav').shadowRoot.querySelector('button[data-t=moves]').click()); await p.waitForTimeout(300); await p.screenshot({ path: 'tests/screens/v2-phone-sheet.png' });
  await p.goto(BASE + '/Recordbook/'); await p.waitForTimeout(1200);
  await p.mouse.move(200, 400); await p.evaluate(() => window.scrollTo(0, 700)); await p.waitForTimeout(150); await p.evaluate(() => window.scrollTo(0, 900)); await p.waitForTimeout(600);
  console.log('away after scroll down:', await p.evaluate(() => document.querySelector('dtf-nav').shadowRoot.querySelector('.ctx').classList.contains('away')), 'top-h', await p.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--dtf-top-h')));
  await p.screenshot({ path: 'tests/screens/v2-phone-scrolled.png' });
  await p.evaluate(() => window.scrollTo(0, 600)); await p.waitForTimeout(600);
  console.log('away after scroll up:', await p.evaluate(() => document.querySelector('dtf-nav').shadowRoot.querySelector('.ctx').classList.contains('away')));
  p = await mk({ width: 390, height: 844 }, true);
  await p.goto(BASE + '/Rulebook/'); await p.waitForTimeout(1500); await p.screenshot({ path: 'tests/screens/v2-phone-standalone.png' });
  p = await mk({ width: 390, height: 844 }, false, 'light');
  await p.goto(BASE + '/SleeperAuction/'); await p.waitForTimeout(1500); await p.screenshot({ path: 'tests/screens/v2-phone-light.png' });
  p = await mk({ width: 1280, height: 800 }, false);
  await p.goto(BASE + '/Recordbook/'); await p.waitForTimeout(1500); await p.screenshot({ path: 'tests/screens/v2-desktop.png' });
  await b.close();
})();
