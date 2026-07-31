import { useEffect, useState } from "react";

type Mode = "system" | "light" | "dark";
const KEY = "monecole.theme";

/* Libellé court : la bascule vit dans le menu de la vignette, large de 228 px,
   où « Thème : système » débordait. La ligne porte déjà le mot « Apparence », et
   la phrase entière reste dans l'`aria-label`. */
const LABELS: Record<Mode, string> = {
  system: "Système",
  light: "Clair",
  dark: "Sombre",
};

const SPOKEN: Record<Mode, string> = {
  system: "thème système",
  light: "thème clair",
  dark: "thème sombre",
};

/**
 * Bascule de thème.
 *
 * Trois états et non deux : « système » suit le réglage de l'appareil, les deux
 * autres l'emportent explicitement. Sans le premier, un utilisateur ne peut plus
 * revenir au comportement par défaut une fois qu'il a choisi une fois.
 */
export default function ThemeToggle() {
  const [mode, setMode] = useState<Mode>(
    () => (localStorage.getItem(KEY) as Mode) || "system",
  );

  useEffect(() => {
    const root = document.documentElement;
    if (mode === "system") {
      root.removeAttribute("data-theme");
      localStorage.removeItem(KEY);
    } else {
      root.setAttribute("data-theme", mode);
      localStorage.setItem(KEY, mode);
    }
  }, [mode]);

  const next: Record<Mode, Mode> = { system: "light", light: "dark", dark: "system" };

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setMode(next[mode])}
      aria-label={`Apparence : ${SPOKEN[mode]}. Cliquer pour passer au ${SPOKEN[next[mode]]}.`}
    >
      {LABELS[mode]}
    </button>
  );
}
