# 0018 — Binaires Go compilés par le projet

- **Statut** : accepté
- **Date** : 2026-10-21
- **Décisions du cadrage** : D62 (`docs/cadrage-technique.md` §7) ; complète l'ADR 0014, dont il
  exerce une condition de réexamen (§ Conditions de réexamen, « `caddy` publie durablement avec une
  bibliothèque Go en retard »), sans le remplacer ; décisions de l'interrogatoire de #147
  (2026-10-21)

## Contexte

Les images `backup` et `caddy` embarquent des binaires Go venus de leurs releases amont : `age` et
`age-keygen` (fichiers de la release 1.3.2, compilés avec Go 1.27.0), `supercronic` (fichier de la
release 0.2.49, Go 1.26.6), `rclone` (image officielle 1.75.2, Go 1.27.2) et `caddy` (image
officielle 2.11.7, Go 1.26.8). Trivy lit la bibliothèque standard Go de chaque binaire, et le scan
bloque toute vulnérabilité HIGH ou CRITICAL, corrigeable ou non (ADR 0014).

Le 2026-10-20, Go 1.26.10 et 1.27.3 corrigent CVE-2026-111943 (HIGH). Le scan du 2026-10-21 la
trouve dans les cinq binaires. `age`, `rclone` et Caddy sont à leur dernière version publiée : le
correctif n'atteindrait leurs images qu'à la release amont suivante, sans date. `supercronic`, lui,
publie le 2026-10-21 une 0.2.51 compilée avec Go 1.27.3. Ce n'est pas la première fois : #125 a
monté Caddy de 2.11.4 à 2.11.7, ce qui a retiré 16 de ses 19 exceptions, et la 2.11.7, sortie le
2026-10-03 avec Go 1.26.8, était déjà en retard sur Go 1.26.9. Trois exceptions sur `age`,
`age-keygen` et `supercronic` attendaient déjà, à 30 jours, une release amont.

La politique de `.trivyignore.yaml` ne laisse passer qu'un code non atteint : « si l'évaluation
conclut que le code est atteint, on corrige l'image ». `rclone` envoie le dump à R2 en HTTPS, donc
vérifie un certificat, et c'est cet appel que l'avis durcit : le code est atteint. `age` ne vérifie
aucun certificat, et Caddy ne termine aucun TLS (D45).

## Facteurs de décision

- Le scan bloque HIGH et CRITICAL ; une exception ne couvre qu'un code non atteint (ADR 0014).
- La bibliothèque standard d'un binaire Go est celle du compilateur de sa release : l'amont fixe le
  rythme des correctifs de Go, pas le projet.
- Chaîne d'approvisionnement (cadrage §6.6, #5) : ce qui entre dans une image est épinglé et
  vérifié, et Dependabot porte les mises à jour qu'il sait lire.
- Chaque binaire reste celui que l'amont publie — mêmes modules, mêmes drapeaux, même version
  annoncée — pour que ce qui a été éprouvé en amont le reste.
- Le cache de couches de la CI est en `mode=max` (`ci.yml`, étape « Images ») : tout ce qu'un layer
  garde, il le garde aussi.

## Options considérées

- **Exceptions datées** : une exception de 30 jours par avis et par binaire, renouvelée jusqu'à la
  release amont.
- **Attendre l'amont** : le scan reste rouge jusqu'aux releases de `age`, `rclone` et Caddy.
- **Compiler dans un étage du projet** : un étage `golang:<x.y.z>-alpine` par Dockerfile, qui
  compile chaque binaire à la version de sa release, avec le Go épinglé.

## Décision

**`age`, `age-keygen`, `rclone` et `caddy` sont compilés par le projet, avec le Go de l'image
`golang` épinglée ; `supercronic` reste le fichier de sa release.**

- **Un étage `golang:<x.y.z>-alpine`**, épinglé étiquette et empreinte, `FROM` en colonne 0, dans
  chaque Dockerfile qui compile : Dependabot le lit comme toute image de base, et une montée de Go
  arrive en une PR par Dockerfile — Dependabot a une entrée par dossier (ADR 0014,
  `.github/dependabot.yml`) —, qui recompile ses binaires. `GOTOOLCHAIN=local`, défaut de l'image :
  un module qui exigerait un Go plus récent fait échouer le build au lieu d'en télécharger un
  autre, et le Go de l'image est celui de chaque binaire. Sans cgo, comme les releases.
- **On change le compilateur, jamais le graphe de dépendances.** Chaque binaire se compile avec les
  versions de modules que fixe sa release : aucun module n'est monté, même corrigé. Une
  vulnérabilité d'un module — `golang.org/x/net` dans Caddy — reste une exception évaluée en trois
  points.
