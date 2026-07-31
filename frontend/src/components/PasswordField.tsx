import { useId, useState } from "react";

/**
 * Champ de mot de passe avec affichage en clair.
 *
 * Le seul composant de saisie de mot de passe du produit : c'est ce qui garantit
 * que l'œil est partout, et pas seulement là où on a pensé à l'ajouter.
 *
 * Trois détails qui font la différence entre un œil et un œil utilisable :
 *
 * - Le bouton est un vrai `<button type="button">`. Sans `type`, il se
 *   comporterait en bouton de soumission et enverrait le formulaire.
 * - Il ne prend pas le focus au clavier (`tabIndex={-1}`) : quelqu'un qui
 *   tabule d'un champ à l'autre ne doit pas buter dessus. Il reste actionnable
 *   à la souris et au toucher, et les lecteurs d'écran l'annoncent par son
 *   `aria-label`.
 * - `aria-pressed` porte l'état, faute de quoi un lecteur d'écran annonce deux
 *   fois « Afficher » sans jamais dire ce qui est en cours.
 */
export default function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  autoFocus,
  required = true,
  hint,
  error,
}: {
  id?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
  autoFocus?: boolean;
  required?: boolean;
  hint?: string;
  error?: string | null;
}) {
  const generated = useId();
  const fieldId = id ?? generated;
  const hintId = `${fieldId}-hint`;
  const [visible, setVisible] = useState(false);

  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <div className={`password-input ${error ? "has-error" : ""}`}>
        <input
          id={fieldId}
          // Le navigateur ne propose plus d'enregistrer un mot de passe affiché
          // en clair ; on ne bascule donc le type que le temps de la lecture.
          type={visible ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          required={required}
          aria-describedby={hint || error ? hintId : undefined}
          aria-invalid={error ? true : undefined}
        />
        <button
          type="button"
          tabIndex={-1}
          className="password-toggle"
          aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
        >
          <EyeIcon crossed={visible} />
        </button>
      </div>
      {error ? (
        <p className="field-error" id={hintId}>
          {error}
        </p>
      ) : hint ? (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/**
 * L'œil barré signale « cliquez pour masquer », donc que le texte est visible.
 * La convention inverse existe aussi ; celle-ci est retenue parce que la barre
 * décrit ce que fait le bouton, comme le reste des commandes du produit.
 */
function EyeIcon({ crossed }: { crossed: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1.8 10s3-5.4 8.2-5.4S18.2 10 18.2 10s-3 5.4-8.2 5.4S1.8 10 1.8 10Z" />
      <circle cx="10" cy="10" r="2.4" />
      {crossed && <path d="M3.4 16.6 16.6 3.4" />}
    </svg>
  );
}
