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

type Attendance = {
  student: { matricule: string; name: string };
  days: number;
  present_days: number;
  results: {
    day: string;
    arrival: string | null;
    departure: string | null;
    passages: number;
  }[];
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

type Panel = "ledger" | "attendance";

export default function ParentHome({ onSignOut }: { onSignOut: () => void }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [panel, setPanel] = useState<Panel>("ledger");
  const [paying, setPaying] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const children = useOfflineResource<{ year: string; children: Child[] }>(
    "/portal/children/",
  );
  const ledger = useOfflineResource<Ledger>(
    selected && panel === "ledger" ? `/portal/children/${selected}/ledger/` : null,
  );
  const attendance = useOfflineResource<Attendance>(
    selected && panel === "attendance"
      ? `/attendance/student/${selected}/?days=30`
      : null,
  );

  function open(childId: number, next: Panel) {
    // Un second clic sur le même onglet referme : c'est le geste attendu d'un
    // bouton qui affiche déjà « Masquer ».
    if (selected === childId && panel === next) {
      setSelected(null);
      return;
    }
    setSelected(childId);
    setPanel(next);
  }

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

          <div className="child-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => open(child.id, "ledger")}
            >
              {selected === child.id && panel === "ledger"
                ? "Masquer la scolarité"
                : "Scolarité"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => open(child.id, "attendance")}
            >
              {selected === child.id && panel === "attendance"
                ? "Masquer les présences"
                : "Présences"}
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

          {selected === child.id && panel === "attendance" && attendance.data && (
            <div className="child-detail">
              <p className="muted" style={{ marginBottom: "var(--space-3)" }}>
                {attendance.data.present_days} jour(s) de présence enregistrés sur les{" "}
                {attendance.data.days} derniers jours.
              </p>
              {attendance.data.results.length === 0 ? (
                <p className="muted">
                  Aucun passage enregistré. L'école n'utilise peut-être pas encore
                  les cartes à badger.
                </p>
              ) : (
                <div className="table-wrap">
                  <table className="table-dense">
                    <thead>
                      <tr>
                        <th>Jour</th>
                        <th>Arrivée</th>
                        <th>Sortie</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attendance.data.results.map((row) => (
                        <tr key={row.day}>
                          <td>
                            {new Date(row.day).toLocaleDateString("fr-FR", {
                              weekday: "long",
                              day: "2-digit",
                              month: "long",
                            })}
                          </td>
                          <td>{row.arrival ?? <span className="muted">—</span>}</td>
                          <td>
                            {row.departure ?? (
                              <span className="muted">non badgée</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {selected === child.id && panel === "ledger" && ledger.data && (
            <div className="child-detail">
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
                <p className="muted discount-note">
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
