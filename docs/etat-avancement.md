# État d'avancement

Arrêté au 4 août 2026, commit `f7d90ab`.

Ce document dit ce qui est **fait et vérifié**, ce qui est **fait mais non
validé par l'école**, et ce qui **bloque une mise en service**. Il ne dit pas ce
qui est prévu : une feuille de route se périme, un état des lieux se relit.

---

## En un coup d'œil

| | |
|---|---|
| Backend | Django 5.2 · DRF · PostgreSQL — 17 300 lignes, 9 applications |
| Frontend | React 19 · TypeScript · Vite — 9 200 lignes, 20 écrans |
| Tests | **306**, tous au vert |
| Routes | 20/20 rendues en session, 2/2 hors session |
| Dépôt | `TechBadji/monecole`, **public** |

---

## Ce qui fonctionne et qui est éprouvé

### Scolarité
- Élèves, classes, familles, inscriptions. Matricule `MXXXX` propre à
  l'établissement, conservé sur tout le cursus.
- **Plusieurs classes par niveau** — CI-A, CI-B, CI-C — créées depuis
  Paramètres, rangées dans l'ordre pédagogique.
- Situation financière d'un élève, année courante et années passées, dépliée
  sous sa ligne.

### Encaissements
- Saisie d'une classe entière en une requête, montants pré-remplis.
- Bourse sociale en pourcentage, répercutée sur les mensualités, les états
  financiers et le tableau de bord.
- Trop-perçu affiché comme tel, et non ramené à un solde nul.
- Arriérés calculés sur les mois échus, après réductions.

### Notes et bulletins
- **Le barème fait le poids**, la moyenne est sur 10. Règle établie en rejouant
  vingt bulletins papier réels : tous retrouvent la moyenne imprimée au
  centième. Voir [bareme-gsk.md](bareme-gsk.md).
- Catalogue de 32 matières, six niveaux, applicable à une classe en un clic.
- Barème ajustable par épreuve — indispensable, la même matière passant de 4 à
  12 dans l'année.
- Une absence retire son barème du dénominateur ; elle n'est jamais un zéro.
- Bulletins PDF, à l'unité ou pour la classe, en-tête paramétrable.

### Finances
- Deux calendriers distincts : exercice d'octobre à septembre, année
  pédagogique d'octobre à juin.
- Dépenses, rapport bilan, synthèse des encaissements.
- Paie au modèle sénégalais : IPRES, CSS, TRIMF, IR progressif à parts
  familiales.

### Comptes et sécurité
- Cloisonnement multi-établissements porté par le modèle, pas par les écrans.
- Rôles et matrice de permissions, appliqués par le serveur à chaque appel.
- Journal d'audit immuable sur toute opération financière.
- Réinitialisation de mot de passe par courrier : jeton haché, deux heures,
  usage unique, réponses indiscernables qu'une adresse existe ou non.
- Sessions listées et révocables, y compris après renouvellement du jeton.
- Affichage en clair sur tous les champs de mot de passe, par un composant
  unique.

### Terrain
- Fonctionnement hors ligne : saisies mises en file, rejouées au retour du
  réseau, données horodatées à l'écran.
- SMS aux parents via LAfricaMobile.
- Paiement Wave, webhooks signés.
- QR par élève, planches imprimables au format carte bancaire.
- Portail parent, restreint aux enfants du numéro appelant.

### Outillage
- [tools/audit-routes.mjs](../tools/audit-routes.mjs) parcourt toutes les
  routes dans un navigateur réel et sort en code 1 sur écran vide. Écrit après
  qu'un écran blanc soit passé alors que compilation et tests étaient au vert.
- `manage.py test_email` éprouve la configuration SMTP de bout en bout.
- `manage.py seed_demo --reset` : 180 élèves, une année complète.

---

## Ce qui bloque une mise en service

| Point | Conséquence si ignoré |
|---|---|
| **`PUBLIC_BASE_URL` non renseignée** | Les liens de réinitialisation envoyés aux écoles pointent vers `localhost`. |
| **Compte Gmail personnel et partagé** | `techbadji@gmail.com` sert aussi au projet `pyexam` : révoquer le mot de passe d'application pour l'un coupe l'autre. Les écoles reçoivent leurs courriers d'une adresse personnelle, et le mot de passe d'application ouvre la boîte entière. Voir [messagerie.md](messagerie.md). |
| **Barèmes de paie non validés** | Les bulletins de salaire n'ont été relus par aucun comptable. Une erreur de taux se paie en redressement. |
| **Données nominatives sur dépôt public** | Le classeur du client, le nom de l'établissement, et le nom et les notes d'une enfant mineure dans `test_catalogue.py:139`. Choix assumé pour les deux premiers ; le troisième n'a jamais été arbitré. |

---

## Fait, mais non validé par l'école

- **Barèmes de référence du catalogue** : ce sont des médianes relevées sur les
  bulletins, pas une règle communiquée par l'établissement. Si un barème
  officiel existe par niveau, il prime.
- **Le préscolaire ne compose pas.** Aucun bulletin de petite, moyenne ou
  grande section n'a été fourni ; rien n'a été inventé.
- **Moyenne générale** combinant contrôles et compositions : elle figure sur
  les bulletins CE2 (9,42 et 9,54 → 9,48) mais la pondération n'est pas
  confirmée, et n'est pas implémentée.
- **Écarts assumés avec le classeur d'origine** : quatre erreurs de formules
  ont été corrigées plutôt que reproduites. Documentées dans
  [modele-excel.md](modele-excel.md).

---

## Ouvert, non commencé

- **Badgeuse murale.** L'API est prête et le contrat écrit
  ([badgeuse-api.md](badgeuse-api.md)), mais l'équipementier n'est pas choisi.
  Deux points à trancher avant commande : l'authentification du boîtier —
  recommandation : clé d'appareil révocable — et le champ `occurred_at` pour
  rejouer les passages faits hors réseau.
- **Orange Money**, en plus de Wave.
- **Row-Level Security PostgreSQL**, en second rideau derrière le
  cloisonnement applicatif.
- **Super-administration** : l'écran de gestion des établissements et des
  abonnements existe côté API, pas côté interface.

---

## Points de vigilance techniques

Trois pièges rencontrés, dont les gardes sont en place — à ne pas défaire :

1. **`queryset = Model.objects…` sur un ViewSet cloisonné** gèle un `.none()`
   à l'import : l'écran répond vide, sans erreur. Utiliser `model = X`. Un test
   parcourt tous les points d'entrée de liste et échoue si l'un d'eux ne
   renvoie rien.
2. **Un service worker en cache d'abord sur des URL sans empreinte** sert
   indéfiniment du code périmé. Réservé aux `/assets/nom-[hash].js`.
3. **Un commentaire qui affirme un invariant non vérifié** en a produit trois
   dans ce projet : un sélecteur CSS mort, un cache mal borné, un ordre
   d'affichage impossible. Vérifier plutôt qu'affirmer.

Et une discipline qui a payé : **la compilation et les tests au vert ne disent
rien du rendu.** Plusieurs défauts réels — panneau ouvert hors écran, pied de
barre sous la ligne de flottaison, écran blanc — n'ont été trouvés qu'en
regardant, ou en mesurant.
