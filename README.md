# MonÉcole

SaaS multi-tenant de gestion d'établissement scolaire — préscolaire et primaire.
Remplace le classeur Excel de gestion administrative et financière d'un groupe
scolaire par une application web multi-utilisateur, avec états financiers calculés
en temps réel.

**Contexte** : Sénégal, devise XOF (FCFA), exercice d'octobre à septembre.

---

## Démarrage

Prérequis : Python 3.13, PostgreSQL 14+, Node 20+.

```bash
# Base de données
psql -d postgres -c "CREATE ROLE monecole LOGIN PASSWORD 'monecole' CREATEDB;"
psql -d postgres -c "CREATE DATABASE monecole OWNER monecole;"

# Backend
cd backend
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo        # jeu de démonstration
.venv/bin/python manage.py runserver

# Frontend (autre terminal)
cd frontend
npm install && npm run dev
```

> Le backend écoute sur le port 8000 par défaut. Si ce port est déjà pris sur votre
> machine — c'est le cas ici, un autre projet Django l'occupe — lancez
> `manage.py runserver 8001` et pointez le frontend dessus via
> `frontend/.env` : `VITE_API_URL=http://localhost:8001/api`.

- Application : http://localhost:5173
- API : http://localhost:8000/api/
- Documentation API : http://localhost:8000/api/docs/
- Admin Django : http://localhost:8000/admin/

### Comptes de démonstration

Mot de passe commun : `MonEcole2026!`

| Compte | Rôle |
|---|---|
| `admin@darou-louqmane.sn` | Administrateur d'établissement |
| `comptable@darou-louqmane.sn` | Comptable |
| `secretaire@darou-louqmane.sn` | Secrétaire |
| `super@monecole.sn` | Super administrateur |

---

## Architecture

```
monecole/
├── backend/                  Django 5.2 LTS + DRF + PostgreSQL
│   ├── config/               settings, urls, wsgi/asgi
│   └── apps/
│       ├── core/             School (tenant), SchoolYear, User, rôles, audit, tenancy
│       ├── students/         classes, familles, élèves, inscriptions, encaissements
│       ├── staff/            enseignants, contrats, rubriques salariales, paie
│       ├── finance/          rubriques de charge, dépenses, autres produits
│       └── reports/          ENCAIS, Rapport Bilan, exports PDF/Excel
│       ├── notifications/    SMS LaFricaMobile, codes de connexion, rappels
│       └── payments/         Wave Checkout, webhook, espèces, reçus
├── frontend/                 React 18 + TypeScript + Vite (PWA)
│   └── src/offline/          file IndexedDB, synchronisation, cache horodaté
└── docs/
    ├── modele-excel.md       modèle extrait du classeur + écarts documentés
    └── modele-source.xlsx    classeur d'origine
```

