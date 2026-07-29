import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { api, tokens } from "./api";
import type { Profile } from "./types";

type AuthState = {
  profile: Profile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  can: (resource: string, action: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Restaure la session au chargement : un rafraîchissement de page ne doit pas
    // renvoyer l'utilisateur au formulaire de connexion.
    if (!tokens.access) {
      setLoading(false);
      return;
    }
    api
      .get<Profile>("/auth/me/")
      .then(setProfile)
      .catch(() => tokens.clear())
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    await api.login(email, password);
    setProfile(await api.get<Profile>("/auth/me/"));
  }

  function logout() {
    tokens.clear();
    setProfile(null);
  }

  /**
   * L'interface masque ce que le rôle ne permet pas — confort, pas sécurité :
   * l'autorisation qui fait foi est celle appliquée par le serveur.
   */
  function can(resource: string, action: string) {
    return profile?.permissions?.[resource]?.includes(action) ?? false;
  }

  return (
    <AuthContext.Provider value={{ profile, loading, login, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans un AuthProvider.");
  return context;
}
