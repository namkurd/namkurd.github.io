// Real taps on real tooltip triggers (phone portrait): the tooltip must end up between the bars and on screen, scroll if long,
// and survive a tap on itself. Trade Network is not covered here (its d3 CDN is blocked in some sandboxes).
//   node tests/tips-real.js
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
const CASES = [
  ['/FAB-Management/', '[data-t]', '#tip'], ['/FAB-Management/lineup.html', '[data-t]', '#tip'],
  ['/Sleeper-Head-to-Head/', 'td.tip-anchor', '#cell-tooltip'], ['/sleepersheet/', '[data-col]', '#tip'],
  ['/Recordbook/', '.tip', '#tipbox'], ['/SleeperAuction/#drafts', 'td', '.tip'],
];
const visibleTip = sel => [...document.querySelectorAll(sel)].find(e => {
  const c = getComputedStyle(e); return c.display !== 'none' && c.visibility !== 'hidden' && parseFloat(c.opacity) > 0.05 && e.offsetWidth > 0 && !e.hidden;
});
(async () => {
  const b = await chromium.launch(); let bad = 0, shown = 0;
  for (const [vn, vp] of [['390x844', { width: 390, height: 844 }], ['360x640', { width: 360, height: 640 }]]) for (const [path, trig, tsel] of CASES) {
    const ctx = await b.newContext({ viewport: vp, hasTouch: true, isMobile: true }); const pg = await ctx.newPage();
    await pg.goto(BASE + path, { waitUntil: 'load' }).catch(() => {}); await pg.waitForTimeout(1800);
    const handles = await pg.$$(trig);
    const n = handles.length;
    const picks = n > 10 ? [0, 1, 2, Math.floor(n / 3), Math.floor(n / 2), Math.floor(n * 0.7), n - 3, n - 1].map(i => handles[i]) : handles;
    let got = 0, over = 0;
    for (const h of picks) {
      try {
        await h.scrollIntoViewIfNeeded({ timeout: 800 });
        const bb = await h.boundingBox();
        if (!bb || bb.width < 1 || bb.x < 0 || bb.x + bb.width > vp.width) continue;
        await pg.touchscreen.tap(bb.x + bb.width / 2, bb.y + bb.height / 2);
      } catch (e) { continue; }
      await pg.waitForTimeout(450);
      // hover-model tools (H2H, Record Book, sleepersheet): phones emulate a hover on tap; Playwright's tap does not, so do it
      if (!(await pg.evaluate(([fn, sel]) => !!eval('(' + fn + ')')(sel), [visibleTip.toString(), tsel]))) {
        await h.evaluate(e => { const q = e.getBoundingClientRect(), o = { bubbles: true, clientX: q.left + q.width / 2, clientY: q.top + q.height / 2 }; e.dispatchEvent(new MouseEvent('mouseover', o)); e.dispatchEvent(new MouseEvent('mousemove', o)); });
        await pg.waitForTimeout(450);
      }
      const r = await pg.evaluate(([fn, sel]) => {
        const el = eval('(' + fn + ')')(sel);
        if (!el) return null;
        const sb = DTF.safeBox(), q = el.getBoundingClientRect(), cs = getComputedStyle(el);
        return { rect: [q.left, q.top, q.right, q.bottom].map(Math.round), safe: [sb.l, sb.t, sb.r, sb.b].map(Math.round),
          inside: q.left >= sb.l - 1 && q.top >= sb.t - 1 && q.right <= sb.r + 1 && q.bottom <= sb.b + 1,
          overflowing: el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1,
          tappable: cs.pointerEvents !== 'none', scrollable: /auto|scroll/.test(cs.overflowY + cs.overflowX) };
      }, [visibleTip.toString(), tsel]);
      if (!r) { await pg.touchscreen.tap(5, vp.height / 2).catch(() => {}); continue; }
      got++; shown++; if (r.overflowing) over++;
      let ok = r.inside && (!r.overflowing || (r.tappable && r.scrollable));
      if (ok && r.overflowing) {   // scrolling the tooltip must not close it, and neither must a tap on it
        await pg.evaluate(([fn, sel]) => { const e = eval('(' + fn + ')')(sel); e.scrollTop = e.scrollHeight; e.scrollLeft = e.scrollWidth; }, [visibleTip.toString(), tsel]); await pg.waitForTimeout(300);
        if (!(await pg.evaluate(([fn, sel]) => !!eval('(' + fn + ')')(sel), [visibleTip.toString(), tsel]))) { ok = false; r.closedWhileScrolling = true; }
      }
      if (ok && r.overflowing) {   // a tap on the tooltip itself must not dismiss it
        await pg.touchscreen.tap((r.rect[0] + r.rect[2]) / 2, (r.rect[1] + r.rect[3]) / 2); await pg.waitForTimeout(300);
        ok = await pg.evaluate(([fn, sel]) => !!eval('(' + fn + ')')(sel), [visibleTip.toString(), tsel]);
        if (!ok) r.dismissedByOwnTap = true;
      }
      if (!ok) { bad++; console.log('FAIL', vn, path, JSON.stringify(r)); }
      await pg.touchscreen.tap(5, vp.height - 80).catch(() => {}); await pg.waitForTimeout(150);
    }
    console.log(got ? 'ok  ' : 'NONE', vn, path, got, 'tooltips opened,', over, 'needed scrolling');
    await ctx.close();
  }
  console.log(bad ? `${bad} FAILED of ${shown}` : `all ${shown} real tooltips fit`);
  await b.close(); process.exit(bad ? 1 : 0);
})();
