import { useState, type FormEvent } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import PasswordField from "../components/PasswordField";
import type { Profile } from "../types";
import LoginShell from "./LoginShell";

/**
 * Changement imposé du mot de passe provisoire.
 *
 * Cet écran n'est pas une politesse : tant que le mot de passe remis à
 * l'ouverture de l'établissement tient, le serveur refuse tout le reste. Il n'y
 * a donc rien d'autre à afficher, et aucune sortie hors la déconnexion.
 *
 * Le mot de passe provisoire a transité par courrier ou par téléphone. C'est
 * précisément ce qui justifie de le remplacer avant tout usage.
 */
export default function ChangePassword() {
  const { profile, setProfile, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirmation.length > 0 && confirmation !== next;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/me/password/", {
        current_password: current,
        new_password: next,
      });
      // Recharger le profil lève le drapeau et rend l'application accessible,
      // sans imposer une reconnexion à quelqu'un qui vient de s'identifier.
      setProfile(await api.get<Profile>("/auth/me/"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Modification impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <LoginShell
      title="Choisissez votre mot de passe"
      reference="Première connexion"
      onSubmit={onSubmit}
    >
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}

      <p className="fiche-prose">
        Le mot de passe qui vous a été remis est provisoire. Il vous a été
        transmis par un moyen que d'autres ont pu voir : remplacez-le avant
        d'entrer dans l'application.
      </p>

      <p className="fiche-prose">
        Compte : <strong>{profile?.email}</strong>
      </p>

      <div className="ruled">
        <PasswordField
          id="current-password"
          label="Mot de passe provisoire"
          value={current}
          onChange={setCurrent}
          autoComplete="current-password"
          autoFocus
        />
      </div>

      <div className="ruled">
        <PasswordField
          id="new-password"
          label="Nouveau mot de passe"
          value={next}
          onChange={setNext}
          autoComplete="new-password"
          hint="Au moins 10 caractères. Évitez un mot du dictionnaire seul."
        />
      </div>

      <div className="ruled">
        <PasswordField
          id="confirm-password"
          label="Confirmation"
          value={confirmation}
          onChange={setConfirmation}
          autoComplete="new-password"
          error={mismatch ? "Les deux saisies diffèrent." : null}
        />
      </div>

      <button
        type="submit"
        className="fiche-submit"
        disabled={busy || mismatch || !current || !next}
      >
        {busy ? "Enregistrement…" : "Enregistrer et continuer"}
      </button>

      <div className="fiche-row centered">
        <button type="button" className="quiet-link as-button" onClick={logout}>
          Se déconnecter
        </button>
      </div>
    </LoginShell>
  );
}
