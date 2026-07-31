# Messagerie

Le produit n'envoie qu'un seul type de courrier : le **lien de réinitialisation
de mot de passe**. Tout le reste passe par SMS.

## En développement

Rien à configurer. Sans `EMAIL_HOST`, Django bascule sur le backend console et
écrit les messages dans la sortie du serveur — le lien s'y lit et se colle dans
le navigateur.

## En production — **à faire avant la mise en service**

Sans les variables ci-dessous, les courriers ne partent pas : ils s'écrivent
dans les journaux du serveur. L'écran de demande, lui, répondra normalement,
puisqu'il répond la même chose dans tous les cas. **Le circuit paraîtra
fonctionner alors que personne ne recevra rien.**

```dotenv
EMAIL_HOST=smtp.exemple.sn
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=MonEcole <ne-pas-repondre@votre-domaine.sn>

# Déjà utilisée par les retours de paiement Wave : une seule base pour l'interface.
PUBLIC_BASE_URL=https://votre-domaine.sn
```

`PUBLIC_BASE_URL` sert à composer le lien. Le serveur ne peut pas la deviner : le
lien pointe vers l'interface, pas vers l'API. Laissée à sa valeur par défaut,
elle enverra tous les destinataires vers `localhost`.

### Le domaine expéditeur

Un enregistrement **SPF** et une signature **DKIM** sur le domaine de
`DEFAULT_FROM_EMAIL` ne sont pas facultatifs. Sans eux, Gmail et Outlook — que
tout le monde utilise — classent le message en indésirable ou le rejettent. Un
lien de réinitialisation qui arrive en indésirable est un lien qui n'arrive pas.

Vérifier après configuration :

1. Demander une réinitialisation depuis un compte Gmail et un compte Outlook.
2. Contrôler que le message arrive en boîte de réception, pas en indésirables.
3. Vérifier que le lien ouvre bien l'interface de production.

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

## Repli si le courrier n'est pas envisageable

Un administrateur d'établissement peut fixer un mot de passe provisoire depuis
la fiche utilisateur (`PATCH /api/users/<id>/`, champ `password`). Ce chemin ne
dépend d'aucun serveur de messagerie, mais ne dépanne pas l'administrateur
lui-même.