- **Chaque binaire est compilé sous la forme de sa release officielle et annonce sa version**, lues
  à la source le 2026-10-21 :
  - `age` (`.github/workflows/build.yml`) : `-trimpath`, sans `-ldflags`. Seules les commandes
    `age` et `age-keygen` s'installent : `cmd/...` installerait aussi `age-inspect` et
    `age-plugin-batchpass`, que l'image ne demande pas.
  - `rclone` : son image officielle lance la cible par défaut de son `Makefile`, `-ldflags "-s -X
    github.com/rclone/rclone/fs.Version=<tag>"`, sans étiquette ; ses archives de release y
    ajoutent `-trimpath`, repris ici, et l'étiquette `cmount` de `rclone mount`, que l'image
    n'emploie pas (`bin/cross-compile.go`, job `linux` de son workflow). Le projet vide plutôt le
    suffixe, `-X github.com/rclone/rclone/fs.VersionSuffix=` : `fs.Version` vaut alors
    `fs.VersionTag`, que la source porte à la release (`fs/versiontag.go`), et la version ne
    s'épingle qu'une fois. Sans ce drapeau, `rclone version` répond `v1.75.2-DEV` (mesuré).
  - `caddy` (`.goreleaser.yml`) : compilé comme **dépendance** d'un module principal, avec le
    `main.go` de `cmd/caddy`, `go mod edit -require=github.com/caddyserver/caddy/v2@<tag>` puis
    `go mod tidy` ; `-trimpath -mod=readonly`, `-ldflags "-s -w"`, étiquettes
    `nobadger nomysql nopgx`. Compilé en module principal par `go install`, il répond `unknown` à
    `caddy version` (mesuré). Le projet télécharge ce module (`go mod download`) et en copie le
    `main.go` de `cmd/caddy` depuis le cache de modules, là où la release le prend dans son dépôt :
    la version ne s'écrit qu'une fois. Mesuré le 2026-10-21 : même `go.mod`, même `go.sum`, binaire
    identique octet pour octet à la forme `go get`, et les 147 dépendances de `go version -m` aux
    versions du binaire officiel.

  Un test d'image exige de chacun qu'il annonce la version épinglée.
- **L'image `caddy` reste construite sur `caddy:<x.y.z>-alpine`**, dont seul le binaire est
  remplacé : configuration, chemins, variables et utilisateur sont ceux de l'image officielle, et
  Dependabot continue de proposer chaque version de Caddy. La version compilée et l'étiquette de
  l'image de base sont deux épingles d'une même version : un test exige leur égalité. Le binaire
  officiel porte `cap_net_bind_service=ep`, que la copie perd ; l'image tourne en root, et le test
  de fumée l'exerce.
- **`supercronic` reste le fichier de sa release**, à la somme SHA-256 épinglée (`ADD --checksum`,
  que BuildKit vérifie) : sa 0.2.51 a suivi Go 1.27.3 en un jour, et le compiler n'apporterait
  rien.
- **Les modules sont téléchargés sous la base de sommes de Go**, `sum.golang.org`, active par
  défaut dans l'image `golang` : ni `GOSUMDB`, ni `GONOSUMDB`, ni `GOPRIVATE` ; `GOINSECURE` ne la
  coupe pas (`go help environment`). Chaque module est désigné par une version exacte `vX.Y.Z`,
  jamais une requête, une branche ou une pseudo-version. La garde des téléchargements de
  `apps/api/tests/test_supply_chain.py` tient les deux conditions, à côté de `ADD --checksum`.
- **Le layer de compilation garde les binaires sans les caches de Go** : modules
  (`/go/pkg/mod`) et objets de compilation (`/root/.cache/go-build`) sont des montages
  `type=cache`, hors du layer et donc hors du cache exporté par la CI. Mesuré le 2026-10-21 sur
  l'étage de `backup` : 95 Mo de layers avec les montages, 2,9 Go sans — 1,7 Go de modules et
  0,9 Go d'objets.

## Conséquences

**Positives**

- Une montée de Go est une PR Dependabot de l'image `golang` par Dockerfile, qui recompile ses
  binaires : leur bibliothèque standard suit le Go épinglé, sans attendre l'amont.
- Les exceptions sur la bibliothèque standard Go se retirent ; ne restent que celles des modules,
  évaluées comme toute autre — à l'essai du 2026-10-21, sans exception, CVE-2026-78669 sur
  `golang.org/x/net` 0.59.0 dans Caddy, et rien dans `age`, `age-keygen` ni `rclone`.
- Chaque binaire reste celui de l'amont : mêmes modules, mêmes drapeaux, même version annoncée.

**Négatives, assumées**

- Chaque changement d'un étage de compilation se paie en build : à l'essai, 150 s sur le poste
  (`age` 10 s, `rclone` 73 s, `caddy` 45 s). Tant que l'étage ne change pas, le cache de couches
  de la CI le sert sans recompiler.
- Les versions de `age` et `rclone` se montent à la main (`CONTRIBUTING.md`), en relisant la forme
  de leur release. Celle de Caddy suit l'étiquette de son image de base : la PR Dependabot qui la
  monte rougit sur le test d'égalité tant que la version compilée ne l'a pas suivie, et se complète
  à la main.
- Dependabot ne voit plus les releases de `rclone`, dont l'image officielle n'est plus un `FROM`.
- L'image `caddy` garde, masqué dans la couche de son image de base, le binaire officiel qu'elle
  remplace : environ 51 Mo de plus (mesuré le 2026-10-21) ; Trivy ne lit que le système de
  fichiers final, une seule cible `gobinary`.

## Comparaison des options

| | Exceptions datées | Attendre l'amont | Compiler dans un étage |
|---|---|---|---|
| Scan du trunk | vert si le code n'est pas atteint | rouge jusqu'aux releases, sans date | vert |
| Code atteint (`rclone`) | exception refusée par la politique | rouge | corrigé |
| Travail récurrent | une évaluation par avis et par binaire, tous les 30 jours | aucun, trunk bloqué | une PR Dependabot par image et par version de Go |
| Binaire livré | celui de l'amont | celui de l'amont | les modules et les drapeaux de l'amont, le Go du projet |
| Suivi par Dependabot | — | — | Go oui ; versions de `age` et `rclone` non |
| Coût de build | nul | nul | une compilation à chaque changement de l'étage |

## Conditions de réexamen

- L'amont publie de nouveau, durablement, avec un Go à jour : revenir aux binaires de ses releases.
- Dependabot sait suivre un module installé par `go install` : lui confier les versions des
  binaires.
