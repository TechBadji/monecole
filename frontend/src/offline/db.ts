/**
 * Stockage local IndexedDB.
 *
 * Deux magasins, aux rôles volontairement distincts :
 *
 * - `queue` : les écritures faites hors ligne, en attente d'envoi. C'est la
 *   donnée que l'on ne peut pas perdre — elle n'existe nulle part ailleurs.
 * - `cache` : des copies de lecture, horodatées. Toujours reconstructibles, mais
 *   l'horodatage est indispensable : un chiffre financier affiché sans indication
 *   de fraîcheur se lit comme un chiffre courant.
 *
 * `localStorage` ne conviendrait pas : synchrone (il bloque la saisie), limité à
 * ~5 Mo, et sans index pour retrouver une entrée de file.
 */

const DB_NAME = "monecole";
const DB_VERSION = 1;
const QUEUE = "queue";
const CACHE = "cache";

export type QueueStatus = "pending" | "sending" | "failed";

export type QueuedMutation = {
  id?: number;
  /** Identifiant stable, généré au client — sert de clé d'idempotence. */
  clientId: string;
  path: string;
  method: string;
  body: unknown;
  /** Libellé lisible, affiché dans le bandeau de synchronisation. */
  label: string;
  createdAt: number;
  attempts: number;
  status: QueueStatus;
  lastError?: string;
};

export type CachedEntry<T = unknown> = {
  key: string;
  data: T;
  cachedAt: number;
};

let connection: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  if (connection) return connection;

  connection = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(QUEUE)) {
        const store = db.createObjectStore(QUEUE, { keyPath: "id", autoIncrement: true });
        store.createIndex("status", "status");
        store.createIndex("clientId", "clientId", { unique: true });
      }
      if (!db.objectStoreNames.contains(CACHE)) {
        db.createObjectStore(CACHE, { keyPath: "key" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  return connection;
}

async function transact<T>(
  store: string,
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const request = run(tx.objectStore(store));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

// ---------------------------------------------------------------- File d'envoi

export async function enqueue(
  mutation: Omit<QueuedMutation, "id" | "createdAt" | "attempts" | "status">,
): Promise<number> {
  return transact<number>(QUEUE, "readwrite", (store) =>
    store.add({
      ...mutation,
      createdAt: Date.now(),
      attempts: 0,
      status: "pending" as QueueStatus,
    }) as IDBRequest<number>,
  );
}

export async function listQueue(): Promise<QueuedMutation[]> {
  const rows = await transact<QueuedMutation[]>(QUEUE, "readonly", (store) =>
    store.getAll() as IDBRequest<QueuedMutation[]>,
  );
  // Ordre d'arrivée : rejouer les écritures dans le désordre pourrait faire
  // gagner une correction ancienne sur une plus récente.
  return rows.sort((a, b) => a.createdAt - b.createdAt);
}

export async function countPending(): Promise<number> {
  const rows = await listQueue();
  return rows.filter((row) => row.status !== "sending").length;
}

export async function updateQueued(item: QueuedMutation): Promise<void> {
  await transact(QUEUE, "readwrite", (store) => store.put(item));
}

export async function dequeue(id: number): Promise<void> {
  await transact(QUEUE, "readwrite", (store) => store.delete(id));
}

export async function clearQueue(): Promise<void> {
  await transact(QUEUE, "readwrite", (store) => store.clear());
}

// ------------------------------------------------------------------ Cache

export async function putCache<T>(key: string, data: T): Promise<void> {
  await transact(CACHE, "readwrite", (store) =>
    store.put({ key, data, cachedAt: Date.now() } satisfies CachedEntry<T>),
  );
}

export async function getCache<T>(key: string): Promise<CachedEntry<T> | null> {
  const entry = await transact<CachedEntry<T> | undefined>(CACHE, "readonly", (store) =>
    store.get(key) as IDBRequest<CachedEntry<T> | undefined>,
  );
  return entry ?? null;
}

export async function clearCache(): Promise<void> {
  await transact(CACHE, "readwrite", (store) => store.clear());
}

/** Identifiant de mutation, stable côté client. */
export function newClientId(): string {
  return crypto.randomUUID();
}