**Stack** : Django 5.2 LTS (et non 5.0 : l'environnement est en Python 3.13),
DRF, SimpleJWT, django-filter, drf-spectacular, PostgreSQL, openpyxl, ReportLab.

---

## Isolation multi-tenant

Stratégie : *shared database, shared schema* — une colonne `school_id` sur chaque
table métier, avec filtrage automatique.

Le filtrage n'est pas laissé à la discrétion de l'appelant. Tout modèle héritant de
`TenantScopedModel` expose un manager qui applique le filtre à partir du tenant
courant, posé par le middleware depuis **l'utilisateur en base** — jamais depuis un
en-tête, un paramètre d'URL ou un sous-domaine fourni par le client. Une vue qui
oublierait de filtrer ne fuite donc pas : elle ne voit rien.

```python
Student.objects.all()             # filtré sur l'établissement courant
Student.objects.all_tenants()     # échappatoire explicite, repérable en revue
with tenant_context(school): ...  # impose un tenant (commandes, imports, tests)
```

L'écriture est protégée symétriquement : enregistrer un objet rattaché à un autre
établissement que celui du contexte lève une `PermissionError`.

> **Piège à connaître.** Ne jamais écrire `queryset = Model.objects...` sur une vue
> tenant : l'attribut de classe est évalué à l'import du module, sans tenant en
> contexte, et le `.none()` alors produit reste figé pour toute la durée du
> processus. Déclarer `model = Model` à la place — le queryset est reconstruit à
> chaque requête. Le test `test_every_list_endpoint_returns_its_data` verrouille ce
> comportement.

---

## Modèle de données

Le modèle est dérivé du classeur source, dont la structure est documentée dans
[`docs/modele-excel.md`](docs/modele-excel.md).

Deux calendriers cohabitent et ne doivent pas être confondus :

| Calendrier | Période | Porte |
|---|---|---|
| Exercice financier | octobre → **septembre** (12 mois) | dépenses, salaires, bilan |
| Année pédagogique | octobre → **juin** (9 mois) | mensualités des élèves |

Les périodes sont identifiées par leur **fin de mois**, reprenant la convention
`EOMONTH` du classeur, qui sert de clé de jointure aux agrégations du bilan.

Les montants sont des **entiers** : le franc CFA n'a pas de subdivision décimale, et
l'entier écarte toute dérive d'arrondi sur les agrégats.

### Ajouts par rapport au classeur

- **`FeeSchedule`** — le classeur n'enregistre que les sommes *reçues*, ce qui ne
  permet pas de distinguer un paiement partiel d'un paiement complet. Cette grille
  tarifaire fournit le montant *dû*, sans lequel arriérés, échéanciers et relances
  ne sont pas calculables.
- **`Discount`**, **`Family`** — réductions traçables et regroupement de fratrie.
- **`AuditLog`** — journal immuable des opérations financières.
- **`Subscription`** — abonnement SaaS de l'école à la plateforme, distinct de sa
  gestion financière interne.

---

## Écarts assumés avec le classeur

Quatre bugs de formules ont été identifiés dans le classeur source. L'application
implémente le comportement **correct** ; ces écarts sont attendus et chacun est
couvert par un test dédié dans `apps/reports/tests/test_services.py`.

| # | Bug du classeur | Effet | Correction |
|---|---|---|---|
| **B1** | `ENCAIS!F21:M21` lit `CP!` sur la ligne du CI, de novembre à juin | Mensualités du CP comptées deux fois, celles du CI perdues | Chaque classe n'agrège que ses propres élèves |
| **B2** | Totaux d'inscription sur 33 lignes, de mensualité sur 21 | Au-delà de 21 élèves, les mensualités cessent d'être totalisées | Les totaux portent sur tous les élèves |
| **B3** | `SUM(E12:O12)` s'arrête en août | Septembre exclu de tous les totaux annuels ; EBE et solde cumulé irréconciliables | Les 12 mois de l'exercice sont couverts |
| **B4** | Effectif = `COUNTA` sur « Inscription payée » | Un élève inscrit mais non à jour disparaît des effectifs | Effectif et inscriptions réglées sont deux mesures distinctes |

Détail complet et anomalies mineures : [`docs/modele-excel.md`](docs/modele-excel.md).

### Sur la validation « zéro écart »

Le cahier des charges demande un bilan généré identique au bilan Excel historique.
**Le classeur fourni est un gabarit vide** (V0) : structure et formules complètes,
mais aucune donnée. Il n'existe donc aujourd'hui aucun bilan historique auquel se
comparer. Le jour où un classeur réellement renseigné sera disponible, il pourra
être substitué au jeu de données de test pour obtenir cette validation.

---

## Tests

```bash
cd backend && .venv/bin/python manage.py test
```

253 tests, répartis ainsi :

| Fichier | Objet |
|---|---|
| `core/tests/test_tenancy.py` | Isolation multi-tenant : ORM, écriture, API, agrégats |
| `core/tests/test_permissions.py` | Matrice de rôles, séparation des tâches, validation des dépenses |
| `core/tests/test_audit.py` | Immuabilité du journal, traçabilité, exports |
| `core/tests/test_api_contract.py` | Garde-fous d'API, séquence des matricules |
| `reports/tests/test_services.py` | Calculs financiers et régressions B1 à B4 |
| `reports/tests/test_performance.py` | Bilan de 500 élèves sous 5 secondes |
| `notifications/tests/test_portal.py` | Codes SMS, énumération, cloisonnement du portail parent |
| `payments/tests/test_payments.py` | Signature Wave, rejeu, idempotence, espèces |
| `core/tests/test_imports.py` | Analyse CSV, pré-contrôle, atomicité |
| `staff/tests/test_payroll.py` | Barème sénégalais vérifié à la main, bulletins |

Les calculs financiers sont vérifiés contre des valeurs posées à la main dans le
test, et non contre une seconde implémentation du même calcul — sinon une erreur de
raisonnement serait reproduite des deux côtés et le test la validerait.

### Critères d'acceptation

| Critère | État |
|---|---|
| Un paiement partiel se distingue d'un paiement complet | ✅ `test_student_ledger_reports_partial_payment` |
| Aucun accès croisé entre établissements par URL ou API | ✅ `TenantAPIIsolationTests` (7 tests) |
| Bilan de 500 élèves sous 5 s | ✅ mesuré à **16 ms** pour 180 élèves, **< 1 s** pour 500 |
| Toute opération financière tracée avec son auteur | ✅ `FinancialAuditTrailTests` |
| Bilan identique au bilan Excel historique | ⏸ classeur source vide — voir ci-dessus |

---

## API

Documentation interactive : `/api/docs/` (OpenAPI 3, générée par drf-spectacular).

```
POST /api/auth/login/                    authentification, retourne le profil
GET  /api/auth/me/                       profil et permissions effectives

GET  /api/students/{id}/ledger/          situation financière : dû, réglé, retard
GET  /api/monthly-payments/register/     grille d'encaissement d'une classe
POST /api/monthly-payments/bulk/         saisie groupée, transactionnelle
GET  /api/monthly-payments/arrears/      élèves en retard de paiement
POST /api/expenses/{id}/approve/         validation d'une dépense
GET  /api/salaries/grid/                 grille rubriques × mois
GET  /api/reports/{bilan|encais|dashboard|comparison|cash-forecast}/
GET  /api/exports/{bilan|encais|students}.{xlsx|pdf}
```

Tous les états acceptent `?year=<id>` ; à défaut, l'année courante est utilisée.

### Rôles

| Rôle | Périmètre |
|---|---|
| Super administrateur | Écoles clientes et abonnements. **Aucun accès** aux finances d'une école. |
| Administrateur | Contrôle complet de son établissement. Seul à pouvoir valider une dépense. |
| Comptable | Encaissements, dépenses, salaires, états. Ne crée ni ne supprime d'élève. |
| Secrétaire | Élèves, inscriptions, personnel. Lecture seule sur les finances. |
| Enseignant / Parent | Lecture seule, périmètre restreint. |

La matrice est déclarée dans `apps/core/permissions.py` — versionnée et testée
plutôt que stockée en base, pour qu'une élévation de privilège ne puisse pas
résulter d'une simple écriture de données.

---

## Sécurité

- JWT (30 min) + refresh rotatif (7 j), limitation de débit sur la connexion.
- Isolation tenant vérifiée par tests d'accès croisé automatisés.
- Journal d'audit immuable : `save()` sur une entrée existante et `delete()` lèvent
  une `PermissionError`. L'identité de l'auteur y est figée avec son email, pour
  rester exploitable après suppression du compte.
- Le CNI et les mots de passe ne sont jamais recopiés dans le journal.
- Séparation des tâches : au-delà de 500 000 XOF, une dépense saisie par le
  comptable requiert la validation d'un administrateur, et n'entre au bilan
  qu'une fois validée.
- En production : HSTS, cookies sécurisés, redirection SSL.

---

## Intégrations

### SMS — LaFricaMobile (LAMPUSH)

Client transposé de `lib/sms.ts` du projet **gynaeasy**, dont la logique est
conservée : normalisation des numéros sénégalais en `221XXXXXXXXX`, tolérance aux
deux formes de réponse de LAM (JSON ou identifiant brut), et **mode simulation**
quand les identifiants manquent — l'application reste utilisable de bout en bout
sans consommer de crédit.

```bash
LAM_ACCESS_KEY=…        # vide = simulation
LAM_ACCESS_PASSWORD=…
LAM_SENDER_ID=MonEcole
```

Tout envoi est consigné dans la boîte d'envoi (`/api/notifications/outbox/`),
**succès comme échec** : sans cette trace, impossible de répondre à un parent qui
affirme n'avoir jamais été relancé.

> Les messages sont tenus sous 160 caractères. Au-delà, l'opérateur découpe et
> facture chaque segment — vingt caractères de trop doublent le coût d'une campagne
> de 400 parents.

### Rappels de paiement

```bash
python manage.py send_reminders --dry-run              # prévisualisation
python manage.py send_reminders --min-amount 20000     # envoi réel
```

Idempotent à la journée : une campagne déjà passée n'est pas rejouée. Un `cron` qui
double, un redémarrage ou un clic de trop ne coûtent pas un second SMS à chaque
parent. `--dry-run` est le mode par défaut de l'endpoint `/api/reminders/arrears/`.

### Paiements — Wave et espèces

`PaymentTransaction` est distincte de `MonthlyPayment` : une transaction peut être
ouverte, abandonnée ou échouée sans jamais produire d'écriture comptable. Confondre
les deux ferait apparaître au bilan des paiements jamais reçus.

- **Wave** : session Checkout, puis confirmation par webhook signé. La signature
  HMAC est **obligatoire** — sans `WAVE_WEBHOOK_SECRET`, le webhook est refusé
  plutôt qu'accepté par défaut. Fenêtre de tolérance de 5 minutes sur l'horodatage,
  pour qu'une signature capturée ne reste pas rejouable.
- **Espèces** : confirmé immédiatement au guichet, réservé au comptable et à
  l'administrateur.
- Reçu PDF au format A5 (deux par feuille A4). Une transaction simulée produit un
  reçu portant la mention « DOCUMENT DE TEST ».

Un règlement en plusieurs versements **s'ajoute** au montant déjà encaissé.

---

## Portail parent

Authentification par **numéro de téléphone et code SMS à 6 chiffres**, valable
10 minutes. Aucun mot de passe : le numéro figure déjà dans la fiche de l'élève.

Le code n'est pas stocké en clair — seule une empreinte SHA-256 liant le code au
numéro l'est. Un code intercepté ne vaut donc que pour la ligne qui l'a reçu, et
une fuite de la table ne permet pas de se connecter.

Le compte parent est créé au premier accès réussi : aucun provisionnement manuel.
Le périmètre visible découle du numéro rapproché des fiches élèves — jamais d'un
identifiant fourni par le client.

**Points durcis, chacun couvert par un test :**

| Risque | Traitement |
|---|---|
| Énumération des parents d'une école | La demande de code répond la même chose pour un numéro connu et inconnu |
| Force brute sur le code | Verrouillage après 5 tentatives, 5 demandes par heure et par IP |
| Code réutilisé | Usage unique ; une nouvelle demande invalide la précédente |
| Même numéro dans deux écoles | Le rattachement est par établissement, pas par numéro seul |
| Accès à l'administration | Bilan, dépenses, paie, bulletins : tous en 403 |

---

## Import CSV de migration

Deux principes, tous deux testés :

1. **Pré-contrôle systématique.** `dry_run` est le défaut, et un paramètre absent
   ou mal orthographié ne déclenche jamais d'écriture. Le rapport situe chaque
   erreur à son numéro de ligne *tel qu'il apparaît dans Excel*.
2. **Tout ou rien.** Une seule ligne en erreur et rien n'est appliqué. Un import à
   moitié passé laisse la base dans un état pire que le point de départ.

Les fichiers réels sortent d'Excel : l'encodage (UTF-8, BOM, Windows-1252,
Latin-1) et le séparateur (`;` ou `,`) sont détectés. Les montants sont lus dans
toutes leurs formes — `15 000`, `15.000`, `15 000,00`, `15 000 FCFA`.

> Le franc CFA n'ayant pas de décimale, un point suivi de trois chiffres est
> nécessairement un séparateur de milliers : `15.000` vaut quinze mille, pas quinze.

---

## Bulletins de paie — schéma sénégalais

```
Brut imposable
  − IPRES régime général (5,6 %, assiette plafonnée à 432 000)
  − IPRES cadres         (2,4 %, plafond 1 296 000)     si cadre
= Brut après cotisations
  − abattement frais professionnels (30 %, plafonné à 900 000 / an)
= Net imposable
  − IR au barème progressif annuel (0 / 20 / 30 / 35 / 37 / 40 %)
    − réduction pour charges de famille (1 à 5 parts, plancher et plafond)
  − TRIMF (forfait annuel par tranche)
= Net à payer  (+ indemnités non imposables)

Charges patronales : IPRES 8,4 % (+ 3,6 % cadres), CSS 7 % + AT 1 % (plafond 63 000)
```

**Les barèmes sont stockés en base (`PayrollScale`), datés et modifiables sans
redéploiement** — IPRES, CSS, IR et TRIMF relèvent de la loi de finances. Conserver
l'historique permet de recalculer un bulletin de l'exercice précédent à l'identique.

> ⚠️ Les valeurs livrées sont des **valeurs par défaut non validées**. Tant que
> `validated_by` est vide, l'API le signale, l'interface affiche un avertissement et
> le PDF porte la mention « non validé par un expert-comptable ». Faites vérifier
> les taux avant de remettre des bulletins réels.

Le détail du calcul est figé sur le bulletin à l'émission : un document remis à un
employé reste reproductible même si le salaire ou le barème changent ensuite.

---

## Graphiques et thème

Les graphiques sont écrits en **SVG natif**, sans bibliothèque. Recharts pesait
114 Ko compressés pour deux formes élémentaires — hors de proportion sur un produit
destiné à des réseaux mobiles. Le module complet en fait 2,8 Ko.

Le palette catégoriel est le palette de référence validé : chaque paire adjacente
tient ΔE ≥ 8 en vision déficiente et ≥ 15 en vision normale, dans les deux modes.
Il a été **vérifié par script**, pas à l'œil.

Trois choix qui ne sont pas affaire de goût :

- **Deux graphiques plutôt qu'un** pour les flux mensuels et le solde cumulé. Les
  flux tournent autour de 2 M, le cumul grimpe vers 6 M ; les superposer écraserait
  les premiers au bas du cadre. Deux échelles sur un même graphique ne sont jamais
  la réponse.
- **Une seule teinte** pour le classement des dépenses. Colorer chaque barre
  différemment ferait porter à la couleur un *rang*, alors qu'elle doit désigner une
  *entité*.
- **Légende et libellé direct** sur les séries multiples : l'identité ne repose
  jamais sur la couleur seule. Une vue tableau est accessible sur chaque graphique.

L'application est **bi-mode** (clair, sombre, ou suivi du système). Les valeurs
sombres ne sont pas un inversement automatique : ce sont les mêmes teintes recalées
sur la surface sombre, et validées comme telles.

### Poids du chargement

| | Avant | Après |
|---|---|---|
| Chargement initial | 690 Ko (201 Ko gz) | **250 Ko (81 Ko gz)** |
| Écran supplémentaire | — | 2 à 8 Ko |
| Tableau de bord complet | 690 Ko | **261 Ko (85 Ko gz)** |

Les écrans sont chargés à la demande ; React et le routeur sont isolés dans leurs
propres fragments, pour qu'une mise à jour applicative n'invalide pas leur cache.

---

## Mode hors ligne (PWA)

Conçu pour les coupures de réseau, fréquentes en usage réel.

| Magasin | Rôle |
|---|---|
| `queue` (IndexedDB) | Écritures faites hors ligne. **Donnée irremplaçable** — elle n'existe nulle part ailleurs. |
| `cache` (IndexedDB) | Copies de lecture **horodatées**. Reconstructibles, mais la fraîcheur doit être affichée. |
| Service worker | Coquille applicative seulement (HTML, JS, CSS). |

**Le service worker n'intercepte jamais `/api/`.** S'il mettait les réponses de
l'API en cache, il les servirait comme des réponses normales et l'interface ne
saurait pas qu'elles sont périmées — exactement le piège à éviter sur des données
financières.

Synchronisation à la reconnexion : séquentielle (l'ordre d'arrivée est préservé),
verrouillée (un seul passage à la fois), et distinguant l'erreur métier de l'erreur
réseau. Un 4xx est définitif — l'entrée est signalée pour intervention humaine
plutôt que rejouée en boucle. Chaque écriture porte un `X-Client-Mutation-Id`, ce
qui rend le rejeu sûr après une coupure survenue *pendant* l'envoi.

Couverture hors ligne : saisie des encaissements, saisie des dépenses, consultation
des élèves et des états financiers. **Toute donnée issue du cache porte un bandeau
daté** — sur les états financiers, avec date et heure précises : « il y a 3 h » est
trop vague pour décider si un chiffre est exploitable.

---

## Reste à faire

Non couvert par cette itération, par ordre de priorité :

1. **Portail parent** et notifications SMS/email (modèle `Notification` en place,
   sans intégration d'agrégateur). À valider auprès des écoles cibles avant
   d'investir — c'est une hypothèse du cahier des charges, pas un besoin exprimé.
2. **Import CSV/Excel** pour la migration des données existantes.
3. **Mobile money** (Wave, Orange Money) pour le règlement des mensualités.
4. **Bulletins de paie PDF** individuels — la structure `SalaryRubric ↔ Teacher`
   est prête, le rendu reste à écrire.
5. **Mode hors ligne / PWA** pour la saisie des encaissements.
6. **Row-Level Security PostgreSQL** en défense supplémentaire de l'isolation
   applicative.
