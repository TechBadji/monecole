import { useState } from "react";

import { api } from "../api";
import { useResource } from "../hooks";

type Grade = {
  code: string;
  label: string;
  level: "PRESCHOOL" | "PRIMARY";
  sections: string[];
};

type ClassRoom = {
  id: number;
  name: string;
  student_count: number;
};

const LEVEL_LABELS: Record<string, string> = {
  PRESCHOOL: "Préscolaire",
  PRIMARY: "Élémentaire",
};

/**
 * Création des sections d'un même niveau : CI-A, CI-B, CI-C.
 *
 * Une école à trois classes de CI ne doit pas saisir trois classes à la main et
 * deviner leur rang d'affichage. Le niveau commande l'ordre, la section
 * départage — c'est le serveur qui le calcule.
 */
export default function ClassSections({ isAdmin }: { isAdmin: boolean }) {
  const { data: grades, reload } = useResource<Grade[]>("/classes/grades/");
  const { data: classes, reload: reloadClasses } =
    useResource<{ results: ClassRoom[] }>("/classes/?page_size=100");

  const [grade, setGrade] = useState("CI");
  const [count, setCount] = useState("2");
  const [capacity, setCapacity] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);

  const selected = grades?.find((row) => row.code === grade);
  const countById = new Map((classes?.results ?? []).map((c) => [c.name, c.student_count]));

  async function createSections() {
    setBusy(true);
    setStatus(null);
    try {
      const response = await api.post<{ detail: string }>("/classes/sections/", {
        grade,
        count: Number(count),
        capacity: capacity ? Number(capacity) : null,
      });
      setStatus({ kind: "success", text: response.detail });
      reload();
      reloadClasses();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Création impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove(classroom: ClassRoom) {
    setBusy(true);
    setStatus(null);
    try {
      await api.delete(`/classes/${classroom.id}/`);
      setStatus({ kind: "success", text: `« ${classroom.name} » a été supprimée.` });
      reload();
      reloadClasses();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Suppression impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card-title">Classes et sections</div>
      <p className="muted" style={{ marginBottom: "var(--space-4)" }}>
        Un niveau peut compter plusieurs classes. Elles sont nommées CI-A, CI-B,
        CI-C, et se rangent d'elles-mêmes dans l'ordre pédagogique.
      </p>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      {isAdmin && (
        <div className="toolbar">
          <div className="field">
            <label htmlFor="grade">Niveau</label>
            <select id="grade" value={grade} onChange={(e) => setGrade(e.target.value)}>
              {grades?.map((row) => (
                <option key={row.code} value={row.code}>
                  {row.label} ({LEVEL_LABELS[row.level]})
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="count">Nombre de classes</label>
            <input
              id="count"
              type="number"
              min={1}
              max={26}
              value={count}
              onChange={(e) => setCount(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="capacity">Capacité (facultatif)</label>
            <input
              id="capacity"
              type="number"
              min={1}
              placeholder="—"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
          </div>
          <button type="button" onClick={createSections} disabled={busy}>
            {busy ? "Création…" : "Créer les classes"}
          </button>
        </div>
      )}

      {/* Prévenir plutôt que surprendre : le renommage préserve les élèves,
          mais l'administrateur doit le savoir avant de cliquer. */}
      {isAdmin && selected?.sections.includes(selected.code) && (
        <div className="alert warning">
          La classe « {selected.code} » sera renommée « {selected.code}-A ». Ses
          élèves, tarifs et notes la suivent.
        </div>
      )}

      <div className="table-wrap">
        <table className="table-dense">
          <thead>
            <tr>
              <th>Niveau</th>
              <th>Cycle</th>
              <th>Classes</th>
            </tr>
          </thead>
          <tbody>
            {grades?.map((row) => (
              <tr key={row.code}>
                <td>
                  <strong>{row.code}</strong>
                  <span className="muted"> · {row.label}</span>
                </td>
                <td className="muted">{LEVEL_LABELS[row.level]}</td>
                <td>
                  {row.sections.length === 0 ? (
                    <span className="muted">— aucune classe</span>
                  ) : (
                    <span className="section-chips">
                      {row.sections.map((name) => {
                        const students = countById.get(name) ?? 0;
                        const classroom = classes?.results.find((c) => c.name === name);
                        return (
                          <span key={name} className="chip section-chip">
                            {name}
                            <span className="muted">
                              {" · "}
                              {students} élève{students > 1 ? "s" : ""}
                            </span>
                            {/* La suppression tient sur la pastille : en colonne
                                séparée, elle sortait du cadre sur un écran de
                                1 400 px et n'était atteignable qu'en faisant
                                défiler le tableau. Seules les classes vides
                                l'offrent — le serveur refuse les autres, autant
                                ne pas proposer le geste. */}
                            {isAdmin && students === 0 && classroom && (
                              <button
                                type="button"
                                className="chip-remove"
                                disabled={busy}
                                onClick={() => remove(classroom)}
                                aria-label={`Supprimer la classe ${name}`}
                                title={`Supprimer ${name}, qui ne compte aucun élève`}
                              >
                                ×
                              </button>
                            )}
                          </span>
                        );
                      })}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
