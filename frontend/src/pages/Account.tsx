import { useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import PasswordField from "../components/PasswordField";
import type { Profile } from "../types";

type Session = {
  id: number;
  device_label: string;
  ip_address: string | null;
  remembered: boolean;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  is_current: boolean;
};

export default function Account() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Mon compte</h1>
          <p>Votre photo, vos coordonnées, votre mot de passe et vos appareils.</p>
        </div>
      </div>

      <div className="account-grid">
        <PhotoCard />
        <ProfileCard />
        <PasswordCard />
        <SessionsCard />
      </div>
    </>
  );
}

/** Avatar réutilisé par la vignette de la barre et par cette page. */
export function Avatar({
  profile,
  size = 40,
}: {
  profile: Pick<Profile, "photo" | "initials" | "full_name">;
  size?: number;
}) {
  const style = { width: size, height: size, fontSize: Math.round(size * 0.38) };
  if (profile.photo) {
    return (
      <img
        className="avatar"
        style={style}
        src={absolute(profile.photo)}
        alt=""
        width={size}
        height={size}
      />
    );
  }
  return (
    <span className="avatar initials" style={style} aria-hidden="true">
      {profile.initials}
    </span>
  );
}

/**
 * Le serveur renvoie un chemin relatif (`/media/avatars/…`) : relatif à l'API,
 * pas à l'interface, qui tourne sur un autre port en développement et peut
 * tourner sur un autre domaine en production.
 */
export function absolute(path: string) {
  if (/^https?:/.test(path)) return path;
  const base = (import.meta.env.VITE_API_URL ?? "http://localhost:8000/api").replace(
    /\/api\/?$/,
    "",
  );
  return `${base}${path}`;
}

function PhotoCard() {
  const { profile, setProfile } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!profile) return null;

  async function send(file: File) {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("photo", file);
      setProfile(await api.upload<Profile>("/auth/me/photo/", body));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Envoi impossible.");
    } finally {
      setBusy(false);
      // Sans cela, recharger deux fois le même fichier ne déclenche pas
      // `change` : la valeur de l'input n'a pas varié.
      if (input.current) input.current.value = "";
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      setProfile(await api.upload<Profile>("/auth/me/photo/", new FormData(), "DELETE"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Suppression impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card account-photo">
      <h2>Photo</h2>
      <div className="account-photo-row">
        <Avatar profile={profile} size={96} />
        <div>
          <div className="page-actions">
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              {profile.photo ? "Remplacer" : "Choisir une photo"}
            </button>
            {profile.photo && (
              <button type="button" className="ghost" disabled={busy} onClick={remove}>
                Retirer
              </button>
            )}
          </div>
          <p className="field-hint">
            JPEG, PNG ou WebP, 8 Mo au plus. L'image est recadrée au carré et
            réduite à 512 px — inutile d'envoyer une photo pleine résolution.
          </p>
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void send(file);
        }}
      />
      {error && <div className="alert error">{error}</div>}
    </section>
  );
}

