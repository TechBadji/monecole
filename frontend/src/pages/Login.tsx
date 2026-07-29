import { useState, type FormEvent } from "react";

import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={onSubmit}>
        <h1>MonÉcole</h1>
        <p>Gestion d'établissement scolaire</p>

        {error && <div className="alert error">{error}</div>}

        <div className="field">
          <label htmlFor="email">Adresse email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="username"
            required
            autoFocus
          />
        </div>

        <div className="field">
          <label htmlFor="password">Mot de passe</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <button type="submit" disabled={busy}>
          {busy ? "Connexion…" : "Se connecter"}
        </button>

        <div className="hint">
          Démonstration — mot de passe <code>MonEcole2026!</code>
          <br />
          <code>admin@darou-louqmane.sn</code> · administrateur
          <br />
          <code>comptable@darou-louqmane.sn</code> · comptable
        </div>
      </form>
    </div>
  );
}
