# Modèle extrait de l'Excel source

Source : `docs/modele-source.xlsx` — *BASE GESTION DAROU LOUQMANE 2025_2026_V0.xlsx*
(le fichier « BASE 1 » est strictement identique : 0 cellule de différence).

> **Le classeur est un gabarit vide (V0)** : structure et formules complètes, mais aucun
> élève, aucune dépense, aucun enseignant saisi. Aucune donnée historique n'est donc
> disponible pour la validation « zéro écart ». Voir [Stratégie de non-régression](#stratégie-de-non-régression).

---

## 1. Calendriers

Deux calendriers cohabitent et ne doivent pas être confondus.

| Calendrier | Période | Utilisé par |
|---|---|---|
| **Exercice financier** | octobre → **septembre** (12 mois) | `Salaires`, `DEPENSES`, `ENCAIS`, `Rapport Bilan` |
| **Année pédagogique** | octobre → **juin** (9 mois) | mensualités élèves (scolarité, cantine, renforcement, uniforme) |

Pour 2025/2026 : exercice = 31/10/2025 → 30/09/2026 ; mensualités = 31/10/2025 → 30/06/2026.
Chaque période est identifiée par sa **date de fin de mois** (`EOMONTH`), y compris dans `DEPENSES!B`
qui est une colonne calculée servant de clé de jointure pour les `SUMIFS` du bilan.

---

## 2. Onglets de classe (GARDERIE, PS, MS, GS, CI, CP, CE1, CE2, CM1, CM2)

Disposition identique sur les 10 onglets. Ligne 7 = en-têtes de période, ligne 8 = totaux,
élèves à partir de la ligne 9.

| Colonnes | Bloc | Contenu |
|---|---|---|
| C | — | N° d'ordre |
| D, E, F, G | Identité | Prénom, Nom, Classe, Date de naissance |
| H → L | **TOTAL INSCRIPTION** | Inscription payée, Montant inscription, Uniforme, Assurance, APE |
| M → U | **MENSUALITE** | 9 mois (oct → juin) |
| W → AE | **CANTINE** | 9 mois |
| AG → AO | **RENFORCE+** | 9 mois |
| AQ → AY | **UNIFORME** | 9 mois (uniforme acheté en cours d'année) |

Soit **4 postes récurrents mensuels** et **5 postes d'inscription** ponctuels.

## 3. ENCAIS — synthèse des encaissements

- Lignes 5–14 : inscription totale reçue par classe. Effectif `D` = `COUNTA` sur la colonne
  « Inscription payée » de l'onglet de classe ; montant `E` = report du total `I8`.
- Ligne 16 : total inscriptions.
- Lignes 17–26 : mensualité totale reçue par classe, mois par mois (report de `M8:U8`).
- Ligne 28 : total mensualités.
- Colonne `Q` : total annuel par ligne. Colonne `R` : chiffre d'affaires par classe = inscriptions + mensualités.

> Cantine, renforcement et uniforme mensuel **ne remontent pas** dans ENCAIS ni dans le bilan.
> Ils sont saisis dans les onglets de classe mais exclus du chiffre d'affaires.

## 4. Rapport Bilan

```
TOTAL RESSOURCE (l.16)  = TOTAL INSCRIPTION REÇUE (l.12, ← ENCAIS!16)
                        + TOTAL MENSUALITÉ REÇUE (l.13, ← ENCAIS!28)
                        + AUTRE PRODUIT (l.14, saisie libre)

TOTAL CHARGE (l.35)     = Σ des 17 rubriques (l.18 → l.34)
EBE (l.37)              = TOTAL RESSOURCE − TOTAL CHARGE
SOLDE CUMULE (l.39)     = cumul mois par mois de l'EBE
SOLDE DU COMPTE (l.42)  = dernier solde cumulé
```

Chaque rubrique de charge est un `SUMIFS(DEPENSES!H, DEPENSES!J = libellé, DEPENSES!B = mois)`,
c'est-à-dire **une agrégation par catégorie × mois**. Le libellé de la rubrique dans le bilan est
la clé de jointure — d'où la nécessité d'un référentiel `ExpenseCategory` en base plutôt que
d'un champ texte libre.

### Les 17 rubriques de charge

| # | Rubrique |
|---|---|
| 1 | ARRIERE SALAIRE PAYE |
| 2 | LOCATIONS DE BÂTIMENTS |
| 3 | SALAIRE |
| 4 | EAU EXPLOITATION - SEN'EAU |
| 5 | ELECTRICITÉ EXPLOITATION - SENELEC |
| 6 | FOURNITURES D'ENTRETIEN, DE BUREAU ET SCOLAIRE |
| 7 | AUTRE PETIT MATÉRIEL |
| 8 | MATÉRIELS ET ÉQUIPEMENTS PEDAGOGIQUE |
| 9 | TRAVAUX, ENTRETIEN ET RÉPARATIONS |
| 10 | TRANSPORTS FG |
| 11 | ASSURANCES |
| 12 | PUBLICITE, PUBLICATIONS, RELATIONS PUBLIQUES |
| 13 | CHARGES ADMINISTRATIVES - DOSSIERS DE REGULARISATION |
| 14 | **FRAIS BANCAIRES ET TRANSFERT** — cas particulier |
| 15 | FRAIS DE FORMATION DU PERSONNEL |
| 16 | FRAIS DE RÉCEPTIONS - RESTAURATION |
| 17 | *(ligne 17 libre)* |

**Cas particulier — rubrique 14.** Sa formule est
`SUMIFS(DEPENSES!$I:$I, DEPENSES!$B:$B, mois)` : elle somme la colonne **frais de transfert**
de *toutes* les dépenses du mois, sans filtrer par catégorie. Ce n'est donc pas une catégorie
de dépense mais un **agrégat transversal**. Modélisé comme tel : `transfer_fee` est un champ de
`Expense`, et la ligne de bilan est calculée, pas stockée.

## 5. Salaires

Grille `RUBRIQUE × mois` (12 mois, oct → sep), rubriques A / B / C (lignes 7–9, lignes 10–17 libres).
Ligne 19 `CHARGES DE PERSONNEL` = somme des rubriques. La ligne 4 conserve l'exercice N-1 pour comparaison.

C'est une ventilation **comptable**, sans lien avec l'employé nominatif. Le lien
rubrique ↔ enseignant n'existe pas dans l'Excel : c'est un ajout du cahier des charges
(bulletins de paie individuels).

## 6. Enseignants

État nominatif, 19 colonnes (`D:V`), ligne 7 = en-têtes. Deux colonnes calculées :
- `B` : nom complet = `Prénom & " " & Nom`
- `D` : matricule auto-incrémenté sur 3 chiffres — `TEXT(D8+1,"000")`, démarre à `001`

## 7. DEPENSES

`B` (calculée, `EOMONTH(C)`), `C` date opération, `D` date paiement, `E` canal, `F` n° facture,
`G` intitulé, `H` montant, `I` frais transfert, `J` items *(= catégorie, clé de jointure du bilan)*.

---

## Écarts volontaires avec l'Excel

Quatre bugs de formules ont été identifiés dans le classeur source. L'application implémente le
comportement **correct** ; ces écarts sont donc attendus et couverts par des tests dédiés.

### B1 — `ENCAIS!F21:M21` — mauvaise référence d'onglet · *critique*

La ligne « Mensualité totale reçue de CI » lit `CP!N8:U8` de novembre à juin ; seul octobre (`E21`)
lit correctement `CI!M8`. Conséquence : **les mensualités du CP sont comptées deux fois** et
**celles du CI sont perdues** sur 8 des 9 mois. Fausse le chiffre d'affaires par classe (ENCAIS!R),
le total mensualités (ENCAIS!28) et donc `TOTAL RESSOURCE`, l'EBE et le solde.

### B2 — Totaux de classe sur des plages incohérentes

En ligne 8 de chaque onglet de classe, les totaux d'inscription portent sur `9:41` (33 lignes)
mais les totaux de mensualité, cantine, renforcement et uniforme sur `9:29` (21 lignes).
Au-delà du 21ᵉ élève, **les mensualités cessent d'être totalisées** alors que l'inscription
continue de l'être. Silencieux et proportionnel à l'effectif.

### B3 — Septembre exclu des totaux annuels

`Rapport Bilan!Q12` = `SUM(E12:O12)` s'arrête à la colonne O (août) alors que l'exercice court
jusqu'à P (septembre). Affecte les lignes 12, 13 et 18 à 34 — donc `TOTAL RESSOURCE`, `TOTAL CHARGE`
et l'EBE annuels. Même erreur dans `Salaires!E7:E17` (`SUM(F7:P7)`, exclut la colonne Q).
Le solde cumulé (l.39), lui, va bien jusqu'à P : **`Q37` (EBE annuel) et `P39` (solde cumulé final)
ne sont pas réconciliables** dès qu'une écriture existe en septembre.

### B4 — Effectif conditionné au paiement

`ENCAIS!D5` = `COUNTA(GARDERIE!H9:H48)` compte la colonne « Inscription payée ». Un élève inscrit
n'ayant pas encore réglé son inscription n'apparaît pas dans l'effectif. L'application distingue
`effectif` (élèves de statut actif) de `nombre d'inscriptions réglées`.

*Autres anomalies mineures, sans effet sur les totaux : l'en-tête `Rapport Bilan!Q9` indique
« TOTAL 2425 » sur un rapport 2025/2026 (reliquat) ; `ENCAIS!E28` somme `E17:E27` en incluant la
ligne vide 27 ; le commentaire en `E51` est celui de l'exercice précédent.*

---

## Stratégie de non-régression

Le classeur étant vide, il n'existe pas de bilan historique à comparer. Le harnais
`backend/apps/reports/tests/test_excel_parity.py` procède donc ainsi :

1. un jeu de données déterministe est chargé en base **et** injecté dans une copie du classeur ;
2. la copie est recalculée par LibreOffice en mode headless ;
3. chaque cellule de `ENCAIS` et `Rapport Bilan` est comparée à la sortie de l'API ;
4. les écarts attendus (B1 à B4) sont déclarés explicitement — tout autre écart fait échouer le test.

Le jour où un classeur réellement renseigné sera fourni, il suffira de le substituer à l'étape 1
pour obtenir la validation sur données réelles exigée par le cahier des charges.
