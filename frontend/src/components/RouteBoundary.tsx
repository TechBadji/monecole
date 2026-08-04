import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Barrière d'erreur autour des écrans chargés à la demande.
 *
 * Sans elle, un module qui ne se charge pas fait disparaître tout l'arbre React
 * et laisse une **page blanche** : l'utilisateur clique sur « Encaissements » et
 * il ne se passe rien, sans le moindre message. C'est le pire mode de panne —
 * indiscernable d'une application cassée, et impossible à signaler autrement
 * que par « ça ne marche pas ».
 *
 * Le cas le plus fréquent n'est pas un bogue de l'écran mais un **module
 * introuvable** : après un déploiement, le navigateur réclame un fragment que le
 * service worker a gardé en cache et que le serveur ne sert plus. La seule
 * issue est de vider le cache et de recharger, ce que le bouton fait.
 */
type Props = { children: ReactNode };
type State = { error: Error | null };

/** Un import dynamique qui échoue ne porte pas de code : seul le message le dit. */
function isModuleLoadError(error: Error) {
  return /dynamically imported module|Importing a module script failed|Failed to fetch|ChunkLoadError/i.test(
    `${error.name} ${error.message}`,
  );
}

async function clearCachesAndReload() {
  try {
    if ("caches" in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map((key) => caches.delete(key)));
    }
    // Le worker lui-même doit partir : il resservirait le même fragment.
    const registrations = await navigator.serviceWorker?.getRegistrations?.();
    await Promise.all((registrations ?? []).map((r) => r.unregister()));
  } finally {
    // `reload()` sans argument suffit : les caches viennent d'être vidés.
    window.location.reload();
  }
}

export default class RouteBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Laisse une trace exploitable : sans elle, le rapport se résume à
    // « la page est blanche », et le défaut est introuvable.
    console.error("Écran en échec", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const stale = isModuleLoadError(error);
    return (
      <div className="route-error">
        <h1>{stale ? "Cet écran n'a pas pu se charger" : "Cet écran a rencontré une erreur"}</h1>
        <p>
          {stale
            ? "Votre navigateur a gardé en mémoire une version antérieure de " +
              "l'application. Vider ce cache et recharger règle la situation."
            : "L'erreur a été consignée dans la console du navigateur. Le reste " +
              "de l'application reste utilisable."}
        </p>

        <div className="page-actions">
          {stale ? (
            <button type="button" onClick={clearCachesAndReload}>
              Vider le cache et recharger
            </button>
          ) : (
            <button type="button" onClick={() => this.setState({ error: null })}>
              Réessayer
            </button>
          )}
          <a className="quiet-link" href="/">
            Revenir au tableau de bord
          </a>
        </div>

        <pre className="route-error-detail">{error.message}</pre>
      </div>
    );
  }
}
