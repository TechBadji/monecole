import { useState } from "react";

import { api, money, tokens } from "../../api";
import { StaleBanner } from "../../components/OfflineBanners";
import { useOfflineResource } from "../../offline/useOfflineResource";

type Child = {
  id: number;
  name: string;
  classroom: string;
  status: string;
  balance: number | null;
  due_now: number | null;
  tariff_missing: boolean;
};

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
    paid_at: string | null;
  }[];
  discounts: { kind: string; scope: string; value: number; reason: string }[];
  total_due: number;
  total_paid: number;
  balance: number;
  due_now: number;
};

const STATUS = {
  PAID: { label: "Réglé", tone: "paid" },
  PARTIAL: { label: "Partiel", tone: "partial" },
  UNPAID: { label: "À régler", tone: "unpaid" },
} as const;

function StatusBadge({ status }: { status: string }) {
  const entry = STATUS[status as keyof typeof STATUS] ?? STATUS.UNPAID;
  return <span className={`badge ${entry.tone}`}>{entry.label}</span>;
}

export default function ParentHome({ onSignOut }: { onSignOut: () => void }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [paying, setPaying] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const children = useOfflineResource<{ year: string; children: Child[] }>(
    "/portal/children/",
  );
  const ledger = useOfflineResource<Ledger>(
    selected ? `/portal/children/${selected}/ledger/` : null,
  );

  async function payWithWave(child: Child) {
    setPaying(child.id);
    setError(null);
    try {
      const transaction = await api.post<{ checkout_url: string; simulated: boolean }>(
        "/payments/wave/",
        { student: child.id, amount: child.due_now, purpose: "TUITION" },
      );
      if (transaction.checkout_url) {
        // Redirection vers Wave — ou vers la page de simulation en développement.
        window.location.href = transaction.checkout_url;
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Paiement indisponible.");
    } finally {
      setPaying(null);
    }
  }

  function signOut() {
    tokens.clear();
    onSignOut();
  }

  if (children.loading) return <div className="spinner">Chargement…</div>;

  return (
    <div className="portal">
      <div className="portal-head">
        <div>
          <h1>Espace parents</h1>
          <p className="muted">Année scolaire {children.data?.year}</p>
        </div>
        <button type="button" className="secondary" onClick={signOut}>
          Se déconnecter
        </button>
      </div>

      <StaleBanner
        freshness={{ stale: children.stale, cachedAt: children.cachedAt }}
        label="Les soldes affichés"
      />
      {error && <div className="alert error">{error}</div>}
      {children.error && <div className="alert error">{children.error}</div>}

      {children.data?.children.map((child) => (
        <div className="child-card" key={child.id}>
          <header>
            <div>
              <h2>{child.name}</h2>
              <span className="muted">
                {child.classroom} · {child.status}
              </span>
            </div>
            <div
              className={`amount ${(child.due_now ?? 0) > 0 ? "due" : "clear"}`}
            >
              {child.tariff_missing ? "—" : money(child.due_now ?? 0)}
              <span className="unit"> FCFA</span>
            </div>
          </header>

          {child.tariff_missing ? (
            <p className="muted">
              Les tarifs de cette classe ne sont pas encore publiés. Rapprochez-vous
              du secrétariat.
            </p>
          ) : (
            <p className="muted">
              {(child.due_now ?? 0) > 0
                ? `Somme exigible à ce jour. Reste dû sur l'année : ${money(child.balance ?? 0)} FCFA.`
                : "Vous êtes à jour des échéances passées."}
            </p>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button
              type="button"
              className="secondary"
              onClick={() => setSelected(selected === child.id ? null : child.id)}
            >
              {selected === child.id ? "Masquer le détail" : "Voir le détail"}
            </button>
            {(child.due_now ?? 0) > 0 && (
              <button
                type="button"
                onClick={() => void payWithWave(child)}
                disabled={paying === child.id || !navigator.onLine}
              >
                {paying === child.id
                  ? "Ouverture…"
                  : `Payer ${money(child.due_now ?? 0)} FCFA par Wave`}
              </button>
            )}
          </div>

          {selected === child.id && ledger.data && (
            <div style={{ marginTop: 16 }}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Échéance</th>
                      <th className="num">Dû</th>
                      <th className="num">Réglé</th>
                      <th>État</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Inscription</td>
                      <td className="num">{money(ledger.data.registration.due)}</td>
                      <td className="num">{money(ledger.data.registration.paid)}</td>
                      <td>
                        <StatusBadge status={ledger.data.registration.status} />
                      </td>
                    </tr>
                    {ledger.data.months.map((month) => (
                      <tr key={month.period}>
                        <td>
                          {new Date(month.period).toLocaleDateString("fr-FR", {
                            month: "long",
                            year: "numeric",
                          })}
                        </td>
                        <td className="num">{money(month.due)}</td>
                        <td className="num">{money(month.paid)}</td>
                        <td>
                          <StatusBadge status={month.status} />
                        </td>
                      </tr>
                    ))}
                    <tr className="total">
                      <td>Total année</td>
                      <td className="num">{money(ledger.data.total_due)}</td>
                      <td className="num">{money(ledger.data.total_paid)}</td>
                      <td>{money(ledger.data.balance)} restant</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {ledger.data.discounts.length > 0 && (
                <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
                  Réduction appliquée :{" "}
                  {ledger.data.discounts
                    .map((d) => `${d.kind} ${d.value} (${d.reason})`)
                    .join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
      ))}

      {children.data?.children.length === 0 && (
        <div className="card empty">
          Aucun élève actif n'est rattaché à ce numéro. Contactez le secrétariat de
          l'établissement.
        </div>
      )}
    </div>
  );
}
