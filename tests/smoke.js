// Smoke test. Mirror the production layout first (see docs/PLAN.md §7), serve it on :8080, then:
//   node tests/smoke.js        (BASE=http://localhost:8080 by default)
const { chromium } = require('playwright');
const fs = require('fs');
const BASE = process.env.BASE || 'http://localhost:8080';
const PAGES = [['/', 'home'], ['/SleeperLiveRumbles/rumbles.html', 'live'], ['/Recordbook/', 'history'], ['/Sleeper-Head-to-Head/', 'history'],
  ['/sleepersheet/', 'history'], ['/SleeperTradeNodes/', 'moves'], ['/FAB-Management/', 'moves'], ['/FAB-Management/lineup.html', 'moves'],
  ['/SleeperAuction/', 'moves'], ['/Rulebook/', 'league'], ['/install/', 'league']];
const VIEWS = [['phone', { width: 390, height: 844 }], ['desktop', { width: 1280, height: 800 }]];
(async () => {
  const b = await chromium.launch(); let fail = 0;
  fs.mkdirSync('tests/screens', { recursive: true });
  for (const [vn, vp] of VIEWS) for (const [path, tab] of PAGES) {
    const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
    const errs = []; pg.on('pageerror', e => errs.push(String(e)));
    await pg.goto(BASE + path, { waitUntil: 'load' }).catch(() => {});
    await pg.waitForTimeout(1500);
    const r = await pg.evaluate(() => {
      const n = document.querySelector('dtf-nav'), sr = n && n.shadowRoot; const q = x => sr && sr.querySelector(x);
      const vt = sr && sr.querySelectorAll('.vt button'), von = q('.vt button.on'), phone = innerWidth < 900;
      const on = phone ? q('.mbar .on') : q('.dsk .on');
      return { nav: !!n, active: on ? (phone ? on.dataset.t : on.textContent.trim()) : null, views: vt ? vt.length : 0, view: von ? von.textContent : null,
        pad: getComputedStyle(document.documentElement).getPropertyValue('--dtf-top-pad').trim(), hscroll: document.documentElement.scrollWidth > innerWidth + 1,
        bars: phone ? [q('.mbar').getBoundingClientRect().height, q('.ctx') && !q('.ctx').hidden ? q('.ctx').getBoundingClientRect().height : 0] : [q('.dsk').getBoundingClientRect().height] };
    });
    const want = vn === 'phone' ? tab : (path === '/' || path === '/install/' ? null : r.active);   // desktop lists every tool; just require one lit
    const ok = r.nav && r.active === want && (vn === 'phone' || want === null || !!r.active) && !r.hscroll;
    if (!ok || errs.length) fail++;
    console.log(ok && !errs.length ? 'PASS' : 'FAIL', vn, path, JSON.stringify(r), errs.slice(0, 2).join(' | '));
    await pg.screenshot({ path: `tests/screens/${vn}-${path.replace(/\W+/g, '_')}.png` });
    await ctx.close();
  }
  await b.close(); process.exit(fail ? 1 : 0);
})();
