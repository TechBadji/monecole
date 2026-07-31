# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Personnel d'établissements scolaires privés sénégalais — préscolaire et primaire.

- **Administrateur / directeur** — inscrit les élèves, fixe les tarifs, arrête le
  bilan, décide des bourses. C'est lui qui achète le produit.
- **Comptable / trésorier** — encaisse les mensualités au guichet, souvent avec
  un parent debout devant lui. La cible du cahier des charges est moins de
  30 secondes par encaissement.
- **Secrétaire** — saisit les élèves, imprime les listes et les cartes.
- **Enseignant** — saisit les notes de composition pour ses classes.
- **Parent** — consulte la situation financière de ses enfants et leurs
  bulletins. Il n'accède qu'à ses propres enfants.

Le matériel est modeste et la connexion coupe. Une part importante des usages se
fait au téléphone.

## Product Purpose

Remplacer le classeur Excel de gestion d'une école par une application
multi-établissements. Le succès se mesure à l'écart : zéro divergence entre les
états produits et ceux que l'école tirait de son classeur, et un bilan calculé en
moins de cinq secondes pour 500 élèves.

## Positioning

Le produit est modelé sur le classeur réel d'une école sénégalaise, pas sur un
progiciel scolaire générique. Il en reprend les deux calendriers — exercice
financier d'octobre à septembre sur douze mois, année pédagogique d'octobre à
juin sur neuf — que confondre fausse tous les agrégats. Il corrige quatre erreurs
de formules du classeur d'origine, documentées dans `docs/modele-excel.md`.

Les montants sont en francs CFA, entiers : le XOF n'a pas de décimales.

## Operating Context

- Rentrée en octobre ; les encaissements s'échelonnent sur neuf mensualités.
- Le guichet est un moment de file d'attente. La saisie groupée d'une classe
  entière en une requête est ce qui tient la cible de 30 secondes.
- Coupures de courant et de réseau courantes : l'application fonctionne hors
  ligne et rejoue ses écritures au retour du réseau.
- Paiement par Wave (mobile money) et en espèces.
- Notifications aux parents par SMS via LAfricaMobile.
- Une badgeuse murale à l'entrée de l'école scannera les cartes élèves via
  l'API. L'équipementier n'est pas choisi ; le contrat est dans
  `docs/badgeuse-api.md`.

## Capabilities and Constraints

- Multi-tenant : base et schéma partagés, cloisonnement par `TenantScopedModel`
  et un gestionnaire à contexte. Aucun accès inter-établissements.
- Rôles et matrice de permissions ; journal d'audit sur toute opération
  financière.
- Matricule élève au format `MXXXX`, propre à une école, conservé pour tout le
  cursus.
- Bourse sociale de X %, répercutée sur les mensualités, les états financiers et
  le tableau de bord.
- Bulletins scolaires et bulletins de paie en PDF ; paie au modèle sénégalais
  (IPRES, CSS, TRIMF, IR progressif à parts familiales).
- **Aucun serveur de messagerie n'est configuré.** La réinitialisation de mot de
  passe par email, décidée par le client, exige un SMTP et un domaine expéditeur
  avec SPF/DKIM avant toute mise en production.
- Les barèmes de paie n'ont pas été validés par un comptable.

## Brand Commitments

Nom : **MonÉcole**. Interface intégralement en français.

L'établissement pilote est le Groupe Scolaire Darou Louqmane ; son nom et son
classeur figurent dans un dépôt public, par choix explicite du client.

## Evidence on Hand

- `docs/modele-source.xlsx` — le classeur réel de l'école, gabarit sans données.
- `docs/modele-excel.md` — le modèle comptable et les quatre erreurs corrigées.
- Jeu de démonstration : 180 élèves, exercice 2025/2026.

Ce qui n'existe pas et ne doit pas être inventé : clients autres que l'école
pilote, tarifs d'abonnement, chiffres d'usage, témoignages, certifications,
mentions de conformité réglementaire.

## Product Principles

1. **Le classeur fait foi.** Toute divergence avec les états que l'école tirait
   de son Excel est un défaut, sauf les quatre bugs corrigés et documentés.
2. **Le guichet commande.** Une fonction qui rallonge un encaissement a échoué,
   quelle que soit sa justesse par ailleurs.
3. **Le réseau va tomber.** Aucun geste métier ne dépend d'une connexion.
4. **Le cloisonnement n'est pas négociable.** Aucune donnée ne franchit la
   frontière d'un établissement, et un parent ne voit que ses enfants.
5. **Toute opération financière laisse une trace.** Le journal d'audit est une
   contrainte de conception, pas une option.

## Accessibility & Inclusion

Français uniquement. Interface lisible sur téléphone d'entrée de gamme et sur
connexion lente. Contraste tenu sur les fonds marine du produit.
