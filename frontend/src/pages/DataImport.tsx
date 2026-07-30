import { useState, type FormEvent } from "react";

import { api, money, tokens } from "../api";
import { useResource } from "../hooks";
import type { ClassRoom, Paginated } from "../types";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

type Format = {
  kind: string;
  required_columns: string[];
  optional_columns: string[];
  template_columns: string[];
  needs_classroom: boolean;
};
type Formats = { kinds: Format[]; notes: string[] };

type WorkbookReport = {
  layout: "management" | "table";
  applied: boolean;
  ok: boolean;
  students?: number;
  classes?: { classroom: string; students: number; registration: number; tuition: number }[];
  total_registration?: number;
  total_tuition?: number;
  created?: number;
  updated?: number;
  enrollments?: number;
  payments?: number;
  warning_count: number;
  warnings: string[];
  year: string;
};

type Report = {
  kind: string;
  dry_run: boolean;
  applied: boolean;
  created: number;
  updated: number;
  error_count: number;
  warning_count: number;
  errors: { line: number; message: string }[];
  warnings: { line: number; message: string }[];
  ok: boolean;
  rows_read: number;
  detail?: string;
};

const LABELS: Record<string, string> = {
  students: "Élèves",
  teachers: "Enseignants",
  expenses: "Dépenses",
};

