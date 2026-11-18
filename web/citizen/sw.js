// Service worker de la page citoyen : la page s'ouvre sans réseau (coquille en cache). Les appels /api ne sont
// jamais mis en cache : un envoi n'est « reçu » que sur réponse réelle du serveur.
const CACHE = "ouaga-citoyen-v1";
const SHELL = [
  "/citizen/", "/citizen/citizen.css", "/citizen/citizen.js",
  "/dashboard/shared/api.js", "/dashboard/shared/store.js", "/dashboard/shared/ui.js", "/dashboard/shared/shared.css",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (!SHELL.includes(url.pathname) && !url.pathname.startsWith("/citizen/")) return;
  // Réseau d'abord (version à jour), cache en secours hors connexion.
  e.respondWith(fetch(e.request).then((resp) => {
    if (resp.ok) {
      const copy = resp.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
    }
    return resp;
  }).catch(() => caches.match(e.request, { ignoreSearch: true }).then((r) => r || caches.match("/citizen/"))));
});
