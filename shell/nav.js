/* DTF Club shell: <script src="/shell/nav.js" defer></script>
 * Adds the global nav (bottom tabs on phones, top bar on desktop), the install manifest, and window.DTF.
 * Safe to include on any page: if anything fails the host page keeps working. Hidden in iframes and with ?embed=1. */
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
  DTF.refresh = function () {
    var ev = new CustomEvent('dtf:refresh', { cancelable: true });
    if (W.dispatchEvent(ev)) location.reload();
  };
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

  // ---- service worker
  function sw() {
    if (!('serviceWorker' in navigator) || (location.protocol !== 'https:' && location.hostname !== 'localhost')) return;
    // Rumble Central used to register its own no-op worker at /SleeperLiveRumbles/; it would shadow the root one.
    navigator.serviceWorker.getRegistrations().then(function (rs) {
      rs.forEach(function (r) { if (/\/SleeperLiveRumbles\/$/.test(r.scope)) r.unregister(); });
    }).catch(function () {});
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
  }

  // ---- registry
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
    var all = [].concat(reg.tools || [], reg.pages || [], reg.external || []).filter(function (x) { return x.path; });
    var best = null;
    all.forEach(function (x) {
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

  var CSS = ':host{all:initial}*{box-sizing:border-box}' +
    '.bar{position:fixed;z-index:2147483000;left:0;right:0;bottom:0;display:flex;background:var(--bg);border-top:1px solid var(--bd);padding-bottom:env(safe-area-inset-bottom);font:12px/1.2 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
    '.bar>a,.bar>button{flex:1;min-width:0;height:56px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;color:var(--dim);background:none;border:0;font:inherit;text-decoration:none;cursor:pointer;-webkit-tap-highlight-color:transparent}' +
    '.bar .on{color:var(--ac)}.bar .sp,.hd .sp{display:none}' +
    '.hd{display:none;position:fixed;z-index:2147483000;top:0;left:0;right:0;height:calc(40px + env(safe-area-inset-top));padding-top:env(safe-area-inset-top);background:var(--bg);border-bottom:1px solid var(--bd);align-items:center;justify-content:space-between;font:600 14px system-ui,sans-serif;color:var(--tx)}' +
    '.hd button{background:none;border:0;color:var(--tx);font-size:22px;width:48px;height:40px;cursor:pointer}.hd button[hidden]{visibility:hidden;display:block}' +
    ':host(.hdr) .hd{display:flex}' +
    '.sheet{position:fixed;z-index:2147483001;left:0;right:0;bottom:0;background:var(--bg);border-top:1px solid var(--bd);border-radius:14px 14px 0 0;padding:6px 0 calc(66px + env(safe-area-inset-bottom));font:15px system-ui,sans-serif;box-shadow:0 -8px 30px rgba(0,0,0,.35)}' +
    '.sheet a{display:block;padding:12px 18px;color:var(--tx);text-decoration:none}.sheet a small{display:block;color:var(--dim);font-size:12px}.sheet a.on{color:var(--ac)}' +
    '.sheet[hidden],.scrim[hidden]{display:none}.scrim{position:fixed;inset:0;z-index:2147483000;background:rgba(0,0,0,.4)}' +
    '@media(min-width:900px){.bar{top:0;bottom:auto;height:48px;border-top:0;border-bottom:1px solid var(--bd);padding:0 12px;justify-content:center;gap:4px}' +
    '.bar>a,.bar>button{flex:none;height:48px;flex-direction:row;gap:8px;padding:0 16px;font-size:14px}.bar .sp{display:block;flex:1}.hd{display:none!important}' +
    '.sheet{left:auto;right:auto;top:48px;bottom:auto;min-width:260px;border:1px solid var(--bd);border-radius:0 0 12px 12px;padding:6px 0}}';

  function build(reg) {
    var tabs = reg.tabs || FALLBACK.tabs, act = activeItem(reg) || {};
    var host = D.createElement('dtf-nav'), s = host.attachShadow({ mode: 'open' });
    var dark = W.matchMedia && W.matchMedia('(prefers-color-scheme: light)').matches ? 0 : 1;
    var vars = dark ? '--bg:#14171d;--bd:#2a2f3a;--tx:#e8eaf0;--dim:#9097a8;--ac:#f0914a' : '--bg:#fff;--bd:#dfe2ea;--tx:#14171f;--dim:#5d6577;--ac:#c4601a';
    function items(tab) {
      var a = [].concat(reg.tools || [], reg.pages || [], reg.external || []).filter(function (x) { return x.tab === tab; });
      return a;
    }
    var html = '<style>:host{' + vars + '}' + CSS + '</style><div class="hd"><button id="back" aria-label="Back" hidden>‹</button><span>DTF Club</span><button id="rf" aria-label="Refresh">⟳</button></div>' +
      '<div class="scrim" hidden></div><div class="sheet" hidden></div><nav class="bar" aria-label="DTF Club">';
    tabs.forEach(function (t) {
      var list = items(t.id), on = act.tab === t.id;
      if (t.id === 'home') html += '<a href="/" data-t="home"' + (on ? ' class="on" aria-current="page"' : '') + '>' + icon('home') + t.label + '</a>';
      else if (list.length === 1 && (list[0].path || list[0].url)) html += '<a href="' + esc(list[0].path || list[0].url) + '" data-t="' + t.id + '"' + (on ? ' class="on" aria-current="page"' : '') + '>' + icon(t.id) + t.label + '</a>';
      else html += '<button data-t="' + t.id + '"' + (on ? ' class="on"' : '') + '>' + icon(t.id) + t.label + '</button>';
    });
    s.innerHTML = html + '</nav>';
    var sheet = s.querySelector('.sheet'), scrim = s.querySelector('.scrim');
    function close() { sheet.hidden = scrim.hidden = true; }
    s.querySelectorAll('button[data-t]').forEach(function (b) {
      b.addEventListener('click', function () {
        var open = !sheet.hidden && sheet.getAttribute('data-t') === b.getAttribute('data-t');
        if (open) return close();
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
    if (act.tab !== 'home' && history.length > 1) back.hidden = false;
    back.addEventListener('click', function () { history.back(); });
    s.getElementById('rf').addEventListener('click', DTF.refresh);
    var standalone = (W.matchMedia && W.matchMedia('(display-mode: standalone)').matches) || navigator.standalone || ls('dtf.header') === '1';
    if (standalone) { host.className = 'hdr'; root.classList.add('dtf-standalone'); }
    return host;
  }

  function layout() {
    var css = D.createElement('style');
    css.textContent = ':root{--dtf-nav-h:0px;--dtf-top-h:0px}' +
      'body.dtf-has-nav{padding-bottom:calc(56px + env(safe-area-inset-bottom))}' +
      '.dtf-standalone body.dtf-has-nav{padding-top:calc(40px + env(safe-area-inset-top))}' +
      'body.dtf-has-nav{--dtf-nav-h:calc(56px + env(safe-area-inset-bottom))}' +
      '@media(min-width:900px){body.dtf-has-nav,.dtf-standalone body.dtf-has-nav{padding-bottom:0;padding-top:48px;--dtf-nav-h:0px}}';
    D.head.appendChild(css);
    D.body.classList.add('dtf-has-nav');
  }

  // Come back to the app after a long absence: ask the page to refresh itself (default: reload).
  var hiddenAt = 0;
  D.addEventListener('visibilitychange', function () {
    if (D.hidden) { hiddenAt = Date.now(); return; }
    if (hiddenAt && Date.now() - hiddenAt > 10 * 60 * 1000) DTF.refresh();
    hiddenAt = 0;
  });

  function start() {
    try { injectHead(); sw(); } catch (e) {}
    if (embedded) { DTF.ready = Promise.resolve(DTF.registry); return; }
    try { layout(); } catch (e) {}
    DTF.ready = loadRegistry().catch(function () { return FALLBACK; }).then(function (reg) {
      DTF.registry = reg; DTF.tools = reg.tools || FALLBACK.tools;
      try { D.body.appendChild(build(reg)); } catch (e) { if (W.console) console.warn('dtf-nav failed', e); }
      return reg;
    });
  }
  if (D.readyState === 'loading') D.addEventListener('DOMContentLoaded', start); else start();
})();
