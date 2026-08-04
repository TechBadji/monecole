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

// Incrémenté à chaque changement de stratégie : l'activation purge les caches
// des versions précédentes, ce qui est le seul moyen de rattraper les postes qui
// tournent encore avec l'ancien worker.
const CACHE = "monecole-shell-v2";
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

/**
 * Une ressource n'est mise en cache d'abord que si son nom porte une empreinte.
 *
 * C'est la condition qui rend le « cache d'abord » sûr : une URL empreintée
 * désigne un contenu immuable, donc jamais périmé à tort. Le commentaire
 * précédent affirmait cet invariant sans le vérifier — et il était faux en
 * développement, où Vite sert `/src/pages/Encaissements.tsx` à une URL stable.
 * Le worker gardait alors indéfiniment la version d'avant un déploiement, et la
 * page devenait blanche au premier champ disparu.
 *
 * Vite produit `/assets/nom-[hash].js`. Tout le reste passe par le réseau.
 */
function isImmutable(url) {
  return /^\/assets\/.+-[A-Za-z0-9_-]{8,}\.[a-z0-9]+$/.test(url.pathname);
}

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

  if (isImmutable(url)) {
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
    return;
  }

  // Le reste — modules de développement, polices, icônes servies à une URL
  // stable — passe par le réseau, avec le cache en filet hors ligne seulement.
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || Response.error())),
  );
});

// Permet à l'application de déclencher une synchronisation depuis le worker.
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});
