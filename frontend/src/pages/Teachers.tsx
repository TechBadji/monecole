import { useResource } from "../hooks";
import type { Paginated } from "../types";

type Teacher = {
  id: number;
  matricule: string;
  full_name: string;
  sex: string;
  function: string;
  class_type: string;
  contract_type: string;
  service_start_date: string | null;
  is_active: boolean;
};

const CONTRACT_LABELS: Record<string, string> = {
  PERMANENT: "CDI",
  FIXED_TERM: "CDD",
  SUBSTITUTE: "Vacataire",
};

export default function Teachers() {
  const { data, error, loading } = useResource<Paginated<Teacher>>(
    "/teachers/?page_size=100",
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Personnel enseignant</h1>
          <p>
            {data ? `${data.count} personne(s)` : "…"} — état nominatif. Le matricule
            est attribué automatiquement par établissement.
          </p>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {loading && <div className="spinner">Chargement…</div>}

      {!loading && data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Matricule</th>
                <th>Nom complet</th>
                <th>Fonction</th>
                <th>Classes</th>
                <th>Contrat</th>
                <th>Prise de service</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((teacher) => (
                <tr key={teacher.id}>
                  <td>{teacher.matricule}</td>
                  <td>{teacher.full_name}</td>
                  <td>{teacher.function || <span className="muted">—</span>}</td>
                  <td>{teacher.class_type || <span className="muted">—</span>}</td>
                  <td>{CONTRACT_LABELS[teacher.contract_type] ?? teacher.contract_type}</td>
                  <td>
                    {teacher.service_start_date ? (
                      new Date(teacher.service_start_date).toLocaleDateString("fr-FR")
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {data.results.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    Aucun personnel enregistré.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
