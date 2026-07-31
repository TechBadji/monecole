"""Vérifie l'hypothèse de calcul sur les 20 bulletins fournis.

Hypothèse : moyenne = (somme des notes / somme des barèmes) × 10.
Si elle tient au centième sur tous les bulletins, le « coefficient » de cette
école est le barème, et la moyenne est sur 10 — pas sur 20.
"""

# (classe, année, épreuve, moyenne imprimée, [(matière, note, barème), ...])
BULLETINS = [
    ("CM2", "2023-2024", "Contrôle 3", 9.81, [
        ("Activités de Mesures", 12, 12), ("Activités Géométriques", 8, 8),
        ("Activités Numériques", 16, 16), ("Arts Plastiques", 10, 10),
        ("Compétences DM", 16, 16), ("Compétences EDD", 16, 16),
        ("Compétences Maths", 60, 60), ("Conjugaison", 10, 10),
        ("Géographie", 8, 8), ("Grammaire", 11, 13), ("Histoire", 8, 8),
        ("IST", 7, 8), ("Lecture Compréhension", 8, 8), ("Orthographe", 3, 5),
        ("Production d'écrits", 59.5, 60), ("Résolution de Problème", 4, 4),
        ("Vivre dans son Milieu", 12, 12), ("Vivre Ensemble", 12, 12),
        ("Vocabulaire", 4, 4),
    ]),
    ("CM2", "2023-2024", "Composition 2", 9.73, [
        ("Activités de Mesures", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 9, 10),
        ("Compétences DM", 16, 16), ("Compétences EDD", 16, 16),
        ("Compétences Maths", 60, 60), ("Conjugaison", 6, 6),
        ("Géographie", 6, 6), ("Grammaire", 12, 13), ("Histoire", 6, 8),
        ("IST", 10, 10), ("Lecture Compréhension", 10, 10), ("Orthographe", 3, 5),
        ("Production d'écrits", 58, 60), ("Récitation/Chant", 10, 10),
        ("Résolution de Problème", 10, 10), ("Vivre dans son Milieu", 12, 12),
        ("Vivre Ensemble", 12, 12), ("Vocabulaire", 6, 6),
    ]),
    ("CM1", "2022-2023", "Contrôle 2", 9.65, [
        ("Activités de Mesures", 9, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 9, 10),
        ("Compétences DM", 16, 16), ("Compétences EDD", 16, 16),
        ("Compétences Maths", 60, 60), ("Conjugaison", 8, 8),
        ("Géographie", 8, 8), ("Grammaire", 8, 8), ("Histoire", 8, 8),
        ("IST", 7.5, 8), ("Orthographe", 10, 10), ("Production d'écrits", 59, 60),
        ("Récitation/Chant", 10, 10), ("Résolution de Problème", 9, 10),
        ("TSQ", 9, 10), ("Vivre dans son Milieu", 12, 12),
        ("Vivre Ensemble", 7, 12), ("Vocabulaire", 4, 4),
    ]),
    ("CM1", "2022-2023", "Composition 2", 9.38, [
        ("Activités de Mesures", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 9.5, 10),
        ("Compétences DM", 16, 16), ("Compétences EDD", 8, 16),
        ("Compétences Maths", 60, 60), ("Conjugaison", 8, 8), ("Fluidité", 5, 5),
        ("Géographie", 8, 8), ("Grammaire", 8, 8), ("Histoire", 8, 8),
        ("IST", 6, 8), ("Orthographe", 5, 5), ("Production d'écrits", 59, 60),
        ("Récitation/Chant", 10, 10), ("Résolution de Problème", 10, 10),
        ("TSQ", 8, 8), ("Vivre dans son Milieu", 8, 12),
        ("Vivre Ensemble", 9, 12), ("Vocabulaire", 6, 6),
    ]),
    ("CE1A", "2024-2025", "Contrôle 1", 9.78, [
        ("Activités de Mesure", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 10, 10),
        ("Compétences DM", 7.5, 8), ("Compétences EDD", 8, 8),
        ("Compétences Maths", 20, 20), ("Conjugaison", 6, 6),
        ("Géographie", 4, 4), ("Grammaire", 4, 4), ("Histoire", 4, 4),
        ("IST", 4, 4), ("Orthographe", 3, 4), ("Production d'écrits", 20, 20),
        ("Récitation/Chant", 9, 10), ("Résolution de Problèmes", 10, 10),
        ("TSQ", 2, 3), ("Vivre dans son Milieu", 6, 6),
        ("Vivre Ensemble", 6, 6), ("Vocabulaire", 3, 3),
    ]),
    ("CE1A", "2024-2025", "Contrôle 2", 9.88, [
        ("Activités de Mesure", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 10, 10),
        ("Compétences DM", 8, 8), ("Compétences EDD", 8, 8),
        ("Compétences Maths", 10, 10), ("Conjugaison", 4, 4),
        ("Conscience Phonologique", 5, 5), ("Déchiffrage de Mots", 5, 5),
        ("Fluidité", 10, 10), ("Géographie", 4, 4), ("Grammaire", 4, 4),
        ("Histoire", 4, 4), ("IST", 4, 4), ("Orthographe", 4, 4),
        ("Principe Alphabétique", 10, 10), ("Production d'écrits", 9, 10),
        ("Récitation/Chant", 9, 10), ("Résolution de Problèmes", 10, 10),
        ("TSQ", 4, 4), ("Vivre dans son Milieu", 6, 6),
        ("Vivre Ensemble", 6, 6), ("Vocabulaire", 4, 4),
    ]),
    ("CE1A", "2024-2025", "Contrôle 3", 9.97, [
        ("Activités de Mesure", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 10, 10),
        ("Compétences DM", 8, 8), ("Compétences EDD", 8, 8),
        ("Compétences Maths", 20, 20), ("Conjugaison", 3, 3),
        ("Géographie", 4, 4), ("Grammaire", 4, 4), ("Histoire", 4, 4),
        ("IST", 4, 4), ("Orthographe", 5, 5), ("Production d'écrits", 20, 20),
        ("Récitation/Chant", 9.5, 10), ("Résolution de Problèmes", 10, 10),
        ("TSQ", 5, 5), ("Vivre dans son Milieu", 6, 6),
        ("Vivre Ensemble", 6, 6), ("Vocabulaire", 3, 3),
    ]),
    ("CE1A", "2024-2025", "Composition 1", 9.78, [
        ("Activités de Mesure", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 10, 10),
        ("Compétences DM", 8, 8), ("Compétences EDD", 8, 8),
        ("Compétences Maths", 20, 20), ("Conjugaison", 9, 9),
        ("Conscience Phonologique", 4, 5), ("Déchiffrage de Mots", 5, 5),
        ("Fluidité", 5, 5), ("Géographie", 4, 4), ("Grammaire", 3, 6),
        ("Histoire", 4, 4), ("IST", 4, 4), ("Orthographe", 4, 4),
        ("Principe Alphabétique", 5, 5), ("Production d'écrits", 10, 10),
        ("Récitation/Chant", 10, 10), ("Résolution de Problèmes", 10, 10),
        ("TSQ", 5, 5), ("Vivre dans son Milieu", 6, 6),
        ("Vivre Ensemble", 6, 6), ("Vocabulaire", 6, 6),
    ]),
    ("CE1A", "2024-2025", "Composition 3", 9.88, [
        ("Conjugaison", None, 2), ("Grammaire", None, 9), ("Vocabulaire", None, 4),
        ("Orthographe", None, 5), ("TSQ", None, 5), ("Production d'écrits", None, 20),
        ("Fluidité", None, 5), ("Activités Numériques", None, 16),
        ("Activités Géométriques", None, 8), ("Activités de Mesure", None, 12),
        ("Résolution de Problème", None, 4), ("Compétences Maths", None, 20),
        ("Histoire", None, 4), ("Géographie", None, 4), ("IST", None, 4),
        ("Compétences DM", None, 8), ("Vivre Ensemble", None, 6),
        ("Vivre dans son Milieu", None, 6), ("Compétences EDD", None, 8),
        ("Arts Plastiques", None, 10), ("Récitation/Chant", None, 10),
    ], 168),
    ("CP A", "2023-2024", "Contrôle 2", 9.90, [
        ("Activités de Mesures", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 10, 10),
        ("AutoDictée", 10, 10), ("Conscience Phonologique", 10, 10),
        ("Copie", 5, 5), ("Déchiffrage de Mots", 10, 10), ("Écriture", 5, 5),
        ("Fluidité", 10, 10), ("Géographie", 10, 10), ("Histoire", 10, 10),
        ("IST", 10, 10), ("Lecture Compréhension", 10, 10),
        ("Principe Alphabétique", 10, 10), ("Production d'écrits", 10, 10),
        ("Récitation/Chant", 10, 10), ("Résolution de Problème", 10, 10),
        ("Vivre dans son Milieu", 8, 10), ("Vivre Ensemble", 10, 10),
        ("Vocabulaire", 10, 10),
    ]),
    ("CP A", "2023-2024", "Contrôle 3", 9.89, [
        ("Activités de Mesures", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 10, 10),
        ("AutoDictée", 10, 10), ("Compétences Maths", 20, 20), ("Copie", 10, 10),
        ("Correspondance graphophonologique", 2, 2), ("Écriture", 10, 10),
        ("Fluidité", 5, 5), ("Géographie", 6, 6), ("Histoire", 8, 8),
        ("Identification des mots", 4, 4), ("IST", 6, 6),
        ("Lecture Compréhension", 6, 6), ("Production d'écrits", 10, 10),
        ("Récitation/Chant", 10, 10), ("Résolution de Problème", 10, 10),
        ("Vivre dans son Milieu", 10, 10), ("Vivre Ensemble", 8, 10),
        ("Vocabulaire", 3, 3),
    ]),
    ("CP A", "2023-2024", "Composition 1", 9.85, [
        ("Activités de Mesures", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 9.5, 10),
        ("AutoDictée", 10, 10), ("Compétences DM", 8, 8),
        ("Compétences EDD", 8, 8), ("Compétences Maths", 10, 10),
        ("Conscience Phonologique", 4, 4), ("Copie", 10, 10),
        ("Dessin des mots", 3, 3), ("Écriture", 10, 10), ("Fluidité", 5, 5),
        ("Géographie", 4, 4), ("Histoire", 4, 4), ("IST", 4, 4),
        ("Lecture Compréhension", 4, 4), ("Production d'écrits", 10, 10),
        ("Récitation/Chant", 10, 10), ("Résolution de Problème", 8, 10),
        ("Vivre dans son Milieu", 6, 6), ("Vivre Ensemble", 6, 6),
        ("Vocabulaire", 4, 4),
    ]),
    ("CP A", "2023-2024", "Composition 3", 9.97, [
        ("Activités de Mesures", 10, 10), ("Activités Géométriques", 10, 10),
        ("Activités Numériques", 10, 10), ("Arts Plastiques", 10, 10),
        ("AutoDictée", 10, 10), ("Compétences DM", 8, 8),
        ("Compétences EDD", 8, 8), ("Compétences Maths", 10, 10),
        ("Copie", 10, 10), ("Correspondance graphophonologique", 4, 4),
        ("Écriture", 10, 10), ("Fluidité", 5, 5), ("Géographie", 4, 4),
        ("Histoire", 4, 4), ("Identification des mots", 6, 6), ("IST", 4, 4),
        ("Production d'écrits", 10, 10), ("Récitation/Chant", 10, 10),
        ("Résolution de Problème", 10, 10), ("TSQ", 10, 10),
        ("Vivre dans son Milieu", 6, 6), ("Vivre Ensemble", 5.5, 6),
        ("Vocabulaire", 5, 5),
    ]),
    ("CI A", "2022-2023", "Composition 2", 9.71, [
        ("Activités de Mesures", 7, 7), ("Activités Géométriques", 7, 7),
        ("Activités Numériques", 9, 9), ("Arts Plastiques", 10, 10),
        ("AutoDictée", 10, 10), ("Compétences DM", 6, 8),
        ("Compétences EDD", 8, 8), ("Compétences Maths", 20, 20),
        ("Copie", 10, 10), ("Correspondance graphophonologique", 3, 3),
        ("Écriture", 8, 10), ("Fluidité", 5, 5), ("Géographie", 4, 4),
        ("Histoire", 4, 4), ("Identification des mots", 3, 3), ("IST", 4, 4),
        ("Lecture Compréhension", 5, 5), ("Production d'écrits", 10, 10),
        ("Récitation/Chant", 9, 10), ("Résolution de Problème", 7, 7),
        ("Vivre dans son Milieu", 6, 6), ("Vivre Ensemble", 6, 6),
        ("Vocabulaire", 4, 4),
    ]),
    ("CE2B", "2025-2026", "Contrôle 1", 8.98, [
        ("TSQ", 6, 10), ("Histoire", 2, 4), ("Grammaire", 3.5, 4),
        ("Orthographe", 3, 4), ("Production d'écrits", 20, 20),
        ("Récitation/Chant", 10, 10), ("Conjugaison", 1, 4), ("Géographie", 1, 4),
        ("Fluidité", 5, 5), ("IST", 4, 4),
        ("Correspondances graphophonologiques", 5, 5), ("Anglais", 10, 10),
        ("Activités Numériques", 11, 16), ("Vivre dans son Milieu", 6, 6),
        ("Activités de Mesure", 12, 12), ("Activités Géométriques", 8, 8),
        ("Vivre Ensemble", 6, 6), ("Résolution de Problèmes", 4, 4),
        ("Arabe", 9.5, 10), ("Compétence EDD", 8, 8), ("Compétence DM", 8, 8),
        ("Arts Plastiques", 9.5, 10), ("Compétence Maths", 20, 20),
        ("Vocabulaire", 2, 3), ("Déchiffrage", 5, 5),
    ]),
    ("CE2B", "2025-2026", "Contrôle 2", 9.68, [
        ("Compétence DM", 7, 8), ("Fluidité", 5, 5),
        ("Activités Numériques", 16, 16), ("Principe Alphabétique", 5, 5),
        ("Vivre Ensemble", 6, 6), ("Vivre dans son Milieu", 6, 6),
        ("Grammaire", 4, 4), ("Activités de Mesure", 12, 12), ("Arabe", 10, 10),
        ("Compétence EDD", 8, 8), ("Conjugaison", 4, 4),
        ("Activités Géométriques", 8, 8), ("Histoire", 3.5, 4),
        ("Orthographe", 4, 4), ("Résolution de Problèmes", 4, 4),
        ("Arts Plastiques", 9, 10), ("Production d'écrits", 16, 20),
        ("Récitation/Chant", 10, 10), ("Conscience Phonémique", 5, 5),
        ("TSQ", 4, 4), ("Anglais", 10, 10), ("Géographie", 4, 4),
        ("Compétence Maths", 20, 20), ("Déchiffrage", 5, 5),
        ("Vocabulaire", 4, 4), ("IST", 4, 4),
    ]),
    ("CE2B", "2025-2026", "Contrôle 3", 9.60, [
        ("Géographie", 4, 4), ("Vocabulaire", 8, 8),
        ("Activités de Mesure", 12, 12), ("Vivre dans son Milieu", 6, 6),
        ("Orthographe", 5, 5), ("Arabe", 10, 10),
        ("Résolution de Problèmes", 4, 4), ("Production d'écrits", 19, 20),
        ("Anglais", 10, 10), ("Identification de mots", 5, 5),
        ("Compétence EDD", 8, 8), ("Grammaire", 8, 8),
        ("Récitation/Chant", 10, 10), ("IST", 4, 4), ("Compétence Maths", 8, 10),
        ("Correspondances graphophonologiques", 1, 5), ("Arts Plastiques", 10, 10),
        ("Activités Géométriques", 8, 8), ("Compétence DM", 8, 8),
        ("Activités Numériques", 16, 16), ("Conjugaison", 8, 8),
        ("Fluidité", 5, 5), ("Histoire", 3.5, 4), ("TSQ", 6, 6),
        ("Vivre Ensemble", 5.5, 6),
    ]),
    ("CE2B", "2025-2026", "Composition 1", 9.50, [
        ("Vivre dans son Milieu", 4, 6), ("Activités Numériques", 10, 10),
        ("Géographie", 4, 4), ("Compréhension", 6, 7),
        ("Activités de Mesure", 10, 10), ("Compétence EDD", 8, 8), ("IST", 4, 4),
        ("Activités Géométriques", 10, 10), ("Arts Plastiques", 10, 10),
        ("Résolution de Problèmes", 9, 10), ("Conjugaison", 7, 10),
        ("Récitation/Chant", 10, 10), ("Arabe", 9.5, 10), ("Vocabulaire", 6, 8),
        ("Compétence DM", 8, 8), ("Orthographe", 5, 5),
        ("Compétence Maths", 19.5, 20), ("Vivre Ensemble", 6, 6),
        ("Production d'écrits", 20, 20), ("Grammaire", 10, 10),
        ("Histoire", 4, 4), ("Anglais", 10, 10),
    ]),
    ("CE2B", "2025-2026", "Composition 2", 9.53, [
        ("Géographie", 4, 4), ("Vocabulaire", 1.5, 3), ("IST", 4, 4),
        ("Compétence DM", 8, 8), ("Conjugaison", 4, 4), ("Vivre Ensemble", 6, 6),
        ("Orthographe", 4.5, 5), ("Principe Alphabétique", 5, 5),
        ("Vivre dans son Milieu", 6, 6), ("Compétence LC", 9, 10),
        ("Compétence EDD", 8, 8), ("Arabe", 6, 10),
        ("Activités Numériques", 16, 16), ("Arts Plastiques", 9.5, 10),
        ("Activités de Mesure", 12, 12), ("Récitation/Chant", 10, 10),
        ("Grammaire", 4, 4), ("Activités Géométriques", 8, 8), ("Anglais", 10, 10),
        ("Résolution de Problèmes", 4, 4), ("Identification de mots", 5, 5),
        ("Compétence Maths", 10, 10), ("Fluidité", 10, 10), ("Histoire", 4, 4),
        ("TSQ", 3, 4),
    ]),
    ("CE2B", "2025-2026", "Composition 3", 9.58, [
        ("Vivre Ensemble", 6, 6), ("Activités de Mesure", 10, 10),
        ("Compétence EDD", 8, 8), ("Compétence Maths", 20, 20),
        ("Activités Géométriques", 6.5, 10), ("Géographie", 4, 4),
        ("Activités Numériques", 10, 10), ("Compétence DM", 6, 8),
        ("Vivre dans son Milieu", 6, 6), ("Vocabulaire", 8, 8),
        ("Arts Plastiques", 9.5, 10), ("Histoire", 4, 4), ("Arabe", 9, 10),
        ("Récitation/Chant", 10, 10), ("Grammaire", 8, 8), ("Conjugaison", 12, 12),
        ("Résolution de Problèmes", 10, 10), ("Orthographe", 3, 4), ("IST", 4, 4),
        ("Production d'écrits", 20, 20), ("TSQ", 8, 8),
    ]),
]


def main():
    print(f"{'Classe':6} {'Année':10} {'Épreuve':15} {'Σnotes':>8} {'Σbarèmes':>9} "
          f"{'calculée':>9} {'imprimée':>9}  écart")
    print("-" * 82)
    ok = failed = 0
    for entry in BULLETINS:
        klass, year, exam, printed, lines = entry[:5]
        forced_total = entry[5] if len(entry) > 5 else None

        total_max = sum(b for _, _, b in lines)
        total = forced_total if forced_total is not None else sum(n for _, n, _ in lines)
        computed = round(total / total_max * 10, 2)
        gap = round(computed - printed, 2)
        flag = "OK" if abs(gap) <= 0.01 else "ÉCART"
        if flag == "OK":
            ok += 1
        else:
            failed += 1
        print(f"{klass:6} {year:10} {exam:15} {total:8} {total_max:9} "
              f"{computed:9.2f} {printed:9.2f}  {gap:+.2f} {flag}")

    print("-" * 82)
    print(f"{ok} bulletins conformes, {failed} en écart.")
    print()
    print("Aucun coefficient multiplicateur n'intervient : le barème EST le poids.")


if __name__ == "__main__":
    main()
