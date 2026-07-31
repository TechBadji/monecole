import type { FormEvent, ReactNode } from "react";

/**
 * La scène commune aux trois écrans d'accès : connexion, mot de passe oublié,
 * réinitialisation.
 *
 * Le volet gauche est la vitrine. Ce qu'il avance est vérifiable dans le code —
 * pas de tarif, pas de client cité, pas de chiffre d'usage : le produit n'a
 * qu'un établissement pilote et l'inventer se verrait à la première question.
 *
 * Le volet droit est la fiche. Ses champs sont des lignes réglées et non des
 * cadres : c'est la grammaire des formulaires d'inscription que ces écoles
 * remplissent à la main, et c'est ce qui distingue cet écran de l'encart
 * centré que tout SaaS pose sur un dégradé.
 */
export default function LoginShell({
  title,
  reference,
  children,
  onSubmit,
}: {
  title: string;
  /** Mention en tête de fiche, à la manière d'un numéro de formulaire. */
  reference: string;
  children: ReactNode;
  onSubmit?: (event: FormEvent) => void;
}) {
  const Wrapper = onSubmit ? "form" : "div";

  return (
    <div className="access">
      <section className="access-pitch">
        <div className="access-brand">
          <Mark />
          <span>MonÉcole</span>
        </div>

        <h1 className="access-headline">
          Du registre d'inscription
          <br />
          au bilan de l'exercice.
        </h1>

        <p className="access-lede">
          La gestion complète d'un établissement préscolaire et primaire —
          effectifs, encaissements, salaires, bulletins.
        </p>
      </section>

      {/* Frère de `.access-pitch`, et non son enfant : sur téléphone, la fiche
          doit s'intercaler entre l'accroche et ces garanties. Un `order` posé
          sur un enfant ne réordonne que sa fratrie — imbriqué, il n'aurait rien
          fait, et la fiche serait restée sous un écran de texte. */}
      <section className="access-proof-zone">
        <ul className="access-proof">
          <li>
            <strong>Deux calendriers, jamais confondus.</strong> L'exercice
            financier court d'octobre à septembre, l'année pédagogique d'octobre
            à juin. Les confondre fausse tous les totaux.
          </li>
          <li>
            <strong>Le franc CFA, sans décimale.</strong> Les montants sont des
            entiers de bout en bout. Aucun arrondi ne se glisse dans un bilan.
          </li>
          <li>
            <strong>Le réseau peut tomber.</strong> Les encaissements se
            saisissent hors ligne et remontent au retour de la connexion.
          </li>
          <li>
            <strong>Chaque opération financière laisse une trace.</strong> Qui a
            saisi, quand, et ce qui a changé.
          </li>
        </ul>
      </section>

      <section className="access-card-zone">
        <Wrapper className="fiche" onSubmit={onSubmit}>
          <header className="fiche-head">
            <span className="fiche-ref">{reference}</span>
            <h2>{title}</h2>
          </header>

          <div className="fiche-body">{children}</div>

          <Cachet />
        </Wrapper>
      </section>
    </div>
  );
}

/**
 * Champ réglé : l'étiquette en capitales surmonte une ligne sur laquelle la
 * saisie se pose. `RuledField` et `PasswordField` doivent rendre le même trait,
 * d'où la classe `ruled` portée par leur conteneur commun.
 */
export function RuledField({
  id,
  label,
  type = "text",
  value,
  onChange,
  autoComplete,
  autoFocus,
  required = true,
  hint,
}: {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
  autoFocus?: boolean;
  required?: boolean;
  hint?: string;
}) {
  return (
    <div className="ruled">
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <input
          id={id}
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          required={required}
        />
        {hint && <p className="field-hint">{hint}</p>}
      </div>
    </div>
  );
}

/**
 * Le cachet. Seul moment de mise en scène de l'écran, et seule animation :
 * il se pose une fois au chargement.
 *
 * L'exercice affiché est déduit de la date — un exercice sénégalais s'ouvre en
 * octobre. Écrire l'année en dur aurait produit un cachet faux dès la rentrée
 * suivante, ce qu'un directeur remarque immédiatement.
 */
function Cachet() {
  const now = new Date();
  const opening = now.getMonth() >= 9 ? now.getFullYear() : now.getFullYear() - 1;

  return (
    <div className="cachet" aria-hidden="true">
      <svg viewBox="0 0 120 120" width="96" height="96">
        <defs>
          <path
            id="cachet-arc"
            d="M60 60 m-42 0 a42 42 0 1 1 84 0 a42 42 0 1 1 -84 0"
            fill="none"
          />
        </defs>
        <circle cx="60" cy="60" r="52" className="cachet-ring" />
        <circle cx="60" cy="60" r="46" className="cachet-ring thin" />
        <text className="cachet-arc-text">
          <textPath href="#cachet-arc" startOffset="25%" textAnchor="middle">
            MONÉCOLE · GESTION D'ÉTABLISSEMENT
          </textPath>
        </text>
        <text x="60" y="55" className="cachet-label" textAnchor="middle">
          EXERCICE
        </text>
        <text x="60" y="76" className="cachet-year" textAnchor="middle">
          {opening}/{opening + 1}
        </text>
      </svg>
    </div>
  );
}

/** Le monogramme : un registre ouvert, deux pages réglées. */
function Mark() {
  return (
    <svg
      viewBox="0 0 28 28"
      width="26"
      height="26"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 7.4C11.8 5.6 9.3 4.8 5.6 4.8v15c3.7 0 6.2.8 8.4 2.6 2.2-1.8 4.7-2.6 8.4-2.6v-15c-3.7 0-6.2.8-8.4 2.6Z" />
      <path d="M14 7.4v14.9" />
      <path d="M8.6 10.2h2.6M8.6 13.4h2.6M16.8 10.2h2.6M16.8 13.4h2.6" />
    </svg>
  );
}
