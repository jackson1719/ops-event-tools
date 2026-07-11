/* Service worker: offline tolerance for convention-center wifi.
   Strategy: cache-first for hashed static assets, network-first with cache
   fallback for pages and media. Never caches auth, manage, or admin pages.
   Bump CACHE_VERSION when changing behavior. */
const CACHE_VERSION = 'ops-v1';

const NEVER_CACHE = ['/accounts/', '/admin/', '/manage', '/sw.js', '/media/pdf_temp/'];

self.addEventListener('install', function(event) {
  self.skipWaiting();
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_VERSION; })
            .map(function(k) { return caches.delete(k); })
      );
    }).then(function() { return self.clients.claim(); })
  );
});

function shouldHandle(request) {
  if (request.method !== 'GET') return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  if (NEVER_CACHE.some(function(p) { return url.pathname.includes(p); })) return false;
  return true;
}

function cacheable(response) {
  // Don't cache errors or responses that got redirected to the login page
  if (!response || response.status !== 200) return false;
  if (response.redirected && response.url.includes('/accounts/login')) return false;
  return true;
}

self.addEventListener('fetch', function(event) {
  const request = event.request;
  if (!shouldHandle(request)) return;

  const url = new URL(request.url);

  // Hashed static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(function(cached) {
        if (cached) return cached;
        return fetch(request).then(function(response) {
          if (cacheable(response)) {
            const copy = response.clone();
            caches.open(CACHE_VERSION).then(function(c) { c.put(request, copy); });
          }
          return response;
        });
      })
    );
    return;
  }

  // Pages and media: network-first, fall back to last cached copy
  event.respondWith(
    fetch(request).then(function(response) {
      if (cacheable(response)) {
        const copy = response.clone();
        caches.open(CACHE_VERSION).then(function(c) { c.put(request, copy); });
      }
      return response;
    }).catch(function() {
      return caches.match(request).then(function(cached) {
        if (cached) return cached;
        return new Response(
          '<html><body style="background:#212529;color:#eee;font-family:sans-serif;text-align:center;padding-top:20vh;">' +
          '<h2>Offline</h2><p>No cached copy of this page yet. Reconnect and try again.</p></body></html>',
          { status: 503, headers: { 'Content-Type': 'text/html' } }
        );
      });
    })
  );
});
