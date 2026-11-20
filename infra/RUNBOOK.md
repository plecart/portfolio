# Runbook — la production

Ce qu'il faut savoir pour amorcer, déployer, réparer et entretenir le VPS de production (ADR 0002),
sans rien retrouver de mémoire (PRD, US 47 et 50). Les commandes sont celles du dépôt : le job
`deploy` de [`.github/workflows/ci.yml`](../.github/workflows/ci.yml),
[`bootstrap.sh`](bootstrap.sh) et [`compose.yml`](compose.yml) font foi s'ils divergent d'ici.

**Aucune étape ne demande d'afficher un secret, ni d'en recopier un extrait** — sauf l'enrôlement
du second facteur de l'admin, qui imprime une fois ce qu'il crée, pour le gestionnaire (« Admin »).
Un secret passe d'un fichier ou du gestionnaire de mots de passe à sa destination — `gh secret
set` le lit sur son entrée, `bootstrap.sh` le saisit sans écho — et une vérification se lit
oui / non. Ne colle jamais un secret dans une issue, une PR ou une conversation.

## La pile

`/srv/portfolio`, sur le VPS : `compose.yml`, déposé par le job `deploy` à chaque déploiement, et
`.env`, écrit par `bootstrap.sh` — sa ligne `IMAGE_TAG`, le SHA complet du commit déployé, est
réécrite par chaque déploiement. Projet Compose `portfolio` : `cloudflared`, `caddy`, `api`,
`worker`, `postgres`, `redis`, `backup`, chacun avec sa sonde, aucun port publié ; `cloudflared` est la seule
entrée (D45). L'utilisateur `deploy` possède le dossier et tire les images de GHCR.

## Où vit chaque secret

| Secret | Où il vit | Écrit par | Se tourne par |
|---|---|---|---|
| Jeton du Tunnel (`TUNNEL_TOKEN`) | gestionnaire de mots de passe ; `.env` du VPS | `bootstrap.sh` | Cloudflare, puis `bootstrap.sh TUNNEL_TOKEN` |
| `SECRET_KEY` | `.env` du VPS seulement | `bootstrap.sh`, qui l'engendre | `bootstrap.sh SECRET_KEY` |
| `POSTGRES_PASSWORD` | `.env` du VPS et la base | `bootstrap.sh`, qui l'engendre | `bootstrap.sh POSTGRES_PASSWORD`, pile démarrée |
| Mot de passe de l'admin (`ADMIN_PASSWORD`) | gestionnaire ; `.env` du VPS ; son empreinte dans la base | `bootstrap.sh`, qui le saisit ; `api`, qui le pose dans la base (« Admin ») | `bootstrap.sh ADMIN_PASSWORD` : `api` recréé pose le nouveau |
| Second facteur de l'admin (URI `otpauth://`, dix codes de secours) | gestionnaire ; l'application TOTP ; la base | `manage.py enroll_second_factor`, à la main (« Admin ») | la même commande : l'ancien appareil et les anciens codes tombent |
| Jeton GHCR (classic, `read:packages`) | gestionnaire ; configuration Docker de `deploy` | `bootstrap.sh` (`docker login`) | `bootstrap.sh GHCR_TOKEN` |
| Clé privée de déploiement | secret `DEPLOY_SSH_KEY` de l'environnement `production` seulement | le mainteneur | nouvelle paire, `bootstrap.sh DEPLOY_KEY` |
| Empreinte de l'hôte | secret `DEPLOY_KNOWN_HOSTS` de `production` | le mainteneur | à chaque VPS reconstruit |
| Hôte et utilisateur | secrets `DEPLOY_HOST`, `DEPLOY_USER` (`deploy`) de `production` | le mainteneur | à chaque VPS reconstruit |
| Mot de passe du rôle de sauvegarde (`BACKUP_POSTGRES_PASSWORD`) | `.env` du VPS et la base | `bootstrap.sh`, qui l'engendre et le pose dans la base | `bootstrap.sh BACKUP_POSTGRES_PASSWORD` |
| Jeton du bucket des médias (`MEDIA_R2_ACCESS_KEY_ID`, `MEDIA_R2_SECRET_ACCESS_KEY`), borné à ce bucket, droit de lister compris | gestionnaire ; `.env` du VPS | `bootstrap.sh` | un nouveau jeton R2, `bootstrap.sh` avec les deux noms, puis l'ancien révoqué |
| Jeton du bucket des sauvegardes (`BACKUP_R2_ACCESS_KEY_ID`, `BACKUP_R2_SECRET_ACCESS_KEY`) | gestionnaire ; `.env` du VPS | `bootstrap.sh` | un nouveau jeton R2, `bootstrap.sh` avec les deux noms, puis l'ancien révoqué |
| Adresse de ping (`BACKUP_PING_URL`) | le contrôle healthchecks.io ; `.env` du VPS | `bootstrap.sh` | un nouveau contrôle, `bootstrap.sh BACKUP_PING_URL`, puis l'ancien supprimé |
| DSN Sentry (`SENTRY_DSN`) | le projet Sentry (« Client Keys (DSN) ») ; `.env` du VPS | `bootstrap.sh` | une nouvelle clé du projet, `bootstrap.sh SENTRY_DSN`, puis l'ancienne révoquée |
| Clé privée `age` des sauvegardes | gestionnaire ; secret `BACKUP_AGE_IDENTITY` de `production`, pour le test mensuel — ni le dépôt, ni une image (ADR 0007, point 2) ; jamais stockée sur le VPS : elle transite par `ssh` vers la mémoire d'un conteneur jetable, le temps d'une restauration | le mainteneur, sur le poste | une nouvelle paire, sa clé publique à `bootstrap.sh BACKUP_AGE_RECIPIENT`, sa clé privée à `BACKUP_AGE_IDENTITY` ; l'ancienne gardée |
| Jeton du bucket en lecture seule (`RESTORE_R2_ACCESS_KEY_ID`, `RESTORE_R2_SECRET_ACCESS_KEY`) | gestionnaire ; secrets de `production` — le test mensuel seul s'en sert, jamais le VPS | le mainteneur | un nouveau jeton R2, les deux secrets remplacés, puis l'ancien révoqué |

L'environnement GitHub `production` n'admet que `main` : un workflow lancé depuis une autre branche
ne lit pas ses secrets, même modifié.

Le gestionnaire est KeePassXC (ADR 0022), un fichier chiffré local : copie-le hors du poste, sur un
support distinct, une fois rangés les secrets d'un chantier, et toujours avant `bootstrap.sh`. Le
poste perdu sans cette copie, la clé privée `age` est perdue, et avec elle les sauvegardes. Son mot
de passe maître n'y est pas : il se retrouve sans elle.

Entrées du groupe `Portfolio` : `Cloudflare`, `Cloudflare Tunnel`, `R2 portfolio-medias-rw`,
`R2 portfolio-backups-rw`, `R2 portfolio-backups-ro`, `Age Sauvegardes` (clé publique dans les Notes,
`age.key` en pièce jointe, seule copie de la clé privée), `Healthchecks backup` (adresse de ping),
`healthchecks.io`, `GHCR token` (Notes : portée, expiration, renouvellement), `Pacome.dev Admin`
(mot de passe, graine TOTP, codes de secours), `portfolio_admin` (phrase de passe de la clé SSH),
`portfolio root console`, et les comptes Hetzner et GitHub. Hors du gestionnaire :

