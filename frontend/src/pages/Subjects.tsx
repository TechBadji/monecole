import { useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import { useYear } from "../year";
import type { ClassRoom, Paginated } from "../types";

type Subject = {
  id: number;
  code: string;
  name: string;
  default_max_score: number;
  order: number;
  is_active: boolean;
};

type ClassSubject = {
  id: number;
  classroom: number;
  subject: number;
  subject_name: string;
  max_score: number;
  teacher: number | null;
  teacher_name: string | null;
  order: number;
};

type Teacher = { id: number; full_name: string; matricule: string };

/** Ligne de configuration d'une classe : matière cochée, barème, enseignant. */
type Row = {
  subject: number;
  name: string;
  enabled: boolean;
  max_score: number;
  teacher: string;
};

export default function Subjects() {
  const { profile } = useAuth();
  const isAdmin = profile?.role === "ADMIN";

  const { data: subjects, reload: reloadSubjects } =
    useResource<Paginated<Subject>>("/subjects/?page_size=100");
  const { data: classes } = useResource<Paginated<ClassRoom>>("/classes/");
  const { data: teachers } = useResource<Paginated<Teacher>>("/teachers/?page_size=100");
  // L'année vient du sélecteur global : la résoudre ici ferait saisir dans
  // l'année courante quelqu'un qui consulte une année close.
  const { selected: currentYear } = useYear();

  const [classroom, setClassroom] = useState<number | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [draft, setDraft] = useState({ code: "", name: "", default_max_score: "1" });

  useEffect(() => {
    if (classroom === null && classes?.results.length) {
      setClassroom(classes.results[0].id);
    }
  }, [classes, classroom]);

  const assignedPath =
    classroom && currentYear
      ? `/class-subjects/?classroom=${classroom}&year=${currentYear.id}&page_size=100`
      : null;
  const { data: assigned, reload: reloadAssigned } =
    useResource<Paginated<ClassSubject>>(assignedPath);

  // La grille se reconstruit à chaque changement de classe : elle croise le
  // catalogue de matières avec ce qui est déjà affecté.
  useEffect(() => {
    if (!subjects || !assigned) return;
    const byId = new Map(assigned.results.map((link) => [link.subject, link]));
    setRows(
      subjects.results.map((subject) => {
        const link = byId.get(subject.id);
        return {
          subject: subject.id,
          name: subject.name,
          enabled: Boolean(link),
          max_score: link?.max_score ?? subject.default_max_score,
          teacher: link?.teacher ? String(link.teacher) : "",
        };
      }),
    );
    setStatus(null);
  }, [subjects, assigned]);

  function update(subjectId: number, patch: Partial<Row>) {
    setRows((current) =>
      current.map((row) => (row.subject === subjectId ? { ...row, ...patch } : row)),
    );
  }

  async function createSubject() {
    if (!draft.code || !draft.name) return;
    setBusy(true);
    setStatus(null);
    try {
      await api.post("/subjects/", {
        code: draft.code.toUpperCase(),
        name: draft.name,
        default_max_score: Number(draft.default_max_score) || 1,
        order: (subjects?.count ?? 0) + 1,
      });
      setDraft({ code: "", name: "", default_max_score: "1" });
      reloadSubjects();
      setStatus({ kind: "success", text: "Matière ajoutée au catalogue." });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Création impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function seedDefaults() {
    setBusy(true);
    try {
      const result = await api.post<{ created: number }>("/subjects/seed-defaults/");
      reloadSubjects();
      setStatus({
        kind: result.created ? "success" : "warning",
        text: result.created
          ? `${result.created} matière(s) ajoutée(s).`
          : "Les matières usuelles sont déjà présentes.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function saveAssignment() {
    if (!classroom || !currentYear) return;
    setBusy(true);
    setStatus(null);
    try {
      const result = await api.post<{
        created: number;
        updated: number;
        removed: number;
        detail: string | null;
      }>("/class-subjects/bulk/", {
        classroom,
        year: currentYear.id,
        subjects: rows
          .filter((row) => row.enabled)
          .map((row) => ({
            subject: row.subject,
            max_score: row.max_score,
            teacher: row.teacher ? Number(row.teacher) : null,
          })),
      });
      reloadAssigned();
      setStatus({
        kind: result.detail ? "warning" : "success",
        text:
          `Configuration enregistrée : ${result.created} ajout(s), ` +
          `${result.updated} mise(s) à jour, ${result.removed} retrait(s).` +
          (result.detail ? ` ${result.detail}` : ""),
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

  const enabled = rows.filter((row) => row.enabled);
  const totalScale = enabled.reduce((sum, row) => sum + row.max_score, 0);

  /**
   * Applique le catalogue relevé pour le niveau de la classe.
   *
   * Le serveur ne retouche pas les matières déjà rattachées : une école qui a
   * ajusté un barème ne doit pas le voir écrasé par un rappel du catalogue.
   */
  async function applyCatalogue() {
    if (!classroom || !currentYear) return;
    setBusy(true);
    setStatus(null);
    try {
      const response = await api.post<{ created: number; detail: string }>(
        "/class-subjects/apply-catalogue/",
        { classroom, year: currentYear.id },
      );
      reloadSubjects();
      reloadAssigned();
      setStatus({ kind: response.created ? "success" : "warning", text: response.detail });
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Application impossible.",
      });
    } finally {
      setBusy(false);
    }
  }
  const withoutTeacher = enabled.filter((row) => !row.teacher).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Matières et barèmes</h1>
          <p>
            Le barème fait le poids : une matière sur 20 compte cinq fois une matière sur 4, et la moyenne vaut la somme des notes divisée par la somme des barèmes. Le catalogue est commun à l'établissement ; les barèmes et
            l'enseignant se règlent classe par classe — le français ne pèse pas le
            même poids en CI et en CM2.
          </p>
        </div>
        {isAdmin && subjects?.count === 0 && (
          <div className="page-actions">
            <button type="button" className="secondary" onClick={seedDefaults} disabled={busy}>
              Créer les matières usuelles
            </button>
          </div>
        )}
      </div>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      {isAdmin && (
        <div className="card">
          <div className="card-title">Ajouter une matière au catalogue</div>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <div className="field" style={{ minWidth: 110 }}>
              <label htmlFor="code">Code</label>
              <input
                id="code"
                value={draft.code}
                placeholder="CONJUGAISON"
                maxLength={16}
                onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              />
            </div>
            <div className="field" style={{ minWidth: 260 }}>
              <label htmlFor="name">Intitulé</label>
              <input
                id="name"
                value={draft.name}
                placeholder="Conjugaison"
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </div>
            <div className="field" style={{ minWidth: 130 }}>
              <label htmlFor="coef">Barème par défaut</label>
              <input
                id="coef"
                type="number"
                min={1}
                max={20}
                value={draft.default_max_score}
                onChange={(event) =>
                  setDraft({ ...draft, default_max_score: event.target.value })
                }
              />
            </div>
            <button
              type="button"
              onClick={createSubject}
              disabled={busy || !draft.code || !draft.name}
            >
              Ajouter
            </button>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-title">Configuration d'une classe</div>

        <div className="toolbar">
          <div className="field">
            <label htmlFor="classroom">Classe</label>
            <select
              id="classroom"
              value={classroom ?? ""}
              onChange={(event) => setClassroom(Number(event.target.value))}
            >
              {classes?.results.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          {isAdmin && (
            <>
              <button type="button" onClick={saveAssignment} disabled={busy || !currentYear}>
                {busy ? "Enregistrement…" : "Enregistrer la configuration"}
              </button>
              {/* Trente matières à cocher et à barémer une par une, pour six
                  classes, c'est une demi-journée et autant d'occasions de se
                  tromper d'un chiffre — une erreur qui ne se voit qu'au bulletin. */}
              <button
                type="button"
                className="secondary"
                onClick={applyCatalogue}
                disabled={busy || !currentYear}
                title="Ajoute les matières relevées pour ce niveau, avec leurs barèmes de référence"
              >
                Appliquer le catalogue du niveau
              </button>
            </>
          )}
        </div>

        {rows.length === 0 ? (
          <div className="empty">
            Aucune matière au catalogue. Commencez par en créer, ou utilisez les
            matières usuelles.
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>Active</th>
                    <th>Matière</th>
                    <th className="num" style={{ width: 120 }}>Barème</th>
                    <th style={{ width: 240 }}>Enseignant</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.subject} className={row.enabled ? "" : "row-off"}>
                      <td>
                        <input
                          type="checkbox"
                          className="checkbox"
                          checked={row.enabled}
                          disabled={!isAdmin}
                          aria-label={`Activer ${row.name}`}
                          onChange={(event) =>
                            update(row.subject, { enabled: event.target.checked })
                          }
                        />
                      </td>
                      <td>{row.name}</td>
                      <td className="num">
                        <input
                          className="cell"
                          type="number"
                          min={1}
                          max={20}
                          value={row.max_score}
                          disabled={!isAdmin || !row.enabled}
                          onChange={(event) =>
                            update(row.subject, {
                              max_score: Number(event.target.value) || 1,
                            })
                          }
                        />
                      </td>
                      <td>
                        <select
                          value={row.teacher}
                          disabled={!isAdmin || !row.enabled}
                          onChange={(event) =>
                            update(row.subject, { teacher: event.target.value })
                          }
                        >
                          <option value="">— non attribué —</option>
                          {teachers?.results.map((teacher) => (
                            <option key={teacher.id} value={teacher.id}>
                              {teacher.full_name}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                  <tr className="total">
                    <td />
                    <td>{enabled.length} matière(s) active(s)</td>
                    <td className="num">{totalScale}</td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>

            {withoutTeacher > 0 && (
              <p className="muted" style={{ marginTop: "var(--space-3)" }}>
                {withoutTeacher} matière(s) sans enseignant attribué : personne ne
                pourra y saisir de notes tant qu'aucun enseignant n'est désigné.
              </p>
            )}
          </>
        )}
      </div>
    </>
  );
}
