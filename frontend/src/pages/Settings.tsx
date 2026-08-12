import { useEffect, useState } from "react";

import { request, tokens } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import ClassSections from "./ClassSections";
import SchoolYears from "./SchoolYears";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

type ReportCardSettings = {
  logo: string | null;
  header_line_1: string;
  header_line_2: string;
  header_line_3: string;
  establishment_code: string;
  principal_name: string;
  principal_title: string;
  show_rank: boolean;
  show_class_average: boolean;
  footer_note: string;
};

type AttendanceSettings = {
  school_opens_at: string;
  late_after: string;
  school_closes_at: string;
  notify_parent_on_entry: boolean;
  notify_parent_on_exit: boolean;
  notify_parent_on_absence: boolean;
};

export default function Settings() {
  const { profile } = useAuth();
  const isAdmin = profile?.role === "ADMIN";

  const report = useResource<ReportCardSettings>("/report-card-settings/");
  const attendance = useResource<AttendanceSettings>("/attendance/settings/");

  const [card, setCard] = useState<ReportCardSettings | null>(null);
  const [presence, setPresence] = useState<AttendanceSettings | null>(null);
  const [logo, setLogo] = useState<File | null>(null);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => setCard(report.data), [report.data]);
  useEffect(() => setPresence(attendance.data), [attendance.data]);

  async function saveReportCard() {
    if (!card) return;
    setBusy(true);
    setStatus(null);
    try {
      // Le logo est un fichier : la requête passe en multipart, les autres champs
      // l'accompagnent pour n'écrire qu'une fois.
      const body = new FormData();
      Object.entries(card).forEach(([key, value]) => {
        if (key === "logo") return;
        body.append(key, typeof value === "boolean" ? String(value) : (value ?? ""));
      });
      if (logo) body.append("logo", logo);

      const response = await fetch(`${API}/report-card-settings/`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${tokens.access}` },
        body,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail || `Erreur ${response.status}`);
      }
      setLogo(null);
      report.reload();
      setStatus({ kind: "success", text: "Paramètres du bulletin enregistrés." });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function saveAttendance() {
    if (!presence) return;
    setBusy(true);
    setStatus(null);
    try {
      await request("/attendance/settings/", { method: "PUT", body: presence });
      attendance.reload();
      setStatus({ kind: "success", text: "Paramètres d'assiduité enregistrés." });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  if (!card || !presence) return <div className="spinner">Chargement…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Paramètres</h1>
          <p>
            Années scolaires, classes et sections, en-tête du bulletin, horaires et
            notifications d'assiduité.
            {!isAdmin && " Consultation seule : la modification est réservée à l'administrateur."}
          </p>
        </div>
      </div>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      <SchoolYears isAdmin={isAdmin} />

      <ClassSections isAdmin={isAdmin} />

      <div className="card">
        <div className="card-title">Bulletin scolaire</div>
        <p className="muted" style={{ marginBottom: "var(--space-4)" }}>
          Ces mentions figurent en tête du bulletin remis aux familles et présenté
          à l'inspection.
        </p>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="h1">Première ligne d'en-tête</label>
            <input
              id="h1"
              value={card.header_line_1}
              placeholder="République du Sénégal"
              disabled={!isAdmin}
              onChange={(event) => setCard({ ...card, header_line_1: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="h2">Deuxième ligne</label>
            <input
              id="h2"
              value={card.header_line_2}
              placeholder="Ministère de l'Éducation nationale"
              disabled={!isAdmin}
              onChange={(event) => setCard({ ...card, header_line_2: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="h3">Troisième ligne</label>
            <input
              id="h3"
              value={card.header_line_3}
              placeholder="Inspection de l'Éducation et de la Formation de…"
              disabled={!isAdmin}
              onChange={(event) => setCard({ ...card, header_line_3: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="code">Code établissement</label>
            <input
              id="code"
              value={card.establishment_code}
              placeholder="IEF-DK-0147"
              disabled={!isAdmin}
              onChange={(event) =>
                setCard({ ...card, establishment_code: event.target.value })
              }
            />
          </div>
          <div className="field">
            <label htmlFor="principal">Nom du responsable</label>
            <input
              id="principal"
              value={card.principal_name}
              disabled={!isAdmin}
              onChange={(event) => setCard({ ...card, principal_name: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="title">Fonction</label>
            <input
              id="title"
              value={card.principal_title}
              placeholder="Le Directeur"
              disabled={!isAdmin}
              onChange={(event) => setCard({ ...card, principal_title: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="logo">Logo de l'établissement</label>
            <input
              id="logo"
              type="file"
              accept="image/png,image/jpeg"
              disabled={!isAdmin}
              onChange={(event) => setLogo(event.target.files?.[0] ?? null)}
            />
            {card.logo && !logo && (
              <img src={card.logo} alt="Logo actuel" className="logo-preview" />
            )}
          </div>
        </div>

        <div className="field" style={{ marginTop: "var(--space-4)" }}>
          <label htmlFor="footer">Mention de pied de bulletin</label>
          <textarea
            id="footer"
            rows={2}
            value={card.footer_note}
            disabled={!isAdmin}
            onChange={(event) => setCard({ ...card, footer_note: event.target.value })}
          />
        </div>

        <div className="checkbox-row">
          <label>
            <input
              type="checkbox"
              className="checkbox"
              checked={card.show_rank}
              disabled={!isAdmin}
              onChange={(event) => setCard({ ...card, show_rank: event.target.checked })}
            />
            Afficher le rang de l'élève
          </label>
          <label>
            <input
              type="checkbox"
              className="checkbox"
              checked={card.show_class_average}
              disabled={!isAdmin}
              onChange={(event) =>
                setCard({ ...card, show_class_average: event.target.checked })
              }
            />
            Afficher la moyenne de la classe
          </label>
        </div>

        {isAdmin && (
          <button type="button" onClick={saveReportCard} disabled={busy}>
            {busy ? "Enregistrement…" : "Enregistrer le bulletin"}
          </button>
        )}
      </div>

      <div className="card">
        <div className="card-title">Assiduité</div>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="opens">Ouverture de l'école</label>
            <input
              id="opens"
              type="time"
              value={presence.school_opens_at.slice(0, 5)}
              disabled={!isAdmin}
              onChange={(event) =>
                setPresence({ ...presence, school_opens_at: event.target.value })
              }
            />
          </div>
          <div className="field">
            <label htmlFor="late">Retard au-delà de</label>
            <input
              id="late"
              type="time"
              value={presence.late_after.slice(0, 5)}
              disabled={!isAdmin}
              onChange={(event) =>
                setPresence({ ...presence, late_after: event.target.value })
              }
            />
          </div>
          <div className="field">
            <label htmlFor="closes">Fermeture</label>
            <input
              id="closes"
              type="time"
              value={presence.school_closes_at.slice(0, 5)}
              disabled={!isAdmin}
              onChange={(event) =>
                setPresence({ ...presence, school_closes_at: event.target.value })
              }
            />
          </div>
        </div>

        <div className="checkbox-row">
          <label>
            <input
              type="checkbox"
              className="checkbox"
              checked={presence.notify_parent_on_entry}
              disabled={!isAdmin}
              onChange={(event) =>
                setPresence({ ...presence, notify_parent_on_entry: event.target.checked })
              }
            />
            Prévenir le parent à l'entrée
          </label>
          <label>
            <input
              type="checkbox"
              className="checkbox"
              checked={presence.notify_parent_on_exit}
              disabled={!isAdmin}
              onChange={(event) =>
                setPresence({ ...presence, notify_parent_on_exit: event.target.checked })
              }
            />
            Prévenir le parent à la sortie
          </label>
        </div>

        {/* Le coût doit être dit : deux SMS par élève et par jour, sur 180 élèves,
            font 360 SMS quotidiens. */}
        {(presence.notify_parent_on_entry || presence.notify_parent_on_exit) && (
          <div className="alert warning">
            Un SMS est envoyé à chaque passage concerné, pour chaque élève. Sur une
            école de 180 élèves, activer les deux représente environ 360 SMS par
            jour de classe.
          </div>
        )}

        {isAdmin && (
          <button type="button" onClick={saveAttendance} disabled={busy}>
            {busy ? "Enregistrement…" : "Enregistrer l'assiduité"}
          </button>
        )}
      </div>
    </>
  );
}
