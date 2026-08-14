# État d'avancement

Arrêté au 14 août 2026, commit `6761c2f`. **En production** :
<https://monecole.digitalmatis.com>

Ce document dit ce qui est **fait et vérifié**, ce qui est **fait mais non
validé par l'école**, et ce qui **bloque**. Il ne dit pas ce qui est prévu :
une feuille de route se périme, un état des lieux se relit.

---

## En un coup d'œil

| | |
|---|---|
| Backend | Django 5.2 · DRF · PostgreSQL — 19 500 lignes, 9 applications |
| Frontend | React 19 · TypeScript · Vite — 10 700 lignes, 23 écrans |
| Tests | **362**, tous au vert |
| Routes | 20/20 rendues, contrôlées pour 4 rôles + hors session |
| Déploiement | Coolify sur Hetzner, comme `pmc` |
| Dépôt | `TechBadji/monecole`, **public** |

---

## Ce qui fonctionne et qui est éprouvé

### Cycle de vie d'un établissement
- **Le super-administrateur ouvre une école** : année courante, dix classes de
  base et trois accès créés d'un coup. Mots de passe tirés au sort par compte,
  affichés une seule fois.
- **Changement de mot de passe imposé** à la première connexion, appliqué par
  le serveur : tant que le mot de passe provisoire tient, le compte ne peut que
  lire son profil et le changer.
- **L'administrateur crée son année scolaire** depuis Paramètres, et bascule
  l'année courante quand il est prêt.

### L'année scolaire commande tout
- **Sélecteur d'année global**, en tête de barre. Tous les écrans le suivent ;
  une année close se signale sur le sélecteur et par une bande.
- **Passage des élèves** : simulation obligatoire avant application, section
  conservée (CI-B → CP-B), redoublants désignés à la main, CM2 signalés en fin
  de cursus plutôt que promus au hasard.
- **Une inscription en attente n'est pas une inscription** : aucun montant
  n'est réclamé avant confirmation. C'est la règle qui gouverne le module.
- **Notes, matières, barèmes et titulaires valent pour une année.**

### Scolarité
- Élèves, classes, familles, inscriptions. Matricule `MXXXX` propre à l'école,
  conservé sur tout le cursus.
- **Plusieurs classes par niveau** — CI-A, CI-B — rangées dans l'ordre
  pédagogique. Une classe au nom nu est renommée plutôt que doublée.
- Situation financière d'un élève, année courante et années passées.

### Encaissements
- Saisie d'une classe entière en une requête, montants pré-remplis.
- Bourse sociale en pourcentage, répercutée partout.
- Trop-perçu affiché comme tel, jamais ramené à zéro.
- Arriérés sur les mois échus, après réductions, hors élèves en attente.

### Notes et bulletins
- **Le barème fait le poids, la moyenne est sur 10.** Établi en rejouant vingt
  bulletins papier : tous retrouvent la moyenne imprimée au centième. Voir
  [bareme-gsk.md](bareme-gsk.md).
- Catalogue de 32 matières, six niveaux, applicable en un clic.
- Barème ajustable par épreuve — la même matière passe de 4 à 12 dans l'année.
- **L'enseignant est rattaché à la classe**, pas à la matière : un maître tient
  toutes les matières de sa classe. `ClassSubject.teacher` reste pour
  l'intervenant d'arabe ou d'anglais.
- Sélecteur de classe à la saisie, avec l'avancement de validation.
- Une absence retire son barème du dénominateur.
- Bulletins PDF, à l'unité ou par classe, en-tête paramétrable.

### Finances
- Deux calendriers distincts : exercice oct→sept, année pédagogique oct→juin.
- Dépenses, rapport bilan, synthèse des encaissements, paie sénégalaise
  (IPRES, CSS, TRIMF, IR à parts familiales).

### Personnel
- Ajout, modification et **départ** d'un enseignant. Un départ se marque, il ne
  s'efface pas : bulletins de paie, notes et historique sont conservés.
- Colonne « Accès » : dit si l'enseignant a un compte pour saisir ses notes.

### Comptes et sécurité
- Cloisonnement multi-établissements porté par le modèle.
- Rôles et matrice de permissions, appliqués par le serveur à chaque appel.
- Journal d'audit immuable sur toute opération financière.
- Réinitialisation par courrier : jeton haché, deux heures, usage unique,
  réponses indiscernables qu'une adresse existe ou non.
- Sessions listées et révocables, y compris après renouvellement du jeton et
  depuis le portail parent.
- Vignette de profil avec photo, affichage en clair sur tous les mots de passe.

### Terrain
- Hors ligne avec rejeu au retour du réseau, données horodatées à l'écran.
- SMS via LAfricaMobile, paiement Wave, QR par élève, portail parent.
- **Questions fréquentes** accessibles avec ou sans session.

### Outillage
- [tools/audit-routes.mjs](../tools/audit-routes.mjs) parcourt toutes les
  routes dans un navigateur réel, sort en code 1 sur écran vide.
- `manage.py test_email` éprouve la configuration SMTP de bout en bout.
- `manage.py seed_demo --reset` : 180 élèves, une année complète.

---

