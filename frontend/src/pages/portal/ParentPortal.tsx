import { useState } from "react";

import { useAuth } from "../../auth";
import ParentHome from "./ParentHome";
import ParentLogin from "./ParentLogin";

/**
 * Racine du portail parent.
 *
 * Volontairement séparée de l'application d'administration : un parent ne partage
 * ni la navigation, ni les écrans, ni le mode d'authentification du personnel.
 */
export default function ParentPortal() {
  const { profile, logout } = useAuth();
  const [, force] = useState(0);

  if (!profile) {
    // Après vérification du code, on recharge pour que le contexte relise le profil.
    return <ParentLogin onAuthenticated={() => window.location.reload()} />;
  }

  return (
    <ParentHome
      onSignOut={() => {
        logout();
        force((value) => value + 1);
      }}
    />
  );
}
