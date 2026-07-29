import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { money } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import type { Dashboard as DashboardData } from "../types";

// Palette catégorielle : teintes distinctes à luminosité proche, lisibles côte à côte.
const PALETTE = ["#1f3864", "#2f6b9a", "#3fa0a0", "#6aa84f", "#c9a227", "#c2703d",
                 "#a8474a", "#8c5a9e", "#5a6b8c", "#7a8a99"];

const AXIS = { fontSize: 11, fill: "#6b7280" };

function compact(value: number) {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} M`;
  if (Math.abs(value) >= 1_000) return `${Math.round(value / 1_000)} k`;
  return String(value);
}

export default function Dashboard() {
  const { profile } = useAuth();
  const { data, error, loading } = useResource<DashboardData>("/reports/dashboard/");
  const currency = profile?.school?.currency ?? "XOF";

  if (loading) return <div className="spinner">Chargement…</div>;
  if (error) return <div className="alert error">{error}</div>;
  if (!data) return null;

  const monthly = data.monthly.periods.map((label, index) => ({
    mois: label.split(" ")[0].slice(0, 4),
    Ressources: data.monthly.resources[index],
    Charges: data.monthly.charges[index],
    Solde: data.monthly.cumulative_balance[index],
  }));

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

      <div className="card">
        <div className="card-title">Ressources et charges par mois</div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={monthly} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eef0f3" vertical={false} />
            <XAxis dataKey="mois" tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={compact} width={52} />
            <Tooltip
              formatter={(value) => `${money(Number(value))} ${currency}`}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e5ea" }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="Ressources" stroke={PALETTE[3]} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="Charges" stroke={PALETTE[6]} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="Solde" stroke={PALETTE[0]} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-title">Principales dépenses</div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={data.top_expenses.map((row) => ({
                ...row,
                short: row.label.length > 22 ? `${row.label.slice(0, 21)}…` : row.label,
              }))}
              layout="vertical"
              margin={{ top: 0, right: 12, left: 0, bottom: 0 }}
            >
              <CartesianGrid stroke="#eef0f3" horizontal={false} />
              <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={compact} />
              <YAxis
                type="category"
                dataKey="short"
                tick={{ ...AXIS, fontSize: 10.5 }}
                tickLine={false}
                axisLine={false}
                width={140}
              />
              <Tooltip
                formatter={(value) => `${money(Number(value))} ${currency}`}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e5ea" }}
              />
              <Bar dataKey="total" radius={[0, 3, 3, 0]}>
                {data.top_expenses.map((_, index) => (
                  <Cell key={index} fill={PALETTE[index % PALETTE.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
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
