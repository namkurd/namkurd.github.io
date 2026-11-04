// DTF Club service worker (scope "/"). Network-first everywhere so data is never stale.
// Bump V on every change to the shell.
const V = 7, SHELL = 'dtf-shell-v' + V, PAGES = 'dtf-pages', DATA = 'dtf-data';
const PRECACHE = ['/', '/offline.html', '/404.html', '/tools.json', '/manifest.webmanifest', '/shell/nav.js',
  '/shell/tokens.css', '/shell/icons/icon-192.png', '/shell/icons/icon-512.png', '/shell/icons/favicon.svg'];
const MAX_BYTES = 1024 * 1024;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => Promise.all(PRECACHE.map(u => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('dtf-shell-') && k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function trim(name, max) {
  const c = await caches.open(name), ks = await c.keys();
  for (let i = 0; i < ks.length - max; i++) await c.delete(ks[i]);
}
function timeout(ms) { return new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms)); }

async function networkFirst(req, store, max, ms, canStore) {
  const cache = await caches.open(store);
  try {
    const res = await (ms ? Promise.race([fetch(req), timeout(ms)]) : fetch(req));
    if (res && res.ok && res.type === 'basic' && (!canStore || await canStore(res))) {
      cache.put(req, res.clone()).then(() => trim(store, max)).catch(() => {});
    }
    return res;
  } catch (err) {
    const hit = await cache.match(req) || await cache.match(req, { ignoreSearch: true }) || await caches.match(req, { ignoreSearch: true });
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;   // cross-origin and writes: untouched
  if (req.mode === 'navigate') {
    e.respondWith(networkFirst(req, PAGES, 30, 4000).catch(() => caches.match('/offline.html')));
  } else if (/\.json$/.test(url.pathname)) {
    const small = async res => { const n = +res.headers.get('content-length'); if (n) return n < MAX_BYTES; return (await res.clone().arrayBuffer()).byteLength < MAX_BYTES; };
    e.respondWith(networkFirst(new Request(req, { cache: 'no-cache' }), DATA, 60, 0, small));
  } else if (PRECACHE.includes(url.pathname)) {
    e.respondWith(networkFirst(req, SHELL, 40, 0).catch(() => caches.match(req)));
  }
});
