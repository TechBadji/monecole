import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import LoginShell, { RuledField } from "./LoginShell";

/**
 * Demande d'un lien de réinitialisation.
 *
 * Le serveur répond la même chose que l'adresse existe ou non ; l'écran doit
 * tenir la même ligne. Afficher « aucun compte à cette adresse » offrirait à
 * n'importe qui le moyen de dresser la liste du personnel d'une école.
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/password-reset/", { email });
      setSent(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Envoi impossible.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <LoginShell title="Vérifiez votre boîte" reference="Fiche d'accès">
        <div className="alert success" role="status">
          Si un compte correspond à <strong>{email}</strong>, un lien vient d'y
          être envoyé.
        </div>
        <p className="fiche-prose">
          Le lien est valable deux heures et ne fonctionne qu'une fois. S'il
          n'arrive pas, regardez dans les indésirables — puis demandez à
          l'administration de votre établissement de vérifier l'adresse
          enregistrée sur votre compte.
        </p>
        <Link to="/" className="fiche-submit as-link">
          Revenir à la connexion
        </Link>
      </LoginShell>
    );
  }

  return (
    <LoginShell
      title="Mot de passe oublié"
      reference="Fiche d'accès"
      onSubmit={onSubmit}
    >
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}

      <p className="fiche-prose">
        Indiquez l'adresse avec laquelle vous vous connectez. Nous y enverrons un
        lien pour choisir un nouveau mot de passe.
      </p>

      <RuledField
        id="email"
        label="Adresse email"
        type="email"
        value={email}
        onChange={setEmail}
        autoComplete="username"
        autoFocus
      />

      <button type="submit" className="fiche-submit" disabled={busy}>
        {busy ? "Envoi…" : "Envoyer le lien"}
      </button>

      <div className="fiche-row centered">
        <Link to="/" className="quiet-link">
          Revenir à la connexion
        </Link>
      </div>
    </LoginShell>
  );
}
