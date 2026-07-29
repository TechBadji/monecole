import { useCallback, useEffect, useState } from "react";

import { api } from "./api";

type Resource<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
};

/**
 * Charge une ressource de l'API.
 *
 * `path` à `null` diffère le chargement — utile quand la requête dépend d'un
 * paramètre que l'utilisateur n'a pas encore choisi.
 */
export function useResource<T>(path: string | null): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
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

    api
      .get<T>(path)
      .then((result) => {
        // Une réponse arrivée après un changement de paramètre ne doit pas écraser
        // la plus récente.
        if (!cancelled) setData(result);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Chargement impossible.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  return { data, error, loading, reload };
}
