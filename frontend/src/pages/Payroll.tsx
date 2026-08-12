import { useState } from "react";

import { api, money } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import { useYear } from "../year";
import type { Paginated, SchoolYear } from "../types";

type Payslip = {
  id: number;
  teacher_name: string;
  matricule: string;
  period: string;
  gross: number;
  non_taxable: number;
  employee_contributions: number;
  employer_contributions: number;
  income_tax: number;
  trimf: number;
  net_pay: number;
  employer_cost: number;
  scale_validated: boolean;
};

type Scale = {
  id: number;
  label: string;
  effective_from: string;
  is_validated: boolean;
  validated_by: string;
};

function monthOptions(year: SchoolYear | null | undefined) {
  if (!year) return [];
  const start = new Date(year.start_date);
  return Array.from({ length: 12 }, (_, index) => {
    const date = new Date(start.getFullYear(), start.getMonth() + index + 1, 0);
    const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
      date.getDate(),
    ).padStart(2, "0")}`;
    return {
      value: iso,
      label: date.toLocaleDateString("fr-FR", { month: "long", year: "numeric" }),
    };
  });
}

export default function Payroll() {
  const { profile } = useAuth();
  const currency = profile?.school?.currency ?? "XOF";

  const { data: scales } = useResource<Paginated<Scale>>("/payroll-scales/");
  // L'année vient du sélecteur global : la résoudre ici ferait saisir dans
  // l'année courante quelqu'un qui consulte une année close.
  const { selected: currentYear } = useYear();
  const periods = monthOptions(currentYear);

  const [period, setPeriod] = useState("");
  const effectivePeriod = period || periods[0]?.value || "";

  const { data, loading, reload } = useResource<Paginated<Payslip>>(
    effectivePeriod ? `/payslips/?period=${effectivePeriod}&page_size=100` : null,
  );

  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: string; text: string } | null>(null);

  const scale = scales?.results[0];
  const rows = data?.results ?? [];

  const totals = rows.reduce(
    (accumulator, row) => ({
      gross: accumulator.gross + row.gross,
      employee: accumulator.employee + row.employee_contributions,
      employer: accumulator.employer + row.employer_contributions,
      tax: accumulator.tax + row.income_tax + row.trimf,
      net: accumulator.net + row.net_pay,
      cost: accumulator.cost + row.employer_cost,
    }),
    { gross: 0, employee: 0, employer: 0, tax: 0, net: 0, cost: 0 },
  );

  async function generate() {
    setBusy(true);
    setStatus(null);
    try {
      const result = await api.post<{
        created: number;
        skipped: number;
        total_net: number;
        warning: string | null;
      }>("/payslips/generate/", { period: effectivePeriod });
      setStatus({
        kind: result.warning ? "warning" : "success",
        text:
          `${result.created} bulletin(s) généré(s)` +
          (result.skipped ? `, ${result.skipped} déjà existant(s)` : "") +
          `. Net total : ${money(result.total_net)} ${currency}.` +
          (result.warning ? ` ${result.warning}` : ""),
      });
      reload();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Génération impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bulletins de paie</h1>
          <p>
            Calcul selon le schéma sénégalais : IPRES, CSS, TRIMF et impôt sur le
            revenu au barème progressif avec parts fiscales.
          </p>
        </div>
        <div className="page-actions">
        {rows.length > 0 && (
          <button
            type="button"
            className="secondary"
            onClick={() =>
              api.download(
                `/payslips/pdf-batch/?period=${effectivePeriod}`,
                `bulletins-${effectivePeriod}.pdf`,
              )
            }
          >
            Tous les bulletins en PDF
          </button>
        )}
        </div>
      </div>

      {scale && !scale.is_validated && (
        <div className="alert warning">
          <strong>Barème non validé.</strong> « {scale.label} » utilise les taux par
          défaut du schéma sénégalais. Faites-les vérifier par votre expert-comptable
          avant de remettre des bulletins à vos employés — les taux IPRES, CSS, TRIMF
          et IR relèvent de la loi de finances et changent d'une année sur l'autre.
        </div>
      )}

      <div className="toolbar">
        <div className="field">
          <label htmlFor="period">Mois</label>
          <select
            id="period"
            value={effectivePeriod}
            onChange={(event) => setPeriod(event.target.value)}
          >
            {periods.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <button type="button" onClick={generate} disabled={busy || !effectivePeriod}>
          {busy ? "Génération…" : "Générer les bulletins du mois"}
        </button>
      </div>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}
      {loading && <div className="spinner">Chargement…</div>}

      {!loading && rows.length === 0 && (
        <div className="card empty">
          Aucun bulletin pour ce mois. Utilisez « Générer les bulletins du mois ».
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div className="stats">
            <div className="stat">
              <div className="label">Masse salariale brute</div>
              <div className="value">{money(totals.gross)}</div>
            </div>
            <div className="stat">
              <div className="label">Net à payer</div>
              <div className="value positive">{money(totals.net)}</div>
            </div>
            <div className="stat">
              <div className="label">Charges patronales</div>
              <div className="value">{money(totals.employer)}</div>
            </div>
            <div className="stat">
              <div className="label">Coût total employeur</div>
              <div className="value">{money(totals.cost)}</div>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Mat.</th>
                  <th>Employé</th>
                  <th className="num">Brut</th>
                  <th className="num">Cotis. sal.</th>
                  <th className="num">IR + TRIMF</th>
                  <th className="num">Net à payer</th>
                  <th className="num">Charges pat.</th>
                  <th className="num">Coût total</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.matricule}</td>
                    <td>{row.teacher_name}</td>
                    <td className="num">{money(row.gross)}</td>
                    <td className="num">{money(row.employee_contributions)}</td>
                    <td className="num">{money(row.income_tax + row.trimf)}</td>
                    <td className="num">
                      <strong>{money(row.net_pay)}</strong>
                    </td>
                    <td className="num">{money(row.employer_contributions)}</td>
                    <td className="num">{money(row.employer_cost)}</td>
                    <td>
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() =>
                          api.download(
                            `/payslips/${row.id}/pdf/`,
                            `bulletin-${row.matricule}-${row.period}.pdf`,
                          )
                        }
                      >
                        PDF
                      </button>
                    </td>
                  </tr>
                ))}
                <tr className="total">
                  <td colSpan={2}>Total — {rows.length} employés</td>
                  <td className="num">{money(totals.gross)}</td>
                  <td className="num">{money(totals.employee)}</td>
                  <td className="num">{money(totals.tax)}</td>
                  <td className="num">{money(totals.net)}</td>
                  <td className="num">{money(totals.employer)}</td>
                  <td className="num">{money(totals.cost)}</td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
