import { useEffect, useRef, useState, type ReactElement } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth";
import { Avatar } from "../pages/Account";
import ThemeToggle from "./ThemeToggle";

const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Super administrateur",
  ADMIN: "Administrateur",
  ACCOUNTANT: "Comptable",
  SECRETARY: "Secrétaire",
  TEACHER: "Enseignant",
  PARENT: "Parent",
};

/**
 * Icônes de groupe, en trait de 1,6 px sur une grille de 16.
 *
 * Elles servent de repère, pas d'ornement : dans une barre de quinze liens, le
 * regard retrouve « Finances » à sa forme avant d'en lire le mot. Le trait est
 * volontairement uniforme d'une icône à l'autre — une famille dépareillée
 * attirerait l'attention sur elle-même.
 */
const GROUP_ICONS: Record<string, ReactElement> = {
  // Quatre panneaux plutôt qu'un cadran : l'arc du compteur et son aiguille se
  // brouillaient en un gribouillis à 14 px, faute de place pour la graduation.
  Pilotage: (
    <path d="M2 2.6h4.6v4.4H2ZM9.4 2.6H14v2.8H9.4ZM2 9.4h4.6v4H2ZM9.4 7.8H14v5.6H9.4Z" />
  ),
  Scolarité: (
    <path d="M8 2.6 14.5 6 8 9.4 1.5 6 8 2.6ZM4 7.5v4c0 1 1.8 1.9 4 1.9s4-.9 4-1.9v-4" />
  ),
  "Vie scolaire": (
    <path d="M3 2.6h7.4L13 5.2v8.2H3V2.6ZM10 2.6v3h3M5.6 8.6h4.8M5.6 11h3.2" />
  ),
  // Un billet, et non un signe dollar : la devise ici est le franc CFA.
  Finances: (
    <path d="M1.6 4.2h12.8v7.6H1.6V4.2ZM8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM4 6.2h.01M12 9.8h.01" />
  ),
  Administration: (
    <path d="M6.4 2.4h3.2l.4 1.7 1.6.7 1.5-.9 1.6 2.8-1.2 1.1v1.7l1.2 1.1-1.6 2.8-1.5-.9-1.6.7-.4 1.7H6.4L6 13.2l-1.6-.7-1.5.9L1.3 10.6l1.2-1.1V7.8L1.3 6.7l1.6-2.8 1.5.9L6 4.1l.4-1.7ZM8 9.9a1.9 1.9 0 1 0 0-3.8 1.9 1.9 0 0 0 0 3.8Z" />
  ),
};

function GroupIcon({ group }: { group: string }) {
  const shape = GROUP_ICONS[group];
  if (!shape) return null;
  return (
    <svg
      className="nav-icon"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {shape}
    </svg>
  );
}

type NavLinkSpec = {
  to: string;
  label: string;
  /** Ressource dont la permission de lecture conditionne l'affichage. */
  resource: string;
  /** `true` pour la racine, qui ne doit correspondre qu'exactement. */
  end?: boolean;
};

const SECTIONS: { group: string; links: NavLinkSpec[] }[] = [
  {
    group: "Pilotage",
    links: [{ to: "/", label: "Tableau de bord", resource: "report", end: true }],
  },
  {
    group: "Scolarité",
    links: [
      { to: "/eleves", label: "Élèves", resource: "student" },
      { to: "/encaissements", label: "Encaissements", resource: "monthlypayment" },
      { to: "/arrieres", label: "Arriérés", resource: "monthlypayment" },
    ],
  },
  {
    group: "Vie scolaire",
    links: [
      { to: "/notes", label: "Saisie des notes", resource: "grade" },
      { to: "/bulletins", label: "Bulletins", resource: "reportcard" },
      { to: "/compositions", label: "Compositions", resource: "composition" },
      { to: "/assiduite", label: "Assiduité", resource: "attendance" },
    ],
  },
  {
    group: "Finances",
    links: [
      { to: "/depenses", label: "Dépenses", resource: "expense" },
      { to: "/bilan", label: "Rapport bilan", resource: "report" },
      { to: "/encais", label: "Encaissements (synthèse)", resource: "report" },
    ],
  },
  {
    group: "Administration",
    links: [
      { to: "/enseignants", label: "Enseignants", resource: "teacher" },
      { to: "/paie", label: "Bulletins de paie", resource: "salary" },
      { to: "/matieres", label: "Matières et coefficients", resource: "subject" },
      { to: "/import", label: "Import de données", resource: "dataimport" },
      { to: "/parametres", label: "Paramètres", resource: "reportcard" },
      { to: "/journal", label: "Journal d'audit", resource: "auditlog" },
    ],
  },
];

/**
 * Vignette de l'utilisateur, en pied de barre.
 *
 * Elle remplace le bloc « nom / rôle / bouton » : trois éléments empilés qui
 * occupaient la place d'un menu et n'en offraient qu'une action. Le menu
 * s'ouvre vers le haut — la vignette est déjà en bas de l'écran.
 */
function UserChip() {
  const { profile, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const holder = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!holder.current?.contains(event.target as Node)) setOpen(false);
    }
    // Échap ferme aussi : un menu qui ne se referme qu'au clic piège qui navigue
    // au clavier.
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!profile) return null;

  return (
    <div className="user-chip-holder" ref={holder}>
      {open && (
        <div className="user-menu" role="menu">
          <div className="user-menu-head">
            <Avatar profile={profile} size={40} />
            <div>
              <strong>{profile.full_name || profile.email}</strong>
              <span>{profile.email}</span>
            </div>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              navigate("/compte");
            }}
          >
            Mon compte
          </button>

          <div className="user-menu-row">
            <span>Apparence</span>
            <ThemeToggle />
          </div>

          <button type="button" role="menuitem" className="danger" onClick={logout}>
            Se déconnecter
          </button>
        </div>
      )}

      <button
        type="button"
        className={`user-chip ${open ? "open" : ""}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <Avatar profile={profile} size={34} />
        <span className="user-chip-text">
          <strong>{profile.full_name || profile.email}</strong>
          <span>{ROLE_LABELS[profile.role] ?? profile.role}</span>
        </span>
        <svg
          className="user-chip-caret"
          viewBox="0 0 16 16"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m4.5 10 3.5-3.5L11.5 10" />
        </svg>
      </button>
    </div>
  );
}

export default function Layout() {
  const { profile, can } = useAuth();

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          MonÉcole
          <small>{profile?.school?.name ?? "Plateforme"}</small>
        </div>

        <nav className="nav">
          {SECTIONS.map((section) => {
            // Une section dont aucune entrée n'est accessible ne s'affiche pas :
            // proposer un lien qui répondra 403 n'aide personne.
            const visible = section.links.filter((link) => can(link.resource, "view"));
            if (visible.length === 0) return null;
            return (
              // `nav-section` porte sa propre colonne flex : sans elle, les liens
              // héritaient du flux en ligne de ce div et coulaient côte à côte,
              // ce qui coupait « Rapport bilan » en deux et tronquait « Arriérés ».
              <div className="nav-section" key={section.group}>
                <h2 className="nav-group" title={section.group}>
                  <GroupIcon group={section.group} />
                  <span className="nav-group-text">{section.group}</span>
                </h2>
                {visible.map((link) => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    end={link.end}
                    className={({ isActive }) => (isActive ? "active" : "")}
                  >
                    {link.label}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <UserChip />
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
