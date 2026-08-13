# Déploiement sur Hetzner

Sous **Coolify**, comme le projet `pmc`. Coolify occupe déjà les ports 80 et
443 du serveur avec son propre frontal : il route le domaine vers le service
`nginx` de la pile et renouvelle le certificat. Le compose ne publie donc
**aucun port** — le faire échouerait sur un conflit d'adresse.

Même schéma interne que `pmc` : PostgreSQL, Django sous gunicorn, interface
statique, nginx devant.

```
Internet → nginx :80 ─┬→ /api /admin /static /media → backend:8000 (gunicorn)
                      └→ /                          → frontend:3000 (serve)
                                                       backend → db:5432
```

## Créer l'application dans Coolify

1. **Nouvelle ressource → Docker Compose**, dépôt `TechBadji/monecole`,
   branche `main`, fichier `docker-compose.prod.yml`.
2. **Domaine** : le poser sur le service **`nginx`**, et sur lui seul. Les
   autres services n'ont pas à être joignables de l'extérieur — surtout pas la
   base.
3. **Variables d'environnement** : voir la section suivante. Coolify les
   injecte dans la pile ; elles ne vivent jamais dans le dépôt.
4. **Déployer.** Migrations et fichiers statiques s'exécutent au démarrage du
   conteneur `backend`.

Le DNS doit pointer sur le serveur **avant** le premier déploiement, faute de
quoi la validation du certificat échoue sans message clair.

## Installation autonome, sans Coolify

Le reste de ce document décrit l'installation directe, utile sur un serveur
neuf. Il faut alors republier le port dans `docker-compose.prod.yml` :
`ports: ["80:80"]` à la place de `expose`.

## Le serveur

Un **CX22** suffit — 2 vCPU, 4 Go — pour un établissement de 500 élèves. Les
limites mémoire du compose totalisent 1,5 Go, laissant de la marge au système et
aux sauvegardes. Prendre l'image **Ubuntu 24.04**, dans la région la plus proche
du Sénégal (Falkenstein ou Helsinki : la latence tient, l'application est
conçue pour une connexion instable).

```bash
ssh root@<ip>
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## Installation

```bash
git clone https://github.com/TechBadji/monecole.git /opt/monecole
cd /opt/monecole
cp .env.prod.example .env
```

Renseigner `.env`. **La clé de signature est obligatoire** — l'application
refuse de démarrer sans elle, sa valeur de repli étant publiée dans ce dépôt :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Puis :

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f backend
```

Les migrations et la collecte des fichiers statiques tournent au démarrage du
conteneur. Un échec de migration arrête le démarrage : mieux vaut un service
absent qu'un service tournant sur un schéma incomplet.

## Le premier compte

Aucun compte n'existe après l'installation. Créer le super-administrateur, qui
ouvrira ensuite les établissements depuis l'interface :

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python manage.py createsuperuser
```

Il ouvre chaque école depuis **Plateforme → Établissements** : année courante,
dix classes et trois accès sont créés d'un coup, avec des mots de passe
provisoires affichés une seule fois.

## HTTPS

Le compose expose le port 80 en clair. Le certificat se pose devant, avec
Caddy — le plus court chemin :

```bash
apt install -y caddy
cat > /etc/caddy/Caddyfile <<'CADDY'
ecole.exemple.sn {
    reverse_proxy 127.0.0.1:80
}
CADDY
systemctl reload caddy
```

Caddy obtient et renouvelle le certificat seul. Il faut que le domaine pointe
déjà sur l'IP du serveur, sinon la validation échoue sans message clair.

**Sans HTTPS, ne pas mettre en service** : `DJANGO_DEBUG=0` active la
redirection SSL, HSTS et les cookies sécurisés. En clair, les identifiants du
personnel circulent en clair.

## Vérifier

```bash
curl -s https://ecole.exemple.sn/health/     # {"status":"ok","database":"ok"}
docker compose -f docker-compose.prod.yml ps # tous « healthy »
```

Puis, depuis l'application : ouvrir un établissement de test, se connecter avec
le compte administrateur, changer le mot de passe imposé, et vérifier qu'un
courrier de réinitialisation arrive réellement :

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python manage.py test_email vous@exemple.com
```

## Mettre à jour

```bash
cd /opt/monecole && git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Les migrations s'appliquent au redémarrage. Les données et les fichiers
téléversés vivent dans des volumes Docker : ils survivent au redéploiement.

## Sauvegarder

**La base et les médias, tous les jours.** Sans cela, un incident coûte l'année
scolaire d'une école.

```bash
cat > /etc/cron.daily/monecole-backup <<'SH'
#!/bin/sh
set -e
DIR=/var/backups/monecole
mkdir -p "$DIR"
cd /opt/monecole
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U monecole monecole | gzip > "$DIR/db-$(date +%F).sql.gz"
docker run --rm -v monecole_media_data:/m -v "$DIR":/b alpine \
  tar czf "/b/media-$(date +%F).tar.gz" -C /m .
find "$DIR" -type f -mtime +30 -delete
SH
chmod +x /etc/cron.daily/monecole-backup
```

**Éprouver la restauration une fois**, sur une machine jetable. Une sauvegarde
jamais restaurée n'est pas une sauvegarde ; c'est un fichier.

## Points de vigilance

| Point | Pourquoi |
|---|---|
| `DJANGO_SECRET_KEY` | Obligatoire. Le démarrage échoue sans elle — c'est voulu : la valeur de repli est publique et signe les jetons. |
| `DJANGO_ALLOWED_HOSTS` | Renseigner le domaine. Laissé à `*`, il ouvre l'injection d'en-tête `Host`. |
| `PUBLIC_BASE_URL` | Compose les liens de réinitialisation. Oubliée, ils pointent vers `localhost` et personne ne peut se dépanner. |
| Messagerie | Sans identifiants SMTP, les courriers partent dans les journaux. Le circuit paraît fonctionner. Voir [messagerie.md](messagerie.md). |
| Compte Gmail partagé | `techbadji@gmail.com` sert aussi au projet `pyexam`, et son mot de passe d'application ouvre toute la boîte. Un compte dédié s'impose avant une mise en service commerciale. |
| Service worker | Le frontal interdit sa mise en cache. Ne pas ajouter de cache devant : un worker périmé sert des fragments effacés, et l'écran devient blanc. |
| `seed_demo` | Ne jamais lancer en production : la commande efface les données de l'établissement avant de les recréer. |
