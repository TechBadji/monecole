import { useState } from "react";

import { api } from "../api";
import type { SchoolYear } from "../types";
import { useYear } from "../year";

type Plan = {
  moves: { student: number; name: string; matricule: string; from: string; to: string }[];
  blocked: { student: number; name: string; classroom: string }[];
  repeats: number;
  already: number;
};

/**
 * Ouverture d'une année scolaire, et passage des élèves.
 *
 * Deux gestes distincts, volontairement séparés : créer l'année ne déplace
 * personne. Une école ouvre souvent l'année suivante en juin, pour préparer les
 * tarifs, bien avant d'arrêter qui passe et qui redouble.
 */
export default function SchoolYears({ isAdmin }: { isAdmin: boolean }) {
  const { years, current, reload } = useYear();

  const [label, setLabel] = useState("");
  const [start, setStart] = useState("");
  const [months, setMonths] = useState("9");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);

  const [target, setTarget] = useState<number | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [repeating, setRepeating] = useState<Set<number>>(new Set());

  /** Octobre de l'année saisie à septembre de la suivante — l'exercice sénégalais. */
  function suggest(startYear: string) {
    const parsed = Number(startYear);
    if (!Number.isInteger(parsed) || parsed < 2000) return;
    setLabel(`${parsed}/${parsed + 1}`);
    setStart(`${parsed}-10-01`);
  }

  async function createYear() {
    setBusy(true);
    setStatus(null);
    try {
      const startDate = new Date(start);
      const end = new Date(startDate.getFullYear() + 1, 8, 30);
      await api.post<SchoolYear>("/school-years/", {
        label,
        start_date: start,
        end_date: end.toISOString().slice(0, 10),
        tuition_months: Number(months) || 9,
        // La nouvelle année ne devient pas courante d'office : l'école bascule
        // quand elle est prête, souvent des semaines après l'avoir créée.
        is_current: false,
      });
      setStatus({ kind: "success", text: `Année ${label} créée.` });
      setLabel("");
      setStart("");
      reload();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Création impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function setCurrent(year: SchoolYear) {
    setBusy(true);
    setStatus(null);
    try {
      await api.patch(`/school-years/${year.id}/`, { is_current: true });
      setStatus({ kind: "success", text: `${year.label} est désormais l'année en cours.` });
      reload();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Bascule impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function preview() {
    if (!current || !target) return;
    setBusy(true);
    setStatus(null);
    try {
      const params = new URLSearchParams({ from: String(current.id), to: String(target) });
      for (const id of repeating) params.append("repeating", String(id));
      setPlan(await api.get<Plan>(`/classes/promotion/?${params}`));
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Calcul impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!current || !target) return;
    setBusy(true);
    setStatus(null);
    try {
      const response = await api.post<{ detail: string }>("/classes/promotion/", {
        from: current.id,
        to: target,
        repeating: [...repeating],
      });
      setStatus({ kind: "success", text: response.detail });
      setPlan(null);
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Passage impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  function toggleRepeat(studentId: number) {
    setRepeating((set) => {
      const next = new Set(set);
      next.has(studentId) ? next.delete(studentId) : next.add(studentId);
      return next;
    });
  }

  return (
    <div className="card">
      <div className="card-title">Années scolaires</div>
      <p className="muted" style={{ marginBottom: "var(--space-4)" }}>
        L'exercice court d'octobre à septembre ; les mensualités s'arrêtent en
        juin. Créer une année ne déplace aucun élève : le passage est un geste
        séparé, en bas de cette carte.
      </p>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      <div className="table-wrap">
        <table className="table-dense">
          <thead>
            <tr>
              <th>Année</th>
              <th>Exercice</th>
              <th className="num">Mensualités</th>
              <th>État</th>
              {isAdmin && <th style={{ width: 150 }} />}
            </tr>
          </thead>
          <tbody>
            {years.map((year) => (
              <tr key={year.id}>
                <td>
                  <strong>{year.label}</strong>
                </td>
                <td className="muted">
                  {year.start_date} → {year.end_date}
                </td>
                <td className="num">{year.tuition_months} mois</td>
                <td>
                  {year.is_current ? (
                    <span className="badge paid">En cours</span>
                  ) : (
                    <span className="muted">close</span>
                  )}
                </td>
                {isAdmin && (
                  <td>
                    {!year.is_current && (
                      <button
                        type="button"
                        className="ghost small"
                        disabled={busy}
                        onClick={() => setCurrent(year)}
                      >
                        Rendre courante
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {years.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  Aucune année scolaire. Créez-en une pour commencer.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {isAdmin && (
        <>
          <h3 className="settings-subtitle">Ouvrir une année</h3>
          <div className="toolbar">
            <div className="field">
              <label htmlFor="start-year">Rentrée</label>
              <input
                id="start-year"
                type="number"
                min={2000}
                max={2100}
                placeholder="2026"
                onChange={(event) => suggest(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="year-label">Libellé</label>
              <input
                id="year-label"
                value={label}
                placeholder="2026/2027"
                onChange={(event) => setLabel(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="year-start">Début d'exercice</label>
              <input
                id="year-start"
                type="date"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </div>
            <div className="field" style={{ maxWidth: 130 }}>
              <label htmlFor="year-months">Mensualités</label>
              <input
                id="year-months"
                type="number"
                min={1}
                max={12}
                value={months}
                onChange={(event) => setMonths(event.target.value)}
              />
            </div>
            <button type="button" onClick={createYear} disabled={busy || !label || !start}>
              Créer l'année
            </button>
          </div>

          <h3 className="settings-subtitle">Passage des élèves</h3>
          <p className="muted" style={{ marginBottom: "var(--space-3)" }}>
            Les élèves montent d'un niveau et arrivent <strong>en attente</strong> :
            ils apparaissent au secrétariat, qui doit les relancer, mais aucune
            mensualité ne leur est réclamée avant confirmation de l'inscription.
          </p>

          <div className="toolbar">
            <div className="field">
              <label>Depuis</label>
              <p className="readonly-value">{current?.label ?? "—"}</p>
            </div>
            <div className="field" style={{ minWidth: 190 }}>
              <label htmlFor="promotion-target">Vers</label>
              <select
                id="promotion-target"
                value={target ?? ""}
                onChange={(event) => {
                  setTarget(event.target.value ? Number(event.target.value) : null);
                  setPlan(null);
                }}
              >
                <option value="">— choisir une année —</option>
                {years
                  .filter((year) => year.id !== current?.id)
                  .map((year) => (
                    <option key={year.id} value={year.id}>
                      {year.label}
                    </option>
                  ))}
              </select>
            </div>
            <button
              type="button"
              className="secondary"
              onClick={preview}
              disabled={busy || !target}
            >
              Simuler le passage
            </button>
            {plan && (
              <button type="button" onClick={apply} disabled={busy}>
                Appliquer
              </button>
            )}
          </div>

          {/* Toujours simuler avant d'appliquer : un passage touche tous les
              élèves de l'établissement d'un coup. */}
          {plan && (
            <>
              <div className="alert success">
                {plan.moves.length} élève(s) monteraient de classe,{" "}
                {plan.repeats} redoubleraient, {plan.already} ont déjà une
                inscription. {plan.blocked.length > 0 && (
                  <>
                    <strong>{plan.blocked.length} sans classe supérieure</strong> —
                    ils sortent de l'école, à traiter à la main.
                  </>
                )}
              </div>

              <div className="table-wrap promotion-preview">
                <table className="table-dense">
                  <thead>
                    <tr>
                      <th>Matricule</th>
                      <th>Élève</th>
                      <th>De</th>
                      <th>Vers</th>
                      <th style={{ width: 120 }}>Redouble</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.moves.map((move) => (
                      <tr key={move.student}>
                        <td className="muted">{move.matricule}</td>
                        <td>{move.name}</td>
                        <td className="muted">{move.from}</td>
                        <td>
                          <strong>
                            {repeating.has(move.student) ? move.from : move.to}
                          </strong>
                        </td>
                        <td>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              checked={repeating.has(move.student)}
                              onChange={() => toggleRepeat(move.student)}
                            />
                            <span className="visually-hidden">
                              {move.name} redouble
                            </span>
                          </label>
                        </td>
                      </tr>
                    ))}
                    {plan.blocked.map((student) => (
                      <tr key={`b-${student.student}`} className="row-error">
                        <td className="muted">—</td>
                        <td>{student.name}</td>
                        <td className="muted">{student.classroom}</td>
                        <td colSpan={2} className="muted">
                          Aucune classe supérieure — fin de cursus
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
