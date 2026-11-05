// Trade Network on a phone: every node (and its label) must be inside the visible graph. d3 is loaded from a local copy when the CDN is blocked:
//   D3=/path/to/d3.min.js node tests/trade-fit.js
const { chromium } = require('playwright');
const fs = require('fs');
const BASE = process.env.BASE || 'http://localhost:8080';
let bad = 0;
(async () => {
  const b = await chromium.launch();
  for (const [name, vp] of [['390x844', { width: 390, height: 844 }], ['360x740', { width: 360, height: 740 }], ['1280x800', { width: 1280, height: 800 }]]) {
    const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 2, hasTouch: vp.width < 900, isMobile: vp.width < 900 }); const pg = await ctx.newPage();
    if (process.env.D3) await pg.route(/d3\.min\.js/, r => r.fulfill({ contentType: 'application/javascript', body: fs.readFileSync(process.env.D3) }));
    await pg.goto(BASE + '/SleeperTradeNodes/'); await pg.waitForTimeout(4500);
    const r = await pg.evaluate(() => {
      const svg = document.querySelector('#graph'), box = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
      const nodes = [...svg.querySelectorAll('.node, g.node, .node-label, circle')].map(e => e.getBoundingClientRect()).filter(q => q.width > 0);
      const out = nodes.filter(q => q.left < box.left - 1 || q.right > box.right + 1 || q.top < box.top - 1 || q.bottom > box.bottom + 1).length;
      return { nodes: nodes.length, outside: out, scale: +(vb.width / box.width).toFixed(2) };
    });
    const ok = r.nodes > 5 && r.outside === 0; if (!ok) bad++;
    console.log(ok ? 'PASS' : 'FAIL', name, JSON.stringify(r));
    await pg.screenshot({ path: `tests/screens/trade-${name}.png`, clip: { x: 0, y: 0, width: vp.width, height: Math.min(vp.height, 760) } });
    await ctx.close();
  }
  await b.close(); process.exit(bad ? 1 : 0);
})();