function ProfileCard() {
  const { profile, setProfile } = useAuth();
  const [firstName, setFirstName] = useState(profile?.first_name ?? "");
  const [lastName, setLastName] = useState(profile?.last_name ?? "");
  const [phone, setPhone] = useState(profile?.phone ?? "");
  const [state, setState] = useState<"idle" | "busy" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  if (!profile) return null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setState("busy");
    setError(null);
    try {
      setProfile(
        await api.patch<Profile>("/auth/me/profile/", {
          first_name: firstName,
          last_name: lastName,
          phone,
        }),
      );
      setState("saved");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Enregistrement impossible.");
      setState("idle");
    }
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h2>Coordonnées</h2>

      <div className="field-pair">
        <div className="field">
          <label htmlFor="first-name">Prénom</label>
          <input
            id="first-name"
            value={firstName}
            onChange={(event) => {
              setFirstName(event.target.value);
              setState("idle");
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="last-name">Nom</label>
          <input
            id="last-name"
            value={lastName}
            onChange={(event) => {
              setLastName(event.target.value);
              setState("idle");
            }}
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="phone">Téléphone</label>
        <input
          id="phone"
          value={phone}
          placeholder="+221 77 123 45 67"
          onChange={(event) => {
            setPhone(event.target.value);
            setState("idle");
          }}
        />
      </div>

      {/* Ni l'email ni le rôle ne se modifient ici : l'un est l'identifiant de
          connexion, l'autre relève de l'administration. Les afficher en lecture
          évite de laisser croire à un oubli. */}
      <div className="field-pair readonly-pair">
        <div className="field">
          <label>Adresse email</label>
          <p className="readonly-value">{profile.email}</p>
        </div>
        <div className="field">
          <label>Rôle</label>
          <p className="readonly-value">{profile.role_label ?? profile.role}</p>
        </div>
      </div>
      <p className="field-hint">
        L'adresse et le rôle sont gérés par l'administration de votre
        établissement.
      </p>

      {error && <div className="alert error">{error}</div>}

      <div className="page-actions">
        <button type="submit" disabled={state === "busy"}>
          {state === "busy" ? "Enregistrement…" : "Enregistrer"}
        </button>
        {state === "saved" && <span className="saved-flag">Enregistré.</span>}
      </div>
    </form>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const mismatch = confirmation.length > 0 && confirmation !== next;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.post<{ sessions_closed: number }>(
        "/auth/me/password/",
        { current_password: current, new_password: next },
      );
      const closed = response.sessions_closed;
      setResult(
        closed > 0
          ? `Mot de passe modifié. ${closed} autre${closed > 1 ? "s" : ""} appareil${
              closed > 1 ? "s ont" : " a"
            } été déconnecté${closed > 1 ? "s" : ""}.`
          : "Mot de passe modifié.",
      );
      setCurrent("");
      setNext("");
      setConfirmation("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Modification impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h2>Mot de passe</h2>

      <PasswordField
        id="current-password"
        label="Mot de passe actuel"
        value={current}
        onChange={setCurrent}
        autoComplete="current-password"
      />
      <PasswordField
        id="next-password"
        label="Nouveau mot de passe"
        value={next}
        onChange={setNext}
        autoComplete="new-password"
        hint="Au moins 10 caractères. Évitez un mot du dictionnaire seul."
      />
      <PasswordField
        id="confirm-new-password"
        label="Confirmation"
        value={confirmation}
        onChange={setConfirmation}
        autoComplete="new-password"
        error={mismatch ? "Les deux saisies diffèrent." : null}
      />

      {error && <div className="alert error">{error}</div>}
      {result && <div className="alert success">{result}</div>}

      <p className="field-hint">
        Changer votre mot de passe déconnecte vos autres appareils. Celui-ci
        reste connecté.
      </p>

      <div className="page-actions">
        <button type="submit" disabled={busy || mismatch || !current || !next}>
          {busy ? "Modification…" : "Changer le mot de passe"}
        </button>
      </div>
    </form>
  );
}

function SessionsCard() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<Session[]>("/auth/sessions/")
      .then(setSessions)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Chargement impossible."),
      );
  }, []);

  async function revoke(id: number) {
    setBusy(id);
    setError(null);
    try {
      await api.delete(`/auth/sessions/${id}/`);
      setSessions((current) => current?.filter((row) => row.id !== id) ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Déconnexion impossible.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card">
      <h2>Appareils connectés</h2>
      <p className="field-hint">
        Si vous ne reconnaissez pas un appareil, déconnectez-le puis changez
        votre mot de passe.
      </p>

      {error && <div className="alert error">{error}</div>}
      {!sessions && !error && <div className="spinner">Chargement…</div>}

      {sessions && (
        <ul className="session-list">
          {sessions.map((session) => (
            <li key={session.id} className={session.is_current ? "current" : ""}>
              <div>
                <strong>
                  {session.device_label}
                  {session.is_current && <span className="chip">Cet appareil</span>}
                </strong>
                <span className="session-meta">
                  {session.ip_address ?? "adresse inconnue"} · vu{" "}
                  {relative(session.last_seen_at)}
                  {session.remembered && " · session prolongée"}
                </span>
              </div>
              {!session.is_current && (
                <button
                  type="button"
                  className="ghost small"
                  disabled={busy === session.id}
                  onClick={() => revoke(session.id)}
                >
                  {busy === session.id ? "…" : "Déconnecter"}
                </button>
              )}
            </li>
          ))}
          {sessions.length === 0 && (
            <li className="empty">Aucune autre session ouverte.</li>
          )}
        </ul>
      )}
    </section>
  );
}

/** « vu il y a 3 minutes » se lit mieux qu'un horodatage dans une liste courte. */
function relative(iso: string) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  return days === 1 ? "hier" : `il y a ${days} jours`;
}
