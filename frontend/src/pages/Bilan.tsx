import { api, money } from "../api";
import { useAuth } from "../auth";
import { abbreviateMonth } from "../components/charts";
import { useResource } from "../hooks";
import { useYearParam } from "../year";
import type { Bilan as BilanData, Series } from "../types";

export default function Bilan() {
  const yearParam = useYearParam();
  const { profile } = useAuth();
  const currency = profile?.school?.currency ?? "XOF";
  const { data, error, loading } = useResource<BilanData>(`/reports/bilan/${yearParam}`);

  if (loading) return <div className="spinner">Chargement…</div>;
  if (error) return <div className="alert error">{error}</div>;
  if (!data) return null;

  const months = data.periods.map((period) => abbreviateMonth(period.label));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Rapport bilan</h1>
          <p>
            {profile?.school?.name} — année scolaire {data.year}. Montants en {currency}.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="secondary"
            onClick={() =>
              api.download(
                "/exports/bilan.xlsx",
                `rapport-bilan-${data.year.replace("/", "-")}.xlsx`,
              )
            }
          >
            Export Excel
          </button>
          <button
            type="button"
            onClick={() =>
              api.download(
                "/exports/bilan.pdf",
                `rapport-bilan-${data.year.replace("/", "-")}.pdf`,
              )
            }
          >
            Export PDF
          </button>
        </div>
      </div>

      <div className="stats">
        <div className="stat">
          <div className="label">Total ressources</div>
          <div className="value">{money(data.total_resources.total)}</div>
        </div>
        <div className="stat">
          <div className="label">Total charges</div>
          <div className="value">{money(data.total_charges.total)}</div>
        </div>
        <div className="stat">
          <div className="label">Excédent brut</div>
          <div className={`value ${data.ebe.total >= 0 ? "positive" : "negative"}`}>
            {money(data.ebe.total)}
          </div>
        </div>
        <div className="stat">
          <div className="label">Solde du compte</div>
          <div className={`value ${data.current_balance >= 0 ? "positive" : "negative"}`}>
            {money(data.current_balance)}
          </div>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="sticky-col">Rubrique</th>
              {months.map((month, index) => (
                <th key={index} className="num">
                  {month}
                </th>
              ))}
              <th className="num">Total</th>
              <th className="num">Poids</th>
            </tr>
          </thead>
          <tbody>
            <SectionRow label="Ressources" span={months.length + 3} />
            {data.resources.map((row) => (
              <Row key={row.key} row={row} />
            ))}
            <Row row={data.total_resources} emphasis />

            <SectionRow label="Charges" span={months.length + 3} />
            {data.charges.map((row) => (
              <Row key={row.key} row={row} />
            ))}
            <Row row={data.total_charges} emphasis />

            <SectionRow label="Résultat" span={months.length + 3} />
            <Row row={data.ebe} emphasis />
            <tr className="total">
              <td className="sticky-col">{data.cumulative_balance.label}</td>
              {data.cumulative_balance.values.map((value, index) => (
                <td key={index} className="num">
                  {money(value)}
                </td>
              ))}
              <td className="num">{money(data.current_balance)}</td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-title">Effectif et chiffre d'affaires par classe</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="sticky-col">Classe</th>
                {data.headcount_by_class.map((row) => (
                  <th key={row.classroom} className="num">
                    {row.classroom}
                  </th>
                ))}
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="sticky-col">Effectif</td>
                {data.headcount_by_class.map((row) => (
                  <td key={row.classroom} className="num">
                    {row.headcount}
                  </td>
                ))}
                <td className="num">{data.headcount_total}</td>
              </tr>
              <tr>
                <td className="sticky-col">Chiffre d'affaires</td>
                {data.headcount_by_class.map((row) => (
                  <td key={row.classroom} className="num">
                    {money(row.revenue)}
                  </td>
                ))}
                <td className="num">{money(data.revenue_total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function SectionRow({ label, span }: { label: string; span: number }) {
  return (
    <tr className="section">
      <td className="sticky-col" colSpan={span}>
        {label}
      </td>
    </tr>
  );
}

function Row({ row, emphasis }: { row: Series; emphasis?: boolean }) {
  return (
    <tr className={emphasis ? "total" : undefined}>
      <td className="sticky-col">{row.label}</td>
      {row.values.map((value, index) => (
        <td key={index} className="num">
          {value ? money(value) : <span className="muted">—</span>}
        </td>
      ))}
      <td className="num">{money(row.total)}</td>
      <td className="num">
        {row.weight != null ? `${(row.weight * 100).toFixed(1)} %` : ""}
      </td>
    </tr>
  );
}
