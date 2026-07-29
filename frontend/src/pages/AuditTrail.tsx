import { useResource } from "../hooks";
import type { Paginated } from "../types";

type Entry = {
  id: number;
  user_label: string;
  action: string;
  entity: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip_address: string | null;
  timestamp: string;
};

const ACTION_LABELS: Record<string, string> = {
  CREATE: "Création",
  UPDATE: "Modification",
  DELETE: "Suppression",
  LOGIN: "Connexion",
  EXPORT: "Export",
};

const ENTITY_LABELS: Record<string, string> = {
  MonthlyPayment: "Encaissement",
  Expense: "Dépense",
  Student: "Élève",
  Teacher: "Enseignant",
  Salary: "Salaire",
  Enrollment: "Inscription",
  Discount: "Réduction",
  SchoolYear: "Année scolaire",
  User: "Utilisateur",
};

/** Résume une modification en listant les seuls champs qui ont changé. */
function summarise(entry: Entry): string {
  if (entry.action !== "UPDATE" || !entry.before || !entry.after) return "";
  const changes = Object.keys(entry.after)
    .filter((key) => JSON.stringify(entry.before![key]) !== JSON.stringify(entry.after![key]))
    .map((key) => `${key} : ${entry.before![key]} → ${entry.after![key]}`);
  return changes.join(" · ");
}

export default function AuditTrail() {
  const { data, error, loading } = useResource<Paginated<Entry>>(
    "/audit-logs/?page_size=100",
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Journal d'audit</h1>
          <p>
            Journal immuable des opérations sensibles. Aucune entrée ne peut être
            modifiée ni supprimée, y compris par un administrateur.
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
                <th>Horodatage</th>
                <th>Auteur</th>
                <th>Action</th>
                <th>Objet</th>
                <th>Détail</th>
                <th>Adresse IP</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((entry) => (
                <tr key={entry.id}>
                  <td>
                    {new Date(entry.timestamp).toLocaleString("fr-FR", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </td>
                  <td>{entry.user_label}</td>
                  <td>
                    <span
                      className={`badge ${
                        entry.action === "DELETE"
                          ? "unpaid"
                          : entry.action === "UPDATE"
                            ? "partial"
                            : ""
                      }`}
                    >
                      {ACTION_LABELS[entry.action] ?? entry.action}
                    </span>
                  </td>
                  <td>
                    {ENTITY_LABELS[entry.entity] ?? entry.entity}
                    {entry.entity_id && (
                      <span className="muted"> #{entry.entity_id}</span>
                    )}
                  </td>
                  <td style={{ whiteSpace: "normal", maxWidth: 420 }}>
                    {summarise(entry) || <span className="muted">—</span>}
                  </td>
                  <td className="muted">{entry.ip_address ?? "—"}</td>
                </tr>
              ))}
              {data.results.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    Aucune entrée dans le journal.
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
