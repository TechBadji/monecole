import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth";
import PasswordField from "../components/PasswordField";
import LoginShell, { RuledField } from "./LoginShell";

/**
 * CONTRAT DE DIRECTION — écran de connexion
 *
 * THESIS : la connexion est une **fiche que l'on remplit**, pas un encart
 * flottant au milieu d'un dégradé. Refuse la carte centrée du SaaS générique.
 * OWN-WORLD : marine profond du produit ; la fiche est blanche, ses champs sont
 * des lignes réglées surmontées d'une étiquette en capitales — la papeterie
 * administrative que ces écoles manipulent tous les jours. Un cachet encré
 * porte l'exercice. Aucun cadre de saisie, aucune ombre décorative.
 * STORY : un directeur comprend en trois secondes ce que fait le produit et à
 * quoi tient sa rigueur ; le personnel, lui, entre sans rien lire.
 * FIRST VIEWPORT : marine plein cadre. À gauche le nom, une accroche en deux
 * lignes et quatre garanties vérifiables. À droite la fiche : en-tête réglé,
 * deux champs, le cachet en bas à droite, l'action au bas de la fiche.
 * FORM : structure 4 de la liste ordonnée (la fiche cartonnée), sans staging
 * rapporté — les trois tirés ajoutaient de la friction à un geste quotidien.
 * Clé de tirage : 8fc4d4de.
 */
export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password, remember);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <LoginShell title="Accès à l'établissement" reference="Fiche d'accès" onSubmit={onSubmit}>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}

      <RuledField
        id="email"
        label="Adresse email"
        type="email"
        value={email}
        onChange={setEmail}
        autoComplete="username"
        autoFocus
      />

      <div className="ruled">
        <PasswordField
          id="password"
          label="Mot de passe"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
      </div>

      <div className="fiche-row">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
          />
          <span>Se souvenir de moi</span>
        </label>
        <Link to="/mot-de-passe-oublie" className="quiet-link">
          Mot de passe oublié ?
        </Link>
      </div>

      <button type="submit" className="fiche-submit" disabled={busy}>
        {busy ? "Connexion…" : "Entrer"}
      </button>

      {/* La case décide du magasin de jetons. Le dire évite qu'on la coche par
          réflexe sur le poste partagé du secrétariat. */}
      <p className="fiche-note">
        {remember
          ? "Vous resterez connecté 30 jours sur cet appareil."
          : "La session se fermera avec le navigateur."}
      </p>
    </LoginShell>
  );
}
