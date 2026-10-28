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
| Clé privée `age` des sauvegardes | gestionnaire ; secret `BACKUP_AGE_IDENTITY` de `production`, pour le test mensuel — ni le dépôt, ni une image (ADR 0007, point 2) ; jamais stockée sur le VPS : elle transite par `ssh` vers la mémoire d'un conteneur jetable, le temps d'une restauration | le mainteneur, sur le poste | une nouvelle paire, sa clé publique à `bootstrap.sh BACKUP_AGE_RECIPIENT`, sa clé privée à `BACKUP_AGE_IDENTITY` ; l'ancienne gardée |
| Jeton du bucket en lecture seule (`RESTORE_R2_ACCESS_KEY_ID`, `RESTORE_R2_SECRET_ACCESS_KEY`) | gestionnaire ; secrets de `production` — le test mensuel seul s'en sert, jamais le VPS | le mainteneur | un nouveau jeton R2, les deux secrets remplacés, puis l'ancien révoqué |

L'environnement GitHub `production` n'admet que `main` : un workflow lancé depuis une autre branche
ne lit pas ses secrets, même modifié.

`SECRET_KEY`, `POSTGRES_PASSWORD` et `BACKUP_POSTGRES_PASSWORD` ne vivent que sur le VPS : rien hors
de la pile ne s'en sert, et un VPS reconstruit en reçoit de neufs — la base restaurée garde ses
données, pas ses rôles, que `bootstrap.sh` recrée. La clé privée `age`, elle, n'est jamais stockée
sur le VPS — elle n'y passe que le temps d'une restauration, dans le `tmpfs` d'un conteneur
jetable : une sauvegarde volée avec lui reste illisible. La clé publique (`BACKUP_AGE_RECIPIENT`)
n'est pas un secret.

## Amorcer un VPS neuf