export default function DataImport() {
  const { data: formats } = useResource<Formats>("/imports/");
  const { data: classes } = useResource<Paginated<ClassRoom>>("/classes/");
  const [kind, setKind] = useState("students");
  const [classroom, setClassroom] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [workbook, setWorkbook] = useState<WorkbookReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Un .xlsx passe par la reprise de classeur, un .csv par l'import tabulaire. */
  const isWorkbook = Boolean(file && /\.xlsx$/i.test(file.name));

  const format = formats?.kinds.find((f) => f.kind === kind);
  // L'application n'est proposée qu'après un pré-contrôle réussi sur ce fichier.
  const canApply = report?.dry_run && report.ok && !report.applied;

  async function uploadWorkbook(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);

    const body = new FormData();
    body.append("file", file);
    body.append("kind", kind);
    body.append("dry_run", dryRun ? "true" : "false");

    try {
      const response = await fetch(`${API}/imports/workbook/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tokens.access}` },
        body,
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.file || data.detail || data.kind || `Erreur ${response.status}`);
        setWorkbook(null);
        return;
      }
      setWorkbook(data);
      setReport(null);
    } catch {
      setError("Envoi impossible. Vérifiez votre connexion.");
    } finally {
      setBusy(false);
    }
  }

  async function upload(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);

    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);
    body.append("dry_run", dryRun ? "true" : "false");
    // Classe de repli pour les lignes sans colonne « Classe ».
    if (classroom) body.append("classroom", classroom);

    try {
      const response = await fetch(`${API}/imports/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tokens.access}` },
        body,
      });
      const data = await response.json();
      if (!response.ok && !data.error_count) {
        setError(data.file || data.kind || data.detail || `Erreur ${response.status}`);
        setReport(null);
        return;
      }
      setReport(data);
      setWorkbook(null);
    } catch {
      setError("Envoi impossible. Vérifiez votre connexion.");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void (isWorkbook ? uploadWorkbook(true) : upload(true));
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Import de données</h1>
          <p>
            Reprise de fichiers existants. Téléchargez le modèle, remplissez-le, puis
            déposez-le ici. Chaque import est d'abord vérifié ligne à ligne — rien
            n'est écrit tant que vous n'avez pas confirmé.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="secondary"
            onClick={() =>
              api.download(`/imports/template/${kind}.csv`, `modele-${kind}.csv`)
            }
          >
            Télécharger le modèle {LABELS[kind]?.toLowerCase() ?? kind}
          </button>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <form className="card" onSubmit={onSubmit}>
        <div className="card-title">Fichier à importer</div>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <div className="field">
            <label htmlFor="kind">Type de données</label>
            <select
              id="kind"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value);
                setReport(null);
              }}
            >
              {formats?.kinds.map((f) => (
                <option key={f.kind} value={f.kind}>
                  {LABELS[f.kind] ?? f.kind}
                </option>
              ))}
            </select>
          </div>

          <div className="field" style={{ minWidth: 280 }}>
            <label htmlFor="file">Fichier CSV ou Excel</label>
            <input
              id="file"
              type="file"
              accept=".csv,.xlsx,text/csv"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setReport(null);
                setWorkbook(null);
              }}
              required
            />
          </div>

          {format?.needs_classroom && (
            <div className="field">
              <label htmlFor="classroom">Classe par défaut</label>
              <select
                id="classroom"
                value={classroom}
                onChange={(event) => setClassroom(event.target.value)}
              >
                <option value="">— d'après le fichier —</option>
                {classes?.results.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <button type="submit" disabled={busy || !file}>
            {busy ? "Analyse…" : "Vérifier le fichier"}
          </button>
        </div>
      </form>

      {format && (
        <div className="card">
          <div className="card-title">Colonnes attendues</div>
          <p className="column-list">
            <strong>Colonnes du modèle :</strong>{" "}
            {format.template_columns.map((c) => (
              <code key={c}>{c}</code>
            ))}
          </p>
          <p className="column-list">
            <strong>Obligatoires :</strong>{" "}
            {format.required_columns.map((c) => (
              <code key={c}>{c}</code>
            ))}
          </p>
          {format.optional_columns.length > 0 && (
            <p className="column-list">
              <strong>Facultatives :</strong>{" "}
              {format.optional_columns.map((c) => (
                <code key={c}>{c}</code>
              ))}
            </p>
          )}
          <ul className="import-notes">
            {formats?.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      {workbook && (
        <div className="card">
          <div className="card-title">
            {workbook.applied ? "Classeur repris" : "Aperçu du classeur"}
          </div>

          {workbook.layout === "management" ? (
            <>
              <p className="muted" style={{ marginBottom: "var(--space-4)" }}>
                Classeur de gestion reconnu : élèves, inscriptions et mensualités
                sont repris depuis les onglets de classe, sur l'année {workbook.year}.
              </p>

              <div className="stats">
                <div className="stat">
                  <div className="label">Élèves</div>
                  <div className="value">{workbook.students}</div>
                </div>
                <div className="stat">
                  <div className="label">Inscriptions</div>
                  <div className="value">{money(workbook.total_registration ?? 0)}</div>
                </div>
                <div className="stat">
                  <div className="label">Mensualités</div>
                  <div className="value">{money(workbook.total_tuition ?? 0)}</div>
                </div>
                <div className="stat">
                  <div className="label">Avertissements</div>
                  <div className={`value ${workbook.warning_count ? "negative" : "positive"}`}>
                    {workbook.warning_count}
                  </div>
                </div>
              </div>

              {workbook.applied && (
                <div className="alert success">
                  {workbook.created} élève(s) créé(s), {workbook.updated} mis à jour,{" "}
                  {workbook.enrollments} inscription(s) et {workbook.payments}{" "}
                  encaissement(s) repris.
                </div>
              )}

              <div className="table-wrap">
                <table className="table-dense">
                  <thead>
                    <tr>
                      <th>Classe</th>
                      <th className="num">Élèves</th>
                      <th className="num">Inscriptions</th>
                      <th className="num">Mensualités</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workbook.classes?.map((row) => (
                      <tr key={row.classroom}>
                        <td>{row.classroom}</td>
                        <td className="num">{row.students}</td>
                        <td className="num">{money(row.registration)}</td>
                        <td className="num">{money(row.tuition)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="muted">
              Tableau simple reconnu : {workbook.created ?? 0} création(s),{" "}
              {workbook.updated ?? 0} mise(s) à jour.
            </p>
          )}

          {workbook.warnings.length > 0 && (
            <>
              <h3 style={{ margin: "var(--space-4) 0 var(--space-2)" }}>
                Points d'attention
              </h3>
              <ul className="import-notes">
                {workbook.warnings.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </>
          )}

          {!workbook.applied && (
            <button
              type="button"
              onClick={() => void uploadWorkbook(false)}
              disabled={busy}
              style={{ marginTop: "var(--space-4)" }}
            >
              {busy ? "Reprise…" : `Reprendre ${workbook.students ?? ""} élève(s)`}
            </button>
          )}
        </div>
      )}

      {report && (
        <div className="card">
          <div className="card-title">
            {report.applied ? "Import appliqué" : "Résultat du pré-contrôle"}
          </div>

          <div className="stats">
            <div className="stat">
              <div className="label">Lignes lues</div>
              <div className="value">{report.rows_read}</div>
            </div>
            <div className="stat">
              <div className="label">{report.applied ? "Créés" : "À créer"}</div>
              <div className="value positive">{report.created}</div>
            </div>
            <div className="stat">
              <div className="label">{report.applied ? "Mis à jour" : "À mettre à jour"}</div>
              <div className="value">{report.updated}</div>
            </div>
            <div className="stat">
              <div className="label">Erreurs</div>
              <div className={`value ${report.error_count ? "negative" : "positive"}`}>
                {report.error_count}
              </div>
            </div>
          </div>

          {report.detail && <div className="alert error">{report.detail}</div>}

          {report.applied && report.ok && (
            <div className="alert success">
              Import terminé : {report.created} création(s), {report.updated} mise(s) à jour.
            </div>
          )}

          {report.errors.length > 0 && (
            <>
              <h3 style={{ marginBottom: 6 }}>Erreurs bloquantes</h3>
              <div className="table-wrap" style={{ marginBottom: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: 80 }}>Ligne</th>
                      <th>Problème</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.errors.map((row, index) => (
                      <tr key={index}>
                        <td>{row.line}</td>
                        <td style={{ whiteSpace: "normal" }}>{row.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {report.warnings.length > 0 && (
            <>
              <h3 style={{ marginBottom: 6 }}>Avertissements</h3>
              <div className="table-wrap" style={{ marginBottom: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: 80 }}>Ligne</th>
                      <th>Remarque</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.warnings.map((row, index) => (
                      <tr key={index}>
                        <td>{row.line}</td>
                        <td style={{ whiteSpace: "normal" }}>{row.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {canApply && (
            <button type="button" onClick={() => void upload(false)} disabled={busy}>
              {busy ? "Import…" : `Appliquer — ${report.created + report.updated} ligne(s)`}
            </button>
          )}
          {report.dry_run && !report.ok && (
            <p className="muted">
              Corrigez les erreurs ci-dessus dans votre fichier, puis relancez la
              vérification. Aucune donnée n'a été écrite.
            </p>
          )}
        </div>
      )}
    </>
  );
}
