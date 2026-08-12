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
  teacher: number | null;
  teacher_name: string | null;
};

type Teacher = { id: number; full_name: string };

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
  const { data: teachers } =
    useResource<{ results: Teacher[] }>("/teachers/?page_size=200");

  const [grade, setGrade] = useState("CI");
  const [count, setCount] = useState("2");
  const [capacity, setCapacity] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);

  const selected = grades?.find((row) => row.code === grade);

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

  /**
   * Désigne le titulaire d'une classe.
   *
   * Dans l'élémentaire, le maître tient toutes les matières de sa classe : le
   * désigner ici évite de l'attribuer matière par matière — vingt-neuf fois
   * pour un CE2.
   */
  async function assignTeacher(classroom: ClassRoom, teacherId: string) {
    setBusy(true);
    setStatus(null);
    try {
      await api.patch(`/classes/${classroom.id}/`, {
        teacher: teacherId ? Number(teacherId) : null,
      });
      reloadClasses();
      setStatus({
        kind: "success",
        text: teacherId
          ? `Titulaire de « ${classroom.name} » enregistré.`
          : `« ${classroom.name} » n'a plus de titulaire.`,
      });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
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
        Un niveau peut compter plusieurs classes — CI-A, CI-B, CI-C — rangées
        d'elles-mêmes dans l'ordre pédagogique. Le titulaire tient toutes les
        matières de sa classe : c'est lui qui en saisit les notes.
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
              <th>Classe</th>
              <th className="num">Élèves</th>
              <th>Titulaire</th>
              {isAdmin && <th style={{ width: 60 }} />}
            </tr>
          </thead>
          <tbody>
            {/* Une ligne par classe, et non par niveau : le titulaire est
                propre à chaque classe, et CI-A n'a pas le même maître que
                CI-B. */}
            {grades?.flatMap((row) =>
              row.sections.length === 0
                ? [
                    <tr key={row.code} className="muted">
                      <td>
                        <strong>{row.code}</strong>
                        <span className="muted"> · {row.label}</span>
                      </td>
                      <td colSpan={isAdmin ? 4 : 3} className="muted">
                        — aucune classe créée
                      </td>
                    </tr>,
                  ]
                : row.sections.map((name, index) => {
                    const classroom = classes?.results.find((c) => c.name === name);
                    const students = classroom?.student_count ?? 0;
                    return (
                      <tr key={name}>
                        <td>
                          {/* Le niveau n'est répété qu'une fois : le rappeler à
                              chaque section brouille la lecture verticale. */}
                          {index === 0 ? (
                            <>
                              <strong>{row.code}</strong>
                              <span className="muted"> · {row.label}</span>
                            </>
                          ) : (
                            <span className="muted">↳</span>
                          )}
                        </td>
                        <td>
                          <strong>{name}</strong>
                        </td>
                        <td className="num">{students}</td>
                        <td>
                          {isAdmin && classroom ? (
                            <select
                              value={classroom.teacher ?? ""}
                              disabled={busy}
                              aria-label={`Titulaire de ${name}`}
                              onChange={(event) =>
                                assignTeacher(classroom, event.target.value)
                              }
                            >
                              <option value="">— non attribué —</option>
                              {teachers?.results.map((teacher) => (
                                <option key={teacher.id} value={teacher.id}>
                                  {teacher.full_name}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="muted">
                              {classroom?.teacher_name ?? "— non attribué —"}
                            </span>
                          )}
                        </td>
                        {isAdmin && (
                          <td>
                            {students === 0 && classroom && (
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
                          </td>
                        )}
                      </tr>
                    );
                  }),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