Prérequis : un VPS Ubuntu LTS en UE (ADR 0002), joignable en `root` par ta clé SSH ; dans le
gestionnaire de mots de passe, le jeton du Tunnel, ceux du bucket des médias et du bucket des
sauvegardes, la paire `age` et le compte de l'admin (« Admin ») ; l'adresse de ping du contrôle
healthchecks.io (#25). À la première connexion, `ssh` affiche l'empreinte de l'hôte : compare-la à
celle que la console du fournisseur rend pour `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
— identiques, oui ou non ? Non : n'accepte pas.

1. **La clé de déploiement**, sur le poste, dédiée et sans phrase de passe — la CI ne peut pas en
   saisir une :
   ```
   ssh-keygen -t ed25519 -N "" -C deploy@portfolio -f deploy_key
   ```
2. **Le jeton GHCR** : un jeton *classic*, portée `read:packages` seule — GHCR n'accepte pas les
   jetons à droits fins (doc GitHub « Working with the Container registry ») —, créé sur
   `https://github.com/settings/tokens/new?scopes=read:packages`, rangé dans le gestionnaire.
3. **Le commit à déployer** : la tête de `main`, si son run a publié (`gh run list --branch main
   --limit 1` : `completed success` ?). Son SHA complet : `git fetch origin && git rev-parse
   origin/main`.
4. **Les trois fichiers de ce commit**, tirés sans changer de branche, puis copiés sur le VPS :
   ```
   git show <sha>:infra/bootstrap.sh > bootstrap.sh
   git show <sha>:infra/compose.yml > compose.yml
   git show <sha>:infra/prod.env.example > prod.env.example
   scp bootstrap.sh compose.yml prod.env.example root@<ip>:
   rm bootstrap.sh compose.yml prod.env.example
   ```
   (Un `compose.yml` laissé à la racine du dépôt serait pris par tout `docker compose` lancé là.)
5. **L'amorçage**, en `root` sur le VPS — `-t` pour les saisies sans écho :
   ```
   ssh -t root@<ip> bash bootstrap.sh
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
   s'arrête sur « cloudflared is unhealthy ».
6. **L'environnement `production` et ses secrets**, depuis le poste, dans le dépôt — d'abord
   l'environnement restreint à `main` (doc GitHub « Deployments and environments »), puis les
   quatre secrets :
   ```
   echo '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' | gh api -X PUT repos/plecart/portfolio/environments/production --input -
   gh api -X POST repos/plecart/portfolio/environments/production/deployment-branch-policies -f name=main -f type=branch
   gh secret set DEPLOY_SSH_KEY --env production < deploy_key
   printf '%s %s\n' <ip> "<ligne de la clé de l'hôte affichée par bootstrap.sh>" | gh secret set DEPLOY_KNOWN_HOSTS --env production
   gh secret set DEPLOY_HOST --env production --body <ip>
   gh secret set DEPLOY_USER --env production --body deploy
   rm deploy_key deploy_key.pub
   ```
   `gh secret list --env production` liste-t-il les quatre noms ? (Il n'affiche jamais les
   valeurs.)
7. **Le déploiement continu** : `gh variable set DEPLOY_ENABLED --body true`. Le prochain push sur
   `main` déploie ; tant que la variable ne vaut pas `true`, le job `deploy` est sauté.

## Commandes sur le VPS

En `deploy`, dans le dossier de la pile — `root` lit l'état aussi, mais n'a pas d'accès à GHCR :
```
ssh root@<ip>
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
   scp compose.yml root@<ip>:/tmp/compose.yml
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
deux envois : nom, mot de passe et jeton, puis l'appareil — l'application ou un code de secours —
et son jeton.

**Application perdue** : un code de secours ouvre l'admin, une seule fois. Relance ensuite la
commande, qui ré-enrôle : l'ancienne application et les anciens codes ne valent plus. Elle ne
demande aucune connexion à l'admin — sans code restant, la relancer sur le VPS suffit.

## Cloudflare — l'état attendu

Un état documenté (cadrage §6.7, point 7 ; ADR 0003) ; #25 le complète au premier déploiement,
règle par règle.

- **Tunnel** — géré depuis Cloudflare ; son jeton est `TUNNEL_TOKEN`. Les noms d'hôte publics du
  site (apex) et de l'API (`api.`) mènent à `http://caddy:80`, qui route par nom d'hôte
  (`infra/caddy/Caddyfile`).
- **DNS** — `www` redirige vers l'apex ; `media.` sert R2 (#13).
- **Access** — devant l'admin, `/admin/` sur l'hôte de l'API (#6, #25).
- **WAF et protection DDoS** — ceux de l'offre gratuite, sans réglage. Turnstile : absent (D41).

## Sauvegarde et restauration

Chaque nuit à 03:00 UTC, `backup` enchaîne dump, chiffrement, envoi, purge et ping
([`backup/backup.sh`](backup/backup.sh)) : l'objet `<base>-<AAAAMMJJ>T<HHMMSS>Z.dump.age` arrive
dans le bucket des sauvegardes, la purge n'y garde que 7 quotidiennes et 4 hebdomadaires de plus
(la règle de `borg prune --keep-daily 7 --keep-weekly 4`, [`backup/retention.sh`](backup/retention.sh)),
puis healthchecks.io reçoit le ping. La première étape qui échoue arrête tout, sans ping :
healthchecks.io alerte de son absence. Pour revenir à une sauvegarde : « Restaurer une sauvegarde »,
et, si la machine elle-même est perdue, « Le VPS a disparu », plus bas. Que la dernière se restaure,
un workflow le prouve chaque mois : « Le test mensuel ».

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

**Au premier déploiement qui porte `backup`** (#25) — ce qu'aucun test ne peut voir :
- [ ] **Le rôle** : `bootstrap.sh` l'a créé si `docker compose ps backup` le dit `healthy` — sa
  sonde ouvre une session sous ce rôle.
- [ ] **Le jeton écrit, liste et supprime dans le vrai bucket** : trois sauvegardes à la main, le
  même jour. Les trois réussissent (écrire, lister), et la deuxième disparaît du bucket à la
  troisième (supprimer) : la règle quotidienne garde la plus récente du jour, la plus ancienne
  reste tant que le bucket est jeune.
- [ ] **Le ping arrive, et l'alerte part quand il manque** : après une sauvegarde à la main, le
  contrôle est « up » ; puis, sa période et son délai de grâce réduits au plus court dans
  healthchecks.io, l'alerte arrive une fois les deux écoulés sans ping — remets ensuite la période
  d'un jour et son délai de grâce.
- [ ] **La clé privée déchiffre une sauvegarde, sur le poste** : l'objet téléchargé du tableau de
  bord R2, le fichier `age.key` tiré du gestionnaire de mots de passe, puis
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
   make restore HOST=<ip> BACKUP=derniere
   ```
   `HOST` : une adresse IPv4 ou un nom d'hôte — lettres, chiffres, `.` et `-` ; pour un VPS en
   IPv6 seul, un alias de `~/.ssh/config`.
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
2. **Louer un VPS** Ubuntu LTS en UE (ADR 0002), joignable en `root` par ta clé SSH (10 min).
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
- [ ] **Les secrets et variables** dans l'environnement `production`, le fichier `age.key` tiré du
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
- [ ] **Le workflow, lancé à la main, est vert** — `DEPLOY_ENABLED` à `true` et une sauvegarde dans
  le bucket : le tirage des images par le jeton du workflow, le vrai jeton en lecture seule, la
  vraie clé.
- [ ] **Une restauration réelle, chronométrée** : `make restore HOST=<ip> BACKUP=derniere`
  (« Restaurer une sauvegarde »), de la commande au site vérifié — la mesure du RTO (1 h), notée
  ici.
