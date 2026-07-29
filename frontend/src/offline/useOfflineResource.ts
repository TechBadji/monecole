import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { enqueue, getCache, newClientId, putCache } from "./db";
import { refreshCounts, sync } from "./sync";

export type Freshness = {
  /** Les données proviennent du cache local, pas du serveur. */
  stale: boolean;
  /** Horodatage de la copie affichée. */
  cachedAt: number | null;
};

type OfflineResource<T> = Freshness & {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
};

/**
 * Charge une ressource, avec repli sur le cache local.
 *
 * En ligne : appel réseau, puis mise en cache. Hors ligne ou en cas d'échec :
 * dernière copie connue, **signalée comme telle** via `stale` et `cachedAt`.
 *
 * L'appelant doit afficher cette fraîcheur. Un solde de trésorerie vieux de trois
 * jours présenté comme courant conduit à des décisions prises sur des chiffres
 * faux — c'est précisément ce que le mode hors ligne ne doit pas provoquer.
 */
export function useOfflineResource<T>(path: string | null): OfflineResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [stale, setStale] = useState(false);
  const [cachedAt, setCachedAt] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (path === null) {
      setData(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const fresh = await api.get<T>(path);
        if (cancelled) return;
        setData(fresh);
        setStale(false);
        setCachedAt(Date.now());
        void putCache(path, fresh);
      } catch (caught) {
        if (cancelled) return;
        const entry = await getCache<T>(path);
        if (entry) {
          setData(entry.data);
          setStale(true);
          setCachedAt(entry.cachedAt);
          setError(null);
        } else {
          setError(
            caught instanceof Error ? caught.message : "Chargement impossible.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  return { data, error, loading, stale, cachedAt, reload };
}

export type MutationResult = {
  /** Vrai si l'écriture a été mise en file au lieu d'être envoyée. */
  queued: boolean;
  response?: unknown;
};

/**
 * Envoie une écriture, ou la met en file si le réseau est absent.
 *
 * `clientId` est généré ici et transmis au serveur : il rend le rejeu sûr, ce qui
 * compte d'autant plus qu'une entrée en file peut être renvoyée après une coupure
 * survenue *pendant* l'envoi — sans savoir si le serveur l'avait reçue.
 */
export async function mutate(
  path: string,
  body: unknown,
  { label, method = "POST" }: { label: string; method?: string },
): Promise<MutationResult> {
  const clientId = newClientId();

  if (!navigator.onLine) {
    await enqueue({ clientId, path, method, body, label });
    await refreshCounts();
    return { queued: true };
  }

  try {
    const response = await api.post(path, body);
    return { queued: false, response };
  } catch (caught) {
    // Coupure en cours d'envoi : on met en file plutôt que de perdre la saisie.
    // Une erreur métier (4xx), elle, doit remonter à l'utilisateur tout de suite.
    const isNetwork =
      caught instanceof TypeError ||
      (caught as { status?: number })?.status === undefined;
    if (isNetwork) {
      await enqueue({ clientId, path, method, body, label });
      await refreshCounts();
      void sync();
      return { queued: true };
    }
    throw caught;
  }
}

/** Libellé relatif d'un horodatage : « il y a 3 h ». */
export function relativeTime(timestamp: number | null): string {
  if (!timestamp) return "";
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "à l'instant";
  if (seconds < 3600) return `il y a ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `il y a ${Math.floor(seconds / 3600)} h`;
  const days = Math.floor(seconds / 86400);
  return days === 1 ? "hier" : `il y a ${days} jours`;
}

/** Date complète, pour les états financiers où l'à-peu-près ne suffit pas. */
export function absoluteTime(timestamp: number | null): string {
  if (!timestamp) return "";
  return new Date(timestamp).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}
