// Tooltip fit audit (phone portrait). Forces each declared tooltip open with worst-case content at awkward
// positions and checks it stays between the bars, inside the screen, and scrollable when bigger than the space.
//   node tests/tips.js      (BASE=http://localhost:8080)
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8080';
const PAGES = [
  ['/SleeperLiveRumbles/rumbles.html', ['#pts-tooltip', '#qb-adj-tooltip', '#qb-adj-captured-tooltip', '#pfpa-tooltip', '#howto-tooltip', '#trend-tip', '#wp-tipx']],
  ['/FAB-Management/', ['#tip']], ['/FAB-Management/lineup.html', ['#tip']], ['/SleeperTradeNodes/', ['#tooltip']], ['/Recordbook/', ['#tipbox']],
  ['/SleeperAuction/', ['.tip']], ['/Sleeper-Head-to-Head/', ['#cell-tooltip']], ['/sleepersheet/', ['#tip']],
];
const VIEWS = [['390x844', { width: 390, height: 844 }], ['360x640', { width: 360, height: 640 }]];
const CONTENT = {
  tall: '<div>' + Array.from({ length: 70 }, (_, i) => `<div>Line ${i + 1}: Some Player Name scored a few points this week</div>`).join('') + '</div>',
  wide: '<table><tbody>' + Array.from({ length: 6 }, () => '<tr>' + Array.from({ length: 14 }, (_, j) => `<td style="white-space:nowrap;padding-right:12px">col${j}-value</td>`).join('') + '</tr>').join('') + '</tbody></table>',
  small: '<b>Short</b> tip',
};
(async () => {
  const b = await chromium.launch(); let bad = 0, n = 0;
  for (const [vn, vp] of VIEWS) for (const [path, sels] of PAGES) {
    const ctx = await b.newContext({ viewport: vp, hasTouch: true, isMobile: true, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
    await pg.goto(BASE + path, { waitUntil: 'load' }).catch(() => {}); await pg.waitForTimeout(1500);
    for (const sel of sels) for (const [cn, html] of Object.entries(CONTENT)) for (const [pn, pos] of [['top-left', [0, 0]], ['bottom-right', [9999, 9999]], ['middle', [120, 300]]]) {
      const r = await pg.evaluate(async ([sel, html, pos]) => {
        const el = document.querySelector(sel); if (!el) return { missing: true };
        // open any collapsed/hidden containers the tooltip lives in (e.g. a closed <details> or sheet), restored afterwards
        const undo = []; for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
          if (p.tagName === 'DETAILS' && !p.open) { p.open = true; undo.push(() => { p.open = false; }); }
          if (p.hasAttribute('hidden')) { p.removeAttribute('hidden'); undo.push(() => p.setAttribute('hidden', '')); }
          if (getComputedStyle(p).display === 'none') { const k = p.getAttribute('style'); p.style.display = 'block'; undo.push(() => (k === null ? p.removeAttribute('style') : p.setAttribute('style', k))); }
        }
        const keep = el.getAttribute('style'), kc = el.className, kh = el.hasAttribute('hidden'), ki = el.innerHTML;
        el.removeAttribute('hidden'); el.classList.add('visible'); el.innerHTML = html;
        Object.assign(el.style, { display: 'block', visibility: 'visible', opacity: '1', left: Math.min(pos[0], innerWidth - 40) + 'px', top: Math.min(pos[1], innerHeight - 20) + 'px' });
        await new Promise(r => setTimeout(r, 250));
        const sb = DTF.safeBox(), q = el.getBoundingClientRect(), cs = getComputedStyle(el);
        const out = { rect: [q.left, q.top, q.right, q.bottom].map(Math.round), safe: [sb.l, sb.t, sb.r, sb.b].map(Math.round), inside: q.left >= sb.l - 1 && q.top >= sb.t - 1 && q.right <= sb.r + 1 && q.bottom <= sb.b + 1,
          overflowing: el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1, scrollable: /auto|scroll/.test(cs.overflowY + cs.overflowX), tappable: cs.pointerEvents !== 'none', fit: el.getAttribute('data-dtf-fit') };
        if (keep === null) el.removeAttribute('style'); else el.setAttribute('style', keep); el.className = kc; if (kh) el.setAttribute('hidden', ''); el.innerHTML = ki;
        undo.reverse().forEach(f => f());
        await new Promise(r => setTimeout(r, 120));
        return out;
      }, [sel, html, pos]);
      if (r.missing) { console.log('SKIP', vn, path, sel, '(not in DOM)'); break; }
      n++; const ok = r.inside && (!r.overflowing || (r.scrollable && r.tappable));
      if (!ok) { bad++; console.log('FAIL', vn, path, sel, cn, pn, JSON.stringify(r)); }
    }
    await ctx.close();
  }
  console.log(bad ? `${bad} of ${n} FAILED` : `all ${n} checks passed`);
  await b.close(); process.exit(bad ? 1 : 0);
})();