## Ce qui bloque

| Point | Conséquence |
|---|---|
| **Mots de passe de démonstration en ligne** | `MonEcole2026!` est publié dans ce dépôt public et fonctionne sur l'instance en production. Rotation à faire depuis le terminal Coolify — voir plus bas. |
| **Jeton API Coolify** | Celui confié pour le déploiement donne accès à `pmc`, `gynaeasy` et `pyexam`. À révoquer. |
| **Compte Gmail personnel et partagé** | `techbadji@gmail.com` sert aussi à `pyexam` ; son mot de passe d'application ouvre toute la boîte, et il est désormais enregistré dans deux applications Coolify. |
| **Barèmes de paie non validés** | Aucun comptable ne les a relus. Une erreur de taux se paie en redressement. |
| **Données nominatives sur dépôt public** | Le classeur du client, le nom de l'établissement, et le nom et les notes d'une enfant mineure dans `backend/apps/academics/tests/test_catalogue.py:139`. Signalé plusieurs fois, jamais arbitré. |

### Rotation des mots de passe de démonstration

Coolify → application `monecole` → Terminal → service `backend` :

```bash
python manage.py shell -c "
import secrets
from apps.core.models import User
A='abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
for u in User.objects.all().order_by('role'):
    p=''.join(secrets.choice(A) for _ in range(14))
    u.set_password(p); u.save(update_fields=['password'])
    print(u.email, u.role, p)
"
```

---

## Fait, mais non validé par l'école

- **Barèmes de référence** : médianes relevées sur les bulletins, pas une règle
  communiquée. Un barème officiel primerait.
- **Le préscolaire ne compose pas.** Aucun bulletin fourni ; rien n'a été
  inventé.
- **Moyenne générale** combinant contrôles et compositions : figure sur les
  bulletins CE2 mais la pondération n'est pas confirmée, ni implémentée.
- **Quatre erreurs de formules** du classeur d'origine corrigées plutôt que
  reproduites — [modele-excel.md](modele-excel.md).

---

## Ouvert, non commencé

- **Badgeuse murale.** API prête, contrat écrit
  ([badgeuse-api.md](badgeuse-api.md)), équipementier non choisi. Deux points à
  trancher avant commande : authentification du boîtier (recommandation : clé
  d'appareil révocable) et champ `occurred_at` pour rejouer les passages hors
  réseau.
- **Départ d'un titulaire** : son affectation de classe survit, donc la classe
  garde son nom au bulletin — juste pour le passé — mais se retrouve sans
  personne pour saisir ses notes, sans que rien ne le signale. À trancher :
  libérer l'affectation, ou l'afficher comme un avertissement.
- **Un parent dont le numéro sert dans deux écoles** n'atteint que la première.
- **Orange Money**, en plus de Wave.
- **Row-Level Security PostgreSQL**, en second rideau.
- **Super-administration** : abonnements et plans existent côté API, pas côté
  interface.
- **Sauvegardes** : la procédure est écrite ([deploiement.md](deploiement.md))
  mais n'est pas en place sur le serveur.

---

## Ce qu'il faut savoir avant de reprendre le code

### Cinq pièges rencontrés, leurs gardes en place

1. **`queryset = Model.objects…` sur un ViewSet cloisonné** gèle un `.none()` à
   l'import : l'écran répond vide, sans erreur. Utiliser `model = X`. Un test
   parcourt tous les points de liste.
2. **Un service worker en cache d'abord sur des URL sans empreinte** sert
   indéfiniment du code périmé. Réservé aux `/assets/nom-[hash].js`.
3. **Un champ calculé accepté en écriture** est ignoré en silence par DRF : la
   requête répond 200 et rien ne change. Le sérialiseur des classes refuse
   désormais explicitement un `teacher` posé sur la classe.
4. **`X-Forwarded-Proto` écrasé par le frontal** : derrière un terminateur TLS,
   Django redirige vers HTTPS et le proxy revient — boucle sans fin.
5. **Un commentaire qui affirme un invariant non vérifié** en a produit quatre
   dans ce projet : un sélecteur CSS mort, un cache mal borné, un ordre
   d'affichage impossible, un `order` sans effet. Vérifier plutôt qu'affirmer.

### Deux disciplines qui ont payé

**La compilation et les tests au vert ne disent rien du rendu.** Panneau ouvert
hors écran, pied de barre sous la ligne de flottaison, écran blanc, boutons
invisibles sur fond blanc, colonne d'actions hors cadre : aucun n'a été trouvé
autrement qu'en regardant une capture ou en mesurant.

**Corriger l'écran ne suffit pas.** La borne de note à 20 subsistait côté
serveur après correction du frontend : c'est le test qui l'a montré, en
échouant sur l'API alors que la saisie paraissait fonctionner.

### Le défaut récurrent à surveiller

**Un champ ajouté au modèle et non propagé au sérialiseur puis à l'écran.** Il
s'est produit quatre fois : matricule élève, `category` d'une réduction,
coordonnées d'un enseignant, et l'endpoint d'historique jamais câblé. Le
symptôme est toujours le même — une colonne vide que personne ne relie au champ
manquant.
