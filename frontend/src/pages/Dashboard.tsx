import { money } from "../api";
import { useAuth } from "../auth";
import { BarChart, LineChart, abbreviateMonth } from "../components/charts";
import { StaleBanner } from "../components/OfflineBanners";
import { useOfflineResource } from "../offline/useOfflineResource";
import type { Dashboard as DashboardData } from "../types";

export default function Dashboard() {
  const { profile } = useAuth();
  const { data, error, loading, stale, cachedAt } =
    useOfflineResource<DashboardData>("/reports/dashboard/");
  const currency = profile?.school?.currency ?? "XOF";

  if (loading) return <div className="spinner">Chargement…</div>;
  if (error) return <div className="alert error">{error}</div>;
  if (!data) return null;

  // Libellés courts : « oct. », « nov. »… Douze mois entiers ne tiennent pas.
  const months = data.monthly.periods.map(abbreviateMonth);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Tableau de bord</h1>
          <p>
            {profile?.school?.name} — année scolaire {data.year}
          </p>
        </div>
      </div>

      {/* Sur un état financier, la fraîcheur s'affiche à l'heure près : « il y a
          3 h » est trop vague pour décider si un chiffre est exploitable. */}
      <StaleBanner
        freshness={{ stale, cachedAt }}
        precise
        label="Les montants de ce tableau de bord"
      />

      {data.budget_overruns.length > 0 && (
        <div className="alert warning">
          <strong>Dépassement de budget</strong> —{" "}
          {data.budget_overruns
            .map((row) => `${row.category} (+${money(row.overrun)} ${currency})`)
            .join(", ")}
        </div>
      )}

      <div className="stats">
        <Stat label="Effectif" value={String(data.headcount)} unit="élèves" />
        <Stat label="Ressources" value={money(data.revenue)} unit={currency} />
        <Stat label="Charges" value={money(data.charges)} unit={currency} />
        <Stat
          label="Excédent brut"
          value={money(data.ebe)}
          unit={currency}
          tone={data.ebe >= 0 ? "positive" : "negative"}
        />
        <Stat
          label="Solde du compte"
          value={money(data.current_balance)}
          unit={currency}
          tone={data.current_balance >= 0 ? "positive" : "negative"}
        />
      </div>

      {/*
        Deux graphiques et non un seul : les flux mensuels tournent autour de 2 M
        tandis que le solde cumulé grimpe vers 6 M. Les superposer écraserait les
        flux au bas du cadre — et deux échelles sur un même graphique ne sont
        jamais la solution.
      */}
      <div className="card">
        <LineChart
          title={`Ressources et charges par mois (${currency})`}
          labels={months}
          unit={currency}
          series={[
            { name: "Ressources", values: data.monthly.resources },
            { name: "Charges", values: data.monthly.charges },
          ]}
        />
      </div>

      <div className="card">
        <LineChart
          title={`Solde cumulé (${currency})`}
          labels={months}
          unit={currency}
          area
          height={200}
          series={[{ name: "Solde cumulé", values: data.monthly.cumulative_balance }]}
        />
      </div>

      <div className="card">
        {/* Une seule mesure, classée par magnitude : une seule teinte. Colorer
            chaque barre différemment ferait porter à la couleur un rang, alors
            qu'elle doit désigner une entité. */}
        <BarChart
          title={`Principales dépenses par rubrique (${currency})`}
          unit={currency}
          data={data.top_expenses.map((row) => ({ label: row.label, value: row.total }))}
        />
      </div>

      <div className="card">
        <div className="card-title">Effectif et chiffre d'affaires par classe</div>
        <div className="table-wrap" style={{ border: "none" }}>
          <table>
            <thead>
              <tr>
                <th>Classe</th>
                <th className="num">Effectif</th>
                <th className="num">Chiffre d'affaires</th>
              </tr>
            </thead>
            <tbody>
              {data.revenue_by_class.map((row) => (
                <tr key={row.classroom}>
                  <td>{row.classroom}</td>
                  <td className="num">{row.headcount}</td>
                  <td className="num">{money(row.revenue)}</td>
                </tr>
              ))}
              <tr className="total">
                <td>Total</td>
                <td className="num">{data.headcount}</td>
                <td className="num">{money(data.revenue)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function Stat({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "positive" | "negative";
}) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
    </div>
  );
}
