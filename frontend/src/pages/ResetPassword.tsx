import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api";
import PasswordField from "../components/PasswordField";
import LoginShell from "./LoginShell";

type Check = { valid: boolean; email: string | null };

/**
 * Choix d'un nouveau mot de passe depuis le lien reçu par courrier.
 *
 * La validité du lien est vérifiée **avant** d'afficher le formulaire : faire
 * saisir deux fois un mot de passe pour apprendre ensuite que le lien avait
 * expiré est le genre d'écran qu'on ne pardonne pas.
 */
export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [check, setCheck] = useState<Check | null>(null);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) {
      setCheck({ valid: false, email: null });
      return;
    }
    api
      .get<Check>(`/auth/password-reset/check/?token=${encodeURIComponent(token)}`)
      .then(setCheck)
      .catch(() => setCheck({ valid: false, email: null }));
  }, [token]);

  const mismatch = confirmation.length > 0 && confirmation !== password;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/password-reset/confirm/", {
        token,
        new_password: password,
      });
      setDone(true);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Réinitialisation impossible.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!check) {
    return (
      <LoginShell title="Vérification du lien" reference="Fiche d'accès">
        <p className="fiche-prose">Un instant…</p>
      </LoginShell>
    );
  }

  if (!check.valid) {
    return (
      <LoginShell title="Lien expiré" reference="Fiche d'accès">
        <div className="alert error" role="alert">
          Ce lien n'est plus valable.
        </div>
        <p className="fiche-prose">
          Un lien de réinitialisation expire au bout de deux heures et ne sert
          qu'une seule fois. Demandez-en un nouveau, il remplacera celui-ci.
        </p>
        <Link to="/mot-de-passe-oublie" className="fiche-submit as-link">
          Demander un nouveau lien
        </Link>
      </LoginShell>
    );
  }

  if (done) {
    return (
      <LoginShell title="Mot de passe changé" reference="Fiche d'accès">
        <div className="alert success" role="status">
          Votre mot de passe a été modifié.
        </div>
        <p className="fiche-prose">
          Par précaution, tous les appareils encore connectés à ce compte ont été
          déconnectés. Reconnectez-vous avec votre nouveau mot de passe.
        </p>
        <Link to="/" className="fiche-submit as-link">
          Se connecter
        </Link>
      </LoginShell>
    );
  }

  return (
    <LoginShell
      title="Nouveau mot de passe"
      reference="Fiche d'accès"
      onSubmit={onSubmit}
    >
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}

      <p className="fiche-prose">
        Compte : <strong>{check.email}</strong>
      </p>

      <div className="ruled">
        <PasswordField
          id="new-password"
          label="Nouveau mot de passe"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          autoFocus
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
        disabled={busy || mismatch || !password}
      >
        {busy ? "Enregistrement…" : "Changer le mot de passe"}
      </button>
    </LoginShell>
  );
}
