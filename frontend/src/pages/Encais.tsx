import { api, money } from "../api";
import { useAuth } from "../auth";
import { abbreviateMonth } from "../components/charts";
import { useResource } from "../hooks";
import type { Period, Series } from "../types";

type Encais = {
  year: string;
  periods: Period[];
  classes: {
    classroom_id: number;
    classroom: string;
    headcount: number;
    paid_registrations: number;
    registration: Series;
    tuition: Series;
    revenue: number;
  }[];
  registration_total: Series;
  tuition_total: Series;
  headcount_total: number;
  revenue_total: number;
};

export default function Encais() {
  const { profile } = useAuth();
  const currency = profile?.school?.currency ?? "XOF";
  const { data, error, loading } = useResource<Encais>("/reports/encais/");

  if (loading) return <div className="spinner">Chargement…</div>;
  if (error) return <div className="alert error">{error}</div>;
  if (!data) return null;

  const months = data.periods.map((period) => abbreviateMonth(period.label));
  const columns = months.length + 4;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Synthèse des encaissements</h1>
          <p>
            Année {data.year} — montants en {currency}. L'effectif compte les élèves
            actifs ; les inscriptions réglées sont indiquées séparément.
          </p>
        </div>
        <div className="page-actions">
        <button
          type="button"
          className="secondary"
          onClick={() =>
            api.download(
              "/exports/encais.xlsx",
              `encaissements-${data.year.replace("/", "-")}.xlsx`,
            )
          }
        >
          Export Excel
        </button>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="sticky-col">Intitulé</th>
              <th className="num">Effectif</th>
              <th className="num">Inscr. réglées</th>
              {months.map((month, index) => (
                <th key={index} className="num">
                  {month}
                </th>
              ))}
              <th className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="section">
              <td className="sticky-col" colSpan={columns}>
                Inscriptions reçues
              </td>
            </tr>
            {data.classes.map((row) => (
              <tr key={`reg-${row.classroom_id}`}>
                <td className="sticky-col">{row.classroom}</td>
                <td className="num">{row.headcount}</td>
                <td className="num">{row.paid_registrations}</td>
                {row.registration.values.map((value, index) => (
                  <td key={index} className="num">
                    {value ? money(value) : <span className="muted">—</span>}
                  </td>
                ))}
                <td className="num">{money(row.registration.total)}</td>
              </tr>
            ))}
            <tr className="total">
              <td className="sticky-col">Total inscription reçue</td>
              <td className="num">{data.headcount_total}</td>
              <td className="num" />
              {data.registration_total.values.map((value, index) => (
                <td key={index} className="num">
                  {money(value)}
                </td>
              ))}
              <td className="num">{money(data.registration_total.total)}</td>
            </tr>

            <tr className="section">
              <td className="sticky-col" colSpan={columns}>
                Mensualités reçues
              </td>
            </tr>
            {data.classes.map((row) => (
              <tr key={`tui-${row.classroom_id}`}>
                <td className="sticky-col">{row.classroom}</td>
                <td className="num">{row.headcount}</td>
                <td className="num" />
                {row.tuition.values.map((value, index) => (
                  <td key={index} className="num">
                    {value ? money(value) : <span className="muted">—</span>}
                  </td>
                ))}
                <td className="num">{money(row.tuition.total)}</td>
              </tr>
            ))}
            <tr className="total">
              <td className="sticky-col">Total mensualité reçue</td>
              <td className="num" colSpan={2} />
              {data.tuition_total.values.map((value, index) => (
                <td key={index} className="num">
                  {money(value)}
                </td>
              ))}
              <td className="num">{money(data.tuition_total.total)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-title">Chiffre d'affaires par classe</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Classe</th>
                <th className="num">Effectif</th>
                <th className="num">Inscriptions</th>
                <th className="num">Mensualités</th>
                <th className="num">Chiffre d'affaires</th>
              </tr>
            </thead>
            <tbody>
              {data.classes.map((row) => (
                <tr key={row.classroom_id}>
                  <td>{row.classroom}</td>
                  <td className="num">{row.headcount}</td>
                  <td className="num">{money(row.registration.total)}</td>
                  <td className="num">{money(row.tuition.total)}</td>
                  <td className="num">
                    <strong>{money(row.revenue)}</strong>
                  </td>
                </tr>
              ))}
              <tr className="total">
                <td>Total</td>
                <td className="num">{data.headcount_total}</td>
                <td className="num">{money(data.registration_total.total)}</td>
                <td className="num">{money(data.tuition_total.total)}</td>
                <td className="num">{money(data.revenue_total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
