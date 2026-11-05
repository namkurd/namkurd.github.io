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
      foot: !document.getElementById('foot').hidden, over: document.documentElement.scrollHeight - innerHeight }));
    const ok = r.tiles === 9 && r.imgs === 9 && !r.hscroll && (!inset || (r.h1top >= inset && r.over <= 0));   // installed app with a notch: still one screen
    if (!ok) bad++; console.log(ok ? 'PASS' : 'FAIL', name, JSON.stringify(r));
    await pg.screenshot({ path: `tests/screens/home-${name}.png` }); await ctx.close();
  };
  // one screen, no scrolling: tiles + feed fit on an iPhone-sized screen and on desktop
  const fit = async (name, vp, mutate) => {
    const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1, hasTouch: vp.width < 900, isMobile: vp.width < 900 }); const pg = await ctx.newPage();
    if (mutate) await mutate(pg);
    await pg.goto(BASE + '/'); await pg.waitForTimeout(1500);
    let worst = 0;   // each tab in turn: the Trades tab (winner tag + every player) is the tallest
    for (const t of await pg.locator('#tabs button').all()) { if (await t.isVisible()) { await t.click(); await pg.waitForTimeout(200); worst = Math.max(worst, await pg.evaluate(() => document.documentElement.scrollHeight - innerHeight)); } }
    const r = await pg.evaluate(() => ({ scroll: document.documentElement.scrollHeight - innerHeight, feed: !document.getElementById('feed').hidden, tiles: document.querySelectorAll('.tile').length,
      panels: [...document.querySelectorAll('.panel')].map(p => p.querySelectorAll('.row').length), badLinks: [...document.querySelectorAll('.row')].filter(a => !/^(\/[A-Za-z]|https:\/\/dtf-club\.slack\.com\/)/.test(a.getAttribute('href'))).length }));
    r.scroll = Math.max(r.scroll, worst);
    const ok = r.scroll <= 0 && r.tiles === 9 && r.badLinks === 0 && (name.includes('nofeed') ? !r.feed : r.feed && r.panels.length >= 4 && r.panels.every(n => n <= 3));
    if (!ok) bad++; console.log(ok ? 'PASS' : 'FAIL', 'fits', name, JSON.stringify(r)); await ctx.close();
  };
  await fit('390x844', { width: 390, height: 844 }); await fit('393x852', { width: 393, height: 852 }); await fit('430x932', { width: 430, height: 932 });
  await fit('1280x800', { width: 1280, height: 800 }); await fit('1366x768', { width: 1366, height: 768 }); await fit('1024x768 tabs', { width: 1024, height: 768 });
  await fit('390x844 nofeed', { width: 390, height: 844 }, pg => pg.route(/\/(feed|slack)\.json/, r => r.fulfill({ status: 404, body: '' })));   // tiles still render without the feed
  await run('phone-dark', { width: 390, height: 844 }, 'dark');
  await run('phone-light', { width: 390, height: 844 }, 'light');
  await run('phone-app-notch', { width: 390, height: 844 }, 'dark', true, 47);
  await run('desktop', { width: 1280, height: 800 }, 'dark');
  await b.close(); process.exit(bad ? 1 : 0);
})();
