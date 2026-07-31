# Notation : matières, barèmes et calcul de la moyenne

Établi à partir de **vingt bulletins réels** du Groupe Scolaire Keur Mame
Nafissa — six niveaux, années 2022-2023 à 2025-2026. Chaque bulletin a été
rejoué : la moyenne calculée retrouve la moyenne imprimée au centième, sur les
vingt.

## Ce que les bulletins établissent

### Le barème est le poids

Il n'y a **aucun coefficient multiplicateur**. Chaque matière a un barème — son
« sur » — et la moyenne vaut :

```
moyenne = (somme des notes ÷ somme des barèmes) × 10
```

Une matière notée sur 20 pèse cinq fois une matière notée sur 4, simplement
parce qu'elle apporte cinq fois plus de points au numérateur comme au
dénominateur. C'est ce que montrent les bulletins récents, qui affichent
explicitement deux colonnes : `NOTES` et `/ SUR`.

Les bulletins plus anciens affichent une colonne « Crédits ». Elle ne porte
aucune information : c'est le barème multiplié par un facteur choisi pour que
le total tombe rond (0,20 · 0,30 · 0,40 · 0,50 · 1,00 selon l'épreuve). Elle
n'a pas été reprise.

### La moyenne est sur 10

Et non sur 20. Deux conséquences dans le code :

- les seuils de mention sont ceux de l'échelle sur 20, divisés par deux
  (8 · 7 · 6 · 5) ;
- le seuil de passage est 5.

Conserver les seuils sur 20 aurait classé un établissement entier
« Insuffisant » sans que rien ne le signale.

### Le barème varie d'une épreuve à l'autre

C'est le constat le plus contraignant. Au CE2, dans la même année :

| Matière | C1 | C2 | C3 | Compo 1 | Compo 2 | Compo 3 |
|---|---|---|---|---|---|---|
| Conjugaison | 4 | 4 | 8 | 10 | 4 | 12 |
| Compétence maths | 20 | 20 | 10 | 20 | 10 | 20 |
| TSQ | 10 | 4 | 6 | — | 4 | 8 |
| Vocabulaire | 3 | 4 | 8 | 8 | 3 | 8 |

La proportion de matières à barème variable va de 15 % (CM1) à 50 % (CP). La
liste des matières varie elle aussi : l'anglais est absent de la 3ᵉ composition
du CE2, la récitation du 3ᵉ contrôle du CM2.

Un barème fixe par classe ne pouvait donc pas reproduire ces bulletins. Le
modèle retenu : **un barème de référence porté par la classe, que
l'administration ajuste à la création de chaque composition.**

## Le modèle dans le code

| Champ | Rôle |
|---|---|
| `Subject.default_max_score` | Amorce du catalogue. Ne sert qu'à la création. |
| `ClassSubject.max_score` | **Barème de référence de la classe.** C'est le poids. |
| `GradeSheet.max_score` | Barème de l'épreuve. Vide = celui de la classe. |
| `Grade.value` | Note **sur le barème de la feuille**, pas sur 20. |

`GradeSheet.effective_max_score` résout la cascade. `Grade.clean()` refuse une
note supérieure au barème : une borne fixe à 20 n'aurait rien attrapé sur une
matière notée sur 4.

## Le catalogue

`backend/apps/academics/catalogue.py` — 32 matières, six niveaux. Le barème de
référence est la **médiane** des valeurs observées : la valeur la plus fréquente
donnait un total de 233 au CP là où les épreuves réelles pèsent 170 à 200, un
contrôle où tout valait 10 la tirant vers le haut.

| Niveau | Matières | Barème de référence | Épreuves réelles |
|---|---|---|---|
| CI | 23 | 170 | 170 |
| CP | 27 | 198 | 170 – 200 |
| CE1 | 24 | 181 | 160 – 180 |
| CE2 | 29 | 219 | 180 – 200 |
| CM1 | 21 | 298 | 300 |
| CM2 | 20 | 286 | 290 – 300 |

Le total de référence peut dépasser celui d'une épreuve : **aucune épreuve ne
convoque toutes les matières à la fois.** C'est attendu.

### Intitulés unifiés

L'école écrit indifféremment « Compétences DM » et « Compétence DM »,
« Activités de Mesure » et « Activités de Mesures », « Résolution de Problème »
et « Résolution de Problèmes ». Une coquille figure même sur deux bulletins :
« IDENTIFCATION DE MOTS ».

Ces variantes ont été ramenées à un intitulé unique. Deux libellés pour une
matière, ce sont deux lignes au bulletin et un total faux.

## Mise en service

Depuis « Matières et barèmes », choisir la classe puis **Appliquer le catalogue
du niveau**. Les matières déjà rattachées ne sont pas retouchées : une école qui
a ajusté un barème ne le voit pas écrasé.

Le rapprochement classe → niveau se fait sur le préfixe du nom : « CE2B » et
« CE2 A » relèvent du CE2. Un niveau non répertorié — le préscolaire — est
refusé avec un message explicite plutôt que configuré au hasard.

## Ce qui reste à vérifier avec l'école

- **Le préscolaire ne compose pas** dans le modèle actuel. Aucun bulletin de
  petite, moyenne ou grande section n'a été fourni ; rien n'a été inventé.
- **Les barèmes de référence sont des médianes**, pas une règle communiquée par
  l'école. Si un barème officiel existe par niveau, il prime.
- **La moyenne générale** combine moyenne des contrôles et moyenne des
  compositions (bulletins CE2 2025-2026 : 9,42 et 9,54 → 9,48, soit la moyenne
  arithmétique des deux). La pondération exacte n'a pas été confirmée et n'est
  pas encore implémentée.
