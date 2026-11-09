// Rumble Hub service worker (scope "/"). Network-first everywhere so data is never stale.
// Bump V on every change to the shell.
const V = 23, SHELL = 'dtf-shell-v' + V, PAGES = 'dtf-pages-v' + V, DATA = 'dtf-data-v' + V;
const PRECACHE = ['/', '/offline.html', '/404.html', '/tools.json', '/manifest.webmanifest', '/shell/nav.js',
  '/shell/tokens.css', '/shell/icons/tools/rumbles.svg', '/shell/icons/tools/recordbook.svg', '/shell/icons/tools/h2h.svg', '/shell/icons/tools/lifetime.svg', '/shell/icons/tools/trades.svg', '/shell/icons/tools/fab.svg', '/shell/icons/tools/auction.svg', '/shell/icons/tools/rulebook.svg', '/shell/icons/icon-192.png', '/shell/icons/icon-512.png', '/shell/icons/favicon.svg'];
const MAX_BYTES = 4 * 1024 * 1024;   // FAB's data.json is ~1.7MB; a data file bigger than this is not kept offline

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => Promise.all(PRECACHE.map(u => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('dtf-') && ![SHELL, PAGES, DATA].includes(k)).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function trim(name, max) {
  const c = await caches.open(name), ks = await c.keys();
  for (let i = 0; i < ks.length - max; i++) await c.delete(ks[i]);
}
function timeout(ms) { return new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms)); }

async function networkFirst(req, store, max, ms, canStore, e, key) {
  const cache = await caches.open(store); key = key || req;   // key: what the entry is stored under (cache-busted URLs share one)
  const net = fetch(req).then(async res => {
    if (res && res.ok && res.type === 'basic' && (!canStore || await canStore(res))) {
      await cache.put(key, res.clone()); trim(store, max);
    }
    return res;
  });
  try {
    // If the network is slow we answer from cache, but the fetch keeps going and refreshes the cache for next time.
    return await (ms ? Promise.race([net, timeout(ms)]) : net);
  } catch (err) {
    const hit = await cache.match(key) || await cache.match(req) || await cache.match(req, { ignoreSearch: true }) || await caches.match(req, { ignoreSearch: true });
    if (hit) { if (e) e.waitUntil(net.catch(() => {})); return hit; }
    if (ms) return net;   // nothing cached yet: keep waiting for the network instead of failing
    throw err;
  }
}

self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;   // cross-origin and writes: untouched
  if (req.mode === 'navigate') {
    e.respondWith(networkFirst(req, PAGES, 30, 8000, null, e).catch(() => caches.match('/offline.html')));
  } else if (/\.json$/.test(url.pathname) || /\/data\.js$/.test(url.pathname)) {   // data.js: the Auction Archive's data, loaded by script tag
    const small = async res => { const n = +res.headers.get('content-length'); if (n) return n < MAX_BYTES; return (await res.clone().arrayBuffer()).byteLength < MAX_BYTES; };
    const key = new Request(url.origin + url.pathname);   // ?_=Date.now() cache-busters would otherwise fill the cache with copies
    e.respondWith(networkFirst(new Request(req, { cache: 'no-cache' }), DATA, 60, 0, small, e, key));
  } else if (PRECACHE.includes(url.pathname)) {
    e.respondWith(networkFirst(req, SHELL, 40, 0, null, e).catch(() => caches.match(req)));
  }
});
