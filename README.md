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
├── frontend/                 React 18 + TypeScript + Vite
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

82 tests, répartis ainsi :

| Fichier | Objet |
|---|---|
| `core/tests/test_tenancy.py` | Isolation multi-tenant : ORM, écriture, API, agrégats |
| `core/tests/test_permissions.py` | Matrice de rôles, séparation des tâches, validation des dépenses |
| `core/tests/test_audit.py` | Immuabilité du journal, traçabilité, exports |
| `core/tests/test_api_contract.py` | Garde-fous d'API, séquence des matricules |
| `reports/tests/test_services.py` | Calculs financiers et régressions B1 à B4 |
| `reports/tests/test_performance.py` | Bilan de 500 élèves sous 5 secondes |

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
