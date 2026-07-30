import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import type { Paginated } from "../types";

type SheetSummary = {
  id: number;
  composition: string;
  composition_status: string;
  classroom: string;
  classroom_id: number;
  subject: string;
  coefficient: number;
  validated: boolean;
  students: number;
  entered: number;
};

type SheetRow = {
  grade: number;
  student: number;
  matricule: string;
  name: string;
  value: string | null;
  is_absent: boolean;
  comment: string;
};

type Sheet = {
  id: number;
  composition: string;
  composition_status: string;
  editable: boolean;
  classroom: string;
  subject: string;
  coefficient: number;
  validated: boolean;
  validated_at: string | null;
  validated_by: string;
  rows: SheetRow[];
};

type Composition = { id: number; name: string; status: string };

/** Une note est valide si elle est vide, absente, ou comprise entre 0 et 20. */
function gradeError(value: string): string | null {
  if (value.trim() === "") return null;
  const parsed = Number(value.replace(",", "."));
  if (Number.isNaN(parsed)) return "note illisible";
  if (parsed < 0 || parsed > 20) return "hors barème 0–20";
  return null;
}

export default function Grades() {
  const { profile } = useAuth();
  const isAdmin = profile?.role === "ADMIN";

  const { data: compositions } = useResource<Paginated<Composition>>("/compositions/");
  const [composition, setComposition] = useState<number | null>(null);

  useEffect(() => {
    if (composition === null && compositions?.results.length) {
      // La composition ouverte est celle sur laquelle on travaille.
      const open = compositions.results.find((c) => c.status === "OPEN");
      setComposition((open ?? compositions.results[0]).id);
    }
  }, [compositions, composition]);

  const { data: sheets, reload: reloadSheets } = useResource<{ results: SheetSummary[] }>(
    composition ? `/grade-sheets/?composition=${composition}` : null,
  );

  const [selected, setSelected] = useState<number | null>(null);
  const { data: sheet, reload: reloadSheet } = useResource<Sheet>(
    selected ? `/grade-sheets/${selected}/` : null,
  );

  const [draft, setDraft] = useState<Record<number, SheetRow>>({});
  const [busy, setBusy] = useState(false);
  const [savingRow, setSavingRow] = useState<number | null>(null);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);

  useEffect(() => {
    if (!sheet) return;
    setDraft(Object.fromEntries(sheet.rows.map((row) => [row.grade, { ...row }])));
    setStatus(null);
  }, [sheet]);

  const grouped = useMemo(() => {
    const byClass = new Map<string, SheetSummary[]>();
    for (const item of sheets?.results ?? []) {
      const list = byClass.get(item.classroom) ?? [];
      list.push(item);
      byClass.set(item.classroom, list);
    }
    return [...byClass.entries()];
  }, [sheets]);

  const rows = sheet?.rows ?? [];
  const values = Object.values(draft);

  const errors = useMemo(
    () =>
      values
        .filter((row) => !row.is_absent && gradeError(String(row.value ?? "")))
        .map((row) => `${row.name} : ${gradeError(String(row.value ?? ""))}`),
    [values],
  );

  const filled = values.filter(
    (row) => row.is_absent || String(row.value ?? "").trim() !== "",
  ).length;

  const average = useMemo(() => {
    const graded = values
      .filter((row) => !row.is_absent && String(row.value ?? "").trim() !== "")
      .map((row) => Number(String(row.value).replace(",", ".")))
      .filter((value) => !Number.isNaN(value));
    if (!graded.length) return null;
    return (graded.reduce((sum, value) => sum + value, 0) / graded.length).toFixed(2);
  }, [values]);

  function update(gradeId: number, patch: Partial<SheetRow>) {
    setDraft((current) => ({ ...current, [gradeId]: { ...current[gradeId], ...patch } }));
  }

  function payload(row: SheetRow) {
    return {
      grade: row.grade,
      value: row.is_absent ? null : String(row.value ?? "").replace(",", "."),
      is_absent: row.is_absent,
      comment: row.comment,
    };
  }

  /** Enregistrement unitaire : l'enseignant corrige une copie isolée. */
  async function saveOne(row: SheetRow) {
    if (!sheet) return;
    setSavingRow(row.grade);
    setStatus(null);
    try {
      await api.post(`/grade-sheets/${sheet.id}/save-one/`, payload(row));
      setStatus({ kind: "success", text: `Note de ${row.name} enregistrée.` });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
      });
    } finally {
      setSavingRow(null);
    }
  }

  /** Enregistrement par lot : toute la classe en une requête. */
  async function saveAll() {
    if (!sheet) return;
    setBusy(true);
    setStatus(null);
    try {
      const result = await api.post<{ saved: number }>(
        `/grade-sheets/${sheet.id}/save/`,
        { rows: values.map(payload) },
      );
      setStatus({ kind: "success", text: `${result.saved} note(s) enregistrée(s).` });
      reloadSheets();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    if (!sheet) return;
    setBusy(true);
    setStatus(null);
    try {
      await api.post(`/grade-sheets/${sheet.id}/save/`, { rows: values.map(payload) });
      await api.post(`/grade-sheets/${sheet.id}/validate_sheet/`);
      reloadSheet();
      reloadSheets();
      setStatus({
        kind: "success",
        text: "Feuille validée. Les bulletins peuvent être édités.",
      });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Validation impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function unvalidate() {
    if (!sheet) return;
    setBusy(true);
    try {
      await api.post(`/grade-sheets/${sheet.id}/unvalidate/`);
      reloadSheet();
      reloadSheets();
      setStatus({ kind: "warning", text: "Feuille rouverte à la correction." });
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
          <h1>Saisie des notes</h1>
          <p>
            Notes sur 20. Une note peut être enregistrée seule ou toute la classe en
            une fois. Un élève absent se coche plutôt que de recevoir un zéro : son
            coefficient sort alors de la moyenne.
          </p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field" style={{ minWidth: 230 }}>
          <label htmlFor="composition">Composition</label>
          <select
            id="composition"
            value={composition ?? ""}
            onChange={(event) => {
              setComposition(Number(event.target.value));
              setSelected(null);
            }}
          >
            {compositions?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      <div className="grid-sidebar">
        <div className="card">
          <div className="card-title">Mes feuilles</div>
          {sheets?.results.length === 0 && (
            <p className="muted">
              Aucune feuille de notes. L'administration doit ouvrir la saisie de
              cette composition, et vous attribuer au moins une matière.
            </p>
          )}
          {/* Regroupées par classe : une liste à plat de quarante-huit feuilles
              oblige à lire chaque ligne pour retrouver la sienne. */}
          {grouped.map(([classroom, items]) => (
            <div className="sheet-group" key={classroom}>
              <h3 className="sheet-group-title">{classroom}</h3>
              <ul className="sheet-list">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`sheet-item ${selected === item.id ? "active" : ""}`}
                      onClick={() => setSelected(item.id)}
                    >
                      <span className="sheet-name">{item.subject}</span>
                      <span className="sheet-meta">
                        coef {item.coefficient} · {item.entered}/{item.students}
                        {item.validated && <span className="badge paid">Validée</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div>
          {!sheet && (
            <div className="card empty">
              Choisissez une feuille de notes à gauche.
            </div>
          )}

          {sheet && (
            <div className="card">
              <div className="chart-head">
                <div>
                  <h2>
                    {sheet.classroom} — {sheet.subject}
                  </h2>
                  <p className="muted">
                    {sheet.composition} · coefficient {sheet.coefficient}
                    {average && ` · moyenne saisie ${average}/20`}
                  </p>
                </div>
                <div className="page-actions">
                  {sheet.editable && (
                    <>
                      <button
                        type="button"
                        className="secondary"
                        onClick={saveAll}
                        disabled={busy || errors.length > 0}
                      >
                        {busy ? "Enregistrement…" : "Tout enregistrer"}
                      </button>
                      <button
                        type="button"
                        onClick={validate}
                        disabled={busy || errors.length > 0 || filled < rows.length}
                      >
                        Valider la feuille
                      </button>
                    </>
                  )}
                  {sheet.validated && isAdmin && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={unvalidate}
                      disabled={busy}
                    >
                      Dévalider
                    </button>
                  )}
                </div>
              </div>

              {sheet.validated && (
                <div className="alert success">
                  Feuille validée le{" "}
                  {sheet.validated_at
                    ? new Date(sheet.validated_at).toLocaleString("fr-FR", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })
                    : "—"}{" "}
                  par {sheet.validated_by}.
                  {isAdmin && " Dévalidez-la pour corriger une note."}
                </div>
              )}

              {!sheet.editable && !sheet.validated && (
                <div className="alert warning">
                  Saisie fermée : la composition n'est pas ouverte.
                </div>
              )}

              {errors.length > 0 && (
                <div className="alert error">
                  {errors.length} note(s) invalide(s) : {errors.slice(0, 3).join(" · ")}
                  {errors.length > 3 && ` … et ${errors.length - 3} autre(s)`}
                </div>
              )}

              {filled < rows.length && sheet.editable && (
                <div className="alert warning">
                  {rows.length - filled} élève(s) sans note ni mention d'absence. La
                  feuille ne pourra pas être validée tant qu'ils ne sont pas traités.
                </div>
              )}

              <div className="table-wrap">
                <table className="table-dense">
                  <thead>
                    <tr>
                      <th style={{ width: 80 }}>Mat.</th>
                      <th>Élève</th>
                      <th className="num" style={{ width: 110 }}>Note /20</th>
                      <th style={{ width: 70 }}>Absent</th>
                      <th>Appréciation</th>
                      {sheet.editable && <th style={{ width: 90 }} />}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const current = draft[row.grade] ?? row;
                      const error = current.is_absent
                        ? null
                        : gradeError(String(current.value ?? ""));
                      return (
                        <tr key={row.grade} className={error ? "row-error" : ""}>
                          <td className="muted">{row.matricule}</td>
                          <td>{row.name}</td>
                          <td className="num">
                            <input
                              className="cell"
                              inputMode="decimal"
                              placeholder="—"
                              value={current.is_absent ? "" : (current.value ?? "")}
                              disabled={!sheet.editable || current.is_absent}
                              aria-invalid={Boolean(error)}
                              aria-label={`Note de ${row.name}`}
                              onChange={(event) =>
                                update(row.grade, { value: event.target.value })
                              }
                            />
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              className="checkbox"
                              checked={current.is_absent}
                              disabled={!sheet.editable}
                              aria-label={`${row.name} absent`}
                              onChange={(event) =>
                                update(row.grade, {
                                  is_absent: event.target.checked,
                                  value: event.target.checked ? null : current.value,
                                })
                              }
                            />
                          </td>
                          <td>
                            <input
                              value={current.comment}
                              placeholder="Facultatif"
                              disabled={!sheet.editable}
                              onChange={(event) =>
                                update(row.grade, { comment: event.target.value })
                              }
                            />
                          </td>
                          {sheet.editable && (
                            <td>
                              <button
                                type="button"
                                className="secondary small"
                                onClick={() => saveOne(current)}
                                disabled={savingRow === row.grade || Boolean(error)}
                              >
                                {savingRow === row.grade ? "…" : "Enregistrer"}
                              </button>
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
