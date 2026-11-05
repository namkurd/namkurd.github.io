/* DTF Club shell: <script src="/shell/nav.js" defer></script>
 * Global nav (bottom tabs on phones, top bar on desktop), a context bar (back, tool name, refresh, view tabs),
 * the install manifest, and window.DTF. Safe on any page; hidden in iframes and with ?embed=1.
 *
 * A tool declares its views BEFORE the script tag (all optional):
 *   <script>window.DTF_VIEWS = { hide: '.tabs', items: [
 *     { label: 'Records', sel: '#tab-records' },          // click this element of the tool to switch (history entry added)
 *     { label: 'Players', sel: '#tab-players', native: 1 }, // tool already makes its own history entries (e.g. hash routes)
 *     { label: 'Sit / start', href: 'lineup.html' } ] };    // separate page, or '#anchor' on this page
 *   </script>
 *
 * A tool lists its tooltip elements so they always fit the screen (before the script tag):
 *   <script>window.DTF_TIPS = ['#tip', '.tooltip'];</script>
 * Whenever one of them is shown, the shell keeps it between the bars and inside the screen, caps its size, and makes it
 * scrollable (on touch screens it also becomes tappable/scrollable and ignores taps that would dismiss it).
 */
(function () {
  'use strict';
  if (window.DTF) return;
  var W = window, D = document, root = D.documentElement;
  var embedded = false;
  try { embedded = W.self !== W.top || /[?&]embed=1\b/.test(location.search); } catch (e) { embedded = true; }

  function ls(k, v) {
    try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {}
    return null;
  }

  // Minimal registry used only if /tools.json cannot be fetched.
  var FALLBACK = { tabs: 'home:Home,live:Live,history:History,moves:Moves,league:League'.split(',').map(function (t) { t = t.split(':'); return { id: t[0], label: t[1] }; }),
    tools: ('rumbles|Rumble Central|live|/SleeperLiveRumbles/rumbles.html,recordbook|Record Book|history|/Recordbook/,h2h|Head-to-Head|history|/Sleeper-Head-to-Head/,' +
      'lifetime|Lifetime Win/Loss|history|/sleepersheet/,trades|Trade Network|moves|/SleeperTradeNodes/,fab|FAB Management|moves|/FAB-Management/,' +
      'auction|Auction Archive|moves|/SleeperAuction/,rulebook|Rulebook|league|/Rulebook/').split(',').map(function (t) { t = t.split('|'); return { id: t[0], name: t[1], tab: t[2], path: t[3] }; }),
    pages: [], external: [] };

  var DTF = W.DTF = { tools: FALLBACK.tools, registry: FALLBACK, ready: null };

  DTF.me = function () { return ls('dtf.me'); };
  DTF.setMe = function (id) { ls('dtf.me', id || null); try { W.dispatchEvent(new CustomEvent('dtf:me', { detail: id })); } catch (e) {} };
  DTF.onRefresh = function (fn) { W.addEventListener('dtf:refresh', fn); };
  DTF.refresh = function () { if (W.dispatchEvent(new CustomEvent('dtf:refresh', { cancelable: true }))) location.reload(); };
  DTF.link = function (id, name, params) {
    var t = (DTF.tools || []).filter(function (x) { return x.id === id; })[0];
    if (!t) return '#';
    var tpl = name && t.links && t.links[name] ? t.links[name] : t.path;
    return tpl.replace(/\{(\w+)\}/g, function (_, k) { return params && params[k] != null ? encodeURIComponent(params[k]) : ''; });
  };

  // ---- head injection (iOS reads these only from the page where Add to Home Screen is tapped)
  function head(sel, make) { if (!D.head.querySelector(sel)) D.head.appendChild(make()); }
  function el(tag, attrs) { var n = D.createElement(tag); for (var k in attrs) n.setAttribute(k, attrs[k]); return n; }
  function injectHead() {
    head('link[rel="manifest"]', function () { return el('link', { rel: 'manifest', href: '/manifest.webmanifest' }); });
    head('link[rel="apple-touch-icon"]', function () { return el('link', { rel: 'apple-touch-icon', href: '/shell/icons/apple-touch-icon-180.png' }); });
    head('link[rel~="icon"]', function () { return el('link', { rel: 'icon', href: '/shell/icons/favicon-32.png' }); });
    head('meta[name="theme-color"]', function () { return el('meta', { name: 'theme-color', content: '#0f1115' }); });
    head('meta[name="apple-mobile-web-app-capable"]', function () { return el('meta', { name: 'apple-mobile-web-app-capable', content: 'yes' }); });
    head('meta[name="mobile-web-app-capable"]', function () { return el('meta', { name: 'mobile-web-app-capable', content: 'yes' }); });
    head('meta[name="apple-mobile-web-app-title"]', function () { return el('meta', { name: 'apple-mobile-web-app-title', content: 'DTF Club' }); });
    head('meta[name="apple-mobile-web-app-status-bar-style"]', function () { return el('meta', { name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent' }); });
    var vp = D.head.querySelector('meta[name="viewport"]');
    if (vp && !/viewport-fit/.test(vp.content)) vp.content += ', viewport-fit=cover';
  }

  function sw() {
    if (!('serviceWorker' in navigator) || (location.protocol !== 'https:' && location.hostname !== 'localhost')) return;
    // Rumble Central used to register its own no-op worker at /SleeperLiveRumbles/; it would shadow the root one.
    navigator.serviceWorker.getRegistrations().then(function (rs) {
      rs.forEach(function (r) { if (/\/SleeperLiveRumbles\/$/.test(r.scope)) r.unregister(); });
    }).catch(function () {});
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
  }

  function loadRegistry() {
    try { var c = sessionStorage.getItem('dtf.registry'); if (c) return Promise.resolve(JSON.parse(c)); } catch (e) {}
    return fetch('/tools.json', { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw 0; return r.json(); }).then(function (j) {
      try { sessionStorage.setItem('dtf.registry', JSON.stringify(j)); } catch (e) {}
      return j;
    });
  }

  function dirOf(p) { return p.replace(/[^\/]*$/, ''); }
  function activeItem(reg) {
    var p = location.pathname.replace(/index\.html$/, '');
    if (p === '/') return { tab: 'home' };
    var best = null;
    [].concat(reg.tools || [], reg.pages || [], reg.external || []).filter(function (x) { return x.path; }).forEach(function (x) {
      var d = dirOf(x.path), hit = p === x.path || (d !== '/' && p.indexOf(d) === 0);
      if (hit && (!best || dirOf(x.path).length > dirOf(best.path).length)) best = x;
    });
    return best;
  }

  var ICONS = {
    home: 'M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
    live: 'M13 2L4 14h6l-1 8 9-12h-6z',
    history: 'M13 3a9 9 0 0 0-9 9H1l4 4 4-4H6a7 7 0 1 1 2 5l-1.4 1.4A9 9 0 1 0 13 3zm-1 5v5l4 2 .8-1.4-3.3-1.9V8z',
    moves: 'M7 7h11l-3-3 1.4-1.4L22 8l-5.6 5.4L15 12l3-3H7zm10 10H6l3 3-1.4 1.4L2 16l5.6-5.4L9 12l-3 3h11z',
    league: 'M5 3h11a3 3 0 0 1 3 3v15H8a3 3 0 0 1-3-3zm3 0v15a1 1 0 0 0 1 1h8V6a1 1 0 0 0-1-1z'
  };
  function icon(id) { return '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="' + (ICONS[id] || ICONS.league) + '"/></svg>'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  // Design: phone = one slim top bar (view tabs; back/refresh only in the installed app) that hides while you scroll down,
  // plus a bottom tab bar whose group tabs show the tool you are in. Desktop = one top bar listing every tool, view tabs underneath.
  var CSS = ':host{all:initial}*{box-sizing:border-box}button{font:inherit;color:inherit}a{color:inherit}' +
    ':focus-visible{outline:2px solid var(--ac);outline-offset:-2px;border-radius:8px}' +
    '.bar,.ctx{background:var(--bg);-webkit-backdrop-filter:saturate(1.4) blur(14px);backdrop-filter:saturate(1.4) blur(14px)}' +
    '.bar{position:fixed;z-index:25;left:0;right:0;bottom:0;display:flex;border-top:1px solid var(--bd);padding-bottom:env(safe-area-inset-bottom);font:600 11px/1.1 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
    '.bar>a,.bar>button{flex:1;min-width:0;height:56px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;color:var(--dim);background:none;border:0;text-decoration:none;cursor:pointer;-webkit-tap-highlight-color:transparent}' +
    '.bar .ic{display:flex;align-items:center;justify-content:center;width:56px;height:28px;border-radius:14px;transition:background .15s}' +
    '.bar .on{color:var(--tx)}.bar .on .ic{background:var(--acbg);color:var(--ac)}.bar .lb{max-width:100%;padding:0 4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '.bar .grp .lb::after{content:" \\25B4";font-size:8px;opacity:.7}.dk{display:none}' +
    '.ctx{position:fixed;z-index:25;top:0;left:0;right:0;height:calc(44px + env(safe-area-inset-top));padding-top:env(safe-area-inset-top);border-bottom:1px solid var(--bd);display:flex;align-items:stretch;font:14px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--tx);transition:transform .22s ease}' +
    '.ctx[hidden]{display:none}.ctx.away{transform:translateY(-100%)}' +
    '.ib{flex:none;width:44px;background:none;border:0;font-size:22px;cursor:pointer;color:var(--tx);-webkit-tap-highlight-color:transparent}.ib[hidden]{display:none}' +
    '.ttl{flex:1;min-width:0;align-self:center;text-align:center;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 8px}' +
    '.vt{flex:1;min-width:0;display:flex;overflow-x:auto;scrollbar-width:none;-webkit-mask-image:linear-gradient(90deg,transparent 0,#000 12px,#000 calc(100% - 12px),transparent 100%);mask-image:linear-gradient(90deg,transparent 0,#000 12px,#000 calc(100% - 12px),transparent 100%)}.vt::-webkit-scrollbar{display:none}' +
    '.vt button{flex:none;position:relative;height:44px;padding:0 16px;background:none;border:0;color:var(--dim);cursor:pointer;white-space:nowrap;font-weight:500;-webkit-tap-highlight-color:transparent}' +
    '.vt button.on{color:var(--tx);font-weight:700}.vt button.on::after{content:"";position:absolute;left:14px;right:14px;bottom:0;height:3px;border-radius:3px 3px 0 0;background:var(--ac)}' +
    '.sheet{position:fixed;z-index:26;left:8px;right:8px;bottom:calc(64px + env(safe-area-inset-bottom));background:var(--bg2);border:1px solid var(--bd);border-radius:16px;padding:6px;font:15px system-ui,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.45);transform-origin:bottom center;animation:up .16s ease-out}' +
    '@keyframes up{from{opacity:0;transform:translateY(10px) scale(.98)}}@media(prefers-reduced-motion:reduce){.sheet{animation:none}.ctx{transition:none}}' +
    '.sheet a{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:52px;padding:8px 12px;border-radius:10px;color:var(--tx);text-decoration:none}.sheet a:active,.sheet a:hover{background:var(--acbg)}' +
    '.sheet a small{display:block;color:var(--dim);font-size:12px;margin-top:1px}.sheet a.on b{color:var(--ac)}.sheet a.on::after{content:"\\2713";color:var(--ac);font-weight:700}.sheet a.xt::after{content:"\\2197";color:var(--dim)}' +
    '.sheet[hidden],.scrim[hidden]{display:none}.scrim{position:fixed;inset:0;z-index:25;background:rgba(0,0,0,.35)}' +
    '@media(min-width:900px){.bar{top:0;bottom:auto;height:48px;border-top:0;border-bottom:1px solid var(--bd);padding:0 16px;justify-content:flex-start;align-items:center;gap:2px;font:500 14px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
    '.bar>a,.bar>button{flex:none;height:36px;flex-direction:row;gap:0;padding:0 12px;border-radius:8px}.bar>a:hover,.bar>button:hover{background:var(--acbg);color:var(--tx)}.bar .ic,.mb{display:none}.bar .on{background:var(--acbg);color:var(--ac)}.bar .on .lb{font-weight:700}' +
    '.bar .grp .lb::after{content:none}.bar .brand{font-weight:800;color:var(--tx);margin-right:10px;letter-spacing:.02em}.bar .sp{flex:1}.dk{display:flex}' +
    '.ctx{top:48px;height:44px;padding:0 16px;border-bottom:1px solid var(--bd)}.ctx.nov,.ctx .ib,.ctx .ttl{display:none}.vt{-webkit-mask-image:none;mask-image:none}.vt button{padding:0 14px}.vt button:first-child{margin-left:-14px}' +
    '.sheet{left:auto;right:16px;top:52px;bottom:auto;min-width:260px;transform-origin:top right}}';

  var VIEWS = null;   // the tool's declared views, normalized
  var UI = {};

  function isOn(e) {
    return e.getAttribute('aria-pressed') === 'true' || e.getAttribute('aria-selected') === 'true' || /(^|\s)(active|on)(\s|$)/.test(e.className || '');
  }
  function currentView() {
    var i, it, path = location.pathname.split('/').pop() || 'index.html';
    for (i = 0; i < VIEWS.items.length; i++) {
      it = VIEWS.items[i];
      if (it.sel) { var e = D.querySelector(it.sel); if (e && isOn(e)) return i; }
      else if (it.href && it.href.charAt(0) === '#') { if (location.hash === it.href) return i; }
      else if (it.href && it.href.split(/[?#]/)[0].split('/').pop() === path) return i;
    }
    var f = VIEWS.items[0];
    return f && f.href && f.href.charAt(0) === '#' && !location.hash ? 0 : -1;
  }
  function paintViews() {
    if (!VIEWS || !UI.vt) return;
    var cur = currentView();
    [].forEach.call(UI.vt.children, function (b, i) { b.className = i === cur ? 'on' : ''; if (i === cur) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); });
  }
  function pick(i, fromHistory) {
    var it = VIEWS.items[i];
    if (it.sel) {
      var e = D.querySelector(it.sel); if (!e) return;
      if (!fromHistory && !it.native) { try { history.pushState(Object.assign({}, history.state, { dtfView: i }), ''); } catch (x) {} }
      e.click();
    } else if (it.href) {
      if (it.href.charAt(0) === '#') location.hash = it.href; else location.href = it.href;
    }
    setTimeout(paintViews, 0);
  }
  function initViews() {
    var cfg = W.DTF_VIEWS;
    if (!cfg || !cfg.items || !cfg.items.length) return;
    VIEWS = cfg;
    if (cfg.hide) { var st = D.createElement('style'); st.textContent = 'body.dtf-has-nav ' + cfg.hide.split(',').join(',body.dtf-has-nav ') + '{display:none!important}'; D.head.appendChild(st); }
    VIEWS.initial = Math.max(0, currentView());
    try { history.replaceState(Object.assign({}, history.state, { dtfView: VIEWS.initial }), ''); } catch (e) {}
    W.addEventListener('popstate', function (ev) {
      var s = ev.state;
      if (s && typeof s.dtfView === 'number') pick(s.dtfView, true);
      else if (s === null && !VIEWS.items.some(function (x) { return x.native || !x.sel; }) && VIEWS.items[VIEWS.initial]) pick(VIEWS.initial, true);
    });
    W.addEventListener('hashchange', paintViews);
    VIEWS.items.forEach(function (it) {
      var e = it.sel && D.querySelector(it.sel);
      if (e && W.MutationObserver) new MutationObserver(paintViews).observe(e, { attributes: true, attributeFilter: ['class', 'aria-pressed', 'aria-selected'] });
    });
  }

  // ---- tooltips: keep every declared tooltip on screen, between the bars, and scrollable when it is bigger than the space
  function safeBox() {
    var t = 6, b = W.innerHeight - 6, h = D.querySelector('dtf-nav'), sr = h && h.shadowRoot;
    if (sr) {
      var c = sr.querySelector('.ctx'), dk = sr.querySelector('.bar.dsk'), mb = sr.querySelector('.bar.mbar'), r;
      if (c && !c.hidden && getComputedStyle(c).display !== 'none' && !c.classList.contains('away')) { r = c.getBoundingClientRect(); if (r.height) t = Math.max(t, r.bottom + 6); }
      if (dk && getComputedStyle(dk).display !== 'none') t = Math.max(t, dk.getBoundingClientRect().bottom + 6);
      if (mb && getComputedStyle(mb).display !== 'none') b = Math.min(b, mb.getBoundingClientRect().top - 6);
    }
    return { l: 6, t: t, r: W.innerWidth - 6, b: b };
  }
  DTF.safeBox = safeBox;
  // 'yes', 'no', or 'fading' (an opacity transition is still running, so look again shortly)
  function tipState(el) {
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || !el.offsetWidth) return 'no';
    if (parseFloat(cs.opacity) > 0.05) return 'yes';
    return parseFloat(cs.transitionDuration) > 0 ? 'fading' : 'no';
  }
  var fitting = false;
  function fitTip(el) {
    if (fitting) return false;
    var state = tipState(el);
    if (state !== 'yes') {
      if (el.hasAttribute('data-dtf-fit')) {   // it was hidden again: give back its taps so an invisible tooltip never blocks the page
        fitting = true; el.style.removeProperty('pointer-events'); el.style.removeProperty('touch-action'); el.removeAttribute('data-dtf-fit'); fitting = false;
      }
      return state === 'fading';
    }
    fitting = true;
    try {
      var sb = safeBox(), st = el.style, aw = sb.r - sb.l, ah = sb.b - sb.t, cs = getComputedStyle(el);
      var mw = parseFloat(cs.maxWidth), mh = parseFloat(cs.maxHeight);
      if (!(mw <= aw)) st.setProperty('max-width', aw + 'px', 'important');
      if (!(mh <= ah)) st.setProperty('max-height', ah + 'px', 'important');
      st.setProperty('overflow', 'auto', 'important'); st.setProperty('overscroll-behavior', 'contain', 'important');
      st.setProperty('-webkit-overflow-scrolling', 'touch');
      st.translate = '';                       // measure where the tool put it, then nudge it inside the safe box
      var r = el.getBoundingClientRect(), dx = 0, dy = 0;
      if (r.right > sb.r) dx = sb.r - r.right;
      if (r.left + dx < sb.l) dx = sb.l - r.left;
      if (r.bottom > sb.b) dy = sb.b - r.bottom;
      if (r.top + dy < sb.t) dy = sb.t - r.top;
      if (dx || dy) st.translate = Math.round(dx) + 'px ' + Math.round(dy) + 'px';
      var more = el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
      if (more && W.matchMedia && W.matchMedia('(hover: none)').matches) {   // touch: let a long tooltip be scrolled, and don't let taps on it dismiss it
        st.setProperty('pointer-events', 'auto', 'important'); st.setProperty('touch-action', 'pan-x pan-y', 'important');
        if (!el.__dtfTap) { el.__dtfTap = 1; ['click', 'pointerdown', 'touchstart', 'mousedown'].forEach(function (n) { el.addEventListener(n, function (e) { e.stopPropagation(); }); }); }
      } else { st.removeProperty('pointer-events'); st.removeProperty('touch-action'); }
      el.setAttribute('data-dtf-fit', more ? 'scroll' : 'ok');
    } catch (e) { if (W.console) console.warn('dtf tip fit failed', e); }
    fitting = false;
    return false;
  }
  function initTips() {
    var sels = W.DTF_TIPS; if (!sels || !sels.length || !W.MutationObserver) return;
    var queued = false, seen = [];
    function run() { queued = false; var again = false; seen.forEach(function (el) { if (fitTip(el)) again = true; }); if (again) setTimeout(ping, 160); }
    function ping() { if (!queued && !fitting) { queued = true; W.requestAnimationFrame(run); } }
    function watch() {
      sels.forEach(function (sel) {
        [].forEach.call(D.querySelectorAll(sel), function (el) {
          if (seen.indexOf(el) > -1) return;
          seen.push(el);
          new MutationObserver(function () { if (!fitting) ping(); }).observe(el, { attributes: true, attributeFilter: ['style', 'class', 'hidden', 'aria-hidden'], childList: true, subtree: true, characterData: true });
        });
      });
    }
    // moving from a trigger onto a tooltip you are scrolling must not read as "mouse left the trigger" (hover-model tools hide on that)
    W.addEventListener('mouseout', function (e) { var t = e.relatedTarget; if (t && t.closest && t.closest('[data-dtf-fit="scroll"]')) e.stopPropagation(); }, true);
    watch();
    new MutationObserver(watch).observe(D.body, { childList: true });   // tooltips a tool creates later
    W.addEventListener('resize', ping);
  }

  function standalone() { return !!((W.matchMedia && W.matchMedia('(display-mode: standalone)').matches) || navigator.standalone); }
  function isHome() { return location.pathname === '/' || location.pathname === '/index.html'; }
  function mobile() { return W.innerWidth < 900; }
  var AWAY = false;
  // Space taken by the fixed top UI. Known without measuring, so the page never shifts when the nav appears.
  function topPad() {
    var inset = 'env(safe-area-inset-top)';
    if (!mobile()) return (48 + (VIEWS && !isHome() ? 44 : 0)) + 'px';
    if (isHome()) return standalone() ? inset : '0px';
    return VIEWS || standalone() ? 'calc(44px + ' + inset + ')' : '0px';
  }
  // --dtf-top-pad is static (body padding); --dtf-top-h follows the bar while it hides on scroll (tools offset sticky things with it)
  function setTop() {
    var pad = topPad(), h = AWAY && mobile() ? (standalone() ? 'env(safe-area-inset-top)' : '0px') : pad;
    root.style.setProperty('--dtf-top-pad', pad); root.style.setProperty('--dtf-top-h', h);
  }
  function away(on) { if (on === AWAY || !UI.ctx) return; AWAY = on; UI.ctx.classList.toggle('away', on); setTop(); }
  function autoHide() {
    var last = W.scrollY, tick = false;
    W.addEventListener('scroll', function () {
      if (tick) return; tick = true;
      W.requestAnimationFrame(function () {
        tick = false;
        if (!mobile() || !UI.ctx || UI.ctx.hidden) return;
        var y = W.scrollY, dy = y - last;
        if (y <= 60) { away(false); last = y; return; }
        if (Math.abs(dy) < 8) return;
        last = y; away(dy > 0 && y > 120);
      });
    }, { passive: true });
    D.addEventListener('focusin', function () { away(false); });
  }

  function build(reg) {
    var tabs = reg.tabs || FALLBACK.tabs, act = activeItem(reg) || {}, home = act.tab === 'home', sa = standalone();
    var host = D.createElement('dtf-nav'), s = host.attachShadow({ mode: 'open' });
    var light = W.matchMedia && W.matchMedia('(prefers-color-scheme: light)').matches;
    var vars = light ? '--bg:rgba(255,255,255,.97);--bg2:#fff;--bd:#dfe2ea;--tx:#14171f;--dim:#5d6577;--ac:#c4601a;--acbg:rgba(196,96,26,.12)'
      : '--bg:rgba(20,23,29,.97);--bg2:#1b1f27;--bd:#2a2f3a;--tx:#e8eaf0;--dim:#9097a8;--ac:#f0914a;--acbg:rgba(240,145,74,.16)';
    function items(tab) { return [].concat(reg.tools || [], reg.pages || [], reg.external || []).filter(function (x) { return x.tab === tab; }); }
    var name = act.name || (home ? 'DTF Club' : D.title || 'DTF Club');
    var ctxHidden = home || (!VIEWS && !sa);
    var html = '<style>:host{' + vars + '}' + CSS + '.dsk{display:none}@media(min-width:900px){.bar.mbar{display:none}.bar.dsk{display:flex}}</style>' +
      '<div class="ctx' + (VIEWS ? '' : ' nov') + '"' + (ctxHidden ? ' hidden' : '') + '><button class="ib" id="back" aria-label="Back" hidden>‹</button>' +
      (VIEWS ? '<div class="vt" role="tablist" aria-label="' + esc(name) + ' views"></div>' : '<div class="ttl">' + esc(name) + '</div>') +
      '<button class="ib" id="rf" aria-label="Refresh"' + (sa ? '' : ' hidden') + '>⟳</button></div>' +
      '<div class="scrim" hidden></div><div class="sheet" role="dialog" aria-label="Menu" hidden></div>';
    // phone: bottom tabs. A group tab shows the tool you are in; a single-tool tab goes straight there.
    html += '<nav class="bar mbar" aria-label="DTF Club">';
    tabs.forEach(function (t) {
      var list = items(t.id), on = act.tab === t.id, cur = on && act.name ? (act.short || act.name) : null;
      var inner = '<span class="ic">' + icon(t.id) + '</span><span class="lb">' + esc(t.id !== 'home' && list.length > 1 && cur ? cur : t.label) + '</span>';
      var one = t.id === 'home' ? { path: '/' } : list.length === 1 && (list[0].path || list[0].url) ? list[0] : null;
      if (one) html += '<a href="' + esc(one.path || one.url) + '" data-t="' + t.id + '"' + (on ? ' class="on" aria-current="page"' : '') + '>' + inner + '</a>';
      else html += '<button class="grp' + (on ? ' on' : '') + '" data-t="' + t.id + '" aria-haspopup="dialog" aria-expanded="false">' + inner + '</button>';
    });
    // desktop: every tool on one bar
    html += '</nav><nav class="bar dsk" aria-label="DTF Club"><a class="brand" href="/">DTF Club</a>';
    [].concat(reg.tools || [], reg.pages || []).forEach(function (x) {
      html += '<a href="' + esc(x.path) + '"' + (act.id === x.id ? ' class="on" aria-current="page"' : '') + '><span class="lb">' + esc(x.short || x.name) + '</span></a>';
    });
    html += '<span class="sp"></span>' + ((reg.external || []).length ? '<button id="more" aria-haspopup="dialog" aria-expanded="false"><span class="lb">More ▾</span></button>' : '') + '</nav>';
    s.innerHTML = html;
    UI.ctx = s.querySelector('.ctx'); UI.vt = s.querySelector('.vt');
    var sheet = s.querySelector('.sheet'), scrim = s.querySelector('.scrim'), opener = null;
    function close() { sheet.hidden = scrim.hidden = true; if (opener) { opener.setAttribute('aria-expanded', 'false'); opener.focus({ preventScroll: true }); opener = null; } }
    function open(btn, list) {
      if (!sheet.hidden && opener === btn) return close();
      if (opener) opener.setAttribute('aria-expanded', 'false');
      opener = btn; btn.setAttribute('aria-expanded', 'true');
      sheet.innerHTML = list.map(function (x) {
        var ext = !x.path;
        return '<a href="' + esc(x.path || x.url) + '"' + (ext ? ' target="_blank" rel="noopener"' : '') + ' class="' + (act.id === x.id ? 'on ' : '') + (ext ? 'xt' : '') + '"><span><b>' + esc(x.name) + '</b>' + (x.description ? '<small>' + esc(x.description) + '</small>' : '') + '</span></a>';
      }).join('');
      sheet.hidden = scrim.hidden = false;
    }
    s.querySelectorAll('button[data-t]').forEach(function (b) { b.addEventListener('click', function () { open(b, items(b.getAttribute('data-t'))); }); });
    var more = s.getElementById('more'); if (more) more.addEventListener('click', function () { open(more, reg.external || []); });
    scrim.addEventListener('click', close);
    sheet.addEventListener('click', function (e) { if (e.target.closest('a')) close(); });
    D.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !sheet.hidden) close(); });
    W.addEventListener('scroll', function () { if (!sheet.hidden) close(); }, { passive: true });
    var back = s.getElementById('back');
    if (sa && !home && history.length > 1) back.hidden = false;
    back.addEventListener('click', function () { history.back(); });
    s.getElementById('rf').addEventListener('click', DTF.refresh);
    if (VIEWS) {
      UI.vt.innerHTML = VIEWS.items.map(function (it, i) { return '<button role="tab" data-i="' + i + '">' + esc(it.label) + '</button>'; }).join('');
      UI.vt.addEventListener('click', function (e) { var b = e.target.closest('button[data-i]'); if (b) { away(false); pick(+b.getAttribute('data-i')); } });
      paintViews();
    }
    if (sa) root.classList.add('dtf-standalone');
    return host;
  }

  function layout() {
    var css = D.createElement('style');
    css.textContent = ':root{--dtf-top-pad:0px;--dtf-top-h:0px;--dtf-nav-h:0px}' +
      'body.dtf-has-nav{padding-top:var(--dtf-top-pad);padding-bottom:calc(56px + env(safe-area-inset-bottom));--dtf-nav-h:calc(56px + env(safe-area-inset-bottom))}' +
      '@media(min-width:900px){body.dtf-has-nav{padding-bottom:0;--dtf-nav-h:0px}}';
    D.head.appendChild(css);
    D.body.classList.add('dtf-has-nav');
    setTop();   // reserve the space before the registry arrives, so nothing jumps
  }

  var hiddenAt = 0;
  D.addEventListener('visibilitychange', function () {
    if (D.hidden) { hiddenAt = Date.now(); return; }
    if (hiddenAt && Date.now() - hiddenAt > 10 * 60 * 1000) DTF.refresh();
    hiddenAt = 0;
  });

  function start() {
    try { injectHead(); sw(); initTips(); } catch (e) {}
    if (embedded) { DTF.ready = Promise.resolve(DTF.registry); return; }
    try { initViews(); layout(); autoHide(); } catch (e) {}
    DTF.ready = loadRegistry().catch(function () { return FALLBACK; }).then(function (reg) {
      DTF.registry = reg; DTF.tools = reg.tools || FALLBACK.tools;
      try {
        D.body.appendChild(build(reg)); setTop();
        W.addEventListener('resize', setTop);
      } catch (e) { if (W.console) console.warn('dtf-nav failed', e); }
      return reg;
    });
  }
  if (D.readyState === 'loading') D.addEventListener('DOMContentLoaded', start); else start();
})();
