/* Service worker ImmoGest : coquille de l'application disponible hors-ligne et assets mis en cache.
   Les réponses de l'API ne sont JAMAIS mises en cache (données personnelles et financières). */
const CACHE = 'immogest-shell-v2'
const SHELL = ['/app/', '/app/favicon.svg', '/app/manifest.webmanifest']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== self.location.origin) return
  if (!url.pathname.startsWith('/app/')) return

  // Fichiers hachés par Vite : immuables, on sert le cache d'abord (chargement instantané).
  if (url.pathname.startsWith('/app/assets/')) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const hit = await cache.match(req)
        if (hit) return hit
        const res = await fetch(req)
        if (res.ok) cache.put(req, res.clone())
        return res
      }),
    )
    return
  }

  // Navigation : réseau d'abord, coquille en cache si hors-ligne.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) caches.open(CACHE).then((c) => c.put('/app/', res.clone()))
          return res
        })
        .catch(() => caches.match('/app/').then((r) => r || Response.error())),
    )
  }
})
