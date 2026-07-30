import { useState } from "react";

import { api } from "../api";
import { useResource } from "../hooks";
import type { ClassRoom, Paginated } from "../types";

type DailyRow = {
  student: number;
  matricule: string;
  name: string;
  classroom: string;
  present: boolean;
  arrival: string | null;
  departure: string | null;
  late: boolean;
  passages: number;
};

type Daily = {
  day: string;
  total: number;
  present: number;
  no_badge: number;
  late: number;
  note: string;
  results: DailyRow[];
};

type History = {
  student: { matricule: string; name: string; classroom: string };
  days: number;
  present_days: number;
  results: { day: string; arrival: string | null; departure: string | null; passages: number }[];
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function Attendance() {
  const { data: classes } = useResource<Paginated<ClassRoom>>("/classes/");
  const [day, setDay] = useState(today());
  const [classroom, setClassroom] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const query = new URLSearchParams({ day });
  if (classroom) query.set("classroom", classroom);
  const { data, loading, error } = useResource<Daily>(
    `/attendance/daily/?${query.toString()}`,
  );

  const { data: history } = useResource<History>(
    selected ? `/attendance/student/${selected}/?days=30` : null,
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Assiduité</h1>
          <p>
            Feuille de présence reconstituée à partir des passages au portail.
            Imprimez les cartes à QR code pour équiper une classe.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="secondary"
            onClick={() =>
              api.download(
                `/qr-sheet/${classroom ? `?classroom=${classroom}` : ""}`,
                `cartes-${classroom ? "classe" : "ecole"}.pdf`,
              )
            }
          >
            Cartes à imprimer
          </button>
        </div>
      </div>

      <div className="toolbar">
        <div className="field">
          <label htmlFor="day">Journée</label>
          <input
            id="day"
            type="date"
            value={day}
            max={today()}
            onChange={(event) => setDay(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="classroom">Classe</label>
          <select
            id="classroom"
            value={classroom}
            onChange={(event) => setClassroom(event.target.value)}
          >
            <option value="">Toutes</option>
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

      {data && (
        <>
          <div className="stats">
            <div className="stat">
              <div className="label">Effectif</div>
              <div className="value">{data.total}</div>
            </div>
            <div className="stat">
              <div className="label">Présents</div>
              <div className="value positive">{data.present}</div>
            </div>
            <div className="stat">
              <div className="label">Retards</div>
              <div className={`value ${data.late ? "negative" : ""}`}>{data.late}</div>
            </div>
            <div className="stat">
              <div className="label">Sans badge</div>
              <div className="value">{data.no_badge}</div>
            </div>
          </div>

          {/* La nuance compte : un lecteur en panne produit le même état qu'une
              absence, et confondre les deux ferait convoquer des familles à tort. */}
          <div className="alert warning">{data.note}</div>

          <div className="table-wrap">
            <table className="table-dense">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Mat.</th>
                  <th>Élève</th>
                  <th>Classe</th>
                  <th>Arrivée</th>
                  <th>Sortie</th>
                  <th>État</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.results.map((row) => (
                  <tr key={row.student}>
                    <td className="muted">{row.matricule}</td>
                    <td>{row.name}</td>
                    <td>{row.classroom}</td>
                    <td>{row.arrival ?? <span className="muted">—</span>}</td>
                    <td>{row.departure ?? <span className="muted">—</span>}</td>
                    <td>
                      {!row.present ? (
                        <span className="badge unpaid">Sans badge</span>
                      ) : row.late ? (
                        <span className="badge partial">En retard</span>
                      ) : (
                        <span className="badge paid">Présent</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() =>
                          setSelected(selected === row.student ? null : row.student)
                        }
                      >
                        {selected === row.student ? "Masquer" : "Historique"}
                      </button>
                    </td>
                  </tr>
                ))}
                {data.results.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty">
                      Aucun élève actif pour cette sélection.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {selected && history && (
        <div className="card">
          <div className="card-title">
            {history.student.name} — {history.present_days} jour(s) de présence sur{" "}
            {history.days}
          </div>
          <div className="table-wrap">
            <table className="table-dense">
              <thead>
                <tr>
                  <th>Jour</th>
                  <th>Arrivée</th>
                  <th>Sortie</th>
                  <th className="num">Passages</th>
                </tr>
              </thead>
              <tbody>
                {history.results.map((row) => (
                  <tr key={row.day}>
                    <td>
                      {new Date(row.day).toLocaleDateString("fr-FR", {
                        weekday: "short",
                        day: "2-digit",
                        month: "short",
                      })}
                    </td>
                    <td>{row.arrival ?? <span className="muted">—</span>}</td>
                    <td>{row.departure ?? <span className="muted">—</span>}</td>
                    <td className="num">{row.passages}</td>
                  </tr>
                ))}
                {history.results.length === 0 && (
                  <tr>
                    <td colSpan={4} className="empty">
                      Aucun passage enregistré sur la période.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
