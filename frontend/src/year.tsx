import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useResource } from "./hooks";
import type { Paginated, SchoolYear } from "./types";

/**
 * Année scolaire consultée, commune à toute l'application.
 *
 * Un sélecteur par écran laisserait l'utilisateur saisir dans une année sans
 * s'en rendre compte — la faute la plus coûteuse de ce produit, puisqu'elle ne
 * se voit qu'au bilan. Ici, un seul réglage commande tous les écrans, et une
 * bande signale en permanence qu'on ne regarde pas l'année en cours.
 *
 * Le choix ne survit pas à la session : rouvrir l'application ramène toujours
 * à l'année courante. Une préférence conservée ferait rouvrir sur 2023 un
 * secrétariat qui a consulté un vieux dossier la veille.
 */
type YearState = {
  years: SchoolYear[];
  current: SchoolYear | null;
  selected: SchoolYear | null;
  select: (id: number) => void;
  /** Vrai dès qu'on consulte autre chose que l'année en cours. */
  isPast: boolean;
  reload: () => void;
};

const YearContext = createContext<YearState | null>(null);

export function YearProvider({ children }: { children: ReactNode }) {
  const { data, reload } = useResource<Paginated<SchoolYear>>("/school-years/");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const years = useMemo(() => data?.results ?? [], [data]);
  const current = useMemo(
    () => years.find((year) => year.is_current) ?? years[0] ?? null,
    [years],
  );

  useEffect(() => {
    if (selectedId === null && current) setSelectedId(current.id);
  }, [current, selectedId]);

  const selected = years.find((year) => year.id === selectedId) ?? current;

  return (
    <YearContext.Provider
      value={{
        years,
        current,
        selected,
        select: setSelectedId,
        isPast: Boolean(selected && current && selected.id !== current.id),
        reload,
      }}
    >
      {children}
    </YearContext.Provider>
  );
}

/**
 * Paramètre `year` à joindre aux appels, ou chaîne vide.
 *
 * Vide tant que les années ne sont pas chargées : sans cela, le premier appel
 * partirait avec `year=undefined` et le serveur retomberait sur l'année
 * courante — donnant l'illusion que le sélecteur fonctionne alors qu'il ne
 * ferait rien au premier rendu.
 */
export function useYearParam(separator: "?" | "&" = "?") {
  const { selected } = useYear();
  return selected ? `${separator}year=${selected.id}` : "";
}

export function useYear() {
  const context = useContext(YearContext);
  if (!context) throw new Error("useYear doit être utilisé dans un YearProvider.");
  return context;
}

/**
 * Sélecteur d'année, en tête de barre latérale.
 *
 * Placé avec la navigation et non dans un écran : il commande l'application
 * entière, et l'enfouir dans une page laisserait croire qu'il n'agit que là.
 */
export function YearSelector() {
  const { years, selected, select, isPast } = useYear();
  if (years.length === 0) return null;

  return (
    <div className={`year-selector ${isPast ? "past" : ""}`}>
      <label htmlFor="app-year">Année scolaire</label>
      <select
        id="app-year"
        value={selected?.id ?? ""}
        onChange={(event) => select(Number(event.target.value))}
      >
        {years.map((year) => (
          <option key={year.id} value={year.id}>
            {year.label}
            {year.is_current ? " — en cours" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Bande d'avertissement pour une année close.
 *
 * Affichée sur chaque écran, pas seulement à la racine : on arrive souvent
 * dans l'application par un lien, et la bande doit se voir là où l'on saisit.
 */
export function PastYearBanner() {
  const { selected, current, select, isPast } = useYear();
  if (!isPast || !selected || !current) return null;

  return (
    <div className="alert warning past-year-banner" role="status">
      <span>
        Vous consultez l'année <strong>{selected.label}</strong>, close. Les
        chiffres affichés sont ceux de cette année-là.
      </span>
      <button type="button" className="quiet-link as-button" onClick={() => select(current.id)}>
        Revenir à {current.label}
      </button>
    </div>
  );
}
