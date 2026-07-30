# Intégration d'une badgeuse murale

Spécification à remettre à l'équipementier. Elle décrit ce que le boîtier doit
envoyer et ce qu'il reçoit en retour, indépendamment du matériel retenu.

---

## Le contrat

### Enregistrer un passage

```http
POST /api/scan/badge/
Content-Type: application/json
Authorization: Bearer <jeton>

{ "payload": "M0042|Diop|Aminata|2018-05-12|221771234567" }
```

Le champ `payload` est le contenu brut du QR code, tel que lu. Le boîtier n'a
rien à en extraire : le serveur s'en charge.

Si la lecture optique échoue et qu'un agent saisit le matricule à la main :

```json
{ "matricule": "M0042" }
```

### Réponse — passage enregistré (`201`)

```json
{
  "duplicate": false,
  "direction_label": "Entrée",
  "is_late": false,
  "student": {
    "id": 42,
    "matricule": "M0042",
    "name": "Aminata Diop",
    "classroom": "CP",
    "parent_phone": "+221771234567"
  },
  "event": {
    "id": 8391,
    "direction": "IN",
    "occurred_at": "2026-07-30T07:42:11+00:00",
    "day": "2026-07-30",
    "source": "QR"
  }
}
```

Ce que le boîtier doit afficher, par ordre d'importance : le **nom**, la
**classe**, et le **sens** (Entrée ou Sortie). Le retard (`is_late`) mérite une
couleur distincte.

### Réponse — carte déjà scannée (`200`)

```json
{
  "duplicate": true,
  "detail": "Aminata Diop vient déjà d'être scanné (entrée à 07:42).",
  "student": { "…": "…" },
  "event": { "…": "…" }
}
```

Deux scans de la même carte à moins de deux minutes d'intervalle comptent pour
un seul passage. Le boîtier doit l'afficher comme une confirmation, **pas comme
une erreur** : l'élève est bien passé.

### Réponses d'erreur

| Code | Cas | Ce que le boîtier affiche |
|---|---|---|
| `404` | Carte inconnue de cet établissement | « Carte non reconnue » |
| `400` | Élève transféré, exclu ou sorti des effectifs | Le message renvoyé dans `detail` |
| `401` | Jeton absent, expiré ou invalide | « Boîtier non autorisé » — voir ci-dessous |
| `5xx` | Panne serveur | Mettre le passage en file et réessayer |

---

## Ce que le serveur fait, et que le boîtier n'a pas à faire

- **Il déduit le sens.** Premier passage de la journée : entrée. Ensuite,
  alternance. Le boîtier n'a **pas** de bouton « entrée / sortie » à prévoir, et
  ne doit pas en imposer un : au portail, à sept heures et demie, personne ne
  sélectionne un sens dans une liste.
- **Il détecte les doublons**, dans une fenêtre de deux minutes.
- **Il qualifie le retard**, selon l'horaire réglé par l'école dans MonÉcole.
- **Il notifie les parents** par SMS, si l'école l'a activé.

Le boîtier se limite donc à : lire, envoyer, afficher la réponse.

---

## Fonctionnement hors réseau

La connexion tombera. Le boîtier doit **mettre les lectures en file locale** et
les rejouer au retour du réseau, en conservant l'horodatage réel de la lecture —
sinon toute une matinée d'arrivées se retrouverait horodatée à l'heure du
rétablissement.

Le champ `occurred_at` peut être fourni dans la requête pour cela :

```json
{ "payload": "M0042|…", "occurred_at": "2026-07-30T07:42:11+02:00" }
```

> Ce champ n'est pas encore accepté par l'API. À ajouter au moment de
> l'intégration, avec une borne : un horodatage antérieur de plus de 24 h ou
> postérieur à l'instant présent doit être refusé, faute de quoi un boîtier
> déréglé réécrirait l'historique.

---

## Authentification — **à trancher avant de choisir l'équipementier**

L'API attend aujourd'hui un jeton JWT d'utilisateur : valable 30 minutes, avec
rotation du jeton de rafraîchissement. **Cela ne convient pas à un boîtier mural
sans opérateur** — personne ne sera là pour se reconnecter.

Il faut donc une identité propre à l'appareil. Trois options, par ordre de
robustesse croissante :

| Option | Principe | Adapté si |
|---|---|---|
| **Clé d'appareil** | Un jeton long, propre au boîtier, en en-tête. Révocable, traçable, limité au seul badgeage. | Le boîtier sait envoyer un en-tête HTTP fixe — c'est le cas de tous. |
| **mTLS** | Certificat client installé sur l'appareil. | L'équipementier le propose et sait gérer le renouvellement. |
| **OAuth client credentials** | Le boîtier échange un secret contre un jeton court. | L'équipementier a déjà une pile OAuth. |

**Recommandation : la clé d'appareil.** Elle fonctionne avec n'importe quel
matériel capable d'un appel HTTPS, se révoque en un clic si un boîtier est
volé, et n'ouvre qu'une seule opération — enregistrer un passage. Un boîtier
compromis ne peut ni lire la liste des élèves, ni toucher aux finances.

Ce mécanisme **n'est pas encore implémenté**. À décider avant de retenir un
fournisseur : la question conditionne le choix.

---

## À vérifier auprès de l'équipementier

1. Sait-il envoyer un **en-tête HTTP personnalisé** sur chaque requête ?
2. Sait-il **mettre en file et rejouer** les lectures faites hors réseau ?
3. Peut-il afficher **une ligne de texte de retour** (nom, classe, sens), ou se
   limite-t-il à un bip et une diode ? Un simple bip prive l'agent de la
   vérification visuelle, et laisse passer les erreurs de carte.
4. Quelle correction d'erreur lit-il ? Les cartes MonÉcole sont générées en
   niveau **H** — le plus tolérant —, car elles sont manipulées quotidiennement
   par des enfants.
5. Le boîtier est-il **alimenté en permanence** ou sur batterie ? Une coupure
   d'électricité au portail est un cas courant.

---

## Cartes élèves

MonÉcole génère les planches à imprimer : dix cartes par page A4, au format
carte bancaire (85 × 54 mm), pour tenir dans les porte-badges du commerce.

```
GET /api/qr-sheet/?classroom=<id>    une classe
GET /api/qr-sheet/                   tout l'établissement
```

Le contenu du QR est décrit dans `backend/apps/attendance/qr.py`.
