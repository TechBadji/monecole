import { useState, type FormEvent } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import { useYear } from "../year";
import type { Paginated } from "../types";

type Composition = {
  id: number;
  name: string;
  kind: "TERM" | "FREE";
  term: number | null;
  date: string;
  status: "DRAFT" | "OPEN" | "CLOSED";
  sheets_total: number;
  sheets_validated: number;
};

type Progress = {
  composition: string;
  status: string;
  total: number;
  validated: number;
  complete: number;
  results: {
    sheet: number;
    classroom: string;
    subject: string;
    max_score: number;
    validated: boolean;
    entered: number;
    expected: number;
    complete: boolean;
  }[];
};

const STATUS = {
  DRAFT: { label: "En préparation", tone: "" },
  OPEN: { label: "Saisie ouverte", tone: "partial" },
  CLOSED: { label: "Clôturée", tone: "paid" },
} as const;

export default function Compositions() {
  const { profile } = useAuth();
  const isAdmin = profile?.role === "ADMIN";

  // L'année vient du sélecteur global : la résoudre ici ferait saisir dans
  // l'année courante quelqu'un qui consulte une année close.
  const { selected: currentYear } = useYear();
  const { data, reload } = useResource<Paginated<Composition>>("/compositions/");

  const [selected, setSelected] = useState<number | null>(null);
  const { data: progress, reload: reloadProgress } = useResource<Progress>(
    selected ? `/compositions/${selected}/progress/` : null,
  );

  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);
  const [draft, setDraft] = useState({
    name: "",
    kind: "TERM",
    term: "1",
    date: new Date().toISOString().slice(0, 10),
  });

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!currentYear) return;
    setBusy(true);
    setStatus(null);
    try {
      await api.post("/compositions/", {
        year: currentYear.id,
        name: draft.name,
        kind: draft.kind,
        term: draft.kind === "TERM" ? Number(draft.term) : null,
        date: draft.date,
      });
      setDraft({ ...draft, name: "" });
      reload();
      setStatus({
        kind: "success",
        text: "Composition créée. Ouvrez la saisie pour générer les feuilles de notes.",
      });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Création impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function act(id: number, action: "open" | "close") {
    setBusy(true);
    setStatus(null);
    try {
      const result = await api.post<{ sheets_created?: number; grades_created?: number }>(
        `/compositions/${id}/${action}/`,
      );
      reload();
      if (selected === id) reloadProgress();
      setStatus({
        kind: "success",
        text:
          action === "open"
            ? `Saisie ouverte : ${result.sheets_created ?? 0} feuille(s) et ` +
              `${result.grades_created ?? 0} ligne(s) d'élève créées.`
            : "Composition clôturée. Les notes ne peuvent plus être modifiées.",
      });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Opération impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Compositions</h1>
          <p>
            Une composition est une période d'évaluation : trimestrielle, ou libre à
            la date et sous l'intitulé de votre choix. Ouvrir la saisie génère une
            feuille de notes par matière et par classe.
          </p>
        </div>
      </div>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      {isAdmin && (
        <form className="card" onSubmit={create}>
          <div className="card-title">Nouvelle composition</div>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <div className="field" style={{ minWidth: 240 }}>
              <label htmlFor="name">Intitulé</label>
              <input
                id="name"
                value={draft.name}
                placeholder="1er trimestre"
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="kind">Nature</label>
              <select
                id="kind"
                value={draft.kind}
                onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
              >
                <option value="TERM">Composition trimestrielle</option>
                <option value="FREE">Évaluation libre</option>
              </select>
            </div>
            {draft.kind === "TERM" && (
              <div className="field" style={{ minWidth: 110 }}>
                <label htmlFor="term">Trimestre</label>
                <select
                  id="term"
                  value={draft.term}
                  onChange={(event) => setDraft({ ...draft, term: event.target.value })}
                >
                  <option value="1">1er</option>
                  <option value="2">2e</option>
                  <option value="3">3e</option>
                </select>
              </div>
            )}
            <div className="field">
              <label htmlFor="date">Date</label>
              <input
                id="date"
                type="date"
                value={draft.date}
                onChange={(event) => setDraft({ ...draft, date: event.target.value })}
                required
              />
            </div>
            <button type="submit" disabled={busy || !currentYear}>
              Créer
            </button>
          </div>
        </form>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Intitulé</th>
              <th>Nature</th>
              <th>Date</th>
              <th>Statut</th>
              <th className="num">Feuilles validées</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data?.results.map((composition) => (
              <tr key={composition.id}>
                <td>{composition.name}</td>
                <td>
                  {composition.kind === "TERM"
                    ? `Trimestre ${composition.term ?? "—"}`
                    : "Évaluation libre"}
                </td>
                <td>{new Date(composition.date).toLocaleDateString("fr-FR")}</td>
                <td>
                  <span className={`badge ${STATUS[composition.status].tone}`}>
                    {STATUS[composition.status].label}
                  </span>
                </td>
                <td className="num">
                  {composition.sheets_validated} / {composition.sheets_total}
                </td>
                <td>
                  <div className="row-actions">
                    <button
                      type="button"
                      className="secondary small"
                      onClick={() =>
                        setSelected(selected === composition.id ? null : composition.id)
                      }
                    >
                      {selected === composition.id ? "Masquer" : "Suivi"}
                    </button>
                    {isAdmin && composition.status !== "CLOSED" && (
                      <button
                        type="button"
                        className="small"
                        onClick={() => act(composition.id, "open")}
                        disabled={busy}
                      >
                        {composition.status === "OPEN" ? "Régénérer" : "Ouvrir la saisie"}
                      </button>
                    )}
                    {isAdmin && composition.status === "OPEN" && (
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => act(composition.id, "close")}
                        disabled={busy}
                      >
                        Clôturer
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {data?.results.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  Aucune composition. Créez-en une pour lancer une période d'évaluation.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && progress && (
        <div className="card">
          <div className="card-title">
            Suivi de saisie — {progress.composition}
          </div>

          <div className="stats">
            <div className="stat">
              <div className="label">Feuilles</div>
              <div className="value">{progress.total}</div>
            </div>
            <div className="stat">
              <div className="label">Complètes</div>
              <div className="value">{progress.complete}</div>
            </div>
            <div className="stat">
              <div className="label">Validées</div>
              <div className={`value ${progress.validated === progress.total ? "positive" : ""}`}>
                {progress.validated}
              </div>
            </div>
          </div>

          {progress.validated < progress.total && (
            <div className="alert warning">
              {progress.total - progress.validated} feuille(s) non validée(s). Les
              bulletins édités maintenant porteront la mention « document provisoire ».
            </div>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Classe</th>
                  <th>Matière</th>
                  <th className="num">Coef.</th>
                  <th className="num">Saisies</th>
                  <th>État</th>
                </tr>
              </thead>
              <tbody>
                {progress.results.map((row) => (
                  <tr key={row.sheet}>
                    <td>{row.classroom}</td>
                    <td>{row.subject}</td>
                    <td className="num">{row.max_score}</td>
                    <td className="num">
                      {row.entered} / {row.expected}
                    </td>
                    <td>
                      {row.validated ? (
                        <span className="badge paid">Validée</span>
                      ) : row.complete ? (
                        <span className="badge partial">À valider</span>
                      ) : (
                        <span className="badge unpaid">Incomplète</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
