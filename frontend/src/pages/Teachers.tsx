import { useState, type FormEvent } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import type { Paginated } from "../types";

type Teacher = {
  id: number;
  matricule: string;
  first_name: string;
  last_name: string;
  full_name: string;
  sex: string;
  phone: string;
  email: string;
  address: string;
  emergency_contact: string;
  function: string;
  specialty: string;
  class_type: string;
  contract_type: string;
  service_start_date: string | null;
  is_active: boolean;
  has_account: boolean;
};

const CONTRACT_LABELS: Record<string, string> = {
  PERMANENT: "CDI",
  FIXED_TERM: "CDD",
  SUBSTITUTE: "Vacataire",
};

const EMPTY = {
  first_name: "",
  last_name: "",
  sex: "",
  phone: "",
  email: "",
  address: "",
  emergency_contact: "",
  function: "",
  specialty: "",
  contract_type: "PERMANENT",
  service_start_date: "",
  is_active: true,
};

type Draft = typeof EMPTY;

export default function Teachers() {
  const { profile } = useAuth();
  const isAdmin = profile?.role === "ADMIN" || profile?.role === "SECRETARY";

  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);

  const query = new URLSearchParams({ page_size: "100" });
  if (search) query.set("search", search);
  if (!showInactive) query.set("is_active", "true");

  const { data, error, loading, reload } = useResource<Paginated<Teacher>>(
    `/teachers/?${query}`,
  );

  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);

  function startCreate() {
    setEditing(null);
    setDraft({ ...EMPTY });
    setStatus(null);
  }

  function startEdit(teacher: Teacher) {
    setEditing(teacher.id);
    setDraft({
      first_name: teacher.first_name,
      last_name: teacher.last_name,
      sex: teacher.sex ?? "",
      phone: teacher.phone ?? "",
      email: teacher.email ?? "",
      address: teacher.address ?? "",
      emergency_contact: teacher.emergency_contact ?? "",
      function: teacher.function ?? "",
      specialty: teacher.specialty ?? "",
      contract_type: teacher.contract_type,
      service_start_date: teacher.service_start_date ?? "",
      is_active: teacher.is_active,
    });
    setStatus(null);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setStatus(null);
    try {
      // Les dates vides doivent partir en `null` : une chaîne vide sur un champ
      // date remonte une erreur de validation illisible pour l'utilisateur.
      const payload = { ...draft, service_start_date: draft.service_start_date || null };
      if (editing) await api.patch(`/teachers/${editing}/`, payload);
      else await api.post("/teachers/", payload);

      setStatus({
        kind: "success",
        text: editing ? "Enseignant modifié." : "Enseignant ajouté.",
      });
      setDraft(null);
      setEditing(null);
      reload();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  /**
   * Un départ se marque, il ne s'efface pas.
   *
   * Un enseignant porte des bulletins de paie, des feuilles de notes et un
   * historique de classe : le supprimer les emporterait, ou serait refusé par
   * la base sans que personne comprenne pourquoi. Le désactiver le retire des
   * listes et des affectations, en gardant ce qu'il a produit.
   */
  async function toggleActive(teacher: Teacher) {
    setBusy(true);
    setStatus(null);
    try {
      await api.patch(`/teachers/${teacher.id}/`, { is_active: !teacher.is_active });
      setStatus({
        kind: "success",
        text: teacher.is_active
          ? `${teacher.full_name} est marqué comme parti.`
          : `${teacher.full_name} est réintégré.`,
      });
      reload();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Modification impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  const teachers = data?.results ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Personnel enseignant</h1>
          <p>
            {data ? `${teachers.length} enseignant(s)` : "…"} — l'email sert à
            relier l'enseignant à son compte de saisie des notes.
          </p>
        </div>
        {isAdmin && (
          <div className="page-actions">
            <button type="button" onClick={startCreate}>
              Ajouter un enseignant
            </button>
          </div>
        )}
      </div>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      {draft && (
        <form className="card" onSubmit={save}>
          <div className="card-title">
            {editing ? "Modifier l'enseignant" : "Nouvel enseignant"}
          </div>

          <div className="form-grid">
            <div className="field">
              <label htmlFor="first-name">Prénom</label>
              <input
                id="first-name"
                value={draft.first_name}
                required
                autoFocus
                onChange={(e) => setDraft({ ...draft, first_name: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="last-name">Nom</label>
              <input
                id="last-name"
                value={draft.last_name}
                required
                onChange={(e) => setDraft({ ...draft, last_name: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sex">Sexe</label>
              <select
                id="sex"
                value={draft.sex}
                onChange={(e) => setDraft({ ...draft, sex: e.target.value })}
              >
                <option value="">—</option>
                <option value="F">Féminin</option>
                <option value="M">Masculin</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="phone">Téléphone</label>
              <input
                id="phone"
                value={draft.phone}
                placeholder="+221 77 123 45 67"
                onChange={(e) => setDraft({ ...draft, phone: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={draft.email}
                onChange={(e) => setDraft({ ...draft, email: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="emergency">Contact d'urgence</label>
              <input
                id="emergency"
                value={draft.emergency_contact}
                onChange={(e) =>
                  setDraft({ ...draft, emergency_contact: e.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="function">Fonction</label>
              <input
                id="function"
                value={draft.function}
                placeholder="Maîtresse titulaire"
                onChange={(e) => setDraft({ ...draft, function: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="specialty">Spécialité</label>
              <input
                id="specialty"
                value={draft.specialty}
                placeholder="Arabe, anglais…"
                onChange={(e) => setDraft({ ...draft, specialty: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="contract">Contrat</label>
              <select
                id="contract"
                value={draft.contract_type}
                onChange={(e) => setDraft({ ...draft, contract_type: e.target.value })}
              >
                {Object.entries(CONTRACT_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="start">Entrée en service</label>
              <input
                id="start"
                type="date"
                value={draft.service_start_date}
                onChange={(e) =>
                  setDraft({ ...draft, service_start_date: e.target.value })
                }
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="address">Adresse</label>
            <input
              id="address"
              value={draft.address}
              onChange={(e) => setDraft({ ...draft, address: e.target.value })}
            />
          </div>

          <p className="field-hint">
            Le matricule est attribué automatiquement. Saisir l'email d'un compte
            existant rattache l'enseignant à ce compte pour la saisie des notes.
          </p>

          <div className="page-actions">
            <button type="submit" disabled={busy}>
              {busy ? "Enregistrement…" : editing ? "Enregistrer" : "Ajouter"}
            </button>
            <button type="button" className="ghost" onClick={() => setDraft(null)}>
              Annuler
            </button>
          </div>
        </form>
      )}

      <div className="toolbar">
        <div className="field">
          <label htmlFor="search">Recherche</label>
          <input
            id="search"
            value={search}
            placeholder="Nom, matricule, spécialité…"
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          <span>Afficher les départs</span>
        </label>
      </div>

      {error && <div className="alert error">{error}</div>}
      {loading && <div className="spinner">Chargement…</div>}

      {!loading && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 80 }}>Mat.</th>
                <th>Nom</th>
                <th>Fonction</th>
                {/* Le téléphone rejoint la cellule du nom : en colonne propre,
                    il poussait les actions hors du cadre sur un écran de
                    1 500 px, et elles n'étaient atteignables qu'en faisant
                    défiler le tableau. */}
                <th>Contact</th>
                {/* « Contrat » retiré de la liste : la colonne poussait les
                    actions hors du cadre, et l'information se lit à l'édition.
                    Une action inatteignable coûte plus qu'une donnée de moins. */}
                <th>Accès</th>
                {isAdmin && <th className="row-actions-head" />}
              </tr>
            </thead>
            <tbody>
              {teachers.map((teacher) => (
                <tr key={teacher.id} className={teacher.is_active ? "" : "muted"}>
                  <td className="muted">{teacher.matricule}</td>
                  <td>
                    {teacher.full_name}
                    {!teacher.is_active && (
                      <span className="badge unpaid" style={{ marginLeft: 8 }}>
                        Parti
                      </span>
                    )}
                  </td>
                  <td>{teacher.function || <span className="muted">—</span>}</td>
                  <td>
                    {teacher.email || teacher.phone ? (
                      <span className="stacked-cell">
                        <span>{teacher.email || teacher.phone}</span>
                        {teacher.email && teacher.phone && (
                          <span className="muted">{teacher.phone}</span>
                        )}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    {/* Un enseignant sans compte ne peut pas saisir ses notes :
                        le signaler évite que l'administration croie l'accès
                        donné alors que l'intéressé ne voit rien. */}
                    {teacher.has_account ? (
                      <span className="badge paid">Compte actif</span>
                    ) : (
                      <span className="muted">sans compte</span>
                    )}
                  </td>
                  {isAdmin && (
                    <td className="row-actions">
                      <span className="row-actions-group">
                        <button
                          type="button"
                          className="ghost small"
                          onClick={() => startEdit(teacher)}
                        >
                          Modifier
                        </button>
                        <button
                          type="button"
                          className="ghost small"
                          disabled={busy}
                          onClick={() => toggleActive(teacher)}
                          title={
                            teacher.is_active
                              ? "Marquer le départ. Ses bulletins de paie et ses notes sont conservés."
                              : "Réintégrer cet enseignant"
                          }
                        >
                          {teacher.is_active ? "Départ" : "Réintégrer"}
                        </button>
                      </span>
                    </td>
                  )}
                </tr>
              ))}
              {teachers.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    Aucun enseignant ne correspond à ces critères.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
