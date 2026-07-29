/**
 * Client API.
 *
 * Le jeton d'accès expire au bout de 30 minutes. Plutôt que de laisser l'utilisateur
 * tomber sur une erreur en pleine saisie d'encaissements, une réponse 401 déclenche
 * un rafraîchissement puis un rejeu transparent de la requête.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

const ACCESS_KEY = "monecole.access";
const REFRESH_KEY = "monecole.refresh";

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set({ access, refresh }: { access: string; refresh?: string }) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(ApiError.readableMessage(status, detail));
    this.status = status;
    this.detail = detail;
  }

  /** Remonte le message du serveur plutôt qu'un « une erreur est survenue » opaque. */
  static readableMessage(status: number, detail: unknown): string {
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const record = detail as Record<string, unknown>;
      if (typeof record.detail === "string") return record.detail;
      const first = Object.entries(record)[0];
      if (first) {
        const [field, value] = first;
        const text = Array.isArray(value) ? value[0] : value;
        return field === "non_field_errors" ? String(text) : `${field} : ${text}`;
      }
    }
    if (status === 401) return "Session expirée. Reconnectez-vous.";
    if (status === 403) return "Votre rôle ne vous autorise pas cette opération.";
    return `Erreur ${status}`;
  }
}

let refreshing: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  // Un seul rafraîchissement à la fois : plusieurs requêtes échouant simultanément
  // ne doivent pas déclencher autant de rotations concurrentes du refresh token.
  if (refreshing) return refreshing;

  refreshing = (async () => {
    const refresh = tokens.refresh;
    if (!refresh) return false;
    const response = await fetch(`${BASE_URL}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!response.ok) {
      tokens.clear();
      return false;
    }
    const data = await response.json();
    tokens.set({ access: data.access, refresh: data.refresh });
    return true;
  })();

  try {
    return await refreshing;
  } finally {
    refreshing = null;
  }
}

type RequestOptions = { method?: string; body?: unknown; raw?: boolean };

export async function request<T = unknown>(
  path: string,
  { method = "GET", body, raw = false }: RequestOptions = {},
): Promise<T> {
  const send = () => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const access = tokens.access;
    if (access) headers.Authorization = `Bearer ${access}`;
    return fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let response = await send();

  if (response.status === 401 && tokens.refresh) {
    if (await refreshAccessToken()) {
      response = await send();
    }
  }

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new ApiError(response.status, detail);
  }

  if (raw) return response as unknown as T;
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: (path: string) => request<void>(path, { method: "DELETE" }),

  async login(email: string, password: string) {
    const response = await fetch(`${BASE_URL}/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      throw new ApiError(response.status, await response.json().catch(() => null));
    }
    const data = await response.json();
    tokens.set({ access: data.access, refresh: data.refresh });
    return data;
  },

  /** Télécharge un export en conservant l'en-tête d'authentification. */
  async download(path: string, filename: string) {
    const response = await request<Response>(path, { raw: true });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },
};

/** Format monétaire XOF : entier, séparateur d'espace, aucune décimale. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(value);
}
