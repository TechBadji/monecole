import { useState } from "react";

import { api, money } from "../api";
import { useResource } from "../hooks";
import type { ClassRoom, Paginated, Student } from "../types";

type Ledger = {
  student: { id: number; name: string; classroom: string };
  year: string;
  registration: { due: number; paid: number; balance: number; status: string };
  months: {
    period: string;
    due: number;
    paid: number;
    balance: number;
    status: string;
  }[];
  total_due: number;
  total_paid: number;
  balance: number;
};

const STATUS_LABELS: Record<string, string> = {
  PAID: "Réglé",
  PARTIAL: "Partiel",
  UNPAID: "Impayé",
};

function StatusBadge({ status }: { status: string }) {
  const tone = status === "PAID" ? "paid" : status === "PARTIAL" ? "partial" : "unpaid";
  return <span className={`badge ${tone}`}>{STATUS_LABELS[status] ?? status}</span>;
}

export default function Students() {
  const [search, setSearch] = useState("");
  const [classroom, setClassroom] = useState<string>("");
  const [selected, setSelected] = useState<number | null>(null);

  const { data: classes } = useResource<Paginated<ClassRoom>>("/classes/");

  const query = new URLSearchParams({ page_size: "100" });
  if (search) query.set("search", search);
  if (classroom) query.set("classroom", classroom);
  const { data, error, loading } = useResource<Paginated<Student>>(
    `/students/?${query.toString()}`,
  );

  const { data: ledger } = useResource<Ledger>(
    selected ? `/students/${selected}/ledger/` : null,
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Élèves</h1>
          <p>{data ? `${data.count} élève(s)` : "…"}</p>
        </div>
        <div className="page-actions">
        <button
          type="button"
          className="secondary"
          onClick={() => api.download("/exports/students.xlsx", "liste-eleves.xlsx")}
        >
          Export Excel
        </button>
        </div>
      </div>

      <div className="toolbar">
        <div className="field">
          <label htmlFor="search">Recherche</label>
          <input
            id="search"
            value={search}
            placeholder="Nom, prénom, parent, téléphone…"
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="filter-class">Classe</label>
          <select
            id="filter-class"
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

      {!loading && data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Nom</th>
                <th>Classe</th>
                <th>Parent / tuteur</th>
                <th>Téléphone</th>
                <th>Statut</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.results.map((student) => (
                <tr key={student.id}>
                  <td>{student.full_name}</td>
                  <td>{student.classroom_name}</td>
                  <td>{student.parent_name || <span className="muted">—</span>}</td>
                  <td>{student.parent_phone || <span className="muted">—</span>}</td>
                  <td>{student.status === "ACTIVE" ? "Actif" : student.status}</td>
                  <td>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        setSelected(selected === student.id ? null : student.id)
                      }
                    >
                      {selected === student.id ? "Fermer" : "Situation"}
                    </button>
                  </td>
                </tr>
              ))}
              {data.results.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    Aucun élève ne correspond à ces critères.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && ledger && (
        <div className="card">
          <div className="card-title">
            {ledger.student.name} — {ledger.student.classroom} · {ledger.year}
          </div>

          <div className="stats">
            <div className="stat">
              <div className="label">Total dû</div>
              <div className="value">{money(ledger.total_due)}</div>
            </div>
            <div className="stat">
              <div className="label">Total réglé</div>
              <div className="value">{money(ledger.total_paid)}</div>
            </div>
            <div className="stat">
              <div className="label">Reste à payer</div>
              <div className={`value ${ledger.balance > 0 ? "negative" : "positive"}`}>
                {money(ledger.balance)}
              </div>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Échéance</th>
                  <th className="num">Dû</th>
                  <th className="num">Réglé</th>
                  <th className="num">Solde</th>
                  <th>État</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Inscription</td>
                  <td className="num">{money(ledger.registration.due)}</td>
                  <td className="num">{money(ledger.registration.paid)}</td>
                  <td className="num">{money(ledger.registration.balance)}</td>
                  <td>
                    <StatusBadge status={ledger.registration.status} />
                  </td>
                </tr>
                {ledger.months.map((month) => (
                  <tr key={month.period}>
                    <td>
                      {new Date(month.period).toLocaleDateString("fr-FR", {
                        month: "long",
                        year: "numeric",
                      })}
                    </td>
                    <td className="num">{money(month.due)}</td>
                    <td className="num">{money(month.paid)}</td>
                    <td className="num">{money(month.balance)}</td>
                    <td>
                      <StatusBadge status={month.status} />
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
