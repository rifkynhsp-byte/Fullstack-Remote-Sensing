/* ===========================================================================
 * sw.js
 * ===========================================================================
 *
 * The service worker. Published at the root of the site so its scope covers
 * the landing page and both book directories.
 *
 * What it is for
 * --------------
 * A reader on a phone in a field station, on a bus, or on hotel wifi that
 * works for ten seconds in every thirty. Chapters they have already opened
 * should still open. That is the whole ambition; this is not an offline
 * download of the book, and it does not pretend to be.
 *
 * The strategy, and why each part is what it is
 * --------------------------------------------
 *   Pages, network first. A chapter is prose that gets corrected. A reader
 *   with a connection should see today's version, not the one they happened
 *   to open a month ago. If the network fails, the cached copy answers, and
 *   if there is no cached copy, the offline page explains why rather than
 *   letting the browser show its dinosaur.
 *
 *   Assets, cache first then refresh in the background. Stylesheets, scripts,
 *   images and fonts are content addressed in practice: when they change,
 *   the page that needs them changes too. Serving them from cache is what
 *   makes a revisit feel instant.
 *
 *   Cross origin, untouched. Plotly comes from a CDN and Pyodide is about ten
 *   megabytes. The browser's own HTTP cache handles both, and putting them in
 *   here would mean managing a cache the size of the runtime for a feature a
 *   reader may never use. Requests that are not same origin pass straight
 *   through.
 *
 * Failure has to be survivable. Every handler falls back to the network, and
 * a caching error is logged rather than thrown: a site that breaks because
 * its offline layer broke is worse than a site with no offline layer.
 * =========================================================================== */

/* The version is the cache name. Bumping it makes the next visit fetch fresh
   copies and drop everything from the old one. Bump it when the precache
   list changes or when a cached asset changes name. */
const VERSION = 'pscg-v1';
const PAGES = `${VERSION}-pages`;
const ASSETS = `${VERSION}-assets`;

/* Kept deliberately short. These are the files without which the site cannot
   render at all, resolved relative to the worker so the same list works at a
   GitHub Pages project path and at a custom domain. */
const PRECACHE = [
  './',
  'index.html',
  'offline.html',
  'manifest.webmanifest',
  'assets/favicon.svg',
  'assets/icon-192.png',
  'lms/lms.css',
  'lms/config.js',
  'lms/lms.js',
  'lms/visitors.js',
  'lms/pyodide-cell.js',
  'lms/app.js'
];

const OFFLINE_URL = 'offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(ASSETS);
    // Added one at a time: addAll rejects the whole batch if any single
    // request 404s, which would leave the worker uninstalled because of one
    // file that had been renamed.
    await Promise.all(PRECACHE.map(async (url) => {
      try {
        await cache.add(new Request(url, { cache: 'reload' }));
      } catch (err) {
        console.warn('[sw] could not precache', url, err);
      }
    }));
    // The book is static and a stale page is worse than a reload, so the new
    // worker takes over immediately rather than waiting for every tab to
    // close.
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keep = new Set([PAGES, ASSETS]);
    const names = await caches.keys();
    await Promise.all(names.map((name) => (keep.has(name) ? null : caches.delete(name))));
    await self.clients.claim();
  })());
});

/* A page can ask the worker to step aside, which is what the update prompt
   in lms/app.js uses. */
self.addEventListener('message', (event) => {
  if (event.data === 'skip-waiting') self.skipWaiting();
});

const isAsset = (url) => /\.(css|js|mjs|png|jpg|jpeg|svg|webp|gif|woff2?|ttf|eot|json|webmanifest)$/i
  .test(new URL(url).pathname);

async function networkFirstPage(request) {
  const cache = await caches.open(PAGES);
  try {
    const fresh = await fetch(request);
    // Opaque and error responses are not worth keeping.
    if (fresh && fresh.ok) {
      cache.put(request, fresh.clone()).catch((err) => console.warn('[sw] page put failed', err));
    }
    return fresh;
  } catch (err) {
    const hit = await cache.match(request, { ignoreSearch: true });
    if (hit) return hit;
    const offline = await caches.match(OFFLINE_URL, { ignoreSearch: true });
    if (offline) return offline;
    throw err;
  }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(ASSETS);
  const hit = await cache.match(request, { ignoreSearch: true });

  // Refresh in the background whether or not there was a hit, so a cached
  // asset is at most one visit out of date.
  const refresh = fetch(request).then((fresh) => {
    if (fresh && fresh.ok) {
      cache.put(request, fresh.clone()).catch(() => {});
    }
    return fresh;
  }).catch(() => null);

  if (hit) return hit;

  const fresh = await refresh;
  if (fresh) return fresh;
  throw new Error('asset unavailable offline');
}

self.addEventListener('fetch', (event) => {
  const request = event.request;

  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Another origin's problem: the CDNs, the fonts, the reader counter.
  if (url.origin !== self.location.origin) return;

  // A range request, which is how a browser asks for part of a media file,
  // must not be answered from a cache that holds the whole thing.
  if (request.headers.has('range')) return;

  if (request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(networkFirstPage(request));
    return;
  }

  if (isAsset(request.url)) {
    event.respondWith(cacheFirstAsset(request));
  }
});
