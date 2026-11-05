// Home screen: screenshots (phone dark/light, desktop, installed-app with a notch) and checks the title clears the status bar.
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const standalone = () => { const mm = window.matchMedia.bind(window); window.matchMedia = q => /display-mode/.test(q) ? { matches: true, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} } : mm(q); };
  const run = async (name, vp, scheme, sa, inset) => {
    const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 2, colorScheme: scheme, hasTouch: vp.width < 900, isMobile: vp.width < 900 });
    if (sa) await ctx.addInitScript(standalone);
    const pg = await ctx.newPage();
    if (inset) { const c = await ctx.newCDPSession(pg); await c.send('Emulation.setSafeAreaInsetsOverride', { insets: { top: inset, bottom: 34, left: 0, right: 0 } }).catch(() => {}); }
    await pg.goto(BASE + '/'); await pg.waitForTimeout(1500);
    const r = await pg.evaluate(() => ({ tiles: document.querySelectorAll('.tile').length, imgs: [...document.querySelectorAll('.tile img')].filter(i => i.complete && i.naturalWidth > 0).length,
      h1top: Math.round(document.querySelector('h1').getBoundingClientRect().top), pad: getComputedStyle(document.documentElement).getPropertyValue('--dtf-top-pad').trim(), hscroll: document.documentElement.scrollWidth > innerWidth + 1,
      foot: !document.getElementById('foot').hidden }));
    const ok = r.tiles === 8 && r.imgs === 8 && !r.hscroll && (!inset || r.h1top >= inset);
    if (!ok) bad++; console.log(ok ? 'PASS' : 'FAIL', name, JSON.stringify(r));
    await pg.screenshot({ path: `tests/screens/home-${name}.png` }); await ctx.close();
  };
  await run('phone-dark', { width: 390, height: 844 }, 'dark');
  await run('phone-light', { width: 390, height: 844 }, 'light');
  await run('phone-app-notch', { width: 390, height: 844 }, 'dark', true, 47);
  await run('desktop', { width: 1280, height: 800 }, 'dark');
  await b.close(); process.exit(bad ? 1 : 0);
})();
