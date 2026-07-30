import { Fragment, useEffect, useState } from "react";

import { api } from "../api";
import { useResource } from "../hooks";
import type { ClassRoom, Paginated } from "../types";

type Composition = { id: number; name: string; status: string };

type Result = {
  student: number;
  matricule: string;
  name: string;
  average: string | null;
  mention: string;
  rank: number | null;
  ranked_out_of: number;
  total_points: string | null;
  total_coefficients: number;
  graded: boolean;
  lines: {
    subject: string;
    coefficient: number;
    value: string | null;
    is_absent: boolean;
    validated: boolean;
  }[];
};

type ClassResults = {
  composition: string;
  classroom: string;
  summary: {
    graded: number;
    class_average: string | null;
    best: string | null;
    lowest: string | null;
    pass_rate: number | null;
    subjects: number;
  };
  subjects: { name: string; coefficient: number }[];
  results: Result[];
};

function ordinal(rank: number) {
  return rank === 1 ? "1er" : `${rank}e`;
}

export default function ReportCards() {
  const { data: compositions } = useResource<Paginated<Composition>>("/compositions/");
  const { data: classes } = useResource<Paginated<ClassRoom>>("/classes/");

  const [composition, setComposition] = useState<number | null>(null);
  const [classroom, setClassroom] = useState<number | null>(null);

  useEffect(() => {
    if (composition === null && compositions?.results.length) {
      setComposition(compositions.results[0].id);
    }
  }, [compositions, composition]);

  useEffect(() => {
    if (classroom !== null || !classes?.results.length) return;
    // Le préscolaire ne compose pas : ouvrir dessus n'afficherait que des tirets.
    const first =
      classes.results.find((item) => item.level === "PRIMARY") ?? classes.results[0];
    setClassroom(first.id);
  }, [classes, classroom]);

  const path =
    composition && classroom
      ? `/report-cards/?composition=${composition}&classroom=${classroom}`
      : null;
  const { data, loading, error } = useResource<ClassResults>(path);

  const [expanded, setExpanded] = useState<number | null>(null);

  function download(studentId?: number) {
    const suffix = studentId ? `&student=${studentId}` : "";
    const name = studentId
      ? `bulletin-${data?.results.find((r) => r.student === studentId)?.matricule}`
      : `bulletins-${data?.classroom}-${data?.composition}`;
    void api.download(
      `/report-cards/pdf/?composition=${composition}&classroom=${classroom}${suffix}`,
      `${name.replace(/[\s/]+/g, "-").toLowerCase()}.pdf`,
    );
  }

  const provisional = data?.results.some((result) =>
    result.lines.some((line) => !line.validated),
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bulletins</h1>
          <p>
            Résultats par classe, avec moyenne pondérée, rang et mention. Les
            bulletins s'éditent individuellement ou en un seul fichier pour toute la
            classe.
          </p>
        </div>
        {data && data.results.length > 0 && (
          <div className="page-actions">
            <button type="button" onClick={() => download()}>
              Tous les bulletins en PDF
            </button>
          </div>
        )}
      </div>

      <div className="toolbar">
        <div className="field" style={{ minWidth: 220 }}>
          <label htmlFor="composition">Composition</label>
          <select
            id="composition"
            value={composition ?? ""}
            onChange={(event) => setComposition(Number(event.target.value))}
          >
            {compositions?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
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
      </div>

      {error && <div className="alert error">{error}</div>}
      {loading && <div className="spinner">Chargement…</div>}

      {provisional && (
        <div className="alert warning">
          Certaines matières ne sont pas encore validées par leur enseignant. Les
          bulletins édités maintenant porteront la mention « document provisoire ».
        </div>
      )}

      {data && data.summary.subjects === 0 && (
        <div className="card empty">
          <p>
            Aucune matière n'est configurée pour la classe <strong>{data.classroom}</strong>.
          </p>
          <p className="muted" style={{ marginTop: "var(--space-2)" }}>
            C'est normal pour le préscolaire, qui ne compose pas. Pour une classe
            élémentaire, rendez-vous dans « Matières et coefficients » pour lui
            affecter des matières.
          </p>
        </div>
      )}

      {data && data.summary.subjects > 0 && (
        <>
          <div className="stats">
            <div className="stat">
              <div className="label">Élèves notés</div>
              <div className="value">{data.summary.graded}</div>
            </div>
            <div className="stat">
              <div className="label">Moyenne de classe</div>
              <div className="value">{data.summary.class_average ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="label">Meilleure moyenne</div>
              <div className="value positive">{data.summary.best ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="label">Taux de réussite</div>
              <div className="value">
                {data.summary.pass_rate !== null ? `${data.summary.pass_rate} %` : "—"}
              </div>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 70 }}>Rang</th>
                  <th style={{ width: 80 }}>Mat.</th>
                  <th>Élève</th>
                  <th className="num">Points</th>
                  <th className="num">Coef.</th>
                  <th className="num">Moyenne</th>
                  <th>Mention</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.results.map((result) => (
                  <Fragment key={result.student}>
                    <tr>
                      <td>{result.rank ? ordinal(result.rank) : <span className="muted">—</span>}</td>
                      <td className="muted">{result.matricule}</td>
                      <td>{result.name}</td>
                      <td className="num">{result.total_points ?? "—"}</td>
                      <td className="num">{result.total_coefficients || "—"}</td>
                      <td className="num">
                        <strong>{result.average ?? "—"}</strong>
                      </td>
                      <td>{result.mention || <span className="muted">—</span>}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="secondary small"
                            onClick={() =>
                              setExpanded(expanded === result.student ? null : result.student)
                            }
                          >
                            {expanded === result.student ? "Masquer" : "Détail"}
                          </button>
                          <button
                            type="button"
                            className="secondary small"
                            onClick={() => download(result.student)}
                          >
                            PDF
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expanded === result.student && (
                      <tr>
                        <td colSpan={8} className="detail-cell">
                          <table className="inner-table">
                            <thead>
                              <tr>
                                <th>Matière</th>
                                <th className="num">Coef.</th>
                                <th className="num">Note</th>
                                <th className="num">Points</th>
                                <th>État</th>
                              </tr>
                            </thead>
                            <tbody>
                              {result.lines.map((line) => (
                                <tr key={line.subject}>
                                  <td>{line.subject}</td>
                                  <td className="num">{line.coefficient}</td>
                                  <td className="num">
                                    {line.is_absent ? (
                                      <span className="muted">Absent</span>
                                    ) : (
                                      line.value ?? <span className="muted">—</span>
                                    )}
                                  </td>
                                  <td className="num">
                                    {line.value && !line.is_absent
                                      ? (Number(line.value) * line.coefficient).toFixed(2)
                                      : "—"}
                                  </td>
                                  <td>
                                    {line.validated ? (
                                      <span className="badge paid">Validée</span>
                                    ) : (
                                      <span className="badge partial">Provisoire</span>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {data.results.length === 0 && (
                  <tr>
                    <td colSpan={8} className="empty">
                      Aucun élève actif dans cette classe.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
