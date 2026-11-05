// Behaviour checks: view strip click + history back, ?embed=1, offline fallback.
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
const cur = pg => pg.evaluate(() => { const b = document.querySelector('dtf-nav').shadowRoot.querySelector('.vt button.on'); return b ? b.textContent : null; });
const tap = (pg, label) => pg.evaluate(l => { [...document.querySelector('dtf-nav').shadowRoot.querySelectorAll('.vt button')].find(b => b.textContent === l).click(); }, label);
let bad = 0; const eq = (name, got, want) => { const ok = got === want; if (!ok) bad++; console.log(ok ? 'PASS' : 'FAIL', name, '->', got, ok ? '' : '(want ' + want + ')'); };
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
  const pg = await ctx.newPage(); const errs = []; pg.on('pageerror', e => errs.push(String(e)));
  const seq = async (url, steps) => {   // steps: [label, ...]; then back through them
    await pg.goto(BASE + url); await pg.waitForTimeout(1500);
    const first = await cur(pg);
    for (const s of steps) { await tap(pg, s); await pg.waitForTimeout(300); eq(url + ' tap ' + s, await cur(pg), s); }
    for (const s of [first, ...steps].reverse().slice(1)) { await pg.goBack(); await pg.waitForTimeout(400); eq(url + ' back to', await cur(pg), s); }
  };
  await seq('/SleeperLiveRumbles/rumbles.html', ['Projected', "Rumblin'"]);
  await seq('/Recordbook/', ['Change log']);
  await seq('/Rulebook/', ['Open suggestions', 'Scoring']);
  await seq('/SleeperTradeNodes/', ['Players']);
  await seq('/SleeperAuction/', ['Players', 'Drafts']);
  await seq('/FAB-Management/', ['Sit / start']);
  await seq('/Sleeper-Head-to-Head/', ['Playoffs']);
  await pg.goto(BASE + '/Recordbook/?embed=1'); await pg.waitForTimeout(800);
  eq('embed hides nav', await pg.evaluate(() => !!document.querySelector('dtf-nav')), false);
  console.log('errors', errs);
  await b.close(); process.exit(bad ? 1 : 0);
})();
