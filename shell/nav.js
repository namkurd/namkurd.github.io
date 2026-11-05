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

  var CSS = ':host{all:initial}*{box-sizing:border-box}button{font:inherit}' +
    '.bar{position:fixed;z-index:25;left:0;right:0;bottom:0;display:flex;background:var(--bg);border-top:1px solid var(--bd);padding-bottom:env(safe-area-inset-bottom);font:12px/1.2 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
    '.bar>a,.bar>button{flex:1;min-width:0;height:56px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;color:var(--dim);background:none;border:0;text-decoration:none;cursor:pointer;-webkit-tap-highlight-color:transparent}' +
    '.bar .on{color:var(--ac)}' +
    '.ctx{position:fixed;z-index:25;top:0;left:0;right:0;background:var(--bg);border-bottom:1px solid var(--bd);padding-top:env(safe-area-inset-top);font:14px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--tx)}' +
    '.ctx[hidden]{display:none}.r1{height:40px;display:flex;align-items:center;justify-content:space-between;font-weight:600}' +
    '.r1 button{background:none;border:0;color:var(--tx);font-size:22px;width:48px;height:40px;cursor:pointer}.r1 button[hidden]{display:block;visibility:hidden}' +
    '.r1 span,.nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '.vt{display:flex;overflow-x:auto;scrollbar-width:none;border-top:1px solid var(--bd)}.vt::-webkit-scrollbar{display:none}.vt[hidden]{display:none}' +
    '.vt button{flex:none;height:38px;padding:0 14px;background:none;border:0;border-bottom:2px solid transparent;color:var(--dim);cursor:pointer;white-space:nowrap}' +
    '.vt button.on{color:var(--ac);border-bottom-color:var(--ac);font-weight:600}.nm{display:none}' +
    '.sheet{position:fixed;z-index:26;left:0;right:0;bottom:calc(56px + env(safe-area-inset-bottom));background:var(--bg);border-top:1px solid var(--bd);border-radius:14px 14px 0 0;padding:6px 0;font:15px system-ui,sans-serif;box-shadow:0 -8px 30px rgba(0,0,0,.35)}' +
    '.sheet a{display:block;padding:12px 18px;color:var(--tx);text-decoration:none}.sheet a small{display:block;color:var(--dim);font-size:12px}.sheet a.on{color:var(--ac)}' +
    '.sheet[hidden],.scrim[hidden]{display:none}.scrim{position:fixed;inset:0;z-index:25;background:rgba(0,0,0,.4)}' +
    '@media(min-width:900px){.bar{top:0;bottom:auto;height:48px;border-top:0;border-bottom:1px solid var(--bd);padding:0 12px;justify-content:center;gap:4px}' +
    '.bar>a,.bar>button{flex:none;height:48px;flex-direction:row;gap:8px;padding:0 16px;font-size:14px}' +
    '.ctx.nov{display:none}.ctx{top:48px;padding-top:0;display:flex;align-items:center;gap:12px;padding:0 16px}.r1{display:none}.vt{border-top:0;flex:1}.nm{display:block;font-weight:600}' +
    '.sheet{left:auto;right:auto;top:48px;bottom:auto;min-width:260px;border:1px solid var(--bd);border-radius:0 0 12px 12px}}';

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

  function setTop() {
    var c = UI.ctx; if (!c || c.hidden) { root.style.setProperty('--dtf-top-h', (W.innerWidth >= 900 ? 48 : 0) + 'px'); return; }
    var h = c.getBoundingClientRect().height + (W.innerWidth >= 900 ? 48 : 0);
    root.style.setProperty('--dtf-top-h', h + 'px');
  }

  function build(reg) {
    var tabs = reg.tabs || FALLBACK.tabs, act = activeItem(reg) || {}, home = act.tab === 'home';
    var host = D.createElement('dtf-nav'), s = host.attachShadow({ mode: 'open' });
    var dark = W.matchMedia && W.matchMedia('(prefers-color-scheme: light)').matches ? 0 : 1;
    var vars = dark ? '--bg:#14171d;--bd:#2a2f3a;--tx:#e8eaf0;--dim:#9097a8;--ac:#f0914a' : '--bg:#fff;--bd:#dfe2ea;--tx:#14171f;--dim:#5d6577;--ac:#c4601a';
    function items(tab) { return [].concat(reg.tools || [], reg.pages || [], reg.external || []).filter(function (x) { return x.tab === tab; }); }
    var name = act.name || (home ? 'DTF Club' : D.title || 'DTF Club');
    var html = '<style>:host{' + vars + '}' + CSS + '</style>' +
      '<div class="ctx' + (VIEWS ? '' : ' nov') + '"' + (home ? ' hidden' : '') + '><div class="r1"><button id="back" aria-label="Back" hidden>‹</button><span>' + esc(name) + '</span><button id="rf" aria-label="Refresh">⟳</button></div>' +
      '<span class="nm">' + esc(name) + '</span><div class="vt" role="tablist" aria-label="' + esc(name) + ' views"' + (VIEWS ? '' : ' hidden') + '></div></div>' +
      '<div class="scrim" hidden></div><div class="sheet" hidden></div><nav class="bar" aria-label="DTF Club">';
    tabs.forEach(function (t) {
      var list = items(t.id), on = act.tab === t.id;
      if (t.id === 'home') html += '<a href="/" data-t="home"' + (on ? ' class="on" aria-current="page"' : '') + '>' + icon('home') + t.label + '</a>';
      else if (list.length === 1 && (list[0].path || list[0].url)) html += '<a href="' + esc(list[0].path || list[0].url) + '" data-t="' + t.id + '"' + (on ? ' class="on" aria-current="page"' : '') + '>' + icon(t.id) + t.label + '</a>';
      else html += '<button data-t="' + t.id + '"' + (on ? ' class="on"' : '') + '>' + icon(t.id) + t.label + '</button>';
    });
    s.innerHTML = html + '</nav>';
    UI.ctx = s.querySelector('.ctx'); UI.vt = s.querySelector('.vt');
    var sheet = s.querySelector('.sheet'), scrim = s.querySelector('.scrim');
    function close() { sheet.hidden = scrim.hidden = true; }
    s.querySelectorAll('button[data-t]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (!sheet.hidden && sheet.getAttribute('data-t') === b.getAttribute('data-t')) return close();
        sheet.setAttribute('data-t', b.getAttribute('data-t'));
        sheet.innerHTML = items(b.getAttribute('data-t')).map(function (x) {
          var href = x.path || x.url, ext = !x.path;
          return '<a href="' + esc(href) + '"' + (ext ? ' target="_blank" rel="noopener"' : '') + (act.id === x.id ? ' class="on"' : '') + '>' + esc(x.name) + (x.description ? '<small>' + esc(x.description) + '</small>' : '') + '</a>';
        }).join('');
        sheet.hidden = scrim.hidden = false;
      });
    });
    scrim.addEventListener('click', close);
    sheet.addEventListener('click', function (e) { if (e.target.closest('a')) close(); });
    var back = s.getElementById('back');
    if (!home && history.length > 1) back.hidden = false;
    back.addEventListener('click', function () { history.back(); });
    s.getElementById('rf').addEventListener('click', DTF.refresh);
    if (VIEWS) {
      UI.vt.innerHTML = VIEWS.items.map(function (it, i) { return '<button role="tab" data-i="' + i + '">' + esc(it.label) + '</button>'; }).join('');
      UI.vt.addEventListener('click', function (e) { var b = e.target.closest('button[data-i]'); if (b) pick(+b.getAttribute('data-i')); });
      paintViews();
    }
    if ((W.matchMedia && W.matchMedia('(display-mode: standalone)').matches) || navigator.standalone) root.classList.add('dtf-standalone');
    return host;
  }

  function layout() {
    var css = D.createElement('style');
    css.textContent = ':root{--dtf-top-h:0px;--dtf-nav-h:0px}' +
      'body.dtf-has-nav{padding-top:var(--dtf-top-h);padding-bottom:calc(56px + env(safe-area-inset-bottom));--dtf-nav-h:calc(56px + env(safe-area-inset-bottom))}' +
      '@media(min-width:900px){body.dtf-has-nav{padding-bottom:0;--dtf-nav-h:0px}}';
    D.head.appendChild(css);
    D.body.classList.add('dtf-has-nav');
    // reserve space before the registry arrives: phone context bar is 40px (plus any status-bar inset); desktop top bar is 48px
    var home = location.pathname === '/' || location.pathname === '/index.html';
    root.style.setProperty('--dtf-top-h', W.innerWidth >= 900 ? '48px' : home ? '0px' : 'calc(40px + env(safe-area-inset-top))');
  }

  var hiddenAt = 0;
  D.addEventListener('visibilitychange', function () {
    if (D.hidden) { hiddenAt = Date.now(); return; }
    if (hiddenAt && Date.now() - hiddenAt > 10 * 60 * 1000) DTF.refresh();
    hiddenAt = 0;
  });

  function start() {
    try { injectHead(); sw(); } catch (e) {}
    if (embedded) { DTF.ready = Promise.resolve(DTF.registry); return; }
    try { layout(); initViews(); } catch (e) {}
    DTF.ready = loadRegistry().catch(function () { return FALLBACK; }).then(function (reg) {
      DTF.registry = reg; DTF.tools = reg.tools || FALLBACK.tools;
      try {
        D.body.appendChild(build(reg)); setTop();
        W.addEventListener('resize', setTop);
        if (W.ResizeObserver && UI.ctx) new ResizeObserver(setTop).observe(UI.ctx);
      } catch (e) { if (W.console) console.warn('dtf-nav failed', e); }
      return reg;
    });
  }
  if (D.readyState === 'loading') D.addEventListener('DOMContentLoaded', start); else start();
})();
