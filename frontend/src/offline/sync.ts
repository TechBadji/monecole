/**
 * Synchronisation de la file d'attente.
 *
 * Déclenchée au retour de connexion, au démarrage de l'application, et
 * manuellement. Trois garanties :
 *
 * 1. **Séquentiel.** Les écritures partent une par une, dans l'ordre d'arrivée.
 *    En parallèle, deux corrections du même encaissement pourraient s'appliquer
 *    dans le désordre.
 * 2. **Un seul passage à la fois.** Un verrou empêche que le retour de connexion
 *    et un clic manuel ne rejouent la même entrée deux fois.
 * 3. **Distinction erreur métier / erreur réseau.** Une réponse 4xx est
 *    définitive : rejouer ne changera rien, l'entrée est marquée en échec pour
 *    intervention humaine. Une coupure réseau, elle, est réessayée.
 */

import { ApiError, request } from "../api";
import { dequeue, listQueue, updateQueued, type QueuedMutation } from "./db";

export type SyncOutcome = {
  sent: number;
  failed: number;
  remaining: number;
  errors: { label: string; message: string }[];
};

type Listener = (state: SyncState) => void;

export type SyncState = {
  online: boolean;
  syncing: boolean;
  pending: number;
  failed: number;
  lastSyncAt: number | null;
  lastError: string | null;
};

let state: SyncState = {
  online: navigator.onLine,
  syncing: false,
  pending: 0,
  failed: 0,
  lastSyncAt: null,
  lastError: null,
};

const listeners = new Set<Listener>();
let running = false;

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

function emit(patch: Partial<SyncState>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener(state));
}

export function getSyncState() {
  return state;
}

export async function refreshCounts() {
  const rows = await listQueue();
  emit({
    pending: rows.filter((r) => r.status === "pending").length,
    failed: rows.filter((r) => r.status === "failed").length,
  });
}

/** Rejoue la file. Sans effet si hors ligne ou déjà en cours. */
export async function sync(): Promise<SyncOutcome> {
  const empty: SyncOutcome = { sent: 0, failed: 0, remaining: 0, errors: [] };

  if (running || !navigator.onLine) return empty;
  running = true;
  emit({ syncing: true, lastError: null });

  const outcome: SyncOutcome = { sent: 0, failed: 0, remaining: 0, errors: [] };

  try {
    const rows = await listQueue();
    for (const item of rows) {
      if (item.status === "failed") {
        // Déjà rejetée par le serveur : ne pas la renvoyer en boucle. Elle reste
        // visible pour que quelqu'un la corrige ou l'abandonne.
        outcome.failed += 1;
        continue;
      }

      const sent = await send(item);
      if (sent.ok) {
        outcome.sent += 1;
      } else if (sent.permanent) {
        outcome.failed += 1;
        outcome.errors.push({ label: item.label, message: sent.message });
      } else {
        // Réseau perdu en cours de route : on s'arrête là et on garde le reste.
        outcome.remaining = rows.length - outcome.sent - outcome.failed;
        emit({ lastError: sent.message });
        break;
      }
    }

    emit({ lastSyncAt: Date.now() });
  } finally {
    running = false;
    emit({ syncing: false });
    await refreshCounts();
  }

  return outcome;
}

async function send(item: QueuedMutation) {
  await updateQueued({ ...item, status: "sending", attempts: item.attempts + 1 });

  try {
    await request(item.path, {
      method: item.method,
      body: item.body,
      // L'en-tête d'idempotence permet au serveur de reconnaître un rejeu.
      headers: { "X-Client-Mutation-Id": item.clientId },
    });
    if (item.id !== undefined) await dequeue(item.id);
    return { ok: true as const, permanent: false, message: "" };
  } catch (error) {
    const isApiError = error instanceof ApiError;
    // 4xx = refus métier, définitif. 5xx et erreurs réseau = réessayable.
    const permanent = isApiError && error.status >= 400 && error.status < 500;
    const message = error instanceof Error ? error.message : "Erreur inconnue";

    await updateQueued({
      ...item,
      status: permanent ? "failed" : "pending",
      attempts: item.attempts + 1,
      lastError: message,
    });

    return { ok: false as const, permanent, message };
  }
}

/** Abandonne une entrée définitivement rejetée. */
export async function discard(id: number) {
  await dequeue(id);
  await refreshCounts();
}

/** Remet une entrée en échec dans la file, après correction côté serveur. */
export async function retry(item: QueuedMutation) {
  await updateQueued({ ...item, status: "pending", lastError: undefined });
  await refreshCounts();
  return sync();
}

export function startSyncWatcher() {
  const goOnline = () => {
    emit({ online: true });
    void sync();
  };
  const goOffline = () => emit({ online: false });

  window.addEventListener("online", goOnline);
  window.addEventListener("offline", goOffline);

  void refreshCounts();
  if (navigator.onLine) void sync();

  return () => {
    window.removeEventListener("online", goOnline);
    window.removeEventListener("offline", goOffline);
  };
}
