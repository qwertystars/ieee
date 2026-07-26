// ResQNet-SAGE service worker — app-shell caching (cache-first).
// Bump CACHE_VERSION on deploys to invalidate old caches.
const CACHE_VERSION = 'resqnet-v1';
const CACHE_NAME = `${CACHE_VERSION}-shell`;

// App shell: known static URLs precached on install. Hashed Vite assets
// (JS/CSS with content hashes) are cached at runtime via the fetch handler.
const APP_SHELL = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon.svg',
  '/icon-maskable.svg',
];

// Same-origin GET requests are served cache-first (app shell + built assets).
// Cross-origin / non-GET requests bypass the cache and go straight to network.
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(APP_SHELL).catch((err) => {
        // A single failed precache entry should not abort the whole install.
        console.warn('[sw] precache partial failure:', err);
      }),
    ),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => !k.startsWith(CACHE_VERSION))
          .map((k) => caches.delete(k)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Cache-first: serve from cache if present, otherwise fetch and cache.
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          // Only cache successful, same-type responses (opaque/basic/cors).
          if (
            response.ok &&
            response.type !== 'opaque' &&
            response.status === 200
          ) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => {
          // Offline fallback: serve cached index.html for navigation requests.
          if (request.mode === 'navigate') {
            return caches.match('/index.html');
          }
          return undefined;
        });
    }),
  );
});
