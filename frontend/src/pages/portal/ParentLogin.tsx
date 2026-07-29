import { useEffect, useState, type FormEvent } from "react";

import { ApiError, tokens } from "../../api";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";
const RESEND_DELAY = 45;

type Props = { onAuthenticated: () => void };

/**
 * Connexion du portail parent : numéro de téléphone puis code reçu par SMS.
 *
 * Aucun mot de passe : le numéro figure déjà dans la fiche de l'élève, et exiger
 * un identifiant supplémentaire d'un parent qui consulte le solde deux fois par
 * trimestre garantirait surtout des oublis et des appels au secrétariat.
 */
export default function ParentLogin({ onAuthenticated }: Props) {
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [countdown, setCountdown] = useState(0);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  async function requestCode(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API}/portal/auth/request-code/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      if (response.status === 429) {
        setError("Trop de demandes. Patientez avant de réessayer.");
        return;
      }
      const data = await response.json();
      setNotice(data.detail);
      setStep("code");
      setCountdown(RESEND_DELAY);
    } catch {
      setError("Connexion impossible. Vérifiez votre accès à Internet.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API}/portal/auth/verify-code/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, code }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new ApiError(response.status, data);
      }
      tokens.set({ access: data.access, refresh: data.refresh });
      onAuthenticated();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Code invalide.");
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-card">
        <h1>Espace parents</h1>
        <p>Suivez la scolarité et les paiements de vos enfants.</p>

        {error && <div className="alert error">{error}</div>}

        {step === "phone" && (
          <form onSubmit={requestCode}>
            {notice && <div className="alert success">{notice}</div>}
            <div className="field">
              <label htmlFor="phone">Numéro de téléphone</label>
              <input
                id="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="77 123 45 67"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                required
                autoFocus
              />
            </div>
            <button type="submit" disabled={busy || phone.length < 9}>
              {busy ? "Envoi…" : "Recevoir mon code"}
            </button>
            <div className="hint">
              Utilisez le numéro que vous avez communiqué à l'école. Vous recevrez un
              code à 6 chiffres par SMS.
            </div>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={verifyCode}>
            {notice && <div className="alert success">{notice}</div>}
            <div className="field">
              <label htmlFor="code">Code reçu par SMS</label>
              <input
                id="code"
                className="otp-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                placeholder="000000"
                value={code}
                onChange={(event) =>
                  setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                }
                required
                autoFocus
              />
            </div>
            <button type="submit" disabled={busy || code.length !== 6}>
              {busy ? "Vérification…" : "Se connecter"}
            </button>

            <div className="hint">
              {countdown > 0 ? (
                <>Vous pourrez demander un nouveau code dans {countdown} s.</>
              ) : (
                <button type="button" className="link" onClick={() => requestCode()}>
                  Renvoyer le code
                </button>
              )}
              <br />
              <button
                type="button"
                className="link"
                onClick={() => {
                  setStep("phone");
                  setCode("");
                  setNotice(null);
                }}
              >
                Modifier le numéro
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