- le client secret de l'application OAuth GitHub d'Access ne vit que dans Cloudflare : il se régénère
  sur GitHub, puis se recolle dans Cloudflare ;
- `portfolio root console` sert à la seule console web de Hetzner, qui demande un mot de passe pour
  comparer l'empreinte de l'hôte : « Reset root password » le pose, SSH reste par clé. Cette console
  est en QWERTY.

`SECRET_KEY`, `POSTGRES_PASSWORD` et `BACKUP_POSTGRES_PASSWORD` ne vivent que sur le VPS : rien hors
de la pile ne s'en sert, et un VPS reconstruit en reçoit de neufs — la base restaurée garde ses
données, pas ses rôles, que `bootstrap.sh` recrée. La clé privée `age`, elle, n'est jamais stockée
sur le VPS — elle n'y passe que le temps d'une restauration, dans le `tmpfs` d'un conteneur
jetable : une sauvegarde volée avec lui reste illisible. La clé publique (`BACKUP_AGE_RECIPIENT`)
n'est pas un secret.

## Amorcer un VPS neuf

Prérequis : un VPS x86 sous Ubuntu LTS en UE (ADR 0002, 0023), joignable en `root` par la clé SSH
`~/.ssh/portfolio_admin` (phrase de passe : entrée `portfolio_admin`), et l'alias `portfolio` de
« L'accès `root` » ci-dessous, son `HostName` à l'adresse du VPS ; dans le
gestionnaire de mots de passe, le jeton du Tunnel, ceux du bucket des médias et du bucket des
sauvegardes, la paire `age` et le compte de l'admin (« Admin ») ; l'adresse de ping du contrôle
healthchecks.io (#25). À la première connexion, `ssh` affiche l'empreinte de l'hôte : compare-la à
celle que la console du fournisseur rend pour `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
— identiques, oui ou non ? Non : n'accepte pas.

**L'accès `root`.** Toute commande `root` vers le VPS passe par l'alias `portfolio` du
`~/.ssh/config` du poste — `ssh portfolio`, `scp … portfolio:` —, posé une fois à la création du
VPS et retouché à chaque VPS reconstruit (`HostName`) :
```
Host portfolio
    HostName <ip>
    User root
    IdentityFile ~/.ssh/portfolio_admin
    IdentitiesOnly yes
```
`IdentityFile` remplace les `~/.ssh/id_*` par défaut et `IdentitiesOnly yes` écarte les clés de
l'agent, que le serveur refuse : seule cette clé est offerte, tant qu'aucun autre bloc (`Host *`)
n'ajoute d'`IdentityFile` (`ssh_config(5)`). La clé de déploiement (`deploy_key`, utilisateur `deploy`) reste hors de
l'alias : elle est à la CI, et ne sert au poste qu'une fois, avec `-i`, à l'étape 6.

Sous Windows, chaque geste du poste se lance dans **Git Bash** : PowerShell 5.1 refuse `<`, perd le
`""` de `-N ""`, et son `|` abîme un binaire.

1. **La clé de déploiement**, sur le poste, hors de tout clone, dédiée et sans phrase de passe — la CI ne peut pas en
   saisir une :
   ```
   ssh-keygen -t ed25519 -N "" -C deploy@portfolio -f deploy_key
   ```
2. **Le jeton GHCR** : un jeton *classic*, portée `read:packages` seule — GHCR n'accepte pas les
   jetons à droits fins (doc GitHub « Working with the Container registry ») —, créé sur
   `https://github.com/settings/tokens/new?scopes=read:packages`, rangé dans le gestionnaire, son
   expiration dans ton agenda : un jeton expiré ne se restaure pas, et un `pull` échoue alors
   (« Un déploiement rouge »). Le premier expire vers le 2027-11-01.
3. **Le commit à déployer** : la tête de `main`, si son run a publié (`gh run list --branch main
   --limit 1` : `completed success` ?). Son SHA complet : `git fetch origin && git rev-parse
   origin/main`.
4. **Les trois fichiers de ce commit**, tirés dans le clone sans changer de branche, puis copiés
   sur le VPS :
   ```
   git show <sha>:infra/bootstrap.sh > bootstrap.sh
   git show <sha>:infra/compose.yml > compose.yml
   git show <sha>:infra/prod.env.example > prod.env.example
   wc -c bootstrap.sh compose.yml prod.env.example
   scp bootstrap.sh compose.yml prod.env.example portfolio:
   rm bootstrap.sh compose.yml prod.env.example
   ```
   Aucun fichier à 0 octet : hors d'un clone, `git show` échoue et `>` laisse un fichier vide. (Un
   `compose.yml` laissé à la racine du dépôt serait pris par tout `docker compose` lancé là.)
