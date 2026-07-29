import { useEffect, useState } from "react";

import {
  absoluteTime,
  relativeTime,
  type Freshness,
} from "../offline/useOfflineResource";
import { listQueue, type QueuedMutation } from "../offline/db";
import { discard, retry, subscribe, sync, type SyncState } from "../offline/sync";

/**
 * Bandeau global de connexion et de synchronisation.
 *
 * Toujours visible dès qu'il y a quelque chose à signaler. Une saisie faite hors
 * ligne et jamais repartie serait une perte silencieuse : l'utilisateur doit
 * savoir en permanence combien d'écritures restent en attente.
 */
export function SyncBanner() {
  const [state, setState] = useState<SyncState | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<QueuedMutation[]>([]);

  useEffect(() => subscribe(setState), []);

  useEffect(() => {
    if (expanded) void listQueue().then(setItems);
  }, [expanded, state?.pending, state?.failed]);

  if (!state) return null;
  const { online, syncing, pending, failed } = state;
  if (online && !syncing && pending === 0 && failed === 0) return null;

  const tone = failed > 0 ? "error" : online ? "success" : "warning";

  return (
    <div className={`sync-banner ${tone}`}>
      <div className="sync-line">
        <span className="sync-dot" aria-hidden="true" />
        <span className="sync-text">
          {!online && "Hors ligne — vos saisies sont conservées sur cet appareil."}
          {online && syncing && "Synchronisation en cours…"}
          {online && !syncing && pending > 0 &&
            `${pending} saisie${pending > 1 ? "s" : ""} en attente d'envoi.`}
          {online && !syncing && pending === 0 && failed > 0 &&
            `${failed} saisie${failed > 1 ? "s" : ""} refusée${failed > 1 ? "s" : ""} par le serveur.`}
        </span>

        {(pending > 0 || failed > 0) && (
          <button type="button" className="link" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Masquer" : "Détail"}
          </button>
        )}
        {online && !syncing && pending > 0 && (
          <button type="button" className="secondary small" onClick={() => void sync()}>
            Envoyer maintenant
          </button>
        )}
      </div>

      {expanded && (
        <ul className="sync-list">
          {items.map((item) => (
            <li key={item.id}>
              <span className="sync-item-label">{item.label}</span>
              <span className="muted">
                {item.status === "failed" ? item.lastError : "en attente"}
              </span>
              {item.status === "failed" && (
                <span className="sync-actions">
                  <button type="button" className="link" onClick={() => void retry(item)}>
                    Réessayer
                  </button>
                  <button
                    type="button"
                    className="link danger"
                    onClick={() => item.id !== undefined && void discard(item.id)}
                  >
                    Abandonner
                  </button>
                </span>
              )}
            </li>
          ))}
          {items.length === 0 && <li className="muted">File vide.</li>}
        </ul>
      )}
    </div>
  );
}

/**
 * Bandeau de fraîcheur, à placer au-dessus de données mises en cache.
 *
 * `precise` pour les états financiers : sur un bilan, « il y a 3 h » est trop vague
 * pour décider si le chiffre est exploitable — on affiche la date et l'heure.
 */
export function StaleBanner({
  freshness,
  precise = false,
  label = "Ces données",
}: {
  freshness: Freshness;
  precise?: boolean;
  label?: string;
}) {
  if (!freshness.stale) return null;
  const when = precise
    ? absoluteTime(freshness.cachedAt)
    : relativeTime(freshness.cachedAt);

  return (
    <div className="alert warning">
      <strong>Données hors ligne.</strong> {label} datent du {when} et n'ont pas été
      actualisées depuis. Reconnectez-vous pour obtenir la situation à jour.
    </div>
  );
}
