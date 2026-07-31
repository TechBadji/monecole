# Messagerie

Le produit n'envoie qu'un seul type de courrier : le **lien de réinitialisation
de mot de passe**. Tout le reste passe par SMS.

L'expéditeur retenu est **Gmail**, via le compte `techbadji@gmail.com`.

## Configuration

Dans `backend/.env` — jamais dans `.env.example`, qui est suivi par git :

```dotenv
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=techbadji@gmail.com
EMAIL_HOST_PASSWORD=…          # mot de passe d'application, 16 caractères
DEFAULT_FROM_EMAIL=MonEcole <techbadji@gmail.com>

PUBLIC_BASE_URL=https://votre-domaine.sn
```

La bascule se fait sur la présence des **identifiants**, pas de l'hôte :
`smtp.gmail.com` est connu d'avance, ce qui manque à une installation neuve
c'est le mot de passe. Sans eux, Django écrit les messages sur la console.

### Le mot de passe d'application

Un mot de passe de compte Google ordinaire **ne fonctionne pas** en SMTP :
Google a fermé l'accès des « applications moins sécurisées ». Il faut un mot de
passe d'application, qui exige la validation en deux étapes sur le compte.

1. Activer la validation en deux étapes sur le compte Google.
2. Se rendre sur <https://myaccount.google.com/apppasswords>.
3. Créer un mot de passe, nommé par exemple `MonEcole`.
4. Coller les 16 caractères dans `EMAIL_HOST_PASSWORD`. Les espaces que Google
   affiche sont décoratifs : avec ou sans, cela fonctionne.

### `PUBLIC_BASE_URL`

Elle compose le lien envoyé, qui pointe vers l'**interface**, pas vers l'API.
Le serveur ne peut pas la deviner. Laissée à sa valeur par défaut, elle enverra
tous les destinataires vers `localhost`. La même variable sert aux retours de
paiement Wave — une seule base pour l'interface.

## Vérifier

```bash
python manage.py test_email vous@exemple.com
```

La commande affiche la configuration retenue, refuse de continuer si les
identifiants manquent, et remonte l'erreur SMTP au lieu de l'avaler. Contrôler
**la boîte de réception et les indésirables** : un lien de réinitialisation
classé en indésirable est un lien qui n'arrive pas.

## Ce que Gmail impose

- **L'en-tête `From` est réécrit** avec le compte authentifié. Mettre autre
  chose dans `DEFAULT_FROM_EMAIL` ne change pas ce que voit le destinataire ;
  seul un alias vérifié dans les paramètres Gmail le permettrait. Le réglage
  par défaut s'aligne donc sur `EMAIL_HOST_USER`.
- **Environ 500 destinataires par jour** sur un compte gratuit (2 000 sur
  Google Workspace). Pour des réinitialisations de mot de passe, la marge est
  large.
- **SPF et DKIM sont ceux de Google**, puisque l'adresse expéditrice est en
  `@gmail.com` : rien à configurer, contrairement à un envoi depuis un domaine
  propre. C'est le principal avantage de ce choix.

## Deux réserves

**Le compte est personnel et partagé.** `techbadji@gmail.com` sert déjà au
projet `pyexam`. Deux conséquences : révoquer le mot de passe d'application
pour l'un coupe l'autre, et les écoles recevront leurs courriers depuis une
adresse personnelle — ce qu'un directeur remarque. Pour une mise en service
commerciale, un compte Google Workspace sur un domaine `monecole.sn` réglerait
les deux, au prix d'une configuration SPF/DKIM sur ce domaine.

**Le mot de passe d'application donne accès à la boîte entière**, pas seulement
à l'envoi. Un serveur compromis donne la lecture de la messagerie personnelle.
C'est la seconde raison de basculer sur un compte dédié avant la production.

## Ce que le circuit garantit

- Le jeton est stocké **haché** (SHA-256). Une fuite de la table
  `core_passwordresettoken` ne permet pas de reprendre un compte.
- Il expire au bout de **deux heures** et ne sert **qu'une fois**.
- Une nouvelle demande **annule** la précédente.
- Les réponses sont **identiques** que l'adresse existe ou non : le formulaire
  ne peut pas servir à dresser la liste du personnel d'un établissement.
- Les demandes sont bornées à **5 par heure**, l'envoi étant déclenché vers une
  adresse choisie par le demandeur.
- Une réinitialisation **ferme toutes les sessions** du compte : ce chemin sert
  précisément quand quelqu'un reprend la main sur un compte compromis.

## Repli si le courrier échoue

Un administrateur d'établissement peut fixer un mot de passe provisoire depuis
la fiche utilisateur (`PATCH /api/users/<id>/`, champ `password`). Ce chemin ne
dépend d'aucun serveur de messagerie, mais ne dépanne pas l'administrateur
lui-même.