5. **L'amorçage**, en `root` sur le VPS — `-t` pour les saisies sans écho :
   ```
   ssh -t portfolio bash bootstrap.sh
   ```
   Il demande : la clé publique (le contenu de `deploy_key.pub`), le jeton GHCR, `IMAGE_TAG` (le
   SHA de l'étape 3), `TUNNEL_TOKEN`, les noms d'hôte — `SITE_HOST`, `API_HOST`, `MEDIA_HOST`
   (ADR 0003) —, le compte de l'admin — `ADMIN_USERNAME`, puis `ADMIN_PASSWORD` sans écho —, ceux
   du bucket public des médias (ADR 0004) : l'adresse, le nom et le jeton, puis ceux de la
   sauvegarde : la clé publique `age`, l'adresse, le jeton et le nom du bucket R2, l'adresse de
   ping. Il engendre le mot de passe du rôle Postgres de `backup`, et crée ce rôle une fois la base
   saine, avant de démarrer le reste. Il finit par `== Fait`, `docker compose ps` où chaque service
   est `healthy`, et la ligne de la clé de l'hôte.
   Il s'arrête sur la première erreur ; relancé, il reprend sans rien refaire de ce qui est en
   place. `cloudflared` ne devient sain qu'avec un Tunnel configuré (#25) : sinon `--wait`
   s'arrête sur « cloudflared is unhealthy ». Un noyau neuf installé en chemin attend un
   redémarrage (`needrestart` le dit) : `ssh portfolio reboot`, et la pile revient seule.
6. **L'environnement `production` et ses secrets**, depuis le poste, dans le dépôt — d'abord
   l'environnement restreint à `main` (doc GitHub « Deployments and environments »), puis les
   quatre secrets :
   ```
   echo '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' | gh api -X PUT repos/plecart/portfolio/environments/production --input -
   gh api -X POST repos/plecart/portfolio/environments/production/deployment-branch-policies -f name=main -f type=branch
   gh secret set DEPLOY_SSH_KEY --env production < deploy_key
   ssh portfolio "cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub" | sed "s/^/<ip> /" | gh secret set DEPLOY_KNOWN_HOSTS --env production
   gh secret set DEPLOY_HOST --env production --body <ip>
   gh secret set DEPLOY_USER --env production --body deploy
   ssh -i deploy_key deploy@<ip> "cd /srv/portfolio && docker compose ps"
   rm deploy_key deploy_key.pub
   ```
   Le `ssh -i` répond-il sans phrase de passe, chaque service `healthy` ? Sinon, ne supprime pas la
   clé : elle ne se relit plus depuis GitHub. `gh secret list --env production` liste-t-il les
   quatre noms ? (Il n'affiche jamais les valeurs, et `gh secret set` écrit « for plecart/portfolio »
   même pour un secret d'environnement : c'est cette liste qui fait foi.)
7. **Le déploiement continu** : `gh variable set DEPLOY_ENABLED --body true`. Le prochain push sur
   `main` déploie ; tant que la variable ne vaut pas `true`, le job `deploy` est sauté.

## Commandes sur le VPS

En `deploy`, dans le dossier de la pile — `root` lit l'état aussi, mais n'a pas d'accès à GHCR :
```
ssh portfolio
sudo -iu deploy
cd /srv/portfolio
docker compose ps
docker compose logs --tail 100 api
docker compose restart caddy
```

Chaque commande Compose exige `IMAGE_TAG` (`${IMAGE_TAG:?}` dans `compose.yml`) : elle le lit dans
le `.env`, qui porte le SHA du dernier déploiement (`grep IMAGE_TAG .env`). Pour viser un autre
commit le temps d'une commande, l'environnement l'emporte sur le `.env` :
`IMAGE_TAG=<sha> docker compose …` — un SHA complet, jamais `latest`, que deux publications
croisées peuvent laisser sur l'avant-dernier commit.

## Déployer à la main

Quand la CI ne peut pas le faire, ou pour revenir à un commit antérieur. Seuls les trois derniers
commits publiés ont encore leurs images (`make prune`) :
`gh api users/plecart/packages/container/portfolio-api/versions --jq '.[].metadata.container.tags'`.

1. Le Compose de ce commit, depuis le poste :
   ```
   git show <sha>:infra/compose.yml > compose.yml
   scp compose.yml portfolio:/tmp/compose.yml
   rm compose.yml
   ```
2. Sur le VPS, les gestes du job `deploy` :
   ```
   install -m 640 -o deploy -g deploy /tmp/compose.yml /srv/portfolio/compose.yml
   sudo -iu deploy
   cd /srv/portfolio && sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=<sha>/' .env && docker compose pull --quiet && docker compose up -d --wait --wait-timeout 300
   ```

Revenir en arrière ne défait aucune migration : un commit antérieur à une migration déjà jouée
tourne sur un schéma plus récent que le sien. Le prochain déploiement de la CI remet la tête de
`main`.

## Un déploiement rouge

- **« required variable X is missing a value »** — une variable est apparue dans `compose.yml` et
  `prod.env.example`. Copie les deux, avec `bootstrap.sh`, depuis ce commit, et relance
  `bash bootstrap.sh` : il ne demande que la nouvelle. Puis relance le job.
- **« container portfolio-<service>-1 is unhealthy »** ou **« application not healthy »** — ce
  service ne répond pas à sa sonde : `docker compose logs <service>`. Un service qui tourne sans
  répondre est déclaré malade au bout de trois minutes environ ; un service qui sort, aussitôt.
- **« unauthorized » ou « denied » au `pull`** — le jeton GHCR a expiré ou a été révoqué :
  `sudo bash bootstrap.sh GHCR_TOKEN` (« Tourner un secret »), puis relance le job.
- **« Host key verification failed »** — l'hôte n'a plus la clé épinglée : VPS reconstruit, ou
  autre machine. Vérifie l'empreinte comme à l'amorçage avant de remplacer `DEPLOY_KNOWN_HOSTS`.
- **« main est passée à … »** — pas une erreur : un commit plus récent se déploie par son propre
  run.
- **`deploy` sauté derrière un `fumee` rouge** — les images du commit sont publiées, jamais
  déployées : le journal du job nomme l'étape ou le scénario, `make smoke` le rejoue sur le poste
  (`CONTRIBUTING.md`) et le correctif passe par une PR ; ne relance le job que sur un rouge du
  runner — tirage, délai.

## Tourner un secret

Pour toutes les entrées sauf `RESTORE_R2_*` — la dernière, qui se tourne sans rien de ce qui suit
— : jamais pendant un déploiement ; le job et le script écrivent le même `.env`, et le script
remettrait l'étiquette qu'il a lue avant le job. Suspends d'abord le déploiement continu —
`gh variable set DEPLOY_ENABLED --body false` —, puis vérifie qu'aucun run de `main` ne tourne ni
n'attend : `gh run list --branch main --status in_progress`, puis `--status queued`, vides ?
Remets `--body true` une fois la rotation faite ; un push arrivé entre-temps se déploie au suivant,
ou par « Déployer à la main ».

Copie ensuite sur le VPS les trois fichiers de la tête de `main` (étape 4 de l'amorçage), et
`sudo bash bootstrap.sh <NOM>…` : il redemande ou réengendre les valeurs nommées,
garde les autres, et relance la pile, qui recrée les services touchés — sans mettre Docker à
niveau ni tirer d'image déjà présente.

- `SECRET_KEY` — les sessions ouvertes sont perdues.
- `POSTGRES_PASSWORD` — pile démarrée : le script change d'abord le mot de passe dans la base.
- `TUNNEL_TOKEN` — régénéré dans Cloudflare d'abord.
- `GHCR_TOKEN` — un nouveau jeton (étape 2 de l'amorçage), puis l'ancien révoqué.
- `DEPLOY_KEY` — une nouvelle paire (étape 1), sa clé publique donnée à `bootstrap.sh DEPLOY_KEY`,
  sa clé privée à `gh secret set DEPLOY_SSH_KEY --env production < deploy_key` ; entre les deux, un déploiement
  échoue.
- `BACKUP_POSTGRES_PASSWORD` — pile démarrée ou non : le script pose le nouveau dans la base une
  fois celle-ci saine, puis recrée `backup`. Pas autour de 03:00 UTC : entre les deux, le
  conteneur garde l'ancien, et une sauvegarde lancée là échoue, sans ping.
- `MEDIA_R2_ACCESS_KEY_ID MEDIA_R2_SECRET_ACCESS_KEY`, ensemble — un nouveau jeton d'abord,
  « Object Read & Write » borné au seul bucket des médias, puis l'ancien révoqué, une fois `api` et
  `worker` recréés : les deux valent pendant la bascule.
- `BACKUP_R2_ACCESS_KEY_ID BACKUP_R2_SECRET_ACCESS_KEY`, ensemble — un nouveau jeton d'abord,
  « Object Read & Write » borné au seul bucket des sauvegardes, puis l'ancien révoqué, une fois
  `backup` recréé : les deux valent pendant la bascule.
- `BACKUP_PING_URL` — l'adresse d'un contrôle ne change pas, son UUID « is immutable » (doc
  healthchecks.io « HTTP API ») : un nouveau contrôle, même période et même délai de grâce, puis
  l'ancien supprimé — sinon il alerte, faute de ping.
- `SENTRY_DSN` — une nouvelle clé dans « Client Keys (DSN) » du projet, puis l'ancienne révoquée,
  une fois `api` et `worker` recréés : la doc Sentry permet de tourner et de révoquer un DSN
  ([DSN](https://docs.sentry.io/concepts/key-terms/dsn-explainer/), lue le 2026-11-05). Puis la
  vérification de « Sentry — les erreurs ».
- `BACKUP_AGE_RECIPIENT` — une nouvelle paire sur le poste, `age-keygen -o age.key`, qui n'affiche
  que la clé publique : celle-ci à `bootstrap.sh BACKUP_AGE_RECIPIENT`, le fichier joint à une
  entrée du gestionnaire, et au secret du test mensuel —
  `gh secret set BACKUP_AGE_IDENTITY --env production < age.key` —, puis `rm age.key`. Garde
  l'ancienne clé privée tant que le bucket porte une sauvegarde chiffrée pour elle : elle seule la
  déchiffre. Jusqu'à la sauvegarde de la nuit suivante, la dernière l'est encore : le test mensuel
  lancé avant échouerait au déchiffrement.
- `RESTORE_R2_ACCESS_KEY_ID RESTORE_R2_SECRET_ACCESS_KEY` — sans `bootstrap.sh` ni suspension du
  déploiement : ils ne vivent que dans `production`. Un nouveau jeton R2, « Object Read only »
  borné au seul bucket des sauvegardes, puis `gh secret set RESTORE_R2_ACCESS_KEY_ID --env
  production` et `gh secret set RESTORE_R2_SECRET_ACCESS_KEY --env production`, chacun saisi au
  clavier, jamais en argument ; puis l'ancien révoqué, et le test mensuel lancé à la main (« Le
  test mensuel »).

## Mises à jour

Les correctifs de sécurité d'Ubuntu s'installent chaque jour (`unattended-upgrades`). Docker vient
de son propre dépôt : chaque mois, en `root`,
`apt-get update && apt-get install --only-upgrade docker-ce docker-ce-cli containerd.io docker-compose-plugin`,
puis `docker compose ps` en `deploy` — le démon redémarre, la pile revient seule
(`restart: unless-stopped`). `/var/run/reboot-required` présent : `reboot`.

## Sécurité de l'hôte

- **Le groupe `docker` vaut `root`** (doc Docker « Docker Engine security ») : `deploy`, qui en est
  membre, et donc la clé de la CI, ont tout pouvoir sur le VPS. Cette clé ne vit que dans le secret
  de l'environnement `production`, que seule `main` lit ; aucune copie ne reste sur un poste.
- SSH par clés seulement ; `root` par clé seulement ; `ufw` n'ouvre que SSH ; `fail2ban` bannit
  les adresses qui échouent sur SSH.
- Aucun port de la pile n'est publié (`apps/api/tests/test_compose.py`) : Docker contournerait
  `ufw` pour un port publié.

## Admin

**Le compte unique** vient de `ADMIN_USERNAME` et `ADMIN_PASSWORD`, dans le `.env` du VPS :
`bootstrap.sh` les saisit à l'amorçage — le nom en clair, le mot de passe sans écho —, et
`compose.yml` les exige. À chaque démarrage, après les migrations, `api` pose le compte
(`manage.py ensure_superuser`, [`api/entrypoint.sh`](api/entrypoint.sh)) : il le crée la première
fois, puis remet le mot de passe s'il a changé ; son journal dit ce qu'il a écrit, jamais le mot
de passe. Celui-ci vit dans le gestionnaire de mots de passe : 12 caractères au moins, ni courant,
ni entièrement numérique, ni proche du nom (les validateurs de Django), et sans apostrophe, que
`bootstrap.sh` refuse.

`api` refuse de démarrer — `docker compose logs api` dit pourquoi — quand l'une des deux variables
est vide, quand les validateurs refusent un mot de passe neuf — à la création du compte, ou quand
`ADMIN_PASSWORD` change —, ou quand la base porte déjà un autre compte d'admin, superutilisateur
ou staff, d'un autre nom : l'admin n'en a qu'un. Un mot de passe inchangé n'est pas rejugé : une
montée de Django qui durcit un validateur n'arrête pas `api`. Le cas de l'autre compte suit une
restauration sur un VPS dont `ADMIN_USERNAME` diffère du compte de la sauvegarde, ou un
`bootstrap.sh ADMIN_USERNAME` qui change le nom : remets le nom du compte existant par
`sudo bash bootstrap.sh ADMIN_USERNAME` (« Tourner un secret »), qui recrée `api`.

**Nom perdu, ou à changer** : le refus ne nomme pas le compte. Un conteneur jetable d'`api`, qui
ne joue aucune étape de démarrage (`STARTUP_STEPS` vide), le lit même quand `api` refuse :

```
docker compose run --rm -e STARTUP_STEPS= api python manage.py shell -c "print(*User.objects.filter(is_superuser=True) | User.objects.filter(is_staff=True))"
```

Pour changer de nom à dessein, renomme d'abord le compte dans la base, par la même voie et
`shell -c "User.objects.filter(username='<ancien>').update(username='<nouveau>')"`, puis
`sudo bash bootstrap.sh ADMIN_USERNAME` avec le nouveau nom ; dans l'autre ordre, `api` refuse.

**Le second facteur** — une application TOTP, et dix codes de secours à usage unique — s'enrôle à
la main, le compte posé, par une commande Compose (« Commandes sur le VPS ») :

```
docker compose exec api python manage.py enroll_second_factor
```

Elle imprime une seule fois l'URI `otpauth://` et les dix codes : range-les aussitôt dans le
gestionnaire de mots de passe, et ouvre ou colle l'URI dans l'application TOTP ; rien ne les
réaffiche. Sans second facteur, l'admin ne sert que sa page de connexion. La connexion se fait en
un envoi : nom, mot de passe et jeton de l'application. Un code de secours en demande deux : nom et
mot de passe, jeton vide — la page revient avec le sélecteur « Appareil OTP », présélectionné sur
l'application —, puis « Code de secours » choisi et le code. Envoyé sans ce choix, un code de
secours est refusé comme un jeton faux de l'application, et reste valable.

**Application perdue** : un code de secours ouvre l'admin, une seule fois. Relance ensuite la
commande, qui ré-enrôle : l'ancienne application et les anciens codes ne valent plus. Elle ne
demande aucune connexion à l'admin — sans code restant, la relancer sur le VPS suffit.

**Session Access expirée devant un formulaire ouvert** (session de 24 h) : l'envoi ne part pas, et
rien ne s'affiche — la console de Chrome écrit « violates the following Content Security Policy
directive: "form-action 'self'" ». Access redirige vers une autre origine, très probablement la
cause ; Firefox n'est pas testé (mesuré le 2026-11-02, #25). La directive reste : levée, l'envoi
partirait vers Access et la saisie serait perdue au retour (déduit). Laisse la page ouverte, ouvre
l'admin dans un autre onglet pour repasser Access, puis renvoie le formulaire (non éprouvé) ;
recharger la page rétablit l'accès, sans la saisie.

Pour éprouver Access à la main, la déconnexion se fait sur
`https://api.pacome.dev/cdn-cgi/access/logout` : l'adresse de l'équipe rend « No Access cookie
found ». Avec GitHub déjà connecté, Access repasse ensuite sans écran : ce n'est pas une barrière
absente, l'onglet Network montre le détour par `cloudflareaccess.com` et GitHub.

## Cloudflare — l'état attendu

L'état constaté du 2026-10-30 au 2026-11-02 (cadrage §6.7, point 7 ; ADR 0003 ; #25),
redirections le 2026-11-16. Compte protégé par un TOTP, que la connexion Google demande aussi.

- **Domaine** — `pacome.dev`, Cloudflare Registrar, renouvellement automatique, expiration en
  octobre 2027.
- **Tunnel** — `portfolio`, géré depuis Cloudflare ; son jeton est `TUNNEL_TOKEN`. Routes, dans cet
  ordre : `pacome.dev` puis `api.pacome.dev`, vers `http://caddy:80`, qui route par nom d'hôte
  (`infra/caddy/Caddyfile`).
- **DNS** — `pacome.dev` et `api` de type Tunnel vers `portfolio` ; `media` de type R2 vers
  `portfolio-medias` ; `www` CNAME vers `pacome.dev` ; tous Proxied. TXT `@` `v=spf1 -all` et TXT
  `_dmarc` `v=DMARC1;p=reject;sp=reject;adkim=s;aspf=s`, en DNS only : le domaine n'envoie aucun
  e-mail.
- **Redirections** — « Always Use HTTPS » activé : `http://` rend 301 vers `https://`. Redirect
  Rule `www-vers-apex` : hôte `www.pacome.dev`, quel que soit le protocole, vers
  `concat("https://pacome.dev", http.request.uri.path)`, 301, chaîne de requête conservée — un seul
  saut (mesuré le 2026-11-16). Sans elles, la Search Console signalait `http://pacome.dev/` en
  doublon et `http://www.pacome.dev/` en 404 (constaté le 2026-11-16), faute de route `www` au
  tunnel (déduit). `https://api.pacome.dev/` et `https://media.pacome.dev/` rendent 404 à la
  racine : ni l'API ni R2 n'ont de page d'accueil, voulu.
- **R2** — `portfolio-medias`, public par `media.pacome.dev` seul, URL `r2.dev` désactivée ;
  `portfolio-backups`, privé. WEUR par indice, classe Standard. Trois jetons bornés à un bucket :
  `portfolio-medias-rw`, `portfolio-backups-rw`, `portfolio-backups-ro` (« Où vit chaque secret »).
  `media.pacome.dev` n'ajoute ni `X-Content-Type-Options` ni CSP, SVG compris : ses fichiers ne
  viennent que de l'auteur, et cet hôte ne porte aucun cookie (ni `<img>` ni un masque CSS
  n'exécutent un SVG ; le masque, mesuré le 2026-11-20 sur Chromium 156 contre un `<iframe>`
  témoin).
  CORS : le site charge les icônes du ruban en masque CSS, donc en CORS (#271), refusé sans la
  règle de `portfolio-medias`, posée dans le tableau de bord (R2 › `portfolio-medias` › Settings ›
  CORS Policy) : `[{ "AllowedOrigins": ["https://pacome.dev"], "AllowedMethods": ["GET", "HEAD"] }]`.
  Propagée en 30 s au plus, elle demande ensuite un Cache Purge de `media.pacome.dev`, que la doc
  prescrit ([CORS](https://developers.cloudflare.com/r2/buckets/cors/), lue le 2026-11-20) : l'arête
  garde les `GET` de ces fichiers, une entrée par `Origin` (`cf-cache-status: HIT`, mesuré le
  2026-11-20 après la règle). Depuis la règle, posée le 2026-11-20, un `GET` rend `Vary: Origin`,
  avec ou sans `Origin`, et `Cache-Control: max-age=14400` (mesuré le même jour) : un navigateur ne
  ressert plus au masque une icône chargée sans `Origin` (mesuré sur le site en ligne, une `<img>`
  puis le masque de la même adresse : 200, aucune erreur). Les en-têtes d'avant la règle ne se
  mesurent plus ; sans `Cache-Control`, la fraîcheur heuristique d'une icône, un dixième de son
  âge, n'aurait pas dépassé 31 h (22 icônes relevées).
  Contrôle — l'en-tête `Access-Control-Allow-Origin` y vaut `https://pacome.dev`, absent le
  2026-11-20 avant la règle, présent après :
  `curl -sI -H "Origin: https://pacome.dev" https://media.pacome.dev/technologies/django.svg`.
- **Access** — équipe `pacome`, fournisseur GitHub (application OAuth `Portfolio Cloudflare
  Access`). Application `portfolio-admin`, chemin `api.pacome.dev/admin`, GitHub seul, session 24 h ;
  politique `admin-mainteneur` : Allow, l'adresse e-mail que GitHub transmet pour le mainteneur. Le
  reste de l'hôte de l'API n'est pas couvert.
- **Barre oblique encodée** — Access ne couvre pas `/admin%2Flogin/`, ni `/admin%2f` : Caddy refuse
  sur l'hôte de l'API tout chemin qui en porte une (`infra/caddy/Caddyfile`).
- **WAF et protection DDoS** — ceux de l'offre gratuite, sans réglage, aucune règle personnalisée.
  La console affiche « No Managed rules created » : l'activité du jeu de règles gratuit n'est pas
  établie. Turnstile : absent (D41).
- **Limitation de débit** — règle `api-100-par-10s`, seule de l'offre gratuite : chemin commençant
  par `/api/`, par IP, 100 requêtes par 10 secondes, Block 10 secondes. L'offre ne filtre pas par
  hôte : le chemin couvre l'API publique, ni l'admin, ni le site, ni les médias.
- **TLS** — minimum 1.2 sur la zone et sur `media.pacome.dev`, deux réglages distincts.
- **Alerte de budget** — `alerte-1-dollar`, 1 $, par e-mail : Cloudflare n'a pas de plafond dur.

Coût constaté (2026-11-02) : environ 15 € par mois, pour une cible d'une dizaine d'euros (ADR 0023) :

| Poste | Prix | Lu sur |
|---|---|---|
| VPS Hetzner CPX12 | 14,39 € TTC par mois, facturation horaire plafonnée | console, [Billing FAQ](https://docs.hetzner.com/cloud/billing/faq/) |
| `pacome.dev` | 8,20 $ la première année, 12,20 $ par an ensuite | caisse, [Registrar](https://developers.cloudflare.com/registrar/about/) |
| R2 | 0 $ : 10 Go-mois, 1 M d'opérations A et 10 M d'opérations B inclus ; au-delà 0,015 $ le Go-mois, 4,50 $ et 0,36 $ le million | caisse, [Pricing](https://developers.cloudflare.com/r2/pricing/) |
| Zero Trust (Access, Tunnel) | 0 $, offre Free, 50 utilisateurs, un seul ici | caisse, [Pricing](https://www.cloudflare.com/plans/sase-zero-trust.md) |
| healthchecks.io | 0 $, 1 contrôle sur 20 | [Pricing](https://healthchecks.io/pricing/) |
| Sentry | 0 $, offre *Developer* : 5 000 erreurs, un utilisateur, 30 jours d'historique ; au-delà du quota, les événements sont refusés, rien n'est facturé | [Pricing](https://sentry.io/pricing/), [Quotas](https://docs.sentry.io/pricing/quotas/), lues le 2026-11-05 par l'ADR 0027 |
| GitHub Pro | abonnement du compte, hors de ce total, prix non relevé ; requis : sur un dépôt privé, sans lui, l'environnement `production` tombe, et avec lui `deploy` et le test mensuel | [Managing environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) |

## Sentry — les erreurs

Les erreurs de `api` et de `worker` arrivent dans le projet Sentry (ADR 0027,
`apps/api/config/observability.py`) : exceptions non gérées de l'API, échecs de tâches — réessais
épuisés compris, en un seul événement —, et tout événement de niveau erreur d'un logger,
`django_redis.cache` et `django.db.backends.base` compris ; chacun porte l'identifiant de
corrélation de sa requête ou de sa tâche, en tag `correlation_id`, le même que dans les journaux.
Rien d'autre : ni traces de performance, ni donnée personnelle — ni utilisateur, ni adresse IP, ni
cookie, ni en-tête, ni corps de requête, ni variable locale d'une trace —, dans Sentry comme dans
les journaux (`apps/api/tests/test_observability.py`, sur une requête de l'admin en erreur). Sans
`SENTRY_DSN`, rien ne part : c'est l'état du poste, de la CI et des piles jetables, qui tournent
sur `prod.env.example`. Les alertes sont celles que Sentry crée par défaut.

**Créer le projet**, une fois :

1. Une organisation, **région Union européenne (Francfort)**, choisie à sa création et définitive :
   « once selected, your data storage location can't be changed »
   ([Data Storage Location](https://docs.sentry.io/organization/data-storage-location/), lue le
   2026-11-05 par l'ADR 0027).
2. Un projet de plateforme Django.
3. Son DSN, dans « Client Keys (DSN) » des réglages du projet
   ([DSN](https://docs.sentry.io/concepts/key-terms/dsn-explainer/), lue le 2026-11-05).

Seul le choix de la région à la création est vérifié dans la doc ; l'ordre des écrans de la console
ne l'est pas.

**Poser le DSN** — `sudo bash bootstrap.sh SENTRY_DSN`, comme toute rotation (« Tourner un
secret ») : il le saisit sans écho. C'est un secret : qui le connaît envoie des événements au
projet, et en épuise le quota. `bootstrap.sh` refuse une valeur vide, comme pour toute variable du
modèle ; seul `compose.yml` le tolère absent (`${SENTRY_DSN:-}`), pour les piles jetables.

**Vérifier la chaîne après un déploiement** — une erreur volontaire depuis chaque conteneur, en
`deploy` dans `/srv/portfolio` :
```
docker compose exec api python manage.py shell -c "import logging; logging.getLogger('verification').error('Sentry depuis api')"
docker compose exec worker python manage.py shell -c "import logging; logging.getLogger('verification').error('Sentry depuis worker')"
```
Chacune doit ouvrir une issue dans le projet, environnement `production`. Le processus envoie
avant de sortir : le SDK vide sa file à l'arrêt de l'interpréteur, en attendant au plus
`shutdown_timeout`, 2 s par défaut
([Shutdown and Draining](https://docs.sentry.io/platforms/python/configuration/draining/), lue le
2026-11-05). Éprouvé en test, sur un transport factice : une erreur journalisée fait un événement
(`apps/api/tests/test_observability.py`). Non vérifié avant le premier déploiement : l'arrivée
réelle dans la console, et son délai — c'est ce que ces deux commandes établissent.

## Sauvegarde et restauration

Chaque nuit à 03:00 UTC, `backup` enchaîne dump, chiffrement, envoi, purge et ping
([`backup/backup.sh`](backup/backup.sh)) : l'objet `<base>-<AAAAMMJJ>T<HHMMSS>Z.dump.age` arrive
dans le bucket des sauvegardes, la purge n'y garde que 7 quotidiennes et 4 hebdomadaires de plus
(la règle de `borg prune --keep-daily 7 --keep-weekly 4`, [`backup/retention.sh`](backup/retention.sh)),
puis healthchecks.io reçoit le ping. La première étape qui échoue arrête tout, sans ping :
healthchecks.io alerte de son absence. Pour revenir à une sauvegarde : « Restaurer une sauvegarde »,
et, si la machine elle-même est perdue, « Le VPS a disparu », plus bas. Que la dernière se restaure,
un workflow le prouve chaque mois : « Le test mensuel ».

**Risque accepté** : le jeton du VPS peut supprimer les sauvegardes — R2 n'a pas de droit d'écriture
sans suppression — et la purge nocturne reste inchangée, sans verrou de bucket (#25). Un VPS
compromis peut donc effacer le bucket. À réexaminer le jour où le site porte un contenu que l'auteur
ne saurait pas ressaisir ; un verrou se pose alors avec une purge adaptée dans le même geste, sinon
la purge échoue chaque nuit, sans ping.

**Lancer une sauvegarde à la main**, en `deploy` dans `/srv/portfolio` (« Commandes sur le VPS ») —
pas autour de 03:00 UTC, où deux chaînes se disputeraient la purge :
```
docker compose exec backup backup.sh
```
Elle écrit `== dump`, `== chiffrement`, `== envoi`, `== purge` — puis `supprimé : <objet>` pour
chaque objet purgé —, `== ping`, et sort en 0. Un échec écrit `échec à l'étape : <étape>`.

**Vérifier qu'une sauvegarde est arrivée** — trois réponses oui / non :
1. Le journal : `docker compose logs --since 24h backup` montre les étapes de la nuit
   (`msg="== dump"`… `msg="== ping"`), sans ligne `level=error` ni `échec à l'étape`.
2. Le bucket : tableau de bord Cloudflare, R2, bucket des sauvegardes — un objet daté de la nuit,
   d'une taille proche de celle de la veille.
3. Le ping : healthchecks.io, contrôle de la sauvegarde — état « up », dernier ping de la nuit.

**Au premier déploiement qui porte `backup`** (#25) — ce qu'aucun test ne peut voir, coché le
2026-11-02 :
- [x] **Le rôle** : `bootstrap.sh` l'a créé si `docker compose ps backup` le dit `healthy` — sa
  sonde ouvre une session sous ce rôle.
- [x] **Le jeton écrit, liste et supprime dans le vrai bucket** : trois sauvegardes à la main, le
  même jour. Les trois réussissent (écrire, lister), et la deuxième disparaît du bucket à la
  troisième (supprimer) : la règle quotidienne garde la plus récente du jour, la plus ancienne
  reste tant que le bucket est jeune. Une sauvegarde de la nuit déjà là, c'est elle la plus
  ancienne : la première manuelle disparaît dès la deuxième.
- [x] **Le ping arrive, et l'alerte part quand il manque** : après une sauvegarde à la main, le
  contrôle est « up ». Réduis sa période et son délai de grâce à 1 minute, envoie un ping (« Ping
  Now »), et attends sans rien toucher : l'alerte arrive. Réduire après le dernier ping ne teste
  rien : le passage à « down » qu'un réglage provoque ne notifie pas (constaté). Remets ensuite la
  période d'un jour et son délai de grâce, puis un ping.
- [x] **La clé privée déchiffre une sauvegarde, sur le poste** : l'objet téléchargé du tableau de
  bord R2, le fichier `age.key` tiré du gestionnaire de mots de passe, puis, dans Git Bash
  (« Amorcer un VPS neuf »)
  ```
  age --decrypt --identity age.key <objet> | docker run --rm -i <image de postgres dans infra/compose.yml> pg_restore --list
  rm age.key <objet>
  ```
  La table des matières liste les tables de l'application ; le dump en clair ne touche pas le
  disque.

### Restaurer une sauvegarde

Depuis le poste, à la racine d'un clone à jour du dépôt :
[`make restore`](../Makefile) copie [`restore.sh`](restore.sh) sur le VPS et l'y lance, en `root`,
dans `/srv/portfolio`. La base de production est **remplacée** par celle de la sauvegarde, et le
site est indisponible le temps de la restauration — quelques minutes.

1. **La clé privée** : le fichier `age.key` de l'entrée du gestionnaire de mots de passe, déposé à
   la racine du clone (`.gitignore` l'écarte). Une sauvegarde antérieure à une rotation de la paire
   ne s'ouvre qu'avec l'ancienne clé (« Tourner un secret », `BACKUP_AGE_RECIPIENT`).
2. **La sauvegarde** : `derniere`, ou l'horodatage d'un objet du bucket — `20261015T030000Z` pour
   `portfolio-20261015T030000Z.dump.age` (tableau de bord Cloudflare, R2, bucket des sauvegardes).
3. **La restauration** :
   ```
   make restore HOST=portfolio BACKUP=derniere
   ```
   `HOST` : l'alias `portfolio` (« Amorcer un VPS neuf », « L'accès `root` ») — `make` y prend
   `root@portfolio`, que l'alias sert avec la bonne clé. Lettres, chiffres, `.` et `-` seulement.
   Elle écrit, dans l'ordre : `== sélection` et `sauvegarde : <objet>` ; `== téléchargement` ;
   `== déchiffrement` ; `== arrêt` et `arrêtés : api worker` ; `== restauration` ; `== migrations`, avec
   chaque migration que Django applique ; `== contrôle` et
   `projets publiés : <N> (attendu ≥ <M>)` ; `== redémarrage` et `redémarrés : api worker` — puis sort en
   0. Le seuil `M` vaut 0, ou `RESTORE_MIN_PROJECTS=<M>` sur la ligne de commande.
4. **La clé effacée** : `rm age.key`.

Un échec écrit `échec à l'étape : <étape>` et sort en erreur. Ce qu'il veut dire, et quoi faire
(commandes en `deploy`, « Commandes sur le VPS ») :

| Étape | La base, `api` et `worker` | Cause probable, et quoi faire |
|---|---|---|
| `préparation`, `sélection` | intactes, `api` et `worker` tournent | `BACKUP` ou le seuil mal formé, aucune clé dans le fichier, ou aucun objet de ce nom : corrige la commande, relance |
| `téléchargement`, `déchiffrement` | intactes, `api` et `worker` tournent | jeton du bucket refusé (`bootstrap.sh BACKUP_R2_ACCESS_KEY_ID BACKUP_R2_SECRET_ACCESS_KEY`) ; clé d'une autre paire ; archive illisible : relance avec une sauvegarde plus ancienne |
| `arrêt` | intacte, `api` ou `worker` peut-être arrêté | `docker compose ps` ; `docker compose start api worker` |
| `restauration` | intacte — la restauration se fait en une transaction —, `api` et `worker` arrêtés | la sortie de `pg_restore` ou de `psql` le dit ; relance, ou `docker compose start api worker` pour revenir à la base d'avant |
| `migrations` | restaurée, `api` et `worker` arrêtés | une migration a échoué, ou `migrate --check` en voit une non appliquée : la sortie de Django la nomme ; une fois réglé, `docker compose up -d --wait api worker` — `api` migre à son démarrage |
| `contrôle` | restaurée et migrée, `api` et `worker` arrêtés | moins de projets publiés que le seuil : une sauvegarde trop ancienne, ou le mauvais seuil — relance avec une autre sauvegarde, ou `docker compose start api worker` si la base est la bonne |
| `redémarrage` | restaurée, `api` ou `worker` ne devient pas sain | `docker compose logs api worker` — un compte d'admin d'un autre nom que `ADMIN_USERNAME` : « Admin » |

Une sauvegarde **plus récente** que le code — des migrations appliquées que le code ne connaît pas —
ne se détecte pas : Django ne les voit pas. Le commit déployé doit être au moins aussi récent que la
sauvegarde (« Déployer à la main » porte le même avertissement).

### Le VPS a disparu

Reconstruire la production sur une machine neuve, en une heure au plus (cadrage §6.7, RTO 1 h) —
temps visé par étape. Les noms d'hôte ne changent pas : le Tunnel suit son jeton (D58), aucun geste
DNS.

1. **Suspendre le déploiement continu** (1 min) — sinon chaque push vise l'ancien hôte :
   `gh variable set DEPLOY_ENABLED --body false`.
2. **Louer un VPS** x86 sous Ubuntu LTS en UE (ADR 0002, 0023), joignable en `root` par la clé
   `portfolio_admin`, puis remettre le `HostName` de l'alias `portfolio` à sa nouvelle adresse
   (« Amorcer un VPS neuf », « L'accès `root` ») (10 min).
3. **L'amorcer** : « Amorcer un VPS neuf », étapes 1 à 5 (25 min) — une clé de déploiement neuve,
   le jeton GHCR, `bootstrap.sh` —, puis, de son étape 6, les trois secrets que la machine change
   seulement, l'environnement `production` et sa règle de branche existant déjà :
   `gh secret set DEPLOY_SSH_KEY …`, `DEPLOY_KNOWN_HOSTS …` et `DEPLOY_HOST …`, suivis de
   `rm deploy_key deploy_key.pub`. `docker compose ps` dit `cloudflared` `healthy` : le Tunnel a
   repris les noms d'hôte. La base est vide, migrée par `api`.
4. **Restaurer** : « Restaurer une sauvegarde » ci-dessus, `BACKUP=derniere` (10 min).
5. **Vérifier** (10 min) — oui / non : le site répond et affiche ses projets ; l'admin s'ouvre
   (Access, puis la page de connexion) ; la restauration a écrit `projets publiés` et `migrate
   --check` vert. Le lendemain : la sauvegarde de la nuit est arrivée (« Vérifier qu'une
   sauvegarde est arrivée »).
6. **Reprendre le déploiement continu** (1 min) : `gh variable set DEPLOY_ENABLED --body true`.

Les médias : sur R2, rien à restaurer — un VPS reconstruit les retrouve dans leur bucket, par les
variables `MEDIA_R2_*` que `bootstrap.sh` redemande.

### Le test mensuel

Le 1ᵉʳ de chaque mois à 04:00 UTC, le workflow « Test de restauration »
([`restore.yml`](../.github/workflows/restore.yml)) rejoue la chaîne de « Restaurer une
sauvegarde » — `restore.sh derniere` — dans une pile jetable du runner : la dernière sauvegarde du
bucket, dans un Postgres vide, migrée par les images publiées sous `latest`. Il écrit les mêmes
étapes, `arrêtés : aucun` et `redémarrés : aucun` compris. Il est sauté tant que `DEPLOY_ENABLED`
ne vaut pas `true`.

Ce qu'il lit, dans l'environnement `production` : les secrets `BACKUP_AGE_IDENTITY` (le fichier
`age.key`), `RESTORE_R2_ACCESS_KEY_ID` et `RESTORE_R2_SECRET_ACCESS_KEY` — un second jeton R2,
« Object Read only », borné au seul bucket des sauvegardes, distinct de celui du VPS ; les
variables `BACKUP_R2_ENDPOINT` et `BACKUP_R2_BUCKET`. Et la variable de dépôt
`RESTORE_MIN_PROJECTS`, le seuil de projets publiés : absente ou vide, 0 ; #27 la passe à 1.

**L'alerte est un run rouge.** GitHub notifie qui a créé le workflow, ou changé sa ligne `cron` en
dernier (doc GitHub « Notifications for workflow runs ») : ce compte garde les notifications
d'Actions activées (GitHub, Settings, Notifications, « Actions »). Le journal du run nomme l'étape
— `échec à l'étape : <étape>` — et la table de « Restaurer une sauvegarde » en donne la cause ; la
pile est jetable, il n'y a rien à remettre en place. `sélection` ou `téléchargement` : bucket vide,
ou jeton en lecture seule refusé ; `déchiffrement` : `BACKUP_AGE_IDENTITY` d'une autre paire
(« Tourner un secret », `BACKUP_AGE_RECIPIENT`) ; `contrôle` : moins de projets publiés que le
seuil.

**Le lancer à la main** — après une rotation, ou pour vérifier une correction ; sur `main`, la
branche par défaut de `gh workflow run` : l'environnement `production` refuse toute autre branche,
et le run y est rouge sans avoir rien restauré.
```
gh workflow run restore.yml
gh run watch
```

**Au premier déploiement** (#25) — ce qu'aucun test ne peut voir :
- [x] **Les secrets et variables** dans l'environnement `production`, le fichier `age.key` tiré du
  gestionnaire ; les deux `RESTORE_R2_*` saisis au clavier, jamais en argument :
  ```
  gh secret set BACKUP_AGE_IDENTITY --env production < age.key
  gh secret set RESTORE_R2_ACCESS_KEY_ID --env production
  gh secret set RESTORE_R2_SECRET_ACCESS_KEY --env production
  gh variable set BACKUP_R2_ENDPOINT --env production --body <adresse S3 du compte>
  gh variable set BACKUP_R2_BUCKET --env production --body <nom du bucket>
  rm age.key
  ```
  Si l'environnement n'est pas disponible sur le plan du compte, mêmes noms en secrets et
  variables de dépôt (#25).
- [x] **Le workflow, lancé à la main, est vert** — `DEPLOY_ENABLED` à `true` et une sauvegarde dans
  le bucket : le tirage des images par le jeton du workflow, le vrai jeton en lecture seule, la
  vraie clé. Vert le 2026-11-02, sur `54fd6dd`.
- [x] **Une restauration réelle, chronométrée** : `make restore HOST=<ip> BACKUP=derniere`
  (« Restaurer une sauvegarde »), de la commande au site vérifié — la mesure du RTO (1 h), notée
  ici. Mesuré le 2026-11-02, sur une base presque vide : 47 s pour la commande, phrases de passe
  comprises ; moins de 7 min jusqu'à l'admin rouvert, second facteur compris. Une base pleine prendra
  plus longtemps.

## Premier déploiement — la liste

Ce qu'aucun test ne voit, sur la vraie pile. Coché le 2026-11-02 sur `66bd224` (#25), où vivent les
mesures brutes ; à rejouer sur un hôte ou un Tunnel neuf. Les listes de « Sauvegarde et
restauration » la complètent.

- [x] `https://pacome.dev/` répond par Cloudflare, `www` redirige vers l'apex en 301, le Tunnel
  `portfolio` est Healthy, chaque service `healthy`, y compris après un `reboot`.
- [x] **Aucun port web ouvert** : scan TCP IPv4 des 65 535 ports depuis l'extérieur de la pile,
  22 seul ouvert. UDP et IPv6 non scannés de l'extérieur ; `ufw` n'y ouvre que 22.
- [x] **Access couvre l'admin** : `curl -I --path-as-is` rend un 302 vers
  `pacome.cloudflareaccess.com` pour `/admin`, `/admin/`, `/admin/login/`, `/admin/auth/user/`,
  `/admin/?x=1`, `/ADMIN/`, `/Admin/`, `/%61dmin/`, `//admin/`, `/./admin/`, `/x/../admin/`,
  `/%2e/admin/` ; un 404 de l'API, sans Access, pour `/`, `/adminx`, `/administration/`, `/api/`,
  `/health/` et `/admin;x/`, sans formulaire. Une autre identité GitHub n'est pas éprouvée, faute de
  second compte.
- [x] **Barre oblique encodée refusée**, sur `54fd6dd` : `/admin%2Flogin/` et `/admin%2f` rendent
  400. Sur `66bd224`, avant la garde de Caddy, le premier servait le formulaire sans Access, et le
  second redirigeait sans Access.
- [x] **Second facteur** : Access, mot de passe, code ; graine et codes rangés, copie du gestionnaire
  refaite hors du poste.
- [x] **CSRF** : un envoi multipart de l'admin passe, schéma `https` compris.
- [x] **Session Access expirée** : la limite de `form-action 'self'` est écrite (« Admin »).
- [x] **Médias** : un téléversement réel depuis l'admin rend cinq variantes `image/webp` sur
  `media.pacome.dev` ; la suppression vide le dossier de l'image.
- [x] **Jetons R2** : les deux `-rw` écrivent et suppriment ; celui des sauvegardes liste, celui des
  médias aussi, par déduction de `delete_folder` ; `-ro` liste et refuse l'écriture en 403.
- [x] **Limitation de débit** : 150 requêtes en 4 s, 43 refusées en 429, retour à 200 après 10 s.
- [x] **Mémoire sur le CPX12**, 19 h après le démarrage, sans trafic : 841 Mo utilisés sur 1 909,
  1 068 Mo disponibles, disque à 12 % ; `docker stats` : `worker` 338 Mio, `api` 207 Mio.
