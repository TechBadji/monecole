import { Fragment, useState } from "react";

import { api, money } from "../api";
import { useResource } from "../hooks";
import type { ClassRoom, Paginated, Student } from "../types";

type Ledger = {
  student: { id: number; matricule: string; name: string; classroom: string };
  year: string;
  year_id: number;
  scholarship: {
    rate: number;
    is_full: boolean;
    forgone: number;
    full_monthly_tuition: number;
  };
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

type History = {
  student: { matricule: string; name: string };
  years: {
    year: string;
    year_id: number;
    available: boolean;
    enrolled: boolean;
    classroom?: string;
    total_due?: number;
    total_paid?: number;
    balance?: number;
    scholarship_rate?: number;
    is_full_scholarship?: boolean;
  }[];
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
  // Année consultée : `null` = année courante. Permet de remonter le cursus.
  const [year, setYear] = useState<number | null>(null);

  const { data: classes } = useResource<Paginated<ClassRoom>>("/classes/");

  const query = new URLSearchParams({ page_size: "100" });
  if (search) query.set("search", search);
  if (classroom) query.set("classroom", classroom);
  const { data, error, loading } = useResource<Paginated<Student>>(
    `/students/?${query.toString()}`,
  );

  const {
    data: ledger,
    loading: ledgerLoading,
    error: ledgerError,
  } = useResource<Ledger>(
    selected ? `/students/${selected}/ledger/${year ? `?year=${year}` : ""}` : null,
  );
  const { data: history } = useResource<History>(
    selected ? `/students/${selected}/history/` : null,
  );

  function toggle(studentId: number) {
    setSelected(selected === studentId ? null : studentId);
    setYear(null);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Élèves</h1>
          <p>
            {data ? `${data.count} élève(s)` : "…"} — « Situation » déplie le détail
            financier de l'élève, année par année.
          </p>
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
            placeholder="Matricule, nom, prénom, parent, téléphone…"
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
                <th style={{ width: 80 }}>Mat.</th>
                <th>Nom</th>
                <th>Classe</th>
                <th>Parent / tuteur</th>
                <th>Téléphone</th>
                <th>Statut</th>
                <th style={{ width: 110 }} />
              </tr>
            </thead>
            <tbody>
              {data.results.map((student) => (
                <Fragment key={student.id}>
                  <tr className={selected === student.id ? "row-open" : ""}>
                    <td className="muted">{student.matricule}</td>
                    <td>{student.full_name}</td>
                    <td>{student.classroom_name}</td>
                    <td>{student.parent_name || <span className="muted">—</span>}</td>
                    <td>{student.parent_phone || <span className="muted">—</span>}</td>
                    <td>{student.status === "ACTIVE" ? "Actif" : student.status}</td>
                    <td>
                      <button
                        type="button"
                        className="secondary small"
                        aria-expanded={selected === student.id}
                        onClick={() => toggle(student.id)}
                      >
                        {selected === student.id ? "Fermer" : "Situation"}
                      </button>
                    </td>
                  </tr>

                  {/*
                    Le panneau se déplie sous la ligne cliquée.

                    Rendu après le tableau, il atterrissait à plusieurs milliers de
                    pixels sous le viewport sur une liste de 180 élèves : le bouton
                    paraissait sans effet, alors que le panneau s'ouvrait bien.
                  */}
                  {selected === student.id && (
                    <tr className="detail-row">
                      <td colSpan={7} className="detail-cell">
                        {ledgerLoading && (
                          <div className="spinner">Chargement de la situation…</div>
                        )}
                        {/* Une erreur était auparavant avalée : le panneau restait
                            vide sans rien dire. */}
                        {ledgerError && !ledgerLoading && (
                          <div className="situation">
                            <div className="alert error">{ledgerError}</div>
                          </div>
                        )}
                        {ledger && !ledgerLoading && (
                          <SituationPanel
                            ledger={ledger}
                            history={history}
                            year={year}
                            onYear={setYear}
                          />
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {data.results.length === 0 && (
                <tr>
                  <td colSpan={7} className="empty">
                    Aucun élève ne correspond à ces critères.
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

function SituationPanel({
  ledger,
  history,
  year,
  onYear,
}: {
  ledger: Ledger;
  history: History | null;
  year: number | null;
  onYear: (id: number) => void;
}) {
  const overpaid = ledger.total_paid - ledger.total_due;
  const activeYear = year ?? ledger.year_id;

  return (
    <div className="situation">
      {/* Le cursus complet : une école consulte régulièrement ce qu'un élève
          devait les années passées, notamment avant de réinscrire. */}
      {history && history.years.length > 1 && (
        <div className="year-tabs">
          {history.years.map((entry) => (
            <button
              key={entry.year_id}
              type="button"
              className={`year-tab ${activeYear === entry.year_id ? "active" : ""}`}
              onClick={() => onYear(entry.year_id)}
            >
              <span className="year-label">{entry.year}</span>
              <span className="year-meta">
                {!entry.enrolled
                  ? "non inscrit"
                  : !entry.available
                    ? "tarif absent"
                    : entry.balance
                      ? `${money(entry.balance)} dû`
                      : "soldé"}
              </span>
            </button>
          ))}
        </div>
      )}

      {ledger.scholarship.rate > 0 && (
        <div className="alert success">
          <strong>
            {ledger.scholarship.is_full
              ? "Bourse totale"
              : `Bourse de ${ledger.scholarship.rate} %`}
          </strong>{" "}
          — mensualité ramenée de {money(ledger.scholarship.full_monthly_tuition)} à{" "}
          {money(ledger.months[0]?.due ?? 0)} FCFA. Manque à gagner sur l'année :{" "}
          {money(ledger.scholarship.forgone)} FCFA.
        </div>
      )}

      <div className="stats">
        <div className="stat">
          <div className="label">Total dû — {ledger.year}</div>
          <div className="value">{money(ledger.total_due)}</div>
        </div>
        <div className="stat">
          <div className="label">Total réglé</div>
          <div className="value">{money(ledger.total_paid)}</div>
        </div>
        {/* Un trop-perçu n'est pas un solde nul : l'école doit un remboursement
            ou un report, et « Reste à payer : 0 » le lui ferait manquer. */}
        {overpaid > 0 ? (
          <div className="stat">
            <div className="label">Trop-perçu</div>
            <div className="value positive">{money(overpaid)}</div>
          </div>
        ) : (
          <div className="stat">
            <div className="label">Reste à payer</div>
            <div className={`value ${ledger.balance > 0 ? "negative" : "positive"}`}>
              {money(ledger.balance)}
            </div>
          </div>
        )}
      </div>

      {overpaid > 0 && (
        <div className="alert warning">
          <strong>Trop-perçu de {money(overpaid)} FCFA.</strong> La famille a réglé
          davantage que le montant dû — le plus souvent parce qu'une réduction a été
          accordée après des versements au tarif plein. À rembourser ou à reporter
          sur l'année suivante.
        </div>
      )}

      <div className="table-wrap">
        <table className="table-dense">
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
                <td className="num">
                  {month.paid > month.due ? (
                    <span className="positive-text">
                      +{money(month.paid - month.due)}
                    </span>
                  ) : (
                    money(month.balance)
                  )}
                </td>
                <td>
                  <StatusBadge status={month.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
