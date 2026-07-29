import { money } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import type { Arrears as ArrearsData } from "../types";

export default function Arrears() {
  const { profile } = useAuth();
  const currency = profile?.school?.currency ?? "XOF";
  const { data, error, loading } = useResource<ArrearsData>("/monthly-payments/arrears/");

  if (loading) return <div className="spinner">Chargement…</div>;
  if (error) return <div className="alert error">{error}</div>;
  if (!data) return null;

  const total = data.results.reduce((sum, row) => sum + row.arrears, 0);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Arriérés de paiement</h1>
          <p>
            Calculés sur les mois échus de l'année {data.year}, au tarif de chaque
            classe et après application des réductions.
          </p>
        </div>
      </div>

      <div className="stats">
        <div className="stat">
          <div className="label">Élèves concernés</div>
          <div className="value">{data.count}</div>
        </div>
        <div className="stat">
          <div className="label">Montant total</div>
          <div className="value negative">
            {money(total)}
            <span className="unit">{currency}</span>
          </div>
        </div>
      </div>

      {data.results.length === 0 ? (
        <div className="card empty">Aucun arriéré. Tous les élèves sont à jour.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Élève</th>
                <th>Classe</th>
                <th>Téléphone du parent</th>
                <th className="num">Dû</th>
                <th className="num">Réglé</th>
                <th className="num">Arriéré</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <tr key={row.student}>
                  <td>{row.name}</td>
                  <td>{row.classroom}</td>
                  <td>{row.parent_phone || <span className="muted">—</span>}</td>
                  <td className="num">{money(row.due)}</td>
                  <td className="num">{money(row.paid)}</td>
                  <td className="num">
                    <strong>{money(row.arrears)}</strong>
                  </td>
                </tr>
              ))}
              <tr className="total">
                <td colSpan={5}>Total</td>
                <td className="num">{money(total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
