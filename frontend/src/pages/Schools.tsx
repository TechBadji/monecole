import { useState, type FormEvent } from "react";

import { api } from "../api";
import { useResource } from "../hooks";
import type { Paginated } from "../types";

type School = {
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
  student_count: number;
};

type Account = { role: string; label: string; email: string; password: string };
type Provisioned = { school: School; year: string; classes: number; accounts: Account[]; detail: string };

const ROLE_LABELS: Record<string, string> = {
  ADMIN: "Administrateur",
  SECRETARY: "Secrétaire",
  TEACHER: "Enseignant",
};

/**
 * Ouverture d'établissements — réservé au super-administrateur.
 *
 * Les mots de passe ne sont affichés qu'ici et qu'une fois : ils ne sont
 * stockés nulle part en clair et ne peuvent pas être relus. L'écran insiste
 * là-dessus parce que fermer la page avant de les avoir transmis oblige à
 * repasser par une réinitialisation pour chacun des trois comptes.
 */
export default function Schools() {
  const { data, reload } = useResource<Paginated<School>>("/schools/?page_size=100");

  const [name, setName] = useState("");
  const [startYear, setStartYear] = useState(String(new Date().getFullYear()));
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Provisioned | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await api.post<Provisioned>("/schools/provision/", {
        name,
        start_year: Number(startYear),
        phone,
      });
      setResult(response);
      setName("");
      setPhone("");
      reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Ouverture impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Établissements</h1>
          <p>
            Ouvrir une école crée son année courante, ses dix classes de base et
            trois accès — administration, secrétariat, salle des maîtres.
          </p>
        </div>
      </div>

      {result && (
        <div className="card provisioned">
          <div className="card-title">{result.school.name}</div>
          <div className="alert warning">
            <strong>Notez ces mots de passe maintenant.</strong> Ils ne sont
            affichés qu'une fois et ne peuvent pas être relus : fermer cette page
            sans les avoir transmis oblige à réinitialiser les trois comptes un
            par un.
          </div>

          <p className="muted">
            Année {result.year} · {result.classes} classes créées.
          </p>

          <div className="table-wrap">
            <table className="table-dense">
              <thead>
                <tr>
                  <th>Rôle</th>
                  <th>Identifiant</th>
                  <th>Mot de passe provisoire</th>
                </tr>
              </thead>
              <tbody>
                {result.accounts.map((account) => (
                  <tr key={account.email}>
                    <td>{ROLE_LABELS[account.role] ?? account.role}</td>
                    <td className="tabular">{account.email}</td>
                    <td>
                      <code className="secret">{account.password}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="field-hint">
            Chaque compte devra changer son mot de passe à la première connexion :
            tant qu'il ne l'a pas fait, il ne peut rien faire d'autre.
          </p>

          <div className="page-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => {
                const text = result.accounts
                  .map((a) => `${ROLE_LABELS[a.role] ?? a.role} · ${a.email} · ${a.password}`)
                  .join("\n");
                void navigator.clipboard?.writeText(
                  `${result.school.name} — année ${result.year}\n${text}`,
                );
              }}
            >
              Copier les accès
            </button>
            <button type="button" className="ghost" onClick={() => setResult(null)}>
              J'ai transmis ces accès
            </button>
          </div>
        </div>
      )}

      <form className="card" onSubmit={onSubmit}>
        <div className="card-title">Ouvrir un établissement</div>

        {error && <div className="alert error">{error}</div>}

        <div className="toolbar">
          <div className="field" style={{ minWidth: 300 }}>
            <label htmlFor="school-name">Nom de l'établissement</label>
            <input
              id="school-name"
              value={name}
              required
              placeholder="Groupe Scolaire Keur Mame Nafissa"
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="field" style={{ maxWidth: 140 }}>
            <label htmlFor="school-year">Rentrée</label>
            <input
              id="school-year"
              type="number"
              min={2000}
              max={2100}
              value={startYear}
              onChange={(event) => setStartYear(event.target.value)}
            />
          </div>
          <div className="field" style={{ maxWidth: 200 }}>
            <label htmlFor="school-phone">Téléphone</label>
            <input
              id="school-phone"
              value={phone}
              placeholder="+221 77 123 45 67"
              onChange={(event) => setPhone(event.target.value)}
            />
          </div>
          <button type="submit" disabled={busy || !name}>
            {busy ? "Ouverture…" : "Ouvrir l'établissement"}
          </button>
        </div>
      </form>

      <div className="card">
        <div className="card-title">Établissements ouverts</div>
        <div className="table-wrap">
          <table className="table-dense">
            <thead>
              <tr>
                <th>Établissement</th>
                <th>Identifiant</th>
                <th className="num">Élèves</th>
                <th>État</th>
              </tr>
            </thead>
            <tbody>
              {data?.results.map((school) => (
                <tr key={school.id}>
                  <td>
                    <strong>{school.name}</strong>
                  </td>
                  <td className="muted tabular">{school.slug}</td>
                  <td className="num">{school.student_count}</td>
                  <td>
                    {school.is_active ? (
                      <span className="badge paid">Actif</span>
                    ) : (
                      <span className="badge unpaid">Suspendu</span>
                    )}
                  </td>
                </tr>
              ))}
              {data?.results.length === 0 && (
                <tr>
                  <td colSpan={4} className="empty">
                    Aucun établissement ouvert.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
