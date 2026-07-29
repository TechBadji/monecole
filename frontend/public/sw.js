/**
 * Service worker — coquille applicative hors ligne.
 *
 * Il ne met en cache que la **coquille** (HTML, JS, CSS) : de quoi démarrer
 * l'application sans réseau. Les données, elles, transitent par IndexedDB
 * (`src/offline/db.ts`), où elles sont horodatées et affichées comme telles.
 *
 * Mettre les réponses de l'API dans ce cache serait une erreur : le service
 * worker les servirait comme des réponses normales, sans que l'interface puisse
 * savoir qu'elles sont périmées — exactement le piège qu'on veut éviter sur des
 * données financières.
 */

const CACHE = "monecole-shell-v1";
const OFFLINE_URL = "/";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll([OFFLINE_URL, "/manifest.webmanifest"])),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // L'API n'est jamais interceptée : c'est la couche applicative qui décide quoi
  // faire d'une réponse absente, et qui sait l'annoncer à l'utilisateur.
  if (url.pathname.startsWith("/api/")) return;
  if (url.origin !== self.location.origin) return;

  // Navigation : réseau d'abord, coquille en cache si le réseau manque.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL).then((r) => r || Response.error())),
    );
    return;
  }

  // Ressources statiques : cache d'abord, puis réseau — elles sont versionnées
  // par le nom de fichier, donc jamais périmées à tort.
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    }),
  );
});

// Permet à l'application de déclencher une synchronisation depuis le worker.
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});
