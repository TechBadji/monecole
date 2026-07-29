import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth";

const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Super administrateur",
  ADMIN: "Administrateur",
  ACCOUNTANT: "Comptable",
  SECRETARY: "Secrétaire",
  TEACHER: "Enseignant",
  PARENT: "Parent",
};

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
      { to: "/journal", label: "Journal d'audit", resource: "auditlog" },
    ],
  },
];

export default function Layout() {
  const { profile, logout, can } = useAuth();

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
              <div key={section.group}>
                <div className="nav-group">{section.group}</div>
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
          <div className="who">
            <strong>{profile?.full_name || profile?.email}</strong>
            {ROLE_LABELS[profile?.role ?? ""] ?? profile?.role}
          </div>
          <button type="button" className="ghost" onClick={logout}>
            Se déconnecter
          </button>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
